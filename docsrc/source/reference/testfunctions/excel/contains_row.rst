contains_row
============

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: Spreadsheet Data
:Function Name: ``contains_row``

**Tests if a row of an Excel sheet matches the given entry layout.**

Compares each row of ``sheet`` column by column with ``entry`` and passes on the first row that matches. On failure the closest rows and their mismatching columns are reported.

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
   * - ``entry``
     - list
     - **Required.** Expected row, one item per column of the sheet's used width (a row with another width never matches). Items are exact strings or ``!re``/``!timestamp`` tags.
   * - ``sheet``
     - string / int
     - **Optional.** Sheet name or 0-based sheet index; an unknown sheet fails. Default: ``0``.
   * - ``header_row``
     - integer
     - **Optional.** Number of top rows to skip before searching (not a row index). Default: ``None`` (skip none).

Usage Example
-------------

.. code-block:: yaml

   tests:
     - name: laptop_recorded
       function: excel.contains_row
       parameter:
         dst: /home/user/Documents/inventory.xlsx
         header_row: 1
         entry: [Laptop, !re '[0-9]+', Office]

Common Use Cases
----------------

**A record was added**
  A new line item exists anywhere in the sheet, whatever its position.

**A record was removed**
  ``excel.row_count`` with ``expected_count: 0`` (or ``expect_to_fail: true`` here).

See Also
--------

* :doc:`row_count` — how many rows match (``0`` for absence).
* :doc:`cell_value_matches` — one cell.
* :doc:`/reference/testfunctions/csv/contains_line` — the same check for CSV files.

Return Values
-------------

**Success**
  At least one row matches ``entry``.

**Failure**
  The workbook was read and no row matches (also an empty sheet), or the sheet does not exist.

**Error**
  The file does not exist, a glob matches no file or more than one, the file cannot be read or is not a valid workbook, or an invalid regex or unknown placeholder in ``entry``.
