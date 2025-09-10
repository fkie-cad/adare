**********************
Environment Management
**********************

Environments define virtual machine configurations for running experiments.

Environment Configuration
**************************

Environments are defined using YAML files with these key fields:

.. code-block:: yaml

   name: my-environment
   vm: "/path/to/vm.ova"
   os:
     os: "Windows"
     platform: "windows"  # or "linux"
     distribution: "Pro"
     version: "11"
     architecture: "x64"
   
   postsetupinstallations:
     - name: "Install Tool"
       command: "setup.exe /S"
       description: "Install custom tool"
       shell: false

   tags: ["windows", "forensics"]
   description: "Windows 11 forensics environment"

Required Fields
===============

- **name**: Environment identifier
- **vm**: Path to VM image file (.ova)
- **os.platform**: Either "windows" or "linux"

Optional Fields
===============

- **postsetupinstallations**: Commands to run after VM boot
- **tags**: Labels for organization
- **description**: Environment purpose
- **vagrantbox**: Legacy Vagrant box (backward compatibility)

Managing Environments
*********************

.. code-block:: bash

   # Load environment from config file
   adare environment load config.yml
   
   # List environments
   adare environment list
   
   # Delete environment
   adare environment delete my-environment

The environment configuration determines what VM is used and any setup commands that run before experiments execute.