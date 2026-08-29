python := ".venv/bin/python"

# List available recipes
default:
    @just --list

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
