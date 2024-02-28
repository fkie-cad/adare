# import helper functions (Add-PathVariable, WriteLog, Write-Status, ...)
. "{{ script_directory }}/helperfunctions.ps1"

# start logging
Start-Transcript "{{ log_directory }}/run.log"

# add different directories to the PATH (e.g. tools used by adarevm)
{% for path in path_directories %}
Add-PathVariable "{{ path }}"
{% endfor %}

# goto the directory of adarevm and install it with poetry
cd "{{ adarevm }}"
poetry install
Write-Status("InstallAdarevm")

adarevm '{{ experiment_config_file }}'
Write-Status("RunAdarevm")

Stop-Transcript