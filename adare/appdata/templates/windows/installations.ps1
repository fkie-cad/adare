. "{{ scripts_directory }}\helperfunctions.ps1"

StartStage "installations"
Start-Transcript  "{{ log_directory }}/postsetup_installations.log"

{% for installationline in installations %}
# {{ installationline.0 }}: {{ installationline.1 }}
{{ installationline.2 }} 2>&1 | WriteLog
StageMessage "installations" "{{ installationline.2 }}"
checkExitCode "installations"
{% endfor %}

Stop-Transcript
EndStage "installations" "finished"