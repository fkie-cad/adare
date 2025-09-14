SQLite Testset
==============

.. role:: status-dev
   :class: status-dev

:Status: :status-dev:`● Development`
:Functions: 1
:Category: Database Validation

The **SQLite** testset provides SQLite database testing capabilities for ADARE experiments. This testset focuses on executing SQL queries against SQLite databases and validating query results, row counts, and data content.

Overview
--------

The SQLite testset enables validation of SQLite database contents through SQL query execution. It includes support for counting result rows, validating specific result data, and using placeholder-based comparison for dynamic content verification.

Test Functions
--------------

.. csv-table::
   :file: ../../_static/tables/testfunctions_sqlite.csv
   :widths: 20, 10, 40, 30
   :header-rows: 1
   :class: sdtable
   :name: sqlite-functions-table



.. toctree::
   :maxdepth: 1
   :hidden:

   query_result