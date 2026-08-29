from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from instagrapi import Client
from instagrapi.exceptions import (
    ClientLoginRequired,
    ClientUnauthorizedError,
    LoginRequired,
    ReloginAttemptExceeded,
)

APP_DIR = Path.home() / "darkroom"
SESSIONS_DIR = APP_DIR / "sessions"
CURRENT_FILE = SESSIONS_DIR / "current"
LEGACY_SESSION_FILE = APP_DIR / "session.json"

AUTH_ERRORS = (
    LoginRequired,
    ClientLoginRequired,
    ClientUnauthorizedError,
    ReloginAttemptExceeded,
)

_migrated = False


class SessionExpired(Exception):
    """Instagram rejected this saved session; the file has been deleted."""


def ensure_app_dir() -> Path:
    global _migrated
    APP_DIR.mkdir(parents=True, exist_ok=True)
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    if not _migrated:
        _migrated = True
        _migrate_legacy()
    return APP_DIR


def sessions_dir() -> Path:
    ensure_app_dir()
    return SESSIONS_DIR


def session_file(pk: str) -> Path:
    if not pk.isdigit():
        raise ValueError("invalid pk")
    return SESSIONS_DIR / f"{pk}.json"


def current_pk() -> str | None:
    ensure_app_dir()
    if not CURRENT_FILE.is_file():
        return None
    pk = CURRENT_FILE.read_text(encoding="utf-8").strip()
    if not pk.isdigit() or not session_file(pk).is_file():
        CURRENT_FILE.unlink(missing_ok=True)
        return None
    return pk


def set_current(pk: str | None) -> None:
    ensure_app_dir()
    if pk is None:
        CURRENT_FILE.unlink(missing_ok=True)
        return
    if not pk.isdigit():
        raise ValueError("invalid pk")
    CURRENT_FILE.write_text(pk, encoding="utf-8")


def session_path() -> Path:
    pk = current_pk()
    if pk:
        return session_file(pk)
    return SESSIONS_DIR


def session_exists() -> bool:
    return current_pk() is not None


def list_session_pks() -> list[str]:
    ensure_app_dir()
    return sorted(
        path.stem for path in SESSIONS_DIR.glob("*.json") if path.stem.isdigit()
    )


def delete_session(pk: str) -> None:
    if not pk.isdigit():
        return
    session_file(pk).unlink(missing_ok=True)
    if CURRENT_FILE.is_file() and CURRENT_FILE.read_text(encoding="utf-8").strip() == pk:
        CURRENT_FILE.unlink(missing_ok=True)


def deactivate() -> None:
    """Sign out without deleting the saved session file."""
    set_current(None)


def save_client(client: Client, pk: str | None = None) -> Path:
    ensure_app_dir()
    user_pk = pk or ""
    if not user_pk.isdigit():
        raw = client.user_id or client.account_info().pk
        user_pk = raw if isinstance(raw, str) else str(raw)
    if not user_pk.isdigit():
        raise RuntimeError("Could not determine Instagram user pk")
    path = session_file(user_pk)
    client.dump_settings(str(path))
    set_current(user_pk)
    return path


def load_client(pk: str | None = None) -> Client:
    user_pk = pk or current_pk()
    if not user_pk:
        raise FileNotFoundError("No active session")
    path = session_file(user_pk)
    if not path.is_file():
        raise FileNotFoundError(f"No session for {user_pk}")
    client = Client()
    client.load_settings(str(path))
    return client


def session_user_pk() -> str | None:
    """Instagram user pk from the active session, with no network call."""
    pk = current_pk()
    if pk:
        return pk
    return None


def profile_from_user(info) -> dict[str, Any]:
    pic = getattr(info, "profile_pic_url_hd", None) or getattr(
        info, "profile_pic_url", None
    )
    bio = (getattr(info, "biography", None) or "").strip()
    return {
        "pk": str(info.pk),
        "username": str(info.username) if info.username else None,
        "full_name": info.full_name or None,
        "biography": bio or None,
        "follower_count": int(getattr(info, "follower_count", 0) or 0),
        "following_count": int(getattr(info, "following_count", 0) or 0),
        "media_count": int(getattr(info, "media_count", 0) or 0),
        "is_private": bool(info.is_private),
        "is_verified": bool(info.is_verified),
        "profile_pic_url": str(pic) if pic else None,
    }


def load_session_profile(pk: str | None = None) -> dict[str, Any] | None:
    """Live Instagram profile for a saved session.

    Returns None if there is no file. Deletes the file and raises
    SessionExpired if Instagram rejected the session.
    """
    user_pk = pk or current_pk()
    if not user_pk:
        return None
    try:
        client = load_client(user_pk)
        user_id = client.user_id or client.account_info().pk
        return profile_from_user(client.user_info(str(user_id)))
    except AUTH_ERRORS as exc:
        delete_session(user_pk)
        raise SessionExpired(user_pk) from exc


def pk_from_dump(path: Path) -> str | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    auth = data.get("authorization_data") or {}
    pk = auth.get("ds_user_id") or (data.get("cookies") or {}).get("ds_user_id")
    return str(pk) if pk and str(pk).isdigit() else None


def _migrate_legacy() -> None:
    if not LEGACY_SESSION_FILE.is_file():
        return
    pk = pk_from_dump(LEGACY_SESSION_FILE)
    if not pk:
        try:
            client = Client()
            client.load_settings(str(LEGACY_SESSION_FILE))
            raw = client.user_id
            pk = str(raw) if raw and str(raw).isdigit() else None
        except Exception:
            pk = None
    if not pk:
        return
    dest = session_file(pk)
    if dest.exists():
        LEGACY_SESSION_FILE.unlink(missing_ok=True)
    else:
        LEGACY_SESSION_FILE.replace(dest)
    if not CURRENT_FILE.is_file():
        CURRENT_FILE.write_text(pk, encoding="utf-8")
