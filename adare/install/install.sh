#!/bin/bash
#
# ADARE Installation Script
#

# Navigate to the 'adare' directory
cd adare || { echo "Directory 'adare' not found. Exiting..."; exit 1; }

# Install dependencies using Poetry
if command -v poetry >/dev/null 2>&1; then
    poetry install
else
    echo "Poetry is not installed. Please install Poetry to continue."
    exit 1
fi

# Install adare-cv-server package
echo "Installing adare-cv-server package..."
cd ../adare-cv-server || { echo "Directory 'adare-cv-server' not found. Exiting..."; exit 1; }
poetry install
cd ../adare

# Create a symbolic link for the 'adare' executable
ADARE_EXECUTABLE=$(poetry run which adare)
if [ -z "$ADARE_EXECUTABLE" ]; then
    echo "The 'adare' executable could not be found. Ensure it's available via Poetry."
    exit 1
fi

ln -sf "$ADARE_EXECUTABLE" ~/.local/bin/adare

# Create a symbolic link for the 'adare-cv-server' executable
cd ../adare-cv-server
ADARE_CV_SERVER_EXECUTABLE=$(poetry run which adare-cv-server)
if [ -z "$ADARE_CV_SERVER_EXECUTABLE" ]; then
    echo "The 'adare-cv-server' executable could not be found. Ensure it's available via Poetry."
    exit 1
fi

ln -sf "$ADARE_CV_SERVER_EXECUTABLE" ~/.local/bin/adare-cv-server
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

# Load testfunctions directly from source appdata after installation is complete
echo "Loading testfunctions from source appdata..."
for testfunction_dir in ~/.adare/adare/adare/appdata/testfunctions/*/; do
    if [ -d "$testfunction_dir" ]; then
        testfunction_name=$(basename "$testfunction_dir")
        echo "Loading $testfunction_name testfunctions..."
        poetry run adare testfunction load "$testfunction_dir"
    fi
done
echo "Testfunction loading complete."
