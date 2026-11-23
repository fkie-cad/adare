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
   * - ``comparison_type``
     - string
     - **Optional.** ``equals`` (default), ``not_equals``, ``greater``, ``less``, ``greater_equal`` or ``less_equal``. Anything but ``equals``, or any of the parameters below, compares the value with ``expected_value`` as a number or timestamp (see :ref:`ordered-comparison`); a ``!re`` tag or ``regex_match`` is then an ERROR, a lone ``{{ name }}`` is the saved variable's value.
   * - ``value_type``
     - string
     - **Optional.** ``auto`` (default: numbers if both sides are numbers, else timestamps), ``number`` or ``timestamp``.
   * - ``tolerance``
     - number
     - **Optional.** Allowed difference for ``equals``/``not_equals`` (seconds for timestamps).
   * - ``time_format``
     - string
     - **Optional.** ``strptime`` format of text timestamps on both sides; default ISO 8601 or RFC 2822.
   * - ``timestamp_epoch``
     - int
     - **Optional.** Read numbers as a count since 1 January of ``1970``, ``1601`` or ``2001``.
   * - ``timestamp_unit``
     - string
     - **Optional.** Unit of that count: ``s`` (default), ``ms``, ``us``, ``ns`` or ``100ns``.
   * - ``utc_offset``
     - string
     - **Optional.** Zone of timestamps without one (``+02:00``); default UTC.
   * - ``value_decode``
     - list / string
     - **Optional.** Decode the value read from the file before comparing: one step or a list applied in order: ``url``, ``base64``, ``hex``, ``utf16``, ``json`` (see "Decoding a stored value" under :ref:`ordered-comparison`). A value a step cannot decode, or an unknown step, is an ERROR.
   * - ``decoded_key_path``
     - string
     - **Optional.** With ``json`` in ``value_decode``: key path into the decoded value (syntax of :doc:`/reference/testfunctions/json/value_matches`); it must select one value: none is FAILED (the value decoded, the key is not in it), several are an ERROR. Required with ``json``, an ERROR without it.

Numbers and Timestamps
----------------------

With ``comparison_type``, ``value_type``, ``tolerance`` or a time parameter the value is compared as a number or a point in time instead of by equality: greater/less (earlier/later), or equal within a tolerance. A value that is no number or timestamp is an ERROR (the test looked at the wrong field), as is a regex ``expected_value``; a lone ``{{ name }}`` placeholder compares with the saved variable. See :ref:`ordered-comparison`.

.. code-block:: yaml

   tests:
     - name: ordered_value
       function: jsonl.value_in_any_line
       parameter:
         dst: /home/user/data/events.jsonl
         key_path: ts
         expected_value: "2026-03-01T10:00:00Z"
         comparison_type: greater
         timestamp_epoch: 1970
         timestamp_unit: ms

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
