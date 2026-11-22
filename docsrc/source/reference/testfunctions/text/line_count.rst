line_count
==========

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: Text and Binary Content
:Function Name: ``line_count``

**Tests the number of text lines that contain a string or match a regex.**

Decodes the file as text, splits it into lines (at ``\n``, ``\r\n`` or ``\r``) and counts the lines that contain ``content`` (or match it with ``re.search``). Passes when the count satisfies ``comparison_type`` against ``expected_count``. ``expected_count: 0`` asserts that no such line exists; an empty file has 0 lines. A missing file is still an error, never a pass.

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
     - **Required.** Path to the text file. A glob must match exactly one file; ``archive.zip!/member`` reads a file inside an archive.
   * - ``content``
     - string
     - **Required.** Substring a line must contain (case-sensitive); an empty string counts every line. With ``regex_match`` a regex (``(?i)`` for case-insensitive).
   * - ``expected_count``
     - integer
     - **Required.** Non-negative number to compare the count with. ``0`` asserts absence.
   * - ``comparison_type``
     - string
     - **Optional.** ``equals``, ``greater``, ``less``, ``greater_equal`` or ``less_equal``. Default: ``equals``.
   * - ``encoding``
     - string
     - **Optional.** Text encoding. Default: auto (a BOM selects UTF-8/16/32, BOM-less UTF-16 is detected from its zero bytes, otherwise UTF-8). A BOM always wins.
   * - ``regex_match``
     - boolean
     - **Optional.** Treat ``content`` as a regex searched in each line. Default: ``false``.

Usage Example
-------------

.. code-block:: yaml

   tests:
     - name: two_deletions_logged
       function: text.line_count
       parameter:
         dst: /home/user/data/app.log
         content: 'deleted: .*report'
         regex_match: true
         expected_count: 2

     - name: entry_removed_from_history
       function: text.line_count
       parameter:
         dst: /home/user/data/history.txt
         content: secret-project
         expected_count: 0

Return Values
-------------

**Success**
  The count comparison holds.

**Failure**
  The file was read and the count comparison does not hold.

**Error**
  The file does not exist or is a directory, a glob matches no file or more than one, the file
  cannot be read or is not valid in the encoding, an unknown encoding, an invalid regex, a
  negative or non-integer ``expected_count``, or an unknown ``comparison_type``.
