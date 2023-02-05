. "{{ scripts_directory }}\helperfunctions.ps1"

Start-Transcript "{{ log_directory }}/run_experiment.log"

Add-PathVariable '/vagrant/externalprograms'

pip3 install /vagrant/scripts/GUIAutomation/ 2>&1 | WriteLog
Write-Status("INSTALL_gui")
pip3 install /vagrant/scripts/ParseAndTest/ 2>&1 | WriteLog
Write-Status("INSTALL_parseandtest")

guiautomation --logfile {{ logfolder }}/gui.log run '{{ gui_scenario }}' 2>&1 | WriteLog
Write-Status("RUN_gui")

$resultfolder = "{{ resultfolder }}"
If(!(test-path $resultfolder))
{
    New-Item -ItemType Directory -Path $resultfolder 2>&1 | WriteLog
}

Start-Sleep -s 30

parseandtest {{ inputfile }} {{ outputfile }} --logfile {{ logfolder }}/parseandtest.log 2>&1 | WriteLog
Write-Status("RUN_parseandtest")

Stop-Transcript