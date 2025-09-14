CSV Testset
===========

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Functions: 1
:Category: CSV Data Validation

The **CSV** testset provides CSV file testing capabilities for ADARE experiments. This testset focuses on validating CSV row content, supporting complex pattern matching with regex patterns and timestamp tolerance.

Overview
--------

The CSV testset enables validation of CSV file contents by matching entire rows against expected patterns. It includes support for exact matching, regex pattern matching, timestamp tolerance, and flexible placeholder-based validation for dynamic content verification.

Test Functions
--------------

.. csv-table::
   :file: ../../_static/tables/testfunctions_csv.csv
   :widths: 20, 10, 40, 30
   :header-rows: 1
   :class: sdtable
   :name: csv-functions-table



.. toctree::
   :maxdepth: 1
   :hidden:

   contains_line