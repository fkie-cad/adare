# ADARE Installation Script (Windows; Linux/macOS: install.sh)
# Usage: powershell -ExecutionPolicy Bypass -File adare\install\install.ps1   (or `make install`)
#
# Installs exactly what uv.lock pins (--locked) into the workspace .venv, puts the
# CLIs on your user PATH, installs appdata, and migrates the database. Safe to
# re-run, which is also how you update on Windows (`make update` does the same).
# QEMU is not supported on Windows hosts, so there is no qemu extra here.

$ErrorActionPreference = 'Stop'

# Work from the workspace root, wherever the script is called from.
Set-Location (Resolve-Path (Join-Path $PSScriptRoot '..\..'))

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw 'uv is not installed: https://docs.astral.sh/uv/getting-started/installation/'
}

# A failing native command does not stop the script on its own, so check each one.
function Invoke-Checked {
    $command = $args[0]
    $arguments = @($args | Select-Object -Skip 1)
    & $command @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "'$($args -join ' ')' failed with exit code $LASTEXITCODE"
    }
}

# --inexact: a re-run never removes what you added on top.
Write-Host 'Installing dependencies...'
Invoke-Checked uv sync --locked --inexact

$binDir = Join-Path (Get-Location) '.venv\Scripts'
foreach ($tool in 'adare', 'adare-cv-server') {
    if (-not (Test-Path (Join-Path $binDir "$tool.exe"))) {
        throw "'$tool' was not installed into $binDir."
    }
}

# The PATH entry points into this clone's .venv: keep the clone where it is.
$userPath = [Environment]::GetEnvironmentVariable('PATH', 'User')
if (-not (($userPath -split ';') -contains $binDir)) {
    $newPath = (@($userPath, $binDir) | Where-Object { $_ }) -join ';'
    [Environment]::SetEnvironmentVariable('PATH', $newPath, 'User')
    Write-Host "Added $binDir to your user PATH. Open a new terminal to run 'adare'."
}

Invoke-Checked uv run --no-sync python adare\install\copy_appdata.py

Write-Host 'Applying database schema migrations...'
Invoke-Checked uv run --no-sync adare db migrate

Write-Host 'Syncing testfunctions...'
Invoke-Checked uv run --no-sync adare testfunction sync
