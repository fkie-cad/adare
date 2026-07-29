<#
.SYNOPSIS
    Provision a Windows 11 (ARM64) ADARE VM with a group of Autopsy versions.

.DESCRIPTION
    Run INSIDE the guest during an `adare env extend ... --interactive` session.
    For each version listed in -VersionsFile it downloads the official 64-bit MSI
    from the sleuthkit/autopsy GitHub releases and installs it silently. Every
    version installs into its own "C:\Program Files\Autopsy-<version>" directory,
    so all versions in a group coexist. Autopsy MSIs are x64-only; on Win11 ARM64
    they run under the built-in Prism x64 emulation.

    A per-version pass/fail summary is printed at the end. The script does not stop
    on a single failed install: it records the failure and continues, so one bad
    (very old) MSI never blocks the rest of the group.

.PARAMETER VersionsFile
    Path to a text file with one Autopsy version per line (e.g. versions_solr4.txt).
    Blank lines and lines starting with '#' are ignored.

.PARAMETER LogDir
    Directory for msiexec verbose logs and this run's transcript.
    Defaults to "$env:USERPROFILE\autopsy-install-logs".

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File Install-Autopsy.ps1 -VersionsFile versions_solr4.txt

.NOTES
    Mirrors the curl + msiexec + logged-exit-code pattern of the ADARE guest
    template adare/appdata/templates/windows/installations.ps1.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$VersionsFile,

    [Parameter(Mandatory = $false)]
    [string]$LogDir = "$env:USERPROFILE\autopsy-install-logs"
)

$ErrorActionPreference = 'Stop'

# ---------------------------------------------------------------------------
# Setup: logging
# ---------------------------------------------------------------------------
if (-not (Test-Path -LiteralPath $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}
$transcript = Join-Path $LogDir 'install-autopsy-transcript.log'
Start-Transcript -Path $transcript -Append | Out-Null

function Write-Section($msg) {
    Write-Host ""
    Write-Host ("=" * 72)
    Write-Host $msg
    Write-Host ("=" * 72)
}

# ---------------------------------------------------------------------------
# Step 1: read + validate the version list
# ---------------------------------------------------------------------------
if (-not (Test-Path -LiteralPath $VersionsFile)) {
    Stop-Transcript | Out-Null
    throw "Versions file not found: $VersionsFile"
}

$versions = Get-Content -LiteralPath $VersionsFile |
    ForEach-Object { $_.Trim() } |
    Where-Object { $_ -and -not $_.StartsWith('#') }

if (-not $versions) {
    Stop-Transcript | Out-Null
    throw "No versions found in $VersionsFile"
}

Write-Section "Installing $($versions.Count) Autopsy version(s) from $VersionsFile"

# ---------------------------------------------------------------------------
# Step 2: download + install each version
# ---------------------------------------------------------------------------
$results = New-Object System.Collections.Generic.List[object]

foreach ($v in $versions) {
    Write-Section "Autopsy $v"

    $msi     = Join-Path $env:TEMP "autopsy-$v-64bit.msi"
    $url     = "https://github.com/sleuthkit/autopsy/releases/download/autopsy-$v/autopsy-$v-64bit.msi"
    $msiLog  = Join-Path $LogDir "autopsy-$v-msi.log"
    $target  = "C:\Program Files\Autopsy-$v"
    $status  = 'FAILED'
    $detail  = ''

    try {
        # Download (curl.exe ships with Windows 10/11). -f => fail on HTTP errors.
        Write-Host "Downloading $url"
        & curl.exe -L -f -o $msi $url
        if ($LASTEXITCODE -ne 0) {
            throw "curl.exe exit code $LASTEXITCODE (download failed)"
        }
        if (-not (Test-Path -LiteralPath $msi)) {
            throw "MSI not present after download: $msi"
        }

        # Silent install. The Autopsy MSI's default install location already
        # embeds the version ("C:\Program Files\Autopsy-<v>"), so each version
        # lands in its own directory without an INSTALLDIR override.
        Write-Host "Installing $msi -> $target"
        $proc = Start-Process -FilePath 'msiexec.exe' `
            -ArgumentList @('/i', "`"$msi`"", '/qn', '/norestart',
                            '/l*v', "`"$msiLog`"") `
            -Wait -PassThru
        # 0 = success, 3010 = success but reboot required (harmless here).
        if ($proc.ExitCode -ne 0 -and $proc.ExitCode -ne 3010) {
            throw "msiexec exit code $($proc.ExitCode) (see $msiLog)"
        }

        # Verify the install actually produced the target directory.
        if (Test-Path -LiteralPath $target) {
            $status = 'INSTALLED'
            $detail = $target
            Write-Host "OK: $target present"
        } else {
            throw "msiexec reported success but $target is missing"
        }
    } catch {
        $detail = $_.Exception.Message
        Write-Warning "Autopsy $v FAILED: $detail"
    } finally {
        # Clean up the downloaded MSI to save disk in the baked image.
        if (Test-Path -LiteralPath $msi) {
            Remove-Item -LiteralPath $msi -Force -ErrorAction SilentlyContinue
        }
    }

    $results.Add([pscustomobject]@{
        Version = $v
        Status  = $status
        Detail  = $detail
    })
}

# ---------------------------------------------------------------------------
# Step 3: harden the boot against hard power-off
# ---------------------------------------------------------------------------
# ADARE force-stops (hard power-off) Windows guests on teardown to avoid
# triggering Windows Update. A hard-killed Win11 guest otherwise intermittently
# comes back into "Windows didn't shut down correctly" / automatic Startup
# Repair, which WAITS FOR INPUT — so the desktop and QEMU Guest Agent never
# start and the next run dead-waits its readiness budget and fails.
#
# Baking these boot-manager policies into the image once makes cold boot off a
# hard-killed disk deterministic: skip failure detection, never auto-launch the
# recovery/repair environment. This is a boot policy only (no files/logs added),
# consistent with the "minimal guest state / no VM remnants" constraint.
Write-Section "Hardening boot policy (survive hard power-off)"
foreach ($bcd in @(
    @('bootstatuspolicy', 'ignoreallfailures'),
    @('recoveryenabled',  'No')
)) {
    $name, $value = $bcd
    Write-Host "bcdedit /set {default} $name $value"
    & bcdedit.exe /set '{default}' $name $value
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "bcdedit /set {default} $name $value failed (exit $LASTEXITCODE) — run elevated?"
    }
}

# ---------------------------------------------------------------------------
# Step 4: summary
# ---------------------------------------------------------------------------
Write-Section "Summary"
$results | Format-Table -AutoSize Version, Status, Detail | Out-String | Write-Host

$installed = @($results | Where-Object { $_.Status -eq 'INSTALLED' })
$failed    = @($results | Where-Object { $_.Status -ne 'INSTALLED' })

Write-Host ("Installed: {0}/{1}" -f $installed.Count, $results.Count)
if ($failed.Count -gt 0) {
    Write-Host "Failed versions: $(( $failed | ForEach-Object { $_.Version }) -join ', ')"
}
Write-Host "Logs: $LogDir"

Stop-Transcript | Out-Null

# Non-zero exit if anything failed, so the operator notices.
if ($failed.Count -gt 0) { exit 1 } else { exit 0 }
