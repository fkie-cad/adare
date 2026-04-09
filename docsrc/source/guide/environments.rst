************
Environments
************

Environments define virtual machine configurations for running experiments.

Environment Configuration
**************************

Environments are defined using YAML files with these key fields:

.. code-block:: yaml

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

VM Storage Options
******************

By default, when you load an environment with a VM, ADARE copies the VM file (OVA) to managed
storage at ``~/.adare/state/vms/``. This ensures the VM is protected and always available for
experiments.

However, for very large VM files (e.g., >50GB), you may want to avoid duplicating the file to
save disk space.

Using ``--no-copy`` Flag
========================

The ``--no-copy`` flag tells ADARE to reference the VM at its original location instead of
copying it:

.. code-block:: bash

   adare environment load my-environment.yml --no-copy

.. important::

   When using ``--no-copy``, the original VM file **must remain at its current location**.
   Do not move or delete it, or your experiments will fail!

**When to use ``--no-copy``:**

* You have very large VM files (50GB+) and limited disk space
* You want to keep VMs on external storage or network drives
* You are certain the VM file location won't change

**What happens if you move the file:**

If the VM file is moved or deleted after loading with ``--no-copy``, you'll see an error when
trying to run experiments:

.. code-block:: text

   External VM file not found: /path/to/original/vm.ova
   This VM was loaded with --no-copy and the original file is missing.

**Note:** The ``--no-copy`` flag only works with local file paths. If your environment specifies
a URL for the VM, the file will always be downloaded to managed storage.

The environment configuration determines what VM is used and any setup commands that run before experiments execute.