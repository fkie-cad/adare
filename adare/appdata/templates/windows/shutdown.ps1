# import helper functions (Add-PathVariable, WriteLog, Write-Status, ...)
. "{{ scripts_directory }}\helperfunctions.ps1"

{% if log_file is defined %}
Start-Transcript -Path "{{ log_file }}"
{% endif %}

# write --- SHUTDOWN --- to log
Write-Host "--- SHUTDOWN ---"

{% if log_file is defined %}
Stop-Transcript
{% endif %}
