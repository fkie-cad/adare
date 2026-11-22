row_count
=========

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: Spreadsheet Data
:Function Name: ``row_count``

**Tests the number of rows in an Excel sheet that match the given entry layout.**

Counts the rows of ``sheet`` that ``excel.contains_row`` would accept for ``entry`` and passes when the count satisfies ``comparison_type`` against ``expected_count``. ``expected_count: 0`` asserts that no such row exists; a missing or unreadable workbook is still an error, never a pass.

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
     - **Required.** Path to the ``.xlsx`` file. A glob must match exactly one file.
   * - ``entry``
     - list
     - **Required.** Expected row, one item per column of the sheet's used width; a row with another width never matches. Items are exact strings (cells are stringified as in ``cell_value_matches``) or ``!re`` / ``!timestamp`` tags.
   * - ``expected_count``
     - integer
     - **Required.** Non-negative number to compare the count with. ``0`` asserts absence.
   * - ``comparison_type``
     - string
     - **Optional.** ``equals``, ``greater``, ``less``, ``greater_equal`` or ``less_equal``. Default: ``equals``.
   * - ``sheet``
     - string or integer
     - **Optional.** Sheet name or 0-based index. Default: ``0``. An unknown sheet fails, as in ``contains_row``.
   * - ``header_row``
     - integer
     - **Optional.** Number of top rows to skip before counting (not a row index). Default: ``None`` (skip none).

Usage Example
-------------

.. code-block:: yaml

   tests:
     - name: one_laptop_listed
       function: excel.row_count
       parameter:
         dst: /home/user/Documents/inventory.xlsx
         entry: [Laptop, !re '[0-9]+', Office]
         expected_count: 1

     - name: deleted_item_gone
       function: excel.row_count
       parameter:
         dst: /home/user/Documents/inventory.xlsx
         sheet: Items
         header_row: 1
         entry: [Printer, !re '.*', !re '.*']
         expected_count: 0

Return Values
-------------

**Success**
  The count comparison holds.

**Failure**
  The workbook was read and the count comparison does not hold, or ``sheet`` does not exist.

**Error**
  The file does not exist, a glob matches no file or more than one, the workbook cannot be read
  or parsed, ``entry`` is not a list, a negative or non-integer ``expected_count`` or
  ``header_row``, an unknown ``comparison_type``, or an unknown placeholder in ``entry``.

See also
--------

- :doc:`contains_row` passes when at least one row matches and reports the closest rows on failure.
- :doc:`../csv/row_count` counts matching rows of a CSV file.

Common use cases
----------------

**Record added exactly once**
  An edit or import must add one row, not zero and not a duplicate.

**Row removed**
  ``expected_count: 0`` after deleting a row in the spreadsheet application.

**Several matching rows**
  ``comparison_type: greater_equal`` with ``!re`` items to count rows of one kind.
