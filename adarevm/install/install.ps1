# Navigate to the 'adarevm' directory
$adareDirectory = "Z:\\"
if (Test-Path $adareDirectory) {
    Set-Location $adareDirectory
} else {
    Write-Host "`nDirectory 'Z:\\' not found. Exiting...`n"
    exit
}

# Install dependencies using uv
if (Get-Command uv -ErrorAction SilentlyContinue) {
    uv sync
} else {
    Write-Host "`nuv is not installed. Please install uv to continue.`n"
    exit
}

# Create a wrapper script in WindowsApps
$windowsAppsPath = "$env:LOCALAPPDATA\Microsoft\WindowsApps"
$wrapperScriptPath = Join-Path $windowsAppsPath "adarevm.cmd"

$wrapperScriptContent = '@echo off
uv run adarevm %*'

# Check if the script already exists
if (-not (Test-Path $wrapperScriptPath)) {
    Set-Content -Path $wrapperScriptPath -Value $wrapperScriptContent -Encoding ASCII
    Write-Host "`nadarevm.cmd created at: $wrapperScriptPath"
} else {
    Write-Host "`nadarevm.cmd already exists at: $wrapperScriptPath"
}

Write-Host "`nYou can now run 'adarevm' from any terminal window."
