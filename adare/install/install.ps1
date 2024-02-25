# Navigate to the 'adare' directory
$adareDirectory = "adare"
if (Test-Path $adareDirectory) {
    Set-Location $adareDirectory
} else {
    Write-Host "`nDirectory 'adare' not found. Exiting...`n"
    exit
}

# Install dependencies using Poetry
if (Get-Command poetry -ErrorAction SilentlyContinue) {
    poetry install
} else {
    Write-Host "`nPoetry is not installed. Please install Poetry to continue.`n"
    exit
}

# Attempt to find the adare CMD executable
$adareExecutable = $(poetry run where adare | Where-Object { $_ -like "*.cmd" })
if (-not $adareExecutable) {
    Write-Host "`nThe 'adare' executable could not be found. Ensure it's available via Poetry.`n"
    exit
} else {
    Write-Host "`nAdare executable found at: $adareExecutable`n"
}

# No need to add individual executables to PATH, instructing to add Poetry's bin if not already included
$poetryBinPath = Split-Path $adareExecutable
$userPath = [Environment]::GetEnvironmentVariable("PATH", "User")
if (-not $userPath.Contains($poetryBinPath)) {
    Write-Host "Please manually add ` $poetryBinPath` to your system PATH to ensure 'adare' and other Poetry-managed scripts can be executed globally."
    Write-Host "You can do this by searching for 'Edit the system environment variables' in the Start menu, clicking on 'Environment Variables', and then adding ` $poetryBinPath` to the 'User variables' PATH.`n"
}

# Run the Python script
$copyAppDataScript = "install\copy_appdata.py"
if (Test-Path $copyAppDataScript) {
    python $copyAppDataScript
    Write-Host "`n"
} else {
    Write-Host "`nThe script 'install\copy_appdata.py' does not exist. Exiting...`n"
    exit
}
