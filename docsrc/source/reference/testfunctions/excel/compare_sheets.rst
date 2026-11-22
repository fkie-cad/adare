compare_sheets
==============

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: Spreadsheet Data
:Function Name: ``compare_sheets``

**Tests if a sheet of one workbook matches a sheet of the same or another workbook.**

Compares the rows of ``actual_sheet`` in ``actual`` with ``reference_sheet`` in ``reference`` (which may be the same file). Needs the in-guest agent: agentless host mode only pulls a ``dst`` parameter, and this function has none.

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
     - **Required.** Path to the reference workbook; may equal ``actual``.
   * - ``actual_sheet``
     - string / int
     - **Optional.** Sheet name or 0-based index in ``actual``. Default: ``0``.
   * - ``reference_sheet``
     - string / int
     - **Optional.** Sheet name or 0-based index in ``reference``. Default: ``0``.
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
   * - ``header_row``
     - integer
     - **Optional.** Number of top rows to skip in both sheets. Default: ``None``.

Usage Example
-------------

.. code-block:: yaml

   tests:
     - name: copied_sheet_identical
       function: excel.compare_sheets
       parameter:
         actual: /home/user/Documents/budget.xlsx
         reference: /home/user/Documents/budget.xlsx
         actual_sheet: Q3 (copy)
         reference_sheet: Q3

Common Use Cases
----------------

**Copy or move of a sheet**
  The copied sheet has the same rows as the original.

**Export against a known-good workbook**
  A reference workbook placed in the guest before the run.

See Also
--------

* :doc:`compare_rows` — rows against inline reference data.
* :doc:`compare_files` — all sheets of two workbooks.

Return Values
-------------

**Success**
  The rows match within the allowed differences.

**Failure**
  The workbooks were read and rows differ, are missing or extra, or ``actual_sheet`` does not exist.

**Error**
  A workbook does not exist, a glob matches no file or more than one, a file cannot be read or is not a valid workbook, or ``reference_sheet`` does not exist.
