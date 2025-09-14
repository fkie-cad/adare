JSON 
============

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Functions: 3
:Category: JSON Data Validation

The **JSON** testset provides comprehensive JSON file testing capabilities for ADARE experiments. This testset focuses on JSON structure validation, key existence checking, value comparison, and array element verification.

Overview
--------

The JSON testset enables detailed validation of JSON files and data structures. It includes functions to check for key existence using dot notation paths, validate values with support for wildcards and regular expressions, and verify array contents with flexible matching options.

Test Functions
--------------

.. csv-table::
   :file: ../../_static/tables/testfunctions_json.csv
   :widths: 20, 10, 40, 30
   :header-rows: 1
   :class: sdtable
   :name: json-functions-table



.. toctree::
   :maxdepth: 1
   :hidden:

   contains_key
   value_matches
   array_contains
