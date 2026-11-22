validate_columns
================

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: Spreadsheet Data
:Function Name: ``validate_columns``

**Tests if the column headers of an Excel sheet match the expected names.**

Reads the header names in row ``column_row`` of ``sheet`` and compares them with ``expected_columns``. Extra, missing and reordered headers fail unless allowed.

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
   * - ``expected_columns``
     - list
     - **Required.** Non-empty list of header names; compared whitespace-stripped and case-sensitive. Empty header cells read as ``''`` and count as extra columns.
   * - ``sheet``
     - string / int
     - **Optional.** Sheet name or 0-based sheet index. Default: ``0``.
   * - ``column_row``
     - integer
     - **Optional.** 0-based row that holds the headers; out of range or an empty row fails. Default: ``0``.
   * - ``allow_extra_columns``
     - boolean
     - **Optional.** Do not fail on headers that are not in ``expected_columns``. Default: ``false``.
   * - ``allow_missing_columns``
     - boolean
     - **Optional.** Do not fail on expected headers absent from the sheet. Default: ``false``.
   * - ``ignore_order``
     - boolean
     - **Optional.** Skip the order check (order is only checked when the names match exactly). Default: ``false``.

Usage Example
-------------

.. code-block:: yaml

   tests:
     - name: inventory_layout
       function: excel.validate_columns
       parameter:
         dst: /home/user/Documents/inventory.xlsx
         expected_columns: [Item, Count, Location]

     - name: required_columns_present
       function: excel.validate_columns
       parameter:
         dst: /home/user/Documents/inventory.xlsx
         expected_columns: [Item, Count]
         allow_extra_columns: true
         ignore_order: true

Common Use Cases
----------------

**Export layout**
  A version of the application writes the same column layout as the last one.

**Inserted or removed columns**
  A GUI action that adds or deletes a column changes the header row.

See Also
--------

* :doc:`compare_rows` — compare the data rows too.

Return Values
-------------

**Success**
  The headers match within the allowed differences.

**Failure**
  The workbook was read and headers are missing, extra or in another order, ``column_row`` is out of range or empty, or the sheet does not exist.

**Error**
  The file does not exist, a glob matches no file or more than one, the file cannot be read or is not a valid workbook, or ``expected_columns`` is not a list or is empty.
