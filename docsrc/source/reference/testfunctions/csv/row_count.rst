row_count
=========

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: CSV Data
:Function Name: ``row_count``

**Tests the number of rows in a CSV file that match the given entry layout.**

Counts the rows that ``csv.contains_line`` would accept for ``entry`` and passes when the count satisfies ``comparison_type`` against ``expected_count``. ``expected_count: 0`` asserts that no such row exists; a missing or unreadable file is still an error, never a pass.

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
     - **Required.** Path to the CSV file. A glob must match exactly one file. Parsed like ``contains_line``: default ``csv`` dialect, the header row is a normal row. Counts CSV records: a quoted field with a line break is one row.
   * - ``entry``
     - list
     - **Required.** Expected row, one item per column; a row with another column count never matches. Items are exact, case-sensitive strings or ``!re`` / ``!timestamp`` tags.
   * - ``expected_count``
     - integer
     - **Required.** Non-negative number to compare the count with. ``0`` asserts absence.
   * - ``comparison_type``
     - string
     - **Optional.** ``equals``, ``greater``, ``less``, ``greater_equal`` or ``less_equal``. Default: ``equals``.
   * - ``encoding``
     - string
     - **Optional.** Default ``None``: a BOM (UTF-8/16/32) or BOM-less UTF-16 is detected, else UTF-8. A name (``cp1252``) reads BOM-less files with it.

Usage Example
-------------

.. code-block:: yaml

   tests:
     - name: one_deletion_recorded
       function: csv.row_count
       parameter:
         dst: '{{ out_dir }}/timeline.csv'
         entry: [report.txt, !re '.*', Deleted]
         expected_count: 1

Return Values
-------------

**Success**
  The count comparison holds.

**Failure**
  The file was read and the count comparison does not hold.

**Error**
  The file does not exist, a glob matches no file or more than one, the file cannot be read or
  decoded, a CSV parse error, ``entry`` is not a list, a negative or non-integer
  ``expected_count``, or an unknown ``comparison_type``.
