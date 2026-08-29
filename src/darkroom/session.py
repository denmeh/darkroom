from pathlib import Path

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


def validate_session() -> tuple[bool, str | None, str | None]:
    """Return (logged_in, username, pk) for the saved session, if any."""
    if not session_exists():
        return False, None, None
    try:
        client = load_client()
        info = client.account_info()
        return True, str(info.username), str(info.pk)
    except Exception:
        return False, None, None
