Linux
=============

.. role:: status-dev
   :class: status-dev

:Status: :status-dev:`● Development`
:Functions: 4
:Category: Linux System Validation

The **Linux** testset provides Linux-specific system testing capabilities for ADARE experiments. This testset focuses on systemd services, process monitoring, user account validation, and log file analysis on Linux systems.

Overview
--------

The Linux testset enables validation of Linux system state and configuration. It includes functions to check systemd service status, verify running processes, validate user accounts, and search log files for specific entries using Linux-native tools and APIs.

Test Functions
--------------

.. csv-table::
   :file: ../../_static/tables/testfunctions_linux.csv
   :widths: 20, 10, 40, 30
   :header-rows: 1
   :class: sdtable
   :name: linux-functions-table



.. toctree::
   :maxdepth: 1
   :hidden:

   system_service_status
   process_running
   user_exists
   log_entry_exists