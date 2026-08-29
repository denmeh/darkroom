"""Resolve bundled files in a source checkout and a PyInstaller build."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def meipass() -> Path | None:
    if not getattr(sys, "frozen", False):
        return None
    root = getattr(sys, "_MEIPASS", None)
    if isinstance(root, str):
        return Path(root)
    return None


def configure_frozen_env() -> None:
    os.environ.setdefault("QT_API", "pyqt6")
    os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
    root = meipass()
    if root is None:
        return
    browsers = root / "ms-playwright"
    if browsers.is_dir():
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(browsers))
    for candidate in (
        root / "QtWebEngineProcess",
        root / "PyQt6" / "Qt6" / "libexec" / "QtWebEngineProcess",
    ):
        if candidate.is_file():
            os.environ.setdefault("QTWEBENGINEPROCESS_PATH", str(candidate))
            break


def ui_dist() -> Path:
    root = meipass()
    if root is not None:
        return root / "ui"
    return Path(__file__).resolve().parent.parent.parent / "ui" / "dist"


def icon_path() -> Path:
    root = meipass()
    if root is not None:
        return root / "assets" / "icon.png"
    return Path(__file__).resolve().parent / "assets" / "icon.png"


configure_frozen_env()
