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

# Install adare-mcp-server package
Write-Host "`nInstalling adare-mcp-server package...`n"
$mcpServerDirectory = "..\adare-mcp-server"
if (Test-Path $mcpServerDirectory) {
    Set-Location $mcpServerDirectory
    poetry install
    Set-Location "..\adare"
} else {
    Write-Host "`nDirectory 'adare-mcp-server' not found. Exiting...`n"
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

# Attempt to find the adare-mcp-server CMD executable
Set-Location $mcpServerDirectory
$mcpServerExecutable = $(poetry run where adare-mcp-server | Where-Object { $_ -like "*.cmd" })
if (-not $mcpServerExecutable) {
    Write-Host "`nThe 'adare-mcp-server' executable could not be found. Ensure it's available via Poetry.`n"
    exit
} else {
    Write-Host "`nAdare MCP Server executable found at: $mcpServerExecutable`n"
}
Set-Location "..\adare"

# No need to add individual executables to PATH, instructing to add Poetry's bin if not already included
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
    Write-Host "Please manually add the following paths to your system PATH to ensure 'adare' and 'adare-mcp-server' can be executed globally:"
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
