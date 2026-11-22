sheet_exists
============

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: Spreadsheet Data
:Function Name: ``sheet_exists``

**Tests if a sheet exists in an Excel file.**

Reads the sheet names of workbook ``dst`` and passes when one is named ``sheet`` (exact and case-sensitive) or, with ``regex_match``, when one matches the regex.

Parameters
----------

.. list-table::
   :widths: 20 15 65
   :header-rows: 1

   * - Parameter
     - Type
     - Description
   * - ``dst``
     - string
     - **Required.** Path to the ``.xlsx`` file. A glob must match exactly one file; ``archive.zip!/member`` reads a file inside an archive.
   * - ``sheet``
     - string
     - **Required.** Exact, case-sensitive sheet name, or a regex with ``regex_match``. Renamed from ``sheet_name``.
   * - ``regex_match``
     - boolean
     - **Optional.** Treat ``sheet`` as a Python regex searched in each sheet name (``re.search``, unanchored; write ``^...$`` for the whole name). Default: ``false``.

Usage Example
-------------

.. code-block:: yaml

   tests:
     - name: quarter_sheet_added
       function: excel.sheet_exists
       parameter:
         dst: /home/user/Documents/budget.xlsx
         sheet: Q3

     - name: some_report_sheet
       function: excel.sheet_exists
       parameter:
         dst: /home/user/Documents/budget.xlsx
         sheet: '^Report \d{4}$'
         regex_match: true

     - name: draft_sheet_deleted
       function: excel.sheet_exists
       expect_to_fail: true
       parameter:
         dst: /home/user/Documents/budget.xlsx
         sheet: Draft

Common Use Cases
----------------

**A GUI action added or renamed a sheet**
  The new name exists after the action; the old one fails with ``expect_to_fail: true``.

See Also
--------

* :doc:`cell_value_matches` — a value in a cell of the sheet.
* :doc:`compare_files` — whole workbooks, sheet names included.

Return Values
-------------

**Success**
  A sheet with the name (or a name matching the regex) exists.

**Failure**
  The workbook was read and no sheet has the name, or the workbook has no sheets.

**Error**
  The file does not exist, a glob matches no file or more than one, the file cannot be read or is not a valid workbook, or an invalid regex.
