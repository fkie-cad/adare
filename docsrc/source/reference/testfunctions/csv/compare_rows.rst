compare_rows
============

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: CSV Data
:Function Name: ``compare_rows``

**Tests if the rows of a CSV file match reference rows given in the playbook.**

Parses ``dst`` (default ``csv`` dialect, the header row is a normal row) and compares its rows with ``reference_rows``. By default row N is compared with reference row N; ``ignore_order`` matches the rows as a multiset. To compare against a second CSV file use ``csv.compare_files``.

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
     - **Required.** Path to the CSV file. A glob must match exactly one file; ``archive.zip!/member`` reads a file inside an archive.
   * - ``reference_rows``
     - list of lists
     - **Required.** Expected rows, a non-empty list of lists of strings (quote numbers in YAML). ``!re``/``!timestamp`` tags are matched by type, other cells exactly.
   * - ``columns``
     - list
     - **Optional.** 0-based column indices to compare; other columns are ignored and out-of-range indices are dropped. ``None`` compares all columns. Default: ``None``.
   * - ``ignore_order``
     - boolean
     - **Optional.** ``true`` matches rows as a multiset regardless of position. Default: ``false``.
   * - ``allow_extra_rows``
     - boolean
     - **Optional.** Do not fail on file rows without a reference counterpart (ordered mode: trailing rows only). Default: ``false``.
   * - ``allow_missing_rows``
     - boolean
     - **Optional.** Do not fail on reference rows missing from the file (ordered mode: trailing rows only). Default: ``false``.
   * - ``encoding``
     - string
     - **Optional.** Default ``None``: a BOM (UTF-8/16/32) or BOM-less UTF-16 is detected, else UTF-8. A name (``cp1252``) reads BOM-less files with it; a BOM always wins.

Usage Example
-------------

.. code-block:: yaml

   tests:
     - name: export_contents
       function: csv.compare_rows
       parameter:
         dst: /home/user/data/export.csv
         reference_rows:
           - [name, size]
           - [report.docx, '1024']
           - [notes.txt, !re '[0-9]+']

     - name: names_any_order
       function: csv.compare_rows
       parameter:
         dst: /home/user/data/export.csv
         columns: [0]
         ignore_order: true
         allow_extra_rows: true
         reference_rows: [[notes.txt], [report.docx]]

Common Use Cases
----------------

**A small export's full contents**
  Every row the application wrote, in order, header included.

**Selected columns**
  ``columns`` ignores volatile columns such as IDs or times.

See Also
--------

* :doc:`compare_files` — against a second CSV file.
* :doc:`contains_line` — one row anywhere in the file.
* :doc:`row_count` — how many rows match a layout.

Return Values
-------------

**Success**
  The rows match within the allowed differences.

**Failure**
  The file was read and rows differ, are missing or extra.

**Error**
  The file does not exist, a glob matches no file or more than one, the file cannot be read or decoded, the encoding is unknown, a CSV parse error, or ``reference_rows`` is empty or not a list of lists.
