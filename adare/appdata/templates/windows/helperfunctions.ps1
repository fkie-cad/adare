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
        [string]$addPath
    )
    if($MyInvocation.ExpectingInput){
        $addPath = $input
    }
    if (Test-Path $addPath){
        $regexAddPath = [regex]::Escape($addPath)
        $arrPath = $env:Path -split ';' | Where-Object {$_ -notMatch "^$regexAddPath\\?"}
        $env:Path = ($arrPath + $addPath) -join ';'
    } else {
        Throw "'$addPath' is not a valid path."
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