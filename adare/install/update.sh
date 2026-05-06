#!/bin/bash
#
# ADARE Update Script
# Refresh deps, appdata, and testfunctions without re-bootstrapping symlinks.
# Run from the workspace root (via Makefile).
#

set -e

if ! command -v uv >/dev/null 2>&1; then
    echo "uv is not installed. Please install uv to continue."
    exit 1
fi

if [[ "$1" == "qemu" ]]; then
    echo "Argument 'qemu' detected. Syncing with QEMU extras..."
    uv sync --extra qemu
else
    echo "Syncing standard dependencies (no QEMU)..."
    uv sync
fi

if [ -f adare/install/copy_appdata.py ]; then
    python3 adare/install/copy_appdata.py
else
    echo "The script 'adare/install/copy_appdata.py' does not exist. Exiting..."
    exit 1
fi

echo "Syncing testfunctions..."
uv run adare testfunction sync
