# Navigate to the 'adarevm' directory
$adareDirectory = "adarevm"
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
$adareExecutable = $(poetry run where adarevm | Where-Object { $_ -like "*.cmd" })
if (-not $adareExecutable) {
    Write-Host "`nThe 'adarevm' executable could not be found. Ensure it's available via Poetry.`n"
    exit
} else {
    Write-Host "`nAdarevm executable found at: $adareExecutable`n"
}

# No need to add individual executables to PATH, instructing to add Poetry's bin if not already included
$poetryBinPath = Split-Path $adareExecutable
$userPath = [Environment]::GetEnvironmentVariable("PATH", "User")
if (-not $userPath.Contains($poetryBinPath)) {
    $newUserPath = $userPath + ";" + $poetryBinPath
    [Environment]::SetEnvironmentVariable("Path", $newUserPath, [EnvironmentVariableTarget]::User)
    Write-Host "Path $poetryBinPath added to user PATH."
}

