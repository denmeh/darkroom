from __future__ import annotations

import re
import threading
import webbrowser
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.requests import Request

from darkroom.avatars import avatar_file, fetch_avatar, has_avatar
from darkroom.paths import ui_dist
from darkroom.db import get_db, utcnow
from darkroom.errors import (
    DarkroomError,
    InstagramUnreachable,
    InvalidAccount,
    LoginInProgress,
    SessionExpired,
    SessionNotFound,
)
from darkroom.login import login_in_browser
from darkroom.scan import (
    ListKind,
    Report,
    ScanStatus,
    ScanSummary,
    UserPage,
    get_report,
    list_scans,
    list_users,
    store as scan_store,
)
from darkroom.session import (
    current_pk,
    deactivate,
    delete_session,
    list_session_pks,
    load_session_profile,
    session_file,
    session_path,
    sessions_dir,
    set_current,
)

IG_USERNAME = re.compile(r"^[A-Za-z0-9._]{1,30}$")

LoginState = Literal["idle", "waiting", "done", "error"]

UI_DIST = ui_dist()


class LoginStatus(BaseModel):
    state: LoginState
    error: str | None = None


class OpenProfile(BaseModel):
    username: str


class Me(BaseModel):
    pk: str
    username: str | None = None
    full_name: str | None = None
    biography: str | None = None
    follower_count: int | None = None
    following_count: int | None = None
    media_count: int | None = None
    is_private: bool | None = None
    is_verified: bool | None = None
    avatar_url: str | None = None


class SavedSession(BaseModel):
    pk: str
    username: str | None = None
    full_name: str | None = None
    avatar_url: str | None = None


class AppStatus(BaseModel):
    logged_in: bool
    username: str | None
    session_path: str
    login: LoginStatus
    me: Me | None = None
    sessions: list[SavedSession] = []


def _me_from(profile: dict) -> Me:
    pk = profile["pk"]
    get_db().upsert_account(
        {
            "pk": pk,
            "username": profile.get("username"),
            "full_name": profile.get("full_name") or "",
            "is_private": profile.get("is_private"),
            "is_verified": profile.get("is_verified"),
            "profile_pic_url": profile.get("profile_pic_url"),
        },
        utcnow(),
    )
    url = profile.get("profile_pic_url")
    if isinstance(url, str) and url:
        fetch_avatar(pk, url)
    has_pic = has_avatar(pk) or bool(url)
    return Me(
        pk=pk,
        username=profile.get("username"),
        full_name=profile.get("full_name"),
        biography=profile.get("biography"),
        follower_count=profile.get("follower_count"),
        following_count=profile.get("following_count"),
        media_count=profile.get("media_count"),
        is_private=profile.get("is_private"),
        is_verified=profile.get("is_verified"),
        avatar_url=f"/api/avatars/{pk}" if has_pic else None,
    )


def _me_from_db(pk: str) -> Me:
    row = get_db().query_one(
        """
        SELECT username, full_name, is_private, is_verified, profile_pic_url
        FROM accounts WHERE pk = ?
        """,
        (pk,),
    )
    if row is None:
        return Me(
            pk=pk,
            avatar_url=f"/api/avatars/{pk}" if has_avatar(pk) else None,
        )
    has_pic = has_avatar(pk) or bool(row["profile_pic_url"])
    return Me(
        pk=pk,
        username=row["username"],
        full_name=row["full_name"] or None,
        is_private=bool(row["is_private"]) if row["is_private"] is not None else None,
        is_verified=bool(row["is_verified"]) if row["is_verified"] is not None else None,
        avatar_url=f"/api/avatars/{pk}" if has_pic else None,
    )


def _saved_sessions() -> list[SavedSession]:
    db = get_db()
    out: list[SavedSession] = []
    for pk in list_session_pks():
        row = db.query_one(
            "SELECT username, full_name FROM accounts WHERE pk = ?",
            (pk,),
        )
        username = row["username"] if row else None
        full_name = (row["full_name"] or None) if row else None
        out.append(
            SavedSession(
                pk=pk,
                username=username,
                full_name=full_name,
                avatar_url=f"/api/avatars/{pk}" if has_avatar(pk) else None,
            )
        )
    return out


class LoginStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.state: LoginState = "idle"
        self.error: str | None = None
        self.username: str | None = None
        self.me: Me | None = None
        self._validated = False

    def snapshot(self) -> AppStatus:
        self.ensure_validated()
        sessions = _saved_sessions()
        logged_in = current_pk() is not None
        with self._lock:
            path = session_path() if logged_in else sessions_dir()
            return AppStatus(
                logged_in=logged_in,
                username=self.username if logged_in else None,
                session_path=str(path),
                login=LoginStatus(state=self.state, error=self.error),
                me=self.me if logged_in else None,
                sessions=sessions,
            )

    def ensure_validated(self) -> None:
        with self._lock:
            if self._validated:
                return
        pk = current_pk()
        if not pk:
            with self._lock:
                if self._validated:
                    return
                self.username = None
                self.me = None
                self._validated = True
            scan_store.bind(None)
            return

        profile = None
        expired = False
        try:
            profile = load_session_profile(pk)
        except SessionExpired:
            expired = True
        except FileNotFoundError:
            expired = True
        except Exception:
            profile = None

        if expired:
            me = None
            owner = None
        elif profile:
            me = _me_from(profile)
            owner = str(profile["pk"])
        else:
            me = _me_from_db(pk)
            owner = pk

        with self._lock:
            if self._validated:
                return
            self.username = me.username if me else None
            self.me = me
            self._validated = True
        scan_store.bind(owner)

    def start(self) -> None:
        with self._lock:
            if self.state == "waiting":
                raise LoginInProgress()
            self.state = "waiting"
            self.error = None
        thread = threading.Thread(target=self._run, name="darkroom-login", daemon=True)
        thread.start()

    def _run(self) -> None:
        try:
            username, pk = login_in_browser()
        except Exception as exc:
            with self._lock:
                self.state = "error"
                self.error = str(exc)
            return
        try:
            profile = load_session_profile(pk)
        except SessionExpired as exc:
            with self._lock:
                self.state = "error"
                self.error = str(exc)
            return
        except FileNotFoundError:
            with self._lock:
                self.state = "error"
                self.error = "Saved session not found"
            return
        except Exception:
            profile = None
        me = Me(pk=pk, username=username)
        if profile:
            try:
                me = _me_from(profile)
            except Exception:
                me = Me(
                    pk=profile["pk"],
                    username=profile.get("username") or username,
                    full_name=profile.get("full_name"),
                )
        with self._lock:
            self.state = "done"
            self.error = None
            self.username = me.username or username
            self.me = me
            self._validated = True
        scan_store.bind(pk)

    def switch_to(self, pk: str) -> AppStatus:
        if not pk.isdigit():
            raise InvalidAccount()
        if not session_file(pk).is_file():
            raise SessionNotFound()
        with self._lock:
            if self.state == "waiting":
                raise LoginInProgress()
        try:
            profile = load_session_profile(pk)
        except FileNotFoundError:
            raise SessionNotFound() from None
        except DarkroomError:
            raise
        except Exception as exc:
            raise InstagramUnreachable(str(exc) or None) from exc
        if not profile:
            raise SessionNotFound()
        set_current(pk)
        me = _me_from(profile)
        with self._lock:
            self.state = "done"
            self.error = None
            self.username = me.username
            self.me = me
            self._validated = True
        scan_store.bind(pk)
        return self.snapshot()

    def forget(self, pk: str) -> AppStatus:
        if not pk.isdigit():
            raise InvalidAccount()
        was_current = current_pk() == pk
        delete_session(pk)
        if was_current:
            scan_store.bind(None)
            with self._lock:
                self.username = None
                self.me = None
                self.state = "idle"
                self.error = None
                self._validated = True
        return self.snapshot()

    def logout(self) -> AppStatus:
        scan_store.bind(None)
        deactivate()
        with self._lock:
            self.username = None
            self.me = None
            self.state = "idle"
            self.error = None
            self._validated = True
        return self.snapshot()


store = LoginStore()
app = FastAPI(title="Darkroom")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(DarkroomError)
def domain_error(_request: Request, exc: DarkroomError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})


@app.get("/api/health")
def api_health() -> dict[str, bool]:
    return {"ok": True}


@app.get("/api/status", response_model=AppStatus)
def api_status() -> AppStatus:
    return store.snapshot()


@app.post("/api/login", response_model=AppStatus)
def api_login() -> AppStatus:
    store.start()
    return store.snapshot()


@app.get("/api/login/status", response_model=AppStatus)
def api_login_status() -> AppStatus:
    return store.snapshot()


@app.post("/api/logout", response_model=AppStatus)
def api_logout() -> AppStatus:
    return store.logout()


@app.post("/api/sessions/{pk}", response_model=AppStatus)
def api_switch_session(pk: str) -> AppStatus:
    return store.switch_to(pk)


@app.delete("/api/sessions/{pk}", response_model=AppStatus)
def api_forget_session(pk: str) -> AppStatus:
    return store.forget(pk)


@app.get("/api/scan", response_model=ScanStatus)
def api_scan_status() -> ScanStatus:
    return scan_store.snapshot()


@app.post("/api/scan", response_model=ScanStatus)
def api_scan_start() -> ScanStatus:
    return scan_store.start()


@app.post("/api/scan/stop", response_model=ScanStatus)
def api_scan_stop() -> ScanStatus:
    return scan_store.stop()


@app.get("/api/report", response_model=Report)
def api_report(scan_id: int | None = None) -> Report:
    return get_report(scan_id)


@app.get("/api/scans", response_model=list[ScanSummary])
def api_scans() -> list[ScanSummary]:
    return list_scans()


@app.get("/api/report/users", response_model=UserPage)
def api_report_users(
    kind: ListKind = "unfollowers",
    offset: int = 0,
    limit: int = 100,
    scan_id: int | None = None,
    q: str | None = None,
) -> UserPage:
    return list_users(kind, offset=offset, limit=limit, scan_id=scan_id, q=q)


@app.post("/api/open-profile")
def api_open_profile(body: OpenProfile) -> dict[str, bool]:
    username = body.username.strip().lstrip("@")
    if not IG_USERNAME.fullmatch(username):
        raise HTTPException(status_code=400, detail="Invalid username")
    webbrowser.open(f"https://www.instagram.com/{username}/")
    return {"ok": True}


@app.get("/api/avatars/{pk}")
def api_avatar(pk: str) -> FileResponse:
    if not pk.isdigit():
        raise HTTPException(status_code=404, detail="Not found")
    headers = {"Cache-Control": "private, max-age=86400"}
    if has_avatar(pk):
        return FileResponse(avatar_file(pk), media_type="image/jpeg", headers=headers)
    row = get_db().query_one("SELECT profile_pic_url FROM accounts WHERE pk = ?", (pk,))
    url = row["profile_pic_url"] if row else None
    if url:
        path = fetch_avatar(pk, url)
        if path is not None:
            return FileResponse(path, media_type="image/jpeg", headers=headers)
    raise HTTPException(status_code=404, detail="Not found")


def mount_ui() -> None:
    if not (UI_DIST / "index.html").is_file():
        raise RuntimeError(f"UI build not found at {UI_DIST}")
    assets = UI_DIST / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(UI_DIST / "index.html")

    @app.get("/{path:path}")
    def spa(path: str) -> FileResponse:
        candidate = UI_DIST / path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(UI_DIST / "index.html")
