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
     - Ubuntu, Windows 10+


Required Software
=================

1. **Python 3.10 or higher**

   Check your Python version:

   .. code-block:: bash

      python3 --version

   If below 3.10 or not installed, download and install from `python.org <https://www.python.org/downloads/>`_ or use your package manager.

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
   * - **Poetry**
     - 1.8.2
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