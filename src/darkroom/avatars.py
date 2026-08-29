from __future__ import annotations

import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from darkroom.session import APP_DIR, ensure_app_dir

AVATARS_DIR = APP_DIR / "avatars"
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="darkroom-avatar")


def avatars_dir() -> Path:
    ensure_app_dir()
    AVATARS_DIR.mkdir(parents=True, exist_ok=True)
    return AVATARS_DIR


def avatar_file(pk: str) -> Path:
    return avatars_dir() / pk


def has_avatar(pk: str) -> bool:
    if not pk.isdigit():
        return False
    path = avatar_file(pk)
    return path.is_file() and path.stat().st_size > 0


def fetch_avatar(pk: str, url: str) -> Path | None:
    if not pk.isdigit() or not url:
        return None
    dest = avatar_file(pk)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
        if not data:
            return dest if has_avatar(pk) else None
        dest.write_bytes(data)
        return dest
    except Exception:
        return dest if has_avatar(pk) else None


def prefetch_avatar(pk: str, url: str | None) -> None:
    if not url or not pk.isdigit():
        return
    _pool.submit(fetch_avatar, pk, url)
