Excel
=====

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Functions: 8
:Category: Spreadsheet Data

.. adare-testfunction-collection:: excel

Overview
--------

Rows are matched against the sheet's used width: an expected row (``entry``) must have one item per column. Absence of a row is checked with ``row_count`` and ``expected_count: 0``. A missing file, a glob matching no file or more than one and an unreadable workbook are errors.

``compare_sheets`` and ``compare_files`` take two paths (``actual``, ``reference``) and need the in-guest agent; agentless host mode only pulls a ``dst`` parameter.

Test Functions
--------------

.. csv-table::
   :file: ../../../_static/tables/testfunctions_excel.csv
   :widths: 20, 10, 40, 30
   :header-rows: 1
   :class: sdtable
   :name: excel-functions-table



.. toctree::
   :maxdepth: 1
   :hidden:

   sheet_exists
   cell_value_matches
   contains_row
   row_count
   validate_columns
   compare_rows
   compare_sheets
   compare_files
