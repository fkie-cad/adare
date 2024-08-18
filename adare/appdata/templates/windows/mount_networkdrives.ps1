. "{{ scripts_directory }}\helperfunctions.ps1"

{% if log_file is defined %}
Start-Transcript -Path "{{ log_file }}"
{% endif %}

StartStage "mount_networkdrives"

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
EndStage "mount_networkdrives"

{% if log_file is defined %}
Stop-Transcript
{% endif %}