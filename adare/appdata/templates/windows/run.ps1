# import helper functions (Add-PathVariable, WriteLog, Write-Status, ...)
. "{{ scripts_directory }}/helperfunctions.ps1"

StartStage "experiment"

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

EndStage "experiment"