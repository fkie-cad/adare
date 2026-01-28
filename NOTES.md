Since it's ext4, we can rule out the 4GB file limit and basic permission metadata issues common with FAT32. However, the fact that it consistently fails right at the 8.4GB mark (just after the RAM dump finishes) points toward a subtle I/O bottleneck or a security policy blocking the finalization of the file.

Here are the likely reasons an ext4 mount on an external drive would fail at the very end:
1. The "Final Sync" Timeout

When libvirt finishes streaming the RAM data, it issues a "flush" to the disk. External drives (especially those connected via USB) often have high latency or slower controllers.

    The Problem: The OS has cached the write in system memory, but the physical drive hasn't caught up. If the drive takes too long to respond to the final "close" command, libvirt may assume the I/O operation has hung and kill the process.

    Why it looks like 8.4GB: The RAM is written, the metadata is added, and the failure occurs during the final handshake to release the file handle.

How to Fix This

Try these steps in order of ease:
A. Increase the Timeout / Disable Caching

You can tell libvirt to be less aggressive with its I/O. Edit /etc/libvirt/qemu.conf and look for (or add):
Ini, TOML

# Avoid using O_DIRECT (which can be finicky on some external mounts)
save_image_format = "raw"
# If you want to compress it (might avoid the size issue entirely)
# save_image_format = "lzop" 

After changing this, restart the service: sudo systemctl restart libvirtd