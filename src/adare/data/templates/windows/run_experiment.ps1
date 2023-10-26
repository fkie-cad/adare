. "{{ scripts_directory }}/helperfunctions.ps1"

Start-Transcript "{{ log_directory }}/run_experiment.log"

Add-PathVariable '{{ additional_tool_directory }}'

pip3 install '{{ project_script_directory }}/GUIAutomation/' 2>&1 | WriteLog
Write-Status("INSTALL_gui")
pip3 install '{{ project_script_directory }}/ParseAndTest/' 2>&1 | WriteLog
Write-Status("INSTALL_parseandtest")

#guiautomation --logfile '{{ logfolder }}/gui.log' run --experimentlog '{{ logfolder }}/experiment.log' '{{ gui_experiment }}' '{{ img_directory }}' '{{ tessdata_directory }}' 2>&1 | WriteLog
py '{{ experiment_file }}' '{{ experiment_config_file }}'
Write-Status("RUN_gui")

$resultfolder = "{{ result_directory }}"
If(!(test-path $resultfolder))
{
    New-Item -ItemType Directory -Path $resultfolder 2>&1 | WriteLog
}

Start-Sleep -s 30

parseandtest '{{ inputfile }}' '{{ outputfile }}' '{{ log_directory }}/status.csv' --logfile '{{ log_directory }}/parseandtest.log' 2>&1 | WriteLog
Write-Status("RUN_parseandtest")

Stop-Transcript