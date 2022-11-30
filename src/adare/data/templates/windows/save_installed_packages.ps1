Start-Transcript {{logfolder}}/save_installed_packages.log

function WriteLog
{
    Param ([string]$LogString)
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

$InstalledSoftware = Get-ChildItem "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall"
foreach($obj in $InstalledSoftware){
    $software = $obj.GetValue('DisplayName');
    $version = $obj.GetValue('DisplayVersion');
    if ($software){
        Write-host "$software=$version" 2>&1 | WriteLog;
    }
}

Stop-Transcript

