#!/bin/bash

# Navigate to the 'adare' directory
cd adarevm || { echo "Directory 'adarevm' not found. Exiting..."; exit 1; }

# Install dependencies using Poetry
if command -v poetry >/dev/null 2>&1; then
    poetry install
else
    echo "Poetry is not installed. Please install Poetry to continue."
    exit 1
fi

# Create a symbolic link for the 'adare' executable
ADARE_EXECUTABLE=$(poetry run which adarevm)
if [ -z "$ADARE_EXECUTABLE" ]; then
    echo "The 'adarevm' executable could not be found. Ensure it's available via Poetry."
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