cell_value_matches
==================

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: Spreadsheet Data
:Function Name: ``cell_value_matches``

**Tests if one cell of an Excel sheet has the expected value.**

Reads the cell at (``row``, ``column``) of ``sheet`` and compares its string form with ``expected_value``: exactly, as a regex with ``regex_match``, or by type for a single ``!re``/``!timestamp`` tag.

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
   * - ``row``
     - integer
     - **Required.** 0-based row index in the raw sheet (row 0 is spreadsheet row 1). Out of range fails.
   * - ``column``
     - integer
     - **Required.** 0-based column index (column A is 0). Out of range fails.
   * - ``expected_value``
     - string / int / float / bool
     - **Required.** Compared exactly with ``str(expected_value)`` (``None`` means ``''``). A single ``!re``/``!timestamp`` tag is matched by type; more than one placeholder is an error.
   * - ``sheet``
     - string / int
     - **Optional.** Sheet name or 0-based sheet index; an unknown sheet fails. Default: ``0``.
   * - ``regex_match``
     - boolean
     - **Optional.** Treat ``expected_value`` as a regex searched in the cell value (``re.search``, unanchored; write ``^...$`` for the whole value). Default: ``false``.

Usage Example
-------------

.. code-block:: yaml

   tests:
     - name: total_typed
       function: excel.cell_value_matches
       parameter:
         dst: /home/user/Documents/budget.xlsx
         sheet: Q3
         row: 1
         column: 2
         expected_value: '1500'

     - name: amount_any_format
       function: excel.cell_value_matches
       parameter:
         dst: /home/user/Documents/budget.xlsx
         row: 1
         column: 2
         expected_value: !re '^1500(\.0)?$'

Notes
-----

* Numbers can read as floats (``1500.0``) when other cells of the row or column are floats, and
  dates as ``2024-01-31 00:00:00`` or ``2024-01-31T00:00:00``; match them with ``!re``.

Common Use Cases
----------------

**A value the user typed**
  The cell the playbook filled holds the text or number after saving.

**A saved formula result**
  The computed value stored in the workbook (not the formula) is the expected one.

See Also
--------

* :doc:`contains_row` — a whole row anywhere in the sheet.
* :doc:`compare_rows` — all rows of a sheet against reference data.

Return Values
-------------

**Success**
  The cell value matches.

**Failure**
  The workbook was read and the cell value does not match, the row or column is out of range, or the sheet does not exist.

**Error**
  The file does not exist, a glob matches no file or more than one, the file cannot be read or is not a valid workbook, more than one placeholder in ``expected_value``, or an invalid regex or unknown placeholder.
