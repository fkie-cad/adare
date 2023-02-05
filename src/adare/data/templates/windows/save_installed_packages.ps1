. "{{ scripts_directory }}\helperfunctions.ps1"

Start-Transcript {{ log_directory }}/save_installed_packages.log

$InstalledSoftware = Get-ChildItem "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall"
foreach($obj in $InstalledSoftware){
    $software = $obj.GetValue('DisplayName');
    $version = $obj.GetValue('DisplayVersion');
    if ($software){
        Write-host "$software=$version" 2>&1 | WriteLog;
    }
}

Stop-Transcript

