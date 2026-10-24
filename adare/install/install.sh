#!/bin/bash
#
# ADARE Installation Script (Linux/macOS; Windows: install.ps1)
# Usage: ./adare/install/install.sh [qemu]   (or `make install`, which passes qemu)
#
# Installs exactly what uv.lock pins (--locked) into the workspace .venv, links the
# CLIs into ~/.local/bin, installs appdata, and migrates the database. Safe to re-run.
#

set -euo pipefail

# Work from the workspace root, wherever the script is called from.
cd "$(dirname "$0")/../.."

if ! command -v uv >/dev/null 2>&1; then
    echo "uv is not installed: https://docs.astral.sh/uv/getting-started/installation/" >&2
    exit 1
fi

# --inexact: a re-run never removes what you added on top (e.g. --extra grounding).
if [[ "${1:-}" == "qemu" ]]; then
    echo "Installing with QEMU support..."
    uv sync --locked --inexact --extra qemu
else
    echo "Installing without QEMU support (for QEMU, run: ./adare/install/install.sh qemu)..."
    uv sync --locked --inexact
fi

# The links point into this clone's .venv: keep the clone where it is.
mkdir -p ~/.local/bin
for tool in adare adare-cv-server; do
    executable="$(pwd)/.venv/bin/$tool"
    if [ ! -f "$executable" ]; then
        echo "'$tool' was not installed into .venv/bin." >&2
        exit 1
    fi
    ln -sf "$executable" ~/.local/bin/"$tool"
done

if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    echo "Warning: $HOME/.local/bin is not in your PATH. Add it to run 'adare' from anywhere."
fi

uv run --no-sync python adare/install/copy_appdata.py

echo "Applying database schema migrations..."
uv run --no-sync adare db migrate

echo "Syncing testfunctions..."
uv run --no-sync adare testfunction sync

echo "Checking optional QEMU/system tools..."
uv run --no-sync adare vm doctor
