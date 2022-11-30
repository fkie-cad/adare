Start-Transcript  "{{logfolder}}/postsetup_installations.log"

function WriteLog
{
    Param ([string]$LogString)
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

{% for installationline in installations %}
# {{ installationline.0 }}: {{ installationline.1 }}
{{ installationline.2 }} 2>&1 | WriteLog
{% endfor %}

Stop-Transcript