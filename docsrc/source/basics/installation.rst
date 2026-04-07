************
Installation
************

This guide will walk you through installing ADARE on your system. ADARE supports Linux, macOS, and Windows platforms.

Prerequisites
*************

Before installing ADARE, ensure you have the following prerequisites:

System Requirements
===================

.. list-table::
   :widths: 20 40
   :header-rows: 1

   * - Component
     - Minimum
   * - **RAM**
     - 16 GB or more
   * - **Storage**
     - 50 GB (for windows VM more)
   * - **CPU**
     - 6+ cores with virtualization support
   * - **OS**
     - Ubuntu, Windows 10+, macOS 13+


Required Software
=================

1. **Python 3.10 or higher**

   Check your Python version:

   .. code-block:: bash

      python3 --version

   If below 3.10 or not installed, download and install from `python.org <https://www.python.org/downloads/>`_ or use your package manager.

   **Windows Installation**

   For Windows users, you can install Python using PowerShell:

   .. code-block:: powershell

      # Download Python installer
      $pythonInstaller = "https://www.python.org/ftp/python/3.12.0/python-3.12.0-amd64.exe"
      $installerPath = "$env:TEMP\python-installer.exe"
      Invoke-WebRequest $pythonInstaller -OutFile $installerPath

      # Install Python (add to PATH, install pip)
      Start-Process -FilePath $installerPath -ArgumentList "/quiet", "InstallAllUsers=1", "PrependPath=1" -Wait

   After installation, restart your PowerShell session and verify:

   .. code-block:: powershell

      python --version

2. **uv** (Python package manager)

   Install using the official installer:

   .. code-block:: bash

      curl -LsSf https://astral.sh/uv/install.sh | sh

   **Windows:**

   .. code-block:: powershell

      powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

   After installation, restart your shell and verify:

   .. code-block:: bash

      uv --version

3. **VirtualBox**

   Download and install from `virtualbox.org <https://www.virtualbox.org/>`_

   .. note::
      On Windows, ensure **Hyper-V is disabled** as it conflicts with VirtualBox:

      - Open "Turn Windows features on or off"
      - Uncheck "Hyper-V"
      - Restart your computer

4. **QEMU** (optional - for QEMU hypervisor support)

   If you plan to use the QEMU hypervisor instead of VirtualBox, you need to install QEMU and libguestfs:

   **Ubuntu/Debian:**

   .. code-block:: bash

      sudo apt update
      sudo apt install qemu-system-x86 qemu-utils python3-guestfs libguestfs-tools

   **Fedora/RHEL/CentOS:**

   .. code-block:: bash

      sudo dnf install qemu-kvm qemu-img python3-libguestfs libguestfs-tools

   **Arch Linux:**

   .. code-block:: bash

      sudo pacman -S qemu python-guestfs libguestfs

   **macOS (Apple Silicon / ARM):**

   .. code-block:: bash

      brew install qemu samba

   QEMU on macOS (Homebrew) has the smbd path hardcoded to ``/opt/local/sbin/smbd``
   (a MacPorts path). You must create a symlink so QEMU can find Homebrew's samba:

   .. code-block:: bash

      sudo mkdir -p /opt/local/sbin
      sudo ln -s /opt/homebrew/opt/samba/sbin/samba-dot-org-smbd /opt/local/sbin/smbd

   .. note::
      On macOS, virtiofsd is not available. ADARE uses QEMU's built-in SMB sharing
      (via ``samba``) to mount host directories in the guest VM. This provides the
      same shared-directory experience as virtiofs on Linux. If ``samba`` is not
      installed or the symlink above is missing, ADARE falls back to QGA file
      transfer (slower, but functional). ADARE will detect the mismatch and print
      the exact symlink command needed.

   .. note::
      The libguestfs tools are required for file operations with stopped QEMU VMs.

5. **Make** (build tool)

   Make sure to have `make` installed.

Installation Steps
******************

1. Clone the Repository
=======================

.. code-block:: bash

   git clone https://github.com/fkie-cad/adare.git
   cd adare

2. Install ADARE
================

Run the installation script:

.. code-block:: bash

   make install

This will:

- Set up a Python virtual environment
- Install all dependencies via uv
- Install ADARE command-line tools
- Configure the development environment

3. Verify Installation
======================

Check that ADARE is installed correctly:

.. code-block:: bash

   adare --version

You should see output similar to:

.. code-block:: text

   ADARE version 0.1.0

4. Test Your Setup
==================

Run a quick system check:

.. code-block:: bash

   adare --help

This should display the main help menu without errors.


Tested Configurations
**********************

ADARE has been tested with the following software versions:

.. list-table::
   :widths: 25 30 20
   :header-rows: 1

   * - Software
     - Version
     - Platform
   * - **Python**
     - 3.13.2
     - All platforms
   * - **uv**
     - 0.7+
     - All platforms
   * - **VirtualBox**
     - 7.0.26+
     - All platforms
   * - **Ubuntu**
     - 22.04
     - Recommended

.. note::
   While later versions should work, earlier versions (especially Python < 3.10) are not supported due to language features used by ADARE.

Next Steps
**********

After successful installation:

1. **Quick Start**: Follow the :doc:`tutorial` guide
2. **Learn the Basics**: Explore :doc:`projects`, :doc:`environments`, and :doc:`experiments`