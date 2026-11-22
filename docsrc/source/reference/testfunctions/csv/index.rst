CSV
===========

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Functions: 4
:Category: CSV Data Validation

The **CSV** testset provides CSV file testing capabilities for ADARE experiments. This testset focuses on validating CSV row content, counting matching rows and comparing whole files, supporting complex pattern matching with regex patterns and timestamp tolerance.

Overview
--------

The CSV testset enables validation of CSV file contents by matching entire rows against expected patterns. It includes support for exact matching, regex pattern matching, timestamp tolerance, and flexible placeholder-based validation for dynamic content verification.

Every CSV function takes ``encoding``: by default a BOM (UTF-8/16/32) or BOM-less UTF-16 is detected, otherwise UTF-8 is read; a name (``cp1252``) reads BOM-less files with it. ``row_count`` (formerly ``line_count``) counts records, so a quoted field with a line break is one row; ``text.line_count`` counts physical text lines and ``jsonl.line_count`` JSON Lines records.

Test Functions
--------------

.. csv-table::
   :file: ../../../_static/tables/testfunctions_csv.csv
   :widths: 20, 10, 40, 30
   :header-rows: 1
   :class: sdtable
   :name: csv-functions-table



.. toctree::
   :maxdepth: 1
   :hidden:

   contains_line
   row_count
   compare_rows
   compare_files