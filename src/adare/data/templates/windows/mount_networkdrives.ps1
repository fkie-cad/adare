Start-Transcript {{logfolder}}/mount_networkdrives.log

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

{% if share %}
New-ItemProperty HKLM:\SOFTWARE\Microsoft\ClientForNFS\CurrentVersion\Default -Name AnonymousUID -Value 1000 -PropertyType "DWord" 2>&1 | WriteLog
New-ItemProperty HKLM:\SOFTWARE\Microsoft\ClientForNFS\CurrentVersion\Default -Name AnonymousGID -Value 1000  -PropertyType "DWord" 2>&1 | WriteLog
Enable-WindowsOptionalFeature -FeatureName ServicesForNFS-ClientOnly, ClientForNFS-Infrastructure -Online -NoRestart 2>&1 | WriteLog
{% else %}
Write-Host 'no share provided'
{% endif %}

{% for s in share %}
{{ s.command }} 2>&1 | WriteLog
{% endfor %}
Stop-Transcript