# PyInstaller spec: just build → dist/darkroom/darkroom (Linux x86_64 / glibc)
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, copy_metadata

ROOT = Path(SPECPATH).resolve()

datas = [
    (str(ROOT / "ui" / "dist"), "ui"),
    (str(ROOT / "src" / "darkroom" / "assets"), "assets"),
]
binaries: list = []
hiddenimports = [
    "darkroom",
    "darkroom.api",
    "darkroom.avatars",
    "darkroom.crawl",
    "darkroom.db",
    "darkroom.errors",
    "darkroom.login",
    "darkroom.paths",
    "darkroom.scan",
    "darkroom.session",
    "webview.platforms.qt",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.http.httptools_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
]

for pkg in (
    "playwright",
    "webview",
    "curl_cffi",
    "uvicorn",
    "fastapi",
    "starlette",
    "anyio",
    "pydantic",
    "pydantic_core",
    "httptools",
    "instagrapi",
):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

for pkg in ("playwright", "instagrapi", "curl_cffi"):
    try:
        datas += copy_metadata(pkg)
    except Exception:
        pass

browsers = Path.home() / ".cache" / "ms-playwright"
if browsers.is_dir():
    for path in browsers.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(browsers)
        if rel.parts and rel.parts[0].startswith("chromium_headless_shell"):
            continue
        dest = str(Path("ms-playwright") / rel.parent)
        datas.append((str(path), dest))

a = Analysis(
    [str(ROOT / "src" / "darkroom" / "__main__.py")],
    pathex=[str(ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="darkroom",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    icon=str(ROOT / "src" / "darkroom" / "assets" / "icon.png"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="darkroom",
)
