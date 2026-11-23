CSV
===========

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Functions: 4
:Category: CSV Data Validation

.. adare-testfunction-collection:: csv

Counting
--------

``row_count`` (formerly ``line_count``) counts records, so a quoted field with a line break is one
row; ``text.line_count`` counts physical text lines and ``jsonl.line_count`` JSON Lines records.

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