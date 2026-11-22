compare_files
=============

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: Spreadsheet Data
:Function Name: ``compare_files``

**Tests if two Excel workbooks match, sheet by sheet.**

Pairs the sheets of ``actual`` and ``reference`` (by name, by position, or only the listed ones) and compares the rows of each pair. Missing or extra sheets fail unless allowed. Needs the in-guest agent: agentless host mode only pulls a ``dst`` parameter, and this function has none.

Parameters
----------

.. list-table::
   :widths: 20 15 65
   :header-rows: 1

   * - Parameter
     - Type
     - Description
   * - ``actual``
     - string
     - **Required.** Path to the workbook under test; a glob must match exactly one file.
   * - ``reference``
     - string
     - **Required.** Path to the reference workbook.
   * - ``sheet_mode``
     - string
     - **Optional.** ``by_name`` (pair equal names), ``by_index`` (pair by position) or ``specific`` (only ``specific_sheets`` present in both; extra sheets ignored). Default: ``by_name``.
   * - ``specific_sheets``
     - list
     - **Optional.** Sheet names for ``specific`` mode. Names absent from ``actual`` count as missing; names absent only from ``reference`` are skipped. An empty list passes.
   * - ``columns``
     - list
     - **Optional.** 0-based column indices to compare; ``None`` compares all. Default: ``None``.
   * - ``ignore_order``
     - boolean
     - **Optional.** Match rows as a multiset instead of position by position. Default: ``false``.
   * - ``allow_extra_rows``
     - boolean
     - **Optional.** Do not fail on extra rows in ``actual`` (ordered mode: trailing rows only). Default: ``false``.
   * - ``allow_missing_rows``
     - boolean
     - **Optional.** Do not fail on reference rows missing from ``actual`` (ordered mode: trailing rows only). Default: ``false``.
   * - ``allow_extra_sheets``
     - boolean
     - **Optional.** Do not fail on sheets only in ``actual``. Default: ``false``.
   * - ``allow_missing_sheets``
     - boolean
     - **Optional.** Do not fail on sheets only in ``reference``. Default: ``false``.
   * - ``header_row``
     - integer
     - **Optional.** Number of top rows to skip in every sheet. Default: ``None``.

Usage Example
-------------

.. code-block:: yaml

   tests:
     - name: workbook_unchanged
       function: excel.compare_files
       parameter:
         actual: /home/user/Documents/report.xlsx
         reference: /home/user/reference/report.xlsx

     - name: summary_sheets_only
       function: excel.compare_files
       parameter:
         actual: /home/user/Documents/report.xlsx
         reference: /home/user/reference/report.xlsx
         sheet_mode: specific
         specific_sheets: [Summary]

Common Use Cases
----------------

**Save round trip**
  A workbook opened and saved again keeps all sheets and rows.

**Version comparison**
  The export of one application version against the export of another, placed in the guest as a reference.

See Also
--------

* :doc:`compare_sheets` — one pair of sheets.
* :doc:`/reference/testfunctions/csv/compare_files` — the same check for CSV files.

Return Values
-------------

**Success**
  All paired sheets match and no sheet is missing or extra (beyond the allowed differences).

**Failure**
  The workbooks were read and a sheet is missing or extra, or the rows of a paired sheet differ; the report lists the differences per sheet.

**Error**
  A workbook does not exist, a glob matches no file or more than one, a file cannot be read or is not a valid workbook, or an unknown ``sheet_mode``.
