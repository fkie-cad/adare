value_in_any_line
=================

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: JSON Lines Data
:Function Name: ``value_in_any_line``

**Tests if a key path has the expected value in at least one line of a JSONL file.**

Parses each line of ``dst`` as JSON, reads ``key_path`` and passes when one line has a matching value. For conditions on several fields of the same line use ``jsonl.line_matches``.

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
     - **Required.** Path to the JSONL file. A glob must match exactly one file; ``archive.zip!/member`` reads a file inside an archive. A 0-byte file fails.
   * - ``key_path``
     - string
     - **Required.** Dot path inside each line's object, e.g. ``event.type``; ``*`` expands object values, ``name[*]`` array elements. No numeric indexes. For multi-value paths one matching element suffices.
   * - ``expected_value``
     - string / int / float / bool
     - **Required.** Value to find; compared with type-sensitive ``==`` unless ``regex_match`` is set. ``!re`` and ``!timestamp`` tags always work.
   * - ``regex_match``
     - boolean
     - **Optional.** Treat a string ``expected_value`` as a regex searched (``re.search``) in ``str(value)``; ``"*"`` then means "key exists". Default: ``false``.
   * - ``skip_malformed``
     - boolean
     - **Optional.** ``true`` ignores lines that are not valid JSON; ``false`` makes the first malformed line an error. Default: ``true``.
   * - ``encoding``
     - string
     - **Optional.** Default ``None``: a BOM (UTF-8/16/32) or BOM-less UTF-16 is detected, else UTF-8. A name (``cp1252``) reads BOM-less files with it.

Usage Example
-------------

.. code-block:: yaml

   tests:
     - name: document_opened
       function: jsonl.value_in_any_line
       parameter:
         dst: /home/user/data/events.jsonl
         key_path: file.name
         expected_value: report.docx

     - name: any_example_url
       function: jsonl.value_in_any_line
       parameter:
         dst: /home/user/data/history.jsonl
         key_path: url
         expected_value: '^https://example\.org/'
         regex_match: true

Common Use Cases
----------------

**A value was logged**
  A file name, URL or search term shows up in a history or event log.

**A field exists somewhere**
  ``expected_value: "*"`` with ``regex_match: true`` passes when any line has the key.

See Also
--------

* :doc:`line_matches` — several fields of the same line.
* :doc:`line_count` — how many lines have the value (``0`` for absence).
* :doc:`/reference/testfunctions/text/occurrence_count` — a string anywhere in the raw file.

Return Values
-------------

**Success**
  At least one line has a matching value at ``key_path``.

**Failure**
  The file was read and no line has a matching value (or the key at all), or the file is empty.

**Error**
  The file does not exist, a glob matches no file or more than one, the file cannot be read or decoded, the encoding is unknown, or a malformed line with ``skip_malformed: false``.
