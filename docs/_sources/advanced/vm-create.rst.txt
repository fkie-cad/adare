********************
Create an ADARE VM  
********************


This guide shows you how to set up a virtual machine that's compatible with ADARE. You'll need to create a custom VM if:

- None of the provided VMs have the OS/distribution you need
- You need specific software pre-installed
- You want a customized forensic analysis environment

Once configured, export the VM as an ``.ova`` or ``.ovf`` file in **OVF 1.0 format**.
At the moment, ADARE only supports VirtualBox VMs but it is planned to support Qemu/KVM in the future.


General Guideline
=================
There are two options for creating your own ADARE-compatible VM:
1. **Start from scratch:** Create a new VM with a minimal OS installation and set it up as explained in TODO.
2. **Modify an existing VM:** Take one of the provided ADARE VMs and customize it by e.g. installing additional software as explained in TODO



Extend
======

VirtualBox
----------




Create
======






VirtualBox Configuration Requirements
=====================================

- Disable all that can create popups as far as possible (like update notifications etc., automatic updates, error reporting, etc.)
- Disable screen lock and sleep mode if possible

Windows Setup
=============

User Account Configuration
--------------------------

- Create a user account with:

  - **Username:** ``adare``
  - **Password:** ``adare``

- Enable **autologin** so the VM boots directly into the ``adare`` user's desktop.

Additional Configuration
------------------------

1. **Disable User Account Control (UAC):**

   - Go to Control Panel → ``User Accounts`` → ``User Accounts`` → ``Change User Account Control settings``
   - Set the slider to the bottom (``Never notify``)

2. **Enable Developer Mode:**

   - In Windows Settings, search for ``For Developers``
   - Toggle the switch to enable Developer Mode
   - This is required to set up shared directories properly

3. **Configure Windows Defender Firewall:**

   a. Press ``Win + R``, type ``wf.msc``, and press Enter
   
   b. In the left panel, right-click **Windows Defender Firewall with Advanced Security on Local Computer** → **Properties**
   
   c. For each profile tab (**Domain Profile**, **Private Profile**, and **Public Profile**), configure:
   
      - **Inbound connections:** Allow
      - **Outbound connections:** Allow (default)
   
   d. Click **Apply** and then **OK**

4. **Apply Changes:**

   - Perform a clean shutdown to apply all security changes

Required Software Installation
------------------------------

Install the following software:

- **VirtualBox Guest Additions**
- **Python 3.9**

  - Download and install from `python.org <https://www.python.org/downloads/>`_
  - Ensure Python is added to PATH during installation

- **Poetry** (Python package manager)

  Install using the official installer:

  .. code-block:: powershell

     # Install Poetry
     (Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | python -

  Add Poetry to PATH permanently:

  .. code-block:: powershell

     # Add Poetry to PATH
     $poetryPath = "$env:APPDATA\Python\Scripts"
     [Environment]::SetEnvironmentVariable("Path", $env:Path + ";$poetryPath", "User")

  After installation, restart your PowerShell session and verify:

  .. code-block:: powershell

     poetry --version
  

Linux Setup
===========

Base Configuration (all environments)
-------------------------------------

- Create a user account with:

  - **Username:** ``adare``
  - **Password:** ``adare``

- Enable **autologin** so the VM boots directly into the ``adare`` user's desktop.

  - **Important:** autologin must start an **X11 session** (not Wayland). (e.g sudo nano /etc/gdm3/custom.conf -> uncomment: WaylandEnable=false)

- Enable passwordless sudo for the ``adare`` user by adding the following line to the sudoers file at the end (edit with ``sudo visudo``):

  ``adare ALL=(ALL) NOPASSWD:ALL``

- Install:
  - Miniforge3

    - Download Install script: ``cd /tmp && wget https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh``
    - Install: ``cd /tmp && bash Miniforge3-Linux-x86_64.sh -b -p /home/adare/.miniforge3`` (install into /home/adare/.miniforge3 instead of /home/adare/miniforge3)
    - Create a conda environment with Python 3.10: ``conda create -n pyadare python=3.10``

  - VirtualBox Guest Additions
  - to be ready for future updates also install:
    - for x11: maim (for screenshots)
    - for wayland: grim (for screenshots) + ydotool (for mouse/keyboard control)


Desktop Environment–Specific Setup
----------------------------------

GNOME/KDE
~~~~~~~~~

- Install:

  - ``gnome-screenshot``

- Configure Seahorse (keyring) to unlock automatically on login by setting an empty password.
- Disable Auto Updates/Notifications:
  - GNOME: ``sudo systemctl stop unattended-upgrades`` and ``sudo systemctl disable unattended-upgrades``


Other Desktop Environments
~~~~~~~~~~~~~~~~~~~~~~~~~~

- Not tested so far. Confirm PyAutoGUI can make screenshots and control the mouse and keyboard.


*************************************************
Installing ADARE Guest Agent (adarevm & adarelib)
*************************************************

Overview
========

The ADARE guest agent consists of two packages:

- **adarevm**: Guest agent that runs inside the VM and executes playbook actions
- **adarelib**: Shared library providing test functions and utilities

.. note::

   **Manual installation is optional.** ADARE automatically installs/updates the agent during experiment runs. Preinstalling saves 10-30 seconds per experiment.

Installation Methods
====================

Choose the method that matches your VM setup:

Windows with Conda (Miniforge)
-------------------------------

Install using pip in the ``pyadare`` conda environment:

.. code-block:: powershell

   # First, mount the shared folder if not already mounted
   net use Z: \\vboxsvr\adare\wheels

   # Install wheels (PowerShell requires explicit wildcard expansion)
   %USERPROFILE%\.miniforge3\Scripts\conda.exe run -n pyadare pip install --force-reinstall @(Get-ChildItem Z:\wheels\*.whl | Select-Object -ExpandProperty FullName)

Windows with Poetry
-------------------

Install using system pip:

.. code-block:: powershell

   # First, mount the shared folder if not already mounted
   net use Z: \\vboxsvr\adare\wheels

   # Install wheels (PowerShell requires explicit wildcard expansion)
   pip install --force-reinstall @(Get-ChildItem Z:\wheels\*.whl | Select-Object -ExpandProperty FullName)

Linux with Conda (Miniforge)
-----------------------------

Install using pip in the ``pyadare`` conda environment:

.. code-block:: bash

   /home/adare/.miniforge3/bin/conda run -n pyadare pip install --break-system-packages /adare/app/wheels/*.whl

Linux with Poetry
-----------------

Install using system pip:

.. code-block:: bash

   pip install --break-system-packages /adare/app/wheels/*.whl

.. note::

   Ubuntu 24.04+ requires the ``--break-system-packages`` flag due to PEP 668.
   This is safe in ADARE's isolated VM environment.

Verification
============

Verify the installation by checking package versions:

.. code-block:: bash

   # For Conda (Windows)
   %USERPROFILE%\.miniforge3\Scripts\conda.exe run -n pyadare pip show adarevm adarelib

   # For Conda (Linux)
   /home/adare/.miniforge3/bin/conda run -n pyadare pip show adarevm adarelib

   # For Poetry (Windows/Linux)
   pip show adarevm adarelib

Expected output:

.. code-block:: text

   Name: adarevm
   Version: 0.1.0
   ...

   Name: adarelib
   Version: 0.1.0
   ...

.. important::

   - Wheels are provided automatically by the ADARE host in the shared folder
   - Windows: Mount as ``Z:\wheels`` using ``net use Z: \\vboxsvr\adare\wheels``
   - Linux: Automatically available at ``/adare/app/wheels/``
   - The shared folder is only accessible during experiment runs
   - ADARE automatically detects version mismatches and reinstalls when needed