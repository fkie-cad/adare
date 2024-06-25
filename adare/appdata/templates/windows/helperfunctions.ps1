function WriteLog
{
    param ([string]$LogString)
    if($MyInvocation.ExpectingInput){
        $LogContent = $input
    }else{
        $LogContent = $LogString
    }
    $LogContent -Split "`r`n" | ForEach-Object {
        $Stamp = (Get-Date).ToUniversalTime().toString("yyyy-MM-ddTHH:mm:ss.ffffff")
        $LogMessage = "[$Stamp]: $_"
        Write-Host "$LogMessage"
    }
}

function StartStage {
    param (
        [string]$stage
    )
    $Stamp = (Get-Date).ToUniversalTime().toString("yyyy-MM-ddTHH:mm:ss.ffffff")
    $LogMessage = "stage $($stage): start ($($Stamp)) (...)"
    Write-Host "$LogMessage"
}

function StageMessage {
    param (
        [string]$stage,
        [string]$message
    )
    $Stamp = (Get-Date).ToUniversalTime().toString("yyyy-MM-ddTHH:mm:ss.ffffff")
    $LogMessage = "stage $($stage): $($message) ($($Stamp)) (...)"
    Write-Host "$LogMessage"
}

function ExitCodeToStatus {
    param (
        [int]$exitCode
    )
    if ($exitCode -eq 0) {
        return "finished"
    } else {
        return "failed"
    }
}

function EndStage {
    param (
        [string]$stage,
        [string]$status = ""
    )
    if ($status -eq "") {
        $status = "(...)"
    }
    $Stamp = (Get-Date).ToUniversalTime().toString("yyyy-MM-ddTHH:mm:ss.ffffff")
    $LogMessage = "stage $($stage): end ($($Stamp)) $($status)"
    Write-Host "$LogMessage"
}

function Add-PathVariable {
    param (
        [Parameter(Mandatory=$true)]
        [string]$addPath
    )

    # First, check if the path is valid and is a directory
    if (Test-Path $addPath -PathType Container) {
        $normalizedAddPath = (Get-Item $addPath).FullName
        $currentPath = [Environment]::GetEnvironmentVariable("Path", "Machine")
        $pathArray = $currentPath -split ';' | Where-Object { $_ }

        # Check if the path already exists to avoid duplicates
        if (-not ($pathArray -contains $normalizedAddPath)) {
            $newPath = $currentPath + ';' + $normalizedAddPath

            # Update the system environment variable using setx
            setx PATH $newPath /M

            # Update the environment variable for the current process
            $env:Path += ";$normalizedAddPath"
            Write-Output "Path added successfully. '$normalizedAddPath' added to current session and system-wide PATH."
        } else {
            Write-Output "$normalizedAddPath is already in the system PATH."
        }
    } else {
        Throw "'$addPath' is not a valid directory path."
    }
}



function checkExitCode {
    param (
        [string]$stage
    )
    # check if lastexitcode is not set
    if ($LastExitCode -eq $null) {
        Write-Host "LastExitCode is not set."
    }
    elseif ($LastExitCode -ne 0) {
        $exit_code = $LastExitCode
        $status = ExitCodeToStatus $exit_code
        EndStage $stage $status
        Write-Host "Exiting with code $exit_code"
        exit $exit_code
    }
}