. "{{ scripts_directory }}\helperfunctions.ps1"

StartStage "mount_networkdrives"
Start-Transcript {{ log_directory }}/mount_networkdrives.log

{% if share %}
{% if share.type == 'NFSShare' %}
New-ItemProperty HKLM:\SOFTWARE\Microsoft\ClientForNFS\CurrentVersion\Default -Name AnonymousUID -Value 1000 -PropertyType "DWord" 2>&1 | WriteLog
Enable-WindowsOptionalFeature -FeatureName ServicesForNFS-ClientOnly, ClientForNFS-Infrastructure -Online -NoRestart 2>&1 | WriteLog
{% endif %}
{% endif %}

{% if share %}
{% else %}
Write-Host 'no share provided'
{% endif %}

{% for s in share %}
{{ s.command }} 2>&1 | WriteLog
{% endfor %}
Stop-Transcript
EndStage "mount_networkdrives"