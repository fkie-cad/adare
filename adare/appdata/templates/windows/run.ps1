# import helper functions (Add-PathVariable, WriteLog, Write-Status, ...)
. "{{ script_directory }}/helperfunctions.ps1"

StartStage "run_experiment"
# start logging
Start-Transcript "{{ log_directory }}/run.log"

# add different directories to the PATH (e.g. tools used by adarevm)
{% for path in path_directories %}
Add-PathVariable "{{ path }}"
{% endfor %}

# goto the directory of adarevm and install it with poetry
cd "{{ adarevm }}"
poetry install
poetry update adarelib

# get path to adarevm executable
$adarevmExecutable = $(poetry run where adarevm | Where-Object { $_ -like "*.cmd" })
# add to the PATH of the session
Add-PathVariable (Split-Path $adarevmExecutable)

adarevm '{{ experiment_config_file }}'

Stop-Transcript
EndStage "run_experiment"