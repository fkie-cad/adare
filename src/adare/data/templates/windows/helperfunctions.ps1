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
        Write-host "$LogMessage"
    }
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

function Write-Status {
    param (
        [string]$statusname
    )
    if($?){
        $status = "success"
    }else{
        $status = "failed"
    }
    $statusfile = "{{ log_directory }}/status.csv"
    "$($statusname),$($status)" | Out-File -Encoding ASCII -Append $statusfile
}