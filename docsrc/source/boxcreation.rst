creation of an vagrant box
=====================================

there a different methods in order to create a new vagrant box:
#. create a box using another vagrant box as base
#. create a box using an virtual box vm as base
#. create a box using packer


it is important to preinstall the following tools in your boxes because these are required in order to use all features like (network drives) and let your vms run faster:
- NFS client (nfs-common for linux)
- SMB cleint (smbclient for linux)
- bash (for linux) [make it also your default shell]
- chocolatey (for windows)