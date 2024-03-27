# Run this script with administrative privileges

# Disable Hibernation
Write-Host "Disabling hibernation..."
powercfg -h off

# Clean temporary files using Disk Cleanup. This may require manual intervention or can be automated with sageset/sagerun
Write-Host "Cleaning temporary files..."
cleanmgr /sagerun:1

Write-Host "Clean up complete. You can now shut down the VM and use your virtualization software's tools to compact the disk."


