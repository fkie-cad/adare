#!/bin/bash
#
# ADARE Installation Script
# Run from the workspace root (via Makefile)
#

# Install dependencies using uv (single sync from workspace root)
if command -v uv >/dev/null 2>&1; then
    if [[ "$1" == "qemu" ]]; then
        echo "Argument 'qemu' detected. Installing with QEMU extras..."
        uv sync --extra qemu
    else
        echo "Installing standard dependencies (no QEMU)..."
        echo "To install with QEMU support, run this script as: ./install.sh qemu"
        uv sync
    fi
else
    echo "uv is not installed. Please install uv to continue."
    exit 1
fi

# Ensure ~/.local/bin exists
if [ ! -d ~/.local/bin ]; then
    mkdir -p ~/.local/bin
fi

# Find the adare executable in the workspace root virtual environment
ADARE_EXECUTABLE="$(pwd)/.venv/bin/adare"
if [ ! -f "$ADARE_EXECUTABLE" ]; then
    echo "The 'adare' executable could not be found. Ensure it's available via uv."
    exit 1
fi

ln -sf "$ADARE_EXECUTABLE" ~/.local/bin/adare

# Find the adare-cv-server executable in the workspace root virtual environment
ADARE_CV_SERVER_EXECUTABLE="$(pwd)/.venv/bin/adare-cv-server"
if [ ! -f "$ADARE_CV_SERVER_EXECUTABLE" ]; then
    echo "The 'adare-cv-server' executable could not be found. Ensure it's available via uv."
    exit 1
fi

ln -sf "$ADARE_CV_SERVER_EXECUTABLE" ~/.local/bin/adare-cv-server

if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    echo "Warning: $HOME/.local/bin is not in your PATH. Consider adding it to ensure 'adare' can be executed globally."
fi

# Run the Python script
if [ -f adare/install/copy_appdata.py ]; then
    python3 adare/install/copy_appdata.py
else
    echo "The script 'adare/install/copy_appdata.py' does not exist. Exiting..."
    exit 1
fi

# Load testfunctions directly from source appdata after installation is complete
echo "Loading testfunctions from source appdata..."
# Check if the directory exists before iterating to avoid errors if empty
if [ -d ~/.adare/adare/adare/appdata/testfunctions/ ]; then
    for testfunction_dir in ~/.adare/adare/adare/appdata/testfunctions/*/; do
        if [ -d "$testfunction_dir" ]; then
            testfunction_name=$(basename "$testfunction_dir")
            # Skip visual testfunctions (host-side only, loaded differently)
            if [ "$testfunction_name" = "visual" ]; then
                echo "Skipping visual testfunctions (host-side only)..."
                continue
            fi
            echo "Loading $testfunction_name testfunctions..."
            uv run adare testfunction load "$testfunction_dir"
        fi
    done
else
    echo "Testfunctions directory not found, skipping load."
fi

echo "Testfunction loading complete."
