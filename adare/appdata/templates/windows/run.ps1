# import helper functions (Add-PathVariable, WriteLog, Write-Status, ...)
. "{{ scripts_directory }}/helperfunctions.ps1"

{% if log_file is defined %}
Start-Transcript -Path "{{ log_file }}"
{% endif %}

# setup experiment
StartStage "experiment_setup"

# add different directories to the PATH (e.g. tools used by adarevm)
{% for path in path_directories %}
Add-PathVariable "{{ path }}"
checkExitCode "experiment_setup"
{% endfor %}

# goto the directory of adarevm and install it with poetry
cd "{{ adarevm }}"
poetry install
checkExitCode "experiment_setup"

poetry update adarelib
checkExitCode "experiment_setup"

# get path to adarevm executable
$adarevmExecutable = $(poetry run where adarevm | Where-Object { $_ -like "*.cmd" })
StageMessage "experiment_setup" "adarevm executable: $adarevmExecutable"
checkExitCode "experiment_setup"
# add to the PATH of the session
Add-PathVariable (Split-Path $adarevmExecutable)
checkExitCode "experiment_setup"

EndStage "experiment_setup" "finished"

# run the experiment
StartStage "experiment_run"

adarevm '{{ experiment_config_file }}'
checkExitCode "experiment_run"

EndStage "experiment_run" "finished"

{% if log_file is defined %}
Stop-Transcript
{% endif %}