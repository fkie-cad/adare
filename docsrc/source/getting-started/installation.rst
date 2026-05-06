************
Installation
************

ADARE drives one of two hypervisors per environment — **QEMU** (recommended)
or **VirtualBox** — and you only ever need to install one. ADARE runs on Linux
and macOS hosts; Windows host support is **experimental**. ADARE is officially
tested only on Ubuntu (Linux) and macOS hosts. See
:ref:`choose-hypervisor` below to pick the right backend for your host.

System Requirements
*******************

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
     - Linux (tested on Ubuntu 22.04) or macOS 13+; Windows 10+ is experimental


.. _choose-hypervisor:

Choose Your Hypervisor
**********************

ADARE drives one of two hypervisors per environment, and you only need to
install one. The choice is per-environment: set ``hypervisor: qemu`` or
``hypervisor: virtualbox`` in the environment YAML to override the project
default. You can switch later without reinstalling ADARE.

.. list-table::
   :widths: 35 20 25
   :header-rows: 1

   * - Host OS
     - Recommended
     - Also works
   * - Ubuntu / Linux (x86_64)
     - QEMU
     - VirtualBox
   * - macOS Intel
     - QEMU
     - VirtualBox
   * - macOS Apple Silicon (arm64)
     - QEMU
     - — (VirtualBox not viable)
   * - Windows 10/11 (experimental)
     - VirtualBox
     - —

Pick **QEMU** if:

- You're on Apple Silicon (ARM) — VirtualBox isn't a viable backend there.
- You want VirtioFS (Linux hosts) or HVF/KVM acceleration for fast
  host-to-guest file sharing and near-native VM performance.
- You want the recommended/primary backend for new projects.

Pick **VirtualBox** if:

- You're on Windows — it's the only supported backend for Windows hosts.
- You want a GUI-managed VM you can also poke at outside ADARE.
- You already have it installed and don't need QEMU's extras.

After installing the :ref:`Common Prerequisites <common-prereqs>` below, jump
to either :ref:`hypervisor-virtualbox` or :ref:`hypervisor-qemu` — you only
need to read one.


.. _common-prereqs:

Common Prerequisites
********************

These are required regardless of which hypervisor you choose.

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

3. **Make** and **git**

   Make sure to have ``make`` and ``git`` installed via your package manager.


.. _hypervisor-virtualbox:

Hypervisor: VirtualBox
**********************

Download and install from `virtualbox.org <https://www.virtualbox.org/>`_

.. note::
   ADARE supports **Windows and Ubuntu guest VMs only** under VirtualBox.
   macOS guest VMs are not supported.

.. note::
   On Windows, ensure **Hyper-V is disabled** as it conflicts with VirtualBox:

   - Open "Turn Windows features on or off"
   - Uncheck "Hyper-V"
   - Restart your computer


.. _hypervisor-qemu:

Hypervisor: QEMU
****************

.. note::
   ADARE supports **Ubuntu and Windows guest VMs only** under QEMU.
   macOS guest VMs are not supported.

Install QEMU and libguestfs for your host:

**Ubuntu/Debian:**

.. code-block:: bash

   sudo apt update
   sudo apt install qemu-system-x86 qemu-utils python3-guestfs libguestfs-tools libvirt-dev

**Fedora/RHEL/CentOS:**

.. code-block:: bash

   sudo dnf install qemu-kvm qemu-img python3-libguestfs libguestfs-tools libvirt-devel

**Arch Linux:**

.. code-block:: bash

   sudo pacman -S qemu python-guestfs libguestfs libvirt

**macOS (Apple Silicon / ARM):**

.. code-block:: bash

   brew install qemu samba libvirt

.. note::
   ``libvirt-dev`` / ``libvirt-devel`` / ``libvirt`` provide the headers required
   to build the ``libvirt-python`` wheel that ``make install`` pulls in by default
   on Linux/macOS. Install the system package before running ``make install``,
   or use ``./adare/install/install.sh`` directly to skip QEMU extras entirely.

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


Install ADARE
*************

With prerequisites and your chosen hypervisor in place:

1. **Clone the repository**

   .. code-block:: bash

      git clone https://github.com/fkie-cad/adare.git
      cd adare

2. **Install ADARE**

   .. code-block:: bash

      make install

   This sets up a Python virtual environment, installs all dependencies via
   uv, installs the ADARE command-line tools, and configures the development
   environment.

   On **Linux and macOS**, ``make install`` includes QEMU support by default
   (it pulls in the ``libvirt-python`` extra). Make sure the libvirt
   development headers listed under :ref:`hypervisor-qemu` are installed
   first, otherwise the wheel build will fail. If you only need VirtualBox
   and want to skip QEMU extras, run the installer directly:

   .. code-block:: bash

      ./adare/install/install.sh

   On **Windows**, ``make install`` runs the PowerShell installer and does
   **not** install QEMU extras (Windows host support is experimental and
   VirtualBox is the supported backend there).

   .. note::
      ``make install-qemu`` is kept as a backwards-compatible alias for
      ``make install`` on Linux/macOS.

3. **Verify the install**

   .. code-block:: bash

      adare --version

   You should see output similar to ``ADARE version 0.1.0``.

4. **Test your setup**

   .. code-block:: bash

      adare --help

   This should display the main help menu without errors.


Tested Configurations
*********************

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
   * - **Ubuntu host**
     - 22.04
     - Recommended
   * - **macOS host**
     - 13+
     - Tested
   * - **Windows host**
     - 10+
     - Experimental

.. note::
   While later versions should work, earlier versions (especially Python < 3.10) are not supported due to language features used by ADARE.

Next Steps
**********

After successful installation:

1. **Quick Start**: Follow the :doc:`tutorial` guide
2. **Learn the Basics**: Explore :doc:`/guide/projects`, :doc:`/guide/environments`, and :doc:`/guide/experiments`
