#!/bin/bash
#
# ADARE Update Script (Linux/macOS; on Windows, re-run install.ps1)
# Refresh deps, appdata, and testfunctions without re-bootstrapping symlinks.
# Usage: ./adare/install/update.sh [qemu]   (or `make update`, which passes qemu)
#

set -euo pipefail

cd "$(dirname "$0")/../.."

if ! command -v uv >/dev/null 2>&1; then
    echo "uv is not installed: https://docs.astral.sh/uv/getting-started/installation/" >&2
    exit 1
fi

if [[ "${1:-}" == "qemu" ]]; then
    echo "Syncing with QEMU support..."
    uv sync --locked --inexact --extra qemu
else
    echo "Syncing without QEMU support..."
    uv sync --locked --inexact
fi

uv run --no-sync python adare/install/copy_appdata.py

echo "Applying database schema migrations..."
uv run --no-sync adare db migrate

echo "Syncing testfunctions..."
uv run --no-sync adare testfunction sync
