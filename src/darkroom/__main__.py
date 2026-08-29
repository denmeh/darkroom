from __future__ import annotations

import argparse
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

os.environ.setdefault("QT_API", "pyqt6")
os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")

import uvicorn
import webview

from darkroom.api import app, mount_ui
from darkroom.session import APP_DIR, ensure_app_dir

API_HOST = "127.0.0.1"
API_PORT = 8765
VITE_URL = "http://127.0.0.1:5173"
ICON = Path(__file__).resolve().parent / "assets" / "icon.png"


def wait_for(url: str, timeout_s: float = 30) -> None:
    deadline = time.monotonic() + timeout_s
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            return
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last_error = exc
            time.sleep(0.2)
    raise RuntimeError(f"Timed out waiting for {url}") from last_error


def start_api() -> None:
    config = uvicorn.Config(
        app,
        host=API_HOST,
        port=API_PORT,
        log_level="info",
        access_log=False,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="darkroom-api", daemon=True)
    thread.start()
    wait_for(f"http://{API_HOST}:{API_PORT}/api/health")


def main() -> None:
    parser = argparse.ArgumentParser(prog="darkroom")
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Load the Vite dev server instead of the production UI build",
    )
    args = parser.parse_args()

    if not args.dev:
        mount_ui()
    start_api()

    url = VITE_URL if args.dev else f"http://{API_HOST}:{API_PORT}/"
    if args.dev:
        wait_for(VITE_URL, timeout_s=60)

    webview.create_window(
        "Darkroom",
        url,
        width=1440,
        height=900,
        min_size=(1100, 720),
    )
    ensure_app_dir()
    webview.start(
        gui="qt",
        private_mode=False,
        storage_path=str(APP_DIR / "webview"),
        icon=str(ICON),
    )


if __name__ == "__main__":
    main()
