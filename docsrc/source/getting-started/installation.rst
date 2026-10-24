************
Installation
************

ADARE uses **QEMU** as its hypervisor on Linux and macOS hosts — that's the
recommended path and the rest of this page walks through it top-to-bottom.
**VirtualBox** is also supported and is the only option for Windows hosts; if
that's you, jump to :ref:`hypervisor-virtualbox` below.

.. _common-prereqs:

Step 1: Install Prerequisites
*****************************

These are required regardless of which hypervisor you use: **uv**, **make**,
and **git**. You do not need to install Python yourself: uv installs the
Python version ADARE needs (3.13) on first use.

.. tab-set::

   .. tab-item:: Linux

      .. tab-set::

         .. tab-item:: Ubuntu/Debian

            .. code-block:: bash

               sudo apt update
               sudo apt install make git
               curl -LsSf https://astral.sh/uv/install.sh | sh

         .. tab-item:: Fedora/RHEL

            .. code-block:: bash

               sudo dnf install make git
               curl -LsSf https://astral.sh/uv/install.sh | sh

         .. tab-item:: Arch

            .. code-block:: bash

               sudo pacman -S make git
               curl -LsSf https://astral.sh/uv/install.sh | sh

      After installing ``uv``, restart your shell so it appears on ``PATH``.

   .. tab-item:: macOS

      Install ``uv`` and the build tools (with Homebrew or MacPorts):

      .. code-block:: bash

         brew install make git
         curl -LsSf https://astral.sh/uv/install.sh | sh

      After installing ``uv``, restart your shell so it appears on ``PATH``.

   .. tab-item:: Windows

      Install ``uv`` from PowerShell:

      .. code-block:: powershell

         powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

      Install ``git`` (for example `Git for Windows <https://gitforwindows.org/>`_).
      ``make`` is optional on Windows: ``make install`` only runs the PowerShell
      installer, which you can also run directly (see below). Restart your
      shell, then verify:

      .. code-block:: powershell

         uv --version
         git --version


.. _hypervisor-qemu:

Step 2: Install QEMU
********************

.. note::
   QEMU is not supported on Windows hosts. If you're on Windows, skip ahead
   to :ref:`hypervisor-virtualbox`.

.. tab-set::

   .. tab-item:: Linux

      .. tab-set::

         .. tab-item:: Ubuntu/Debian

            .. code-block:: bash

               sudo apt update
               sudo apt install qemu-system-x86 qemu-utils python3-guestfs libguestfs-tools libvirt-dev

         .. tab-item:: Fedora/RHEL

            .. code-block:: bash

               sudo dnf install qemu-kvm qemu-img python3-libguestfs libguestfs-tools libvirt-devel

         .. tab-item:: Arch

            .. code-block:: bash

               sudo pacman -S qemu python-guestfs libguestfs libvirt

      .. note::
         ADARE supports **Ubuntu and Windows guest VMs only** under QEMU.
         macOS guest VMs are not supported.

      .. note::
         ``libvirt-dev`` / ``libvirt-devel`` / ``libvirt`` provide the headers
         required to build the ``libvirt-python`` wheel that ``make install``
         pulls in by default. Install the system package before running
         ``make install`` in Step 3.

      .. note::
         The libguestfs tools are required for file operations with stopped
         QEMU VMs.

   .. tab-item:: macOS

      On macOS, QEMU must be installed via **MacPorts**. The Homebrew build of
      QEMU has the ``smbd`` path hardcoded to ``/opt/local/sbin/smbd`` (a
      MacPorts path), so the MacPorts build is the supported way to get
      working SMB host-to-guest sharing out of the box.

      First, install MacPorts itself by following the official installer for
      your macOS version: `macports.org/install.php
      <https://www.macports.org/install.php>`_. After installation, restart
      your shell so ``/opt/local/bin`` is on ``PATH``, then verify:

      .. code-block:: bash

         port version

      Install QEMU and its samba/libvirt dependencies via MacPorts:

      .. code-block:: bash

         sudo port install qemu samba4 libvirt

      MacPorts installs samba's ``smbd`` at ``/opt/local/sbin/smbd``, which is
      exactly the path QEMU expects — no symlink needed.

      .. note::
         ADARE supports **Ubuntu and Windows guest VMs only** under QEMU.
         macOS guest VMs are not supported.

      .. note::
         On macOS, virtiofsd is not available. ADARE uses QEMU's built-in SMB
         sharing (via ``samba``) to mount host directories in the guest VM.
         This provides the same shared-directory experience as virtiofs on
         Linux. If ``samba`` is not installed at ``/opt/local/sbin/smbd``,
         ADARE falls back to QGA file transfer (slower, but functional).
         ADARE will detect the mismatch and print the exact command needed.


Step 3: Install ADARE
*********************

With prerequisites and QEMU in place, clone and install ADARE.

.. tab-set::

   .. tab-item:: Linux

      .. code-block:: bash

         git clone https://github.com/fkie-cad/adare.git
         cd adare
         make install

      ``make install`` installs the dependencies pinned in ``uv.lock`` into a
      virtual environment and puts the ADARE command-line tools on your PATH. It
      includes QEMU support by default (it pulls in the ``libvirt-python``
      extra), so make sure the libvirt development headers from Step 2 are
      installed first or the wheel build will fail.

      .. note::
         ``make install-qemu`` is kept as a backwards-compatible alias for
         ``make install`` on Linux/macOS.

   .. tab-item:: macOS

      .. code-block:: bash

         git clone https://github.com/fkie-cad/adare.git
         cd adare
         make install

      ``make install`` installs the dependencies pinned in ``uv.lock`` into a
      virtual environment and puts the ADARE command-line tools on your PATH. It
      includes QEMU support by default (it pulls in the ``libvirt-python``
      extra), so make sure ``libvirt`` is installed via MacPorts (Step 2) or
      the wheel build will fail.


Verify Installation
*******************

Check that ADARE is on your ``PATH``:

.. code-block:: bash

   adare --version

You should see output similar to ``ADARE version 0.1.0``. Then test the help
menu:

.. code-block:: bash

   adare --help

This should display the main help menu without errors.


Updating
********

After pulling a new version, refresh the dependencies, appdata, testfunctions
and database schema:

.. code-block:: bash

   git pull
   make update

On Windows, re-run ``install.ps1`` (or ``make update``). Both install exactly
the versions in ``uv.lock`` and stop with an error if a step fails. The
``adare`` command points into your clone's ``.venv``, so keep the clone where
you installed it.


.. _choose-hypervisor:
.. _hypervisor-virtualbox:

Alternative: VirtualBox
***********************

VirtualBox is a supported alternative to QEMU. Pick it if:

- You're on a **Windows host** — VirtualBox is the only supported backend
  there.
- You want a **GUI-managed VM** you can also poke at outside ADARE.
- You **already have VirtualBox installed** and don't need QEMU's extras
  (VirtioFS on Linux, HVF acceleration, SMB sharing on macOS).

The choice is per-environment: set ``hypervisor: virtualbox`` in the
environment YAML to override the project default. You can switch later
without reinstalling ADARE.

Install VirtualBox
==================

.. tab-set::

   .. tab-item:: Linux

      Download and install from
      `virtualbox.org <https://www.virtualbox.org/>`_.

      .. note::
         ADARE supports **Windows and Ubuntu guest VMs only** under
         VirtualBox. macOS guest VMs are not supported.

   .. tab-item:: Windows

      Download and install from
      `virtualbox.org <https://www.virtualbox.org/>`_.

      .. note::
         On Windows, ensure **Hyper-V is disabled** as it conflicts with
         VirtualBox:

         - Open "Turn Windows features on or off"
         - Uncheck "Hyper-V"
         - Restart your computer

      .. note::
         ADARE supports **Windows and Ubuntu guest VMs only** under
         VirtualBox. macOS guest VMs are not supported.

Install ADARE (VirtualBox-only)
===============================

.. tab-set::

   .. tab-item:: Linux

      If you only need VirtualBox and want to skip QEMU extras, run the
      installer directly instead of ``make install``:

      .. code-block:: bash

         git clone https://github.com/fkie-cad/adare.git
         cd adare
         ./adare/install/install.sh

   .. tab-item:: Windows

      .. code-block:: powershell

         git clone https://github.com/fkie-cad/adare.git
         cd adare
         powershell -ExecutionPolicy Bypass -File adare\install\install.ps1

      ``make install`` runs the same script if you have ``make``. It installs
      the dependencies pinned in ``uv.lock``, adds ADARE's ``.venv\Scripts``
      to your user ``PATH`` (open a new terminal afterwards), and sets up the
      appdata and database. It does **not** install QEMU extras (Windows host
      support is experimental and VirtualBox is the supported backend there).
      To update after a ``git pull``, run it again.


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
   The host side requires Python 3.13, which uv installs for you. Guest VMs
   need Python 3.10+ for the ADARE agent.


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


Next Steps
**********

After successful installation:

1. **Quick Start**: Follow the :doc:`tutorial` guide
2. **Learn the Basics**: Explore :doc:`/guide/projects`, :doc:`/guide/environments`, and :doc:`/guide/experiments`
