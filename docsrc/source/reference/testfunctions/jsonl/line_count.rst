line_count
==========

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: JSON Lines Data
:Function Name: ``line_count``

**Tests the number of JSONL lines that meet all given conditions.**

Counts the lines of ``dst`` that meet every entry of ``conditions`` (the same rules as ``jsonl.line_matches``) and compares the count with ``expected_count``: an exact number with ``comparison_type``, a ``{min, max}`` range, or ``None`` for "at least one". ``expected_count: 0`` asserts that no such line exists; a missing file is still an error, never a pass.

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
     - **Required.** Path to the JSONL file. A glob must match exactly one file; ``archive.zip!/member`` reads a file inside an archive. A 0-byte file has 0 lines (passes ``expected_count: 0``).
   * - ``conditions``
     - dict
     - **Optional.** Mapping ``key_path -> expected value``; all must hold, and for multi-value paths one matching element suffices. ``None`` or empty counts every valid JSON line.
   * - ``expected_count``
     - integer / dict
     - **Optional.** A non-negative integer compared with ``comparison_type``, ``{min: N, max: M}`` for a range (either bound optional: ``min`` defaults to 0, ``max`` to unbounded), or ``None`` (default) for "at least 1". A negative number, a boolean, other keys or ``min > max`` are an error.
   * - ``regex_match``
     - boolean
     - **Optional.** Treat string expected values as regexes searched (``re.search``) in ``str(value)``; the value ``"*"`` then means "key exists". Default: ``false``.
   * - ``skip_malformed``
     - boolean
     - **Optional.** ``true`` ignores lines that are not valid JSON; ``false`` makes the first malformed line an error. Default: ``true``.
   * - ``comparison_type``
     - string
     - **Optional.** ``equals``, ``greater``, ``less``, ``greater_equal`` or ``less_equal`` for an integer ``expected_count``; with a range or ``None`` only ``equals`` is allowed. Default: ``equals``.
   * - ``encoding``
     - string
     - **Optional.** Default ``None``: a BOM (UTF-8/16/32) or BOM-less UTF-16 is detected, else UTF-8. A name (``cp1252``) reads BOM-less files with it.

Usage Example
-------------

.. code-block:: yaml

   tests:
     - name: three_deletions_logged
       function: jsonl.line_count
       parameter:
         dst: /home/user/data/events.jsonl
         conditions: {event: file_deleted}
         expected_count: 3

     - name: some_uploads
       function: jsonl.line_count
       parameter:
         dst: /home/user/data/events.jsonl
         conditions: {event: upload}
         expected_count: {min: 1, max: 5}

     - name: no_entry_for_example_org
       function: jsonl.line_count
       parameter:
         dst: /home/user/data/history.jsonl
         conditions: {url: https://example.org/}
         expected_count: 0

Common Use Cases
----------------

**How often an action was recorded**
  Exactly one ``file_deleted`` event per deletion the playbook performed.

**Absence of a record**
  ``expected_count: 0`` shows that a private-mode visit or a cleared entry left no line.

See Also
--------

* :doc:`line_matches` — one line (or every line) meets the conditions.
* :doc:`/reference/testfunctions/text/line_count` — lines of a plain text file that contain a string.
* :doc:`/reference/testfunctions/csv/row_count` — rows of a CSV file.
* :doc:`/guide/absence` — checking that something is absent.

Return Values
-------------

**Success**
  The count of matching lines satisfies ``expected_count``.

**Failure**
  The file was read and the count does not satisfy ``expected_count``.

**Error**
  The file does not exist, a glob matches no file or more than one, the file cannot be read or decoded, the encoding is unknown, a malformed line with ``skip_malformed: false``, an invalid ``expected_count``, or an unknown ``comparison_type`` (or one other than ``equals`` with a range or ``None``).
