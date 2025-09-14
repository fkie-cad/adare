Windows
===============

.. role:: status-dev
   :class: status-dev

:Status: :status-dev:`● Development`
:Functions: 2
:Category: Windows System Validation

The **Windows** testset provides Windows-specific system testing capabilities for ADARE experiments. This testset focuses on Windows Registry operations, including key existence validation and registry value verification.

Overview
--------

The Windows testset enables validation of Windows system state and configuration through Registry access. It includes functions to check for registry key existence and validate registry values with support for different data types (strings, DWORD, etc.).

Test Functions
--------------

.. csv-table::
   :file: ../../_static/tables/testfunctions_windows.csv
   :widths: 20, 10, 40, 30
   :header-rows: 1
   :class: sdtable
   :name: windows-functions-table



.. toctree::
   :maxdepth: 1
   :hidden:

   registry_key_exists
   registry_value_matches