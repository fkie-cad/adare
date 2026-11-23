lines_in_order
==============

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: Text and Binary Content
:Function Name: ``lines_in_order``

**Tests that lines matching each of several patterns occur in the given order.**

Decodes the file as text, splits it into lines (at ``\n``, ``\r\n`` or ``\r``) and looks for the ``patterns`` one after the other: each pattern must match a line after the line the previous pattern matched. Lines in between are ignored. Each pattern takes the earliest such line, so two patterns never match the same line, and when this fails no other choice of lines would pass either. For how often one pattern occurs use ``text.line_count``; for JSON Lines records use ``jsonl.lines_in_order``.

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
   * - ``patterns``
     - list
     - **Required.** Non-empty list of non-empty strings, in the expected order. Each is a substring a line must contain, or with ``regex`` a regex searched in each line (``re.search``). A ``!re`` tag or ``{{placeholder}}`` is an error: write regexes as plain strings with ``regex: true``.
   * - ``regex``
     - boolean
     - **Optional.** Treat every pattern as a regex. Default: ``false``.
   * - ``case_sensitive``
     - boolean
     - **Optional.** Default: ``true``. ``false`` compares substrings after casefolding, or compiles the regexes with ``re.IGNORECASE``.
   * - ``encoding``
     - string
     - **Optional.** Text encoding. Default: ``utf-8``; ``null`` also detects BOM-less UTF-16 from its zero bytes. A BOM always wins.

Usage Example
-------------

.. code-block:: yaml

   tests:
     - name: report_opened_then_deleted
       function: text.lines_in_order
       parameter:
         dst: /var/log/app/service.log
         patterns:
           - 'service started'
           - 'opened .*report\.txt'
           - 'deleted .*report\.txt'
         regex: true

Return Values
-------------

**Success**
  Every pattern matched a line after the previous one. Details list the matched line numbers
  (counted from 1).

**Failure**
  The file was read and a pattern matches no line after the line of the pattern before it. The
  first such pattern is named; if it occurs only earlier, its earlier line numbers are listed
  ("out of order"). The lines matched so far follow.

**Error**
  The file does not exist or is a directory, a glob matches no file or more than one, the file
  cannot be read or is not valid in the encoding, an unknown encoding, an empty ``patterns``
  list, a pattern that is not a non-empty string, an invalid regex, or a non-boolean ``regex``
  or ``case_sensitive``.
