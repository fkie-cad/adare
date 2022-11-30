Start-Transcript "{{logfolder}}/run_experiment.log"

function WriteLog
{
    param ([string]$LogString)
    if($MyInvocation.ExpectingInput){
        $LogContent = $input
    }else{
        $LogContent = $LogString
    }
    $LogContent -Split "`r`n" | ForEach-Object {
        $Stamp = (Get-Date).toString("yyyy-MM-dd HH:mm:ss")
        $LogMessage = "[$Stamp]: $_"
        Write-host "$LogMessage"
    }
}

function Add-PathVariable {
    param (
        [string]$addPath
    )
    if($MyInvocation.ExpectingInput){
        $addPath = $input
    }
    if (Test-Path $addPath){
        $regexAddPath = [regex]::Escape($addPath)
        $arrPath = $env:Path -split ';' | Where-Object {$_ -notMatch "^$regexAddPath\\?"}
        $env:Path = ($arrPath + $addPath) -join ';'
    } else {
        Throw "'$addPath' is not a valid path."
    }
}

Add-PathVariable '/vagrant/externalprograms'

pip3 install /vagrant/scripts/GUIAutomation/ 2>&1 | WriteLog
pip3 install /vagrant/scripts/ParseAndTest/ 2>&1 | WriteLog

guiautomation --logfile {{ logfolder }}/gui.log run '{{ gui_scenario }}' 2>&1 | WriteLog

$resultfolder = "/vagrant/result/"
If(!(test-path $resultfolder))
{
    New-Item -ItemType Directory -Path $resultfolder 2>&1 | WriteLog
}

Start-Sleep -s 60

parseandtest {{ inputfile }} {{ outputfile }} --logfile {{ logfolder }}/parseandtest.log 2>&1 | WriteLog

Stop-Transcript