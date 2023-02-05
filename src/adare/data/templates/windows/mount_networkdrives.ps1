. "{{ scripts_directory }}\helperfunctions.ps1"

Start-Transcript {{ log_directory }}/mount_networkdrives.log

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