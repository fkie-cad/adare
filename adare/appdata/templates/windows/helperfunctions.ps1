function WriteLog
{
    param ([string]$LogString)
    if($MyInvocation.ExpectingInput){
        $LogContent = $input
    }else{
        $LogContent = $LogString
    }
    $LogContent -Split "`r`n" | ForEach-Object {
        $Stamp = (Get-Date).toString("yyyy-MM-dd HH:mm:ss")
        $LogMessage = "[$Stamp]: $_"
        Write-Host "$LogMessage"
    }
}

function StartStage {
    param (
        [string]$stage
    )
    $Stamp = (Get-Date).toString("yyyy-MM-dd HH:mm:ss")
    $LogMessage = "stage $($stage): start ($($Stamp))"
    Write-Host "$LogMessage"
}

function StageMessage {
    param (
        [string]$stage,
        [string]$message
    )
    $Stamp = (Get-Date).toString("yyyy-MM-dd HH:mm:ss")
    $LogMessage = "stage $($stage): $($message) ($($Stamp))"
    Write-Host "$LogMessage"
}

function EndStage {
    param (
        [string]$stage
    )
    $Stamp = (Get-Date).toString("yyyy-MM-dd HH:mm:ss")
    $LogMessage = "stage $($stage): end ($($Stamp))"
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
