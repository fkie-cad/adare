Excel
=====

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Functions: 8
:Category: Spreadsheet Data

The **Excel** testset checks ``.xlsx`` workbooks: sheet names, single cells, rows, header layouts, and whole sheets or workbooks compared with reference data.

Overview
--------

Workbooks are read with openpyxl. Cell values are turned into strings before they are compared: an empty cell is ``''``, numbers use ``str()`` (an integer may read as ``5.0`` when the column holds floats), and dates read as ``2024-01-31 00:00:00`` or ``2024-01-31T00:00:00``. Use ``!re`` for numbers and dates when unsure. ``!re`` and ``!timestamp`` tags work in every expected value and row.

Rows and columns are 0-based (row 0 is spreadsheet row 1, column 0 is column A). ``sheet`` is a sheet name or a 0-based sheet index; an unknown sheet fails. ``header_row`` is the *number* of top rows to skip, not a row index.

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
