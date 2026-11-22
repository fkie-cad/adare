compare_files
=============

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: CSV Data
:Function Name: ``compare_files``

**Tests if a CSV file matches a reference CSV file row by row.**

Parses both files (default ``csv`` dialect, header rows included) and compares their rows. By default row N is compared with row N; ``ignore_order`` matches the rows as a multiset. For expectations written in the playbook use ``csv.compare_rows``. Needs the in-guest agent: agentless host mode only pulls a ``dst`` parameter, and this function has none.

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
     - **Required.** Path to the CSV file under test; a glob must match exactly one file.
   * - ``reference``
     - string
     - **Required.** Path to the reference CSV file, resolved like ``actual``.
   * - ``columns``
     - list
     - **Optional.** 0-based column indices to compare; ``None`` compares all columns. Default: ``None``.
   * - ``ignore_order``
     - boolean
     - **Optional.** ``true`` matches rows as a multiset. Default: ``false``.
   * - ``allow_extra_rows``
     - boolean
     - **Optional.** Do not fail on rows only in ``actual`` (ordered mode: trailing rows only). Default: ``false``.
   * - ``allow_missing_rows``
     - boolean
     - **Optional.** Do not fail on rows only in ``reference`` (ordered mode: trailing rows only). Default: ``false``.
   * - ``encoding``
     - string
     - **Optional.** Default ``None``: a BOM (UTF-8/16/32) or BOM-less UTF-16 is detected, else UTF-8. A name (``cp1252``) reads BOM-less files (both) with it; a BOM always wins.

Usage Example
-------------

.. code-block:: yaml

   tests:
     - name: export_like_reference
       function: csv.compare_files
       parameter:
         actual: /home/user/data/export.csv
         reference: /home/user/reference/export.csv
         ignore_order: true

Common Use Cases
----------------

**Export against a known-good file**
  A reference CSV placed in the guest before the run.

**Two exports of one run**
  Two files the application wrote should hold the same rows.

See Also
--------

* :doc:`compare_rows` — against rows written in the playbook.
* :doc:`/reference/testfunctions/excel/compare_files` — the same check for Excel workbooks.

Return Values
-------------

**Success**
  The rows match within the allowed differences.

**Failure**
  Both files were read and rows differ, are missing or extra.

**Error**
  A file does not exist, a glob matches no file or more than one, a file cannot be read or decoded, the encoding is unknown, or a CSV parse error.
