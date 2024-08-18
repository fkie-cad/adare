. "{{ scripts_directory }}\helperfunctions.ps1"

{% if log_file is defined %}
Start-Transcript -Path "{{ log_file }}"
{% endif %}

StartStage "installations"

{% for installationline in installations %}
# {{ installationline.0 }}: {{ installationline.1 }}
{{ installationline.2 }} 2>&1 | WriteLog
StageMessage "installations" "{{ installationline.2 }}"
checkExitCode "installations"
{% endfor %}

Stop-Transcript
EndStage "installations" "finished"

{% if log_file is defined %}
Stop-Transcript
{% endif %}