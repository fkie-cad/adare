. "{{ scripts_directory }}\helperfunctions.ps1"

{% if log_file is defined %}
Start-Transcript -Path "{{ log_file }}"
{% endif %}

StartStage "dump_installed_software"

$InstalledSoftware = Get-ChildItem "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall"
foreach($obj in $InstalledSoftware){
    $software = $obj.GetValue('DisplayName');
    $version = $obj.GetValue('DisplayVersion');
    if ($software){
        Write-host "$software=$version" 2>&1 | WriteLog;
    }
}

EndStage "dump_installed_software" "finished"

{% if log_file is defined %}
Stop-Transcript
{% endif %}