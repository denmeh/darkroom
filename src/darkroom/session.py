from pathlib import Path
from typing import Any

from instagrapi import Client

APP_DIR = Path.home() / "darkroom"
SESSION_FILE = APP_DIR / "session.json"


def session_path() -> Path:
    return SESSION_FILE


def ensure_app_dir() -> Path:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    return APP_DIR


def session_exists() -> bool:
    return SESSION_FILE.is_file()


def clear_session() -> None:
    if SESSION_FILE.is_file():
        SESSION_FILE.unlink()


def save_client(client: Client) -> Path:
    ensure_app_dir()
    client.dump_settings(str(SESSION_FILE))
    return SESSION_FILE


def load_client() -> Client:
    client = Client()
    client.load_settings(str(SESSION_FILE))
    return client


def session_user_pk() -> str | None:
    """Instagram user pk from the saved session, with no network call."""
    if not session_exists():
        return None
    try:
        pk = load_client().user_id
    except Exception:
        return None
    return str(pk) if pk else None


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


def load_session_profile() -> dict[str, Any] | None:
    """Live Instagram profile for the saved session, or None if it is dead."""
    if not session_exists():
        return None
    try:
        client = load_client()
        pk = client.user_id
        if not pk:
            pk = client.account_info().pk
        return profile_from_user(client.user_info(pk))
    except Exception:
        return None
