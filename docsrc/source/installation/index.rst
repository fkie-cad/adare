******************
Installation Guide
******************

This guide will walk you through installing ADARE on your system. ADARE supports Linux, macOS, and Windows platforms.

Prerequisites
*************

Before installing ADARE, ensure you have the following prerequisites:

System Requirements
===================

.. list-table::
   :widths: 20 40 40
   :header-rows: 1

   * - Component
     - Minimum
     - Recommended
   * - **RAM**
     - 8 GB
     - 16 GB or more (for running VMs)
   * - **Storage**
     - 50 GB free
     - 200 GB+ (for VM images and results)
   * - **CPU**
     - 4 cores
     - 8+ cores with virtualization support
   * - **OS**
     - Linux, macOS, Windows 10+
     - Linux (Ubuntu 20.04+) or macOS

Required Software
=================

1. **Python 3.10 or higher**
   
   Check your Python version:
   
   .. code-block:: bash
   
      python3 --version
   
   If you need to install Python 3.10+:
   
   - **Ubuntu/Debian**: ``sudo apt update && sudo apt install python3.10 python3.10-venv``
   - **macOS**: Use Homebrew: ``brew install python@3.10``
   - **Windows**: Download from `python.org <https://www.python.org/downloads/>`_

2. **Poetry** (Python package manager)
   
   Install using the official installer:
   
   .. code-block:: bash
   
      curl -sSL https://install.python-poetry.org | python3 -

3. **VirtualBox**
   
   Download and install from `virtualbox.org <https://www.virtualbox.org/>`_
   
   .. note::
      On Windows, ensure **Hyper-V is disabled** as it conflicts with VirtualBox:
      
      - Open "Turn Windows features on or off"
      - Uncheck "Hyper-V" 
      - Restart your computer

4. **Make** (build tool)
   
   - **Ubuntu/Debian**: ``sudo apt install build-essential``
   - **macOS**: Install Xcode Command Line Tools: ``xcode-select --install``
   - **Windows**: Use WSL2 or install via chocolatey: ``choco install make``

Installation Steps
******************

1. Clone the Repository
=======================

.. code-block:: bash

   git clone https://github.com/fkie-cad/Adare.git
   cd Adare

2. Install ADARE
================

Run the installation script:

.. code-block:: bash

   make install

This will:

- Set up a Python virtual environment
- Install all dependencies via Poetry
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

   adare help
   
This should display the main help menu without errors.

Troubleshooting Installation
****************************

VirtualBox Issues
=================

**Error: VirtualBox not found**
   Ensure VirtualBox is installed and the ``VBoxManage`` command is available in your PATH.

**Error: VM creation fails**
   - Check that virtualization is enabled in your BIOS/UEFI
   - On Windows, ensure Hyper-V is disabled
   - Verify you have sufficient RAM and disk space

Python Issues
=============

**Error: Python version too old**
   ADARE requires Python 3.10+. Install a newer version or use pyenv to manage multiple Python versions.

**Error: Poetry not found**
   Ensure Poetry is installed and added to your PATH. You may need to restart your terminal after installation.

Permission Issues
=================

**Error: Permission denied during installation**
   - On Linux/macOS: Don't use ``sudo`` with the install command
   - Ensure you have write permissions to the installation directory
   - Check that your user has VirtualBox permissions

Getting Help
============

If you encounter issues:

1. Check the :doc:`../troubleshooting/index` section
2. Search existing issues on `GitHub <https://github.com/fkie-cad/Adare/issues>`_
3. Create a new issue with your system details and error messages

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
     - 3.10.2, 3.11.x, 3.12.x
     - All platforms
   * - **Poetry**
     - 1.8.2+
     - All platforms  
   * - **VirtualBox**
     - 7.0.26+
     - All platforms
   * - **Ubuntu**
     - 20.04, 22.04, 24.04
     - Recommended
   * - **macOS**
     - 12.0+ (Monterey)
     - Supported
   * - **Windows**
     - 10, 11
     - Supported

.. note::
   While later versions should work, earlier versions (especially Python < 3.10) are not supported due to language features used by ADARE.

Next Steps
**********

After successful installation:

1. **Quick Start**: Follow the :doc:`../quickstart/index` guide
2. **First Experiment**: Create your :doc:`../quickstart/first-experiment`
3. **User Guide**: Learn about :doc:`../user-guide/index` for daily usage

Development Installation
************************

If you plan to contribute to ADARE or need the development environment:

.. code-block:: bash

   # Clone with development branch
   git clone -b dev https://github.com/fkie-cad/Adare.git
   cd Adare
   
   # Install in development mode
   make install-dev
   
   # Run tests to verify
   make test

This installs additional development dependencies and sets up pre-commit hooks.
