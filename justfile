python := ".venv/bin/python"

# List available recipes
default:
    @just --list

# Fail unless this machine is Linux x86_64 (tested on Fedora)
[private]
linux-x64:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ "$(uname -s)" != Linux || "$(uname -m)" != x86_64 ]]; then
        echo "Linux x86_64 only (tested on Fedora). Windows and macOS are not supported." >&2
        exit 1
    fi

# Create .venv, install Python + UI deps, download Chromium
install:
    python3 -m venv --clear .venv
    {{python}} -m pip install -e .
    {{python}} -m playwright install chromium
    npm --prefix ui install

# Vite HMR in a native window (API on :8765)
dev:
    #!/usr/bin/env bash
    set -euo pipefail
    npm --prefix ui run dev &
    vite_pid=$!
    trap 'kill "$vite_pid" 2>/dev/null || true' EXIT
    {{python}} -m darkroom --dev

# Production UI build, then the desktop window
run:
    npm --prefix ui run build
    {{python}} -m darkroom

# Frozen desktop binary at dist/darkroom/ (Linux x86_64 only)
build: linux-x64
    {{python}} -m pip install -q '.[build]'
    npm --prefix ui run build
    {{python}} -m playwright install chromium
    {{python}} -m PyInstaller darkroom.spec --noconfirm
    @echo "Run with: dist/darkroom/darkroom"

# Freedesktop launcher so GNOME/KDE can pin the app (Linux only)
install-desktop: linux-x64
    #!/usr/bin/env bash
    set -euo pipefail
    root="{{justfile_directory()}}"
    data="${XDG_DATA_HOME:-$HOME/.local/share}"
    apps="$data/applications"
    mkdir -p "$apps" "$data/icons/hicolor/256x256/apps" "$data/icons/hicolor/scalable/apps"
    cp "$root/src/darkroom/assets/icon.png" "$data/icons/hicolor/256x256/apps/darkroom.png"
    cp "$root/src/darkroom/assets/icon.svg" "$data/icons/hicolor/scalable/apps/darkroom.svg"
    if [[ -x "$root/dist/darkroom/darkroom" ]]; then
        exec_line="$(realpath "$root/dist/darkroom/darkroom")"
    else
        exec_line="$(realpath "$root/{{python}}") -m darkroom"
    fi
    cat > "$apps/darkroom.desktop" <<EOF
    [Desktop Entry]
    Type=Application
    Name=Darkroom
    Comment=Local Instagram session app
    Exec=$exec_line
    Icon=darkroom
    Terminal=false
    Categories=Network;
    StartupWMClass=darkroom
    EOF
    chmod +x "$apps/darkroom.desktop"
    update-desktop-database "$apps" 2>/dev/null || true
    echo "Installed $apps/darkroom.desktop"
    echo "GNOME: Activities → search Darkroom → Pin / Add to Favorites."
    echo "KDE: right-click the taskbar icon → Pin to Task Manager."
