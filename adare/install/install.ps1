# Navigate to the 'adare' directory
$adareDirectory = "adare"
if (Test-Path $adareDirectory) {
    Set-Location $adareDirectory
} else {
    Write-Host "`nDirectory 'adare' not found. Exiting...`n"
    exit
}

# Install dependencies using uv
if (Get-Command uv -ErrorAction SilentlyContinue) {
    uv sync
} else {
    Write-Host "`nuv is not installed. Please install uv to continue.`n"
    exit
}

# Install adare-cv-server package
Write-Host "`nInstalling adare-cv-server package...`n"
$mcpServerDirectory = "..\adare-cv-server"
if (Test-Path $mcpServerDirectory) {
    Set-Location $mcpServerDirectory
    uv sync
    Set-Location "..\adare"
} else {
    Write-Host "`nDirectory 'adare-cv-server' not found. Exiting...`n"
    exit
}

# Attempt to find the adare CMD executable in the virtual environment
$adareExecutable = Join-Path (Get-Location) ".venv\Scripts\adare.exe"
if (-not (Test-Path $adareExecutable)) {
    Write-Host "`nThe 'adare' executable could not be found. Ensure it's available via uv.`n"
    exit
} else {
    Write-Host "`nAdare executable found at: $adareExecutable`n"
}

# Attempt to find the adare-cv-server CMD executable
Set-Location $mcpServerDirectory
$mcpServerExecutable = Join-Path (Get-Location) ".venv\Scripts\adare-cv-server.exe"
if (-not (Test-Path $mcpServerExecutable)) {
    Write-Host "`nThe 'adare-cv-server' executable could not be found. Ensure it's available via uv.`n"
    exit
} else {
    Write-Host "`nAdare MCP Server executable found at: $mcpServerExecutable`n"
}
Set-Location "..\adare"

# No need to add individual executables to PATH, instructing to add uv's bin if not already included
$poetryBinPath = Split-Path $adareExecutable
$mcpServerBinPath = Split-Path $mcpServerExecutable
$userPath = [Environment]::GetEnvironmentVariable("PATH", "User")

$pathsToAdd = @()
if (-not $userPath.Contains($poetryBinPath)) {
    $pathsToAdd += $poetryBinPath
}
if (-not $userPath.Contains($mcpServerBinPath) -and $mcpServerBinPath -ne $poetryBinPath) {
    $pathsToAdd += $mcpServerBinPath
}

if ($pathsToAdd.Count -gt 0) {
    Write-Host "Please manually add the following paths to your system PATH to ensure 'adare' and 'adare-cv-server' can be executed globally:"
    foreach ($path in $pathsToAdd) {
        Write-Host "  - $path"
    }
    Write-Host "You can do this by searching for 'Edit the system environment variables' in the Start menu, clicking on 'Environment Variables', and then adding these paths to the 'User variables' PATH.`n"
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
