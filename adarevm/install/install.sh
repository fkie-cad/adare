#!/bin/bash

# Navigate to the 'adare' directory
cd adarevm || { echo "Directory 'adarevm' not found. Exiting..."; exit 1; }

# Install dependencies using uv
if command -v uv >/dev/null 2>&1; then
    uv sync
else
    echo "uv is not installed. Please install uv to continue."
    exit 1
fi

# Find the adarevm executable in the virtual environment
ADARE_EXECUTABLE="$(pwd)/.venv/bin/adarevm"
if [ ! -f "$ADARE_EXECUTABLE" ]; then
    echo "The 'adarevm' executable could not be found. Ensure it's available via uv."
    exit 1
fi

ln -sf "$ADARE_EXECUTABLE" ~/.local/bin/adarevm

# Ensure ~/.local/bin exists and is in PATH
if [ ! -d ~/.local/bin ]; then
    mkdir -p ~/.local/bin
fi
if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    echo "Warning: $HOME/.local/bin is not in your PATH. Consider adding it to ensure 'adare' can be executed globally."
fi
