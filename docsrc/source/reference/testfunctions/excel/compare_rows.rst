compare_rows
============

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: Spreadsheet Data
:Function Name: ``compare_rows``

**Tests if the rows of an Excel sheet match reference rows (inline or from a reference workbook).**

Compares the rows of ``sheet`` with ``reference_rows`` given in the playbook or with a sheet of ``reference_file``. Give exactly one of the two. By default row N is compared with reference row N; ``ignore_order`` matches the rows as a multiset.

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
     - **Required.** Path to the ``.xlsx`` file under test. A glob must match exactly one file; ``archive.zip!/member`` reads a file inside an archive.
   * - ``reference_rows``
     - list of lists
     - **Optional.** Expected rows as lists of strings (quote numbers in YAML); ``!re``/``!timestamp`` tags allowed. Either this or ``reference_file``.
   * - ``reference_file``
     - string
     - **Optional.** Path to a reference ``.xlsx`` on the same machine (not pulled in agentless host mode). Either this or ``reference_rows``.
   * - ``reference_sheet``
     - string / int
     - **Optional.** Sheet name or 0-based index in ``reference_file``. Default: ``0``.
   * - ``reference_header_row``
     - integer
     - **Optional.** Number of top rows to skip in ``reference_file``. Default: ``None``.
   * - ``sheet``
     - string / int
     - **Optional.** Sheet name or 0-based index in ``dst``. Default: ``0``.
   * - ``columns``
     - list
     - **Optional.** 0-based column indices to compare; ``None`` compares all. Default: ``None``.
   * - ``ignore_order``
     - boolean
     - **Optional.** Match rows as a multiset instead of position by position. Default: ``false``.
   * - ``allow_extra_rows``
     - boolean
     - **Optional.** Do not fail on extra rows of ``dst`` (ordered mode: trailing rows only). Default: ``false``.
   * - ``allow_missing_rows``
     - boolean
     - **Optional.** Do not fail on reference rows missing from ``dst`` (ordered mode: trailing rows only). Default: ``false``.
   * - ``header_row``
     - integer
     - **Optional.** Number of top rows of ``dst`` to skip (not a row index). Default: ``None``.

Usage Example
-------------

.. code-block:: yaml

   tests:
     - name: inventory_contents
       function: excel.compare_rows
       parameter:
         dst: /home/user/Documents/inventory.xlsx
         header_row: 1
         reference_rows:
           - [Laptop, '3', Office]
           - [Monitor, '5', !re '.*']

     - name: names_and_counts_any_order
       function: excel.compare_rows
       parameter:
         dst: /home/user/Documents/inventory.xlsx
         header_row: 1
         columns: [0, 1]
         ignore_order: true
         reference_rows: [[Monitor, '5'], [Laptop, '3']]

Common Use Cases
----------------

**A small sheet's full contents**
  Every row the playbook entered, and nothing else.

**Selected columns**
  ``columns`` ignores volatile columns such as IDs or times.

See Also
--------

* :doc:`compare_sheets` — two sheets of the same or different workbooks.
* :doc:`contains_row` — one row anywhere in the sheet.
* :doc:`/reference/testfunctions/csv/compare_rows` — the same check for CSV files.

Return Values
-------------

**Success**
  The rows match within the allowed differences.

**Failure**
  The workbooks were read and rows differ, are missing or extra, or the sheet of ``dst`` does not exist.

**Error**
  ``dst`` or ``reference_file`` does not exist, a glob matches no file or more than one, a file cannot be read or is not a valid workbook, the reference sheet does not exist, both or neither of ``reference_rows`` and ``reference_file`` are given, or ``reference_rows`` is empty or not a list of lists.
