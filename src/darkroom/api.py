from __future__ import annotations

import threading
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from darkroom.login import login_in_browser
from darkroom.scan import (
    ListKind,
    Report,
    ScanStatus,
    ScanSummary,
    UserPage,
    latest_report,
    list_scans,
    list_users,
    store as scan_store,
)
from darkroom.session import session_path, validate_session

LoginState = Literal["idle", "waiting", "done", "error"]

UI_DIST = Path(__file__).resolve().parent.parent.parent / "ui" / "dist"


class LoginStatus(BaseModel):
    state: LoginState
    error: str | None = None


class AppStatus(BaseModel):
    logged_in: bool
    username: str | None
    session_path: str
    login: LoginStatus


class LoginStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.state: LoginState = "idle"
        self.error: str | None = None
        self.logged_in = False
        self.username: str | None = None
        self._validated = False

    def snapshot(self) -> AppStatus:
        self.ensure_validated()
        with self._lock:
            return AppStatus(
                logged_in=self.logged_in,
                username=self.username,
                session_path=str(session_path()),
                login=LoginStatus(state=self.state, error=self.error),
            )

    def ensure_validated(self) -> None:
        with self._lock:
            if self._validated:
                return
            logged_in, username = validate_session()
            self.logged_in = logged_in
            self.username = username
            self._validated = True

    def start(self) -> None:
        with self._lock:
            if self.state == "waiting":
                raise HTTPException(status_code=409, detail="Login already in progress")
            self.state = "waiting"
            self.error = None
        thread = threading.Thread(target=self._run, name="darkroom-login", daemon=True)
        thread.start()

    def _run(self) -> None:
        try:
            username = login_in_browser()
        except Exception as exc:
            with self._lock:
                self.state = "error"
                self.error = str(exc)
            return
        with self._lock:
            self.state = "done"
            self.error = None
            self.logged_in = True
            self.username = username
            self._validated = True


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


@app.get("/api/scan", response_model=ScanStatus)
def api_scan_status() -> ScanStatus:
    return scan_store.snapshot()


@app.post("/api/scan", response_model=ScanStatus)
def api_scan_start() -> ScanStatus:
    if not store.snapshot().logged_in:
        raise HTTPException(status_code=401, detail="Not logged in")
    return scan_store.start()


@app.post("/api/scan/stop", response_model=ScanStatus)
def api_scan_stop() -> ScanStatus:
    return scan_store.stop()


@app.get("/api/report", response_model=Report)
def api_report() -> Report:
    return latest_report()


@app.get("/api/scans", response_model=list[ScanSummary])
def api_scans() -> list[ScanSummary]:
    return list_scans()


@app.get("/api/report/users", response_model=UserPage)
def api_report_users(
    kind: ListKind = "unfollowers",
    offset: int = 0,
    limit: int = 100,
) -> UserPage:
    return list_users(kind, offset=offset, limit=limit)


def mount_ui() -> None:
    if not UI_DIST.is_dir():
        return
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
