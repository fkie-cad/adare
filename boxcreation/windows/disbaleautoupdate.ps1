# PowerShell script to disable Windows Update permanently

# Stop the Windows Update service
Stop-Service -Name wuauserv -Force

# Set the Startup Type of the Windows Update service to Disabled
Set-Service -Name wuauserv -StartupType Disabled

# Optionally, disable related services like BITS (Background Intelligent Transfer Service) and the Update Orchestrator Service
Stop-Service -Name bits -Force
Set-Service -Name bits -StartupType Disabled

Stop-Service -Name UsoSvc -Force
Set-Service -Name UsoSvc -StartupType Disabled

Write-Host "Windows Update services have been disabled."