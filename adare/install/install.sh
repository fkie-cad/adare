#!/bin/bash

# Navigate to the 'adare' directory
cd adare || { echo "Directory 'adare' not found. Exiting..."; exit 1; }

# Install dependencies using Poetry
if command -v poetry >/dev/null 2>&1; then
    poetry install
else
    echo "Poetry is not installed. Please install Poetry to continue."
    exit 1
fi

# Install adare-mcp-server package
echo "Installing adare-mcp-server package..."
cd ../adare-mcp-server || { echo "Directory 'adare-mcp-server' not found. Exiting..."; exit 1; }
poetry install
cd ../adare

# Create a symbolic link for the 'adare' executable
ADARE_EXECUTABLE=$(poetry run which adare)
if [ -z "$ADARE_EXECUTABLE" ]; then
    echo "The 'adare' executable could not be found. Ensure it's available via Poetry."
    exit 1
fi

ln -sf "$ADARE_EXECUTABLE" ~/.local/bin/adare

# Create a symbolic link for the 'adare-mcp-server' executable
cd ../adare-mcp-server
ADARE_MCP_SERVER_EXECUTABLE=$(poetry run which adare-mcp-server)
if [ -z "$ADARE_MCP_SERVER_EXECUTABLE" ]; then
    echo "The 'adare-mcp-server' executable could not be found. Ensure it's available via Poetry."
    exit 1
fi

ln -sf "$ADARE_MCP_SERVER_EXECUTABLE" ~/.local/bin/adare-mcp-server
cd ../adare

# Ensure ~/.local/bin exists and is in PATH
if [ ! -d ~/.local/bin ]; then
    mkdir -p ~/.local/bin
fi
if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    echo "Warning: $HOME/.local/bin is not in your PATH. Consider adding it to ensure 'adare' can be executed globally."
fi

# Run the Python script
if [ -f install/copy_appdata.py ]; then
    python3 install/copy_appdata.py
else
    echo "The script 'install/copy_appdata.py' does not exist. Exiting..."
    exit 1
fi
