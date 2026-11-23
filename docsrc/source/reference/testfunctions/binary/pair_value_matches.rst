pair_value_matches
==================

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: Binary Containers
:Function Name: ``pair_value_matches``

**Tests the value of a key in a table of separator-delimited key/value strings in a binary file.**

Reads the bytes ``[start, end)`` as alternating key and value strings (``key\0value\0key\0value\0``),
and passes when the value of ``key`` matches ``expected_value``. Many containers keep their
metadata this way; ``start`` and ``end`` take offset expressions (see :doc:`index`), so the table
can be found through a trailer pointer.

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
     - **Required.** Path to the file. A glob must match exactly one file; ``archive.tar!/member`` reads a file inside an archive.
   * - ``key``
     - string
     - **Required.** Key to look up, compared exactly after decoding.
   * - ``expected_value``
     - string/int/float
     - **Required.** Compared as text (a number as its text). A ``!re`` tag (``re.match``) or a ``{{placeholder}}`` is supported. A value not valid in ``encoding`` is an error.
   * - ``start``
     - int/string
     - **Optional.** Offset of the first key (default ``0``): an int (negative from the end) or an offset expression.
   * - ``end``
     - int/string
     - **Optional.** End of the table, exclusive (default: the end of the file).
   * - ``separator``
     - string
     - **Optional.** Bytes between the strings, ASCII and Python escapes. Default: NUL (``\x00``). UTF-16 tables use ``\x00\x00``; separators are only found at code-unit boundaries.
   * - ``encoding``
     - string
     - **Optional.** Encoding of keys and values. Default ``utf-8``; ``utf-16-le``, ``latin-1``, ...
   * - ``regex_match``
     - boolean
     - **Optional.** Treat a string ``expected_value`` as a regex searched (``re.search``). Default: ``false``.
   * - ``wildcard_mode``
     - string
     - **Optional.** When the key occurs several times: ``any`` (default): one value must match; ``all``: every value must match.

The region must hold whole key/value pairs. One separator after the last value is allowed; an odd
number of strings (for example padding, or a region that starts in the middle of the table) is an
error, so a wrong ``start``/``end`` cannot shift keys into values. An empty value
(``key\0\0``) is an empty string.

Usage Example
-------------

.. code-block:: yaml

   tests:
     # metadata block starts 16 bytes after the offset stored in the last 4 bytes
     - name: entry_content_type
       function: binary.pair_value_matches
       parameter:
         dst: /home/user/app/cache/entry.bin
         start: u32be@-4+16
         end: -4
         key: content-type
         expected_value: text/plain

     - name: every_origin_on_example_org
       function: binary.pair_value_matches
       parameter:
         dst: /home/user/app/cache/entry.bin
         start: u32be@-4+16
         end: -4
         key: origin
         expected_value: 'example\.org'
         regex_match: true
         wildcard_mode: all

Common Use Cases
----------------

**A metadata element has a value**
  Response headers, origins, titles or flags stored as key/value strings in a binary container.

See Also
--------

* :doc:`pair_count` — how often a key occurs (``0`` for absence).
* :doc:`struct_value_matches` — one value at an offset.

Return Values
-------------

**Success**
  The value of ``key`` (``any``: one of its values, ``all``: every value) matches.

**Failure**
  The table was read and ``key`` does not occur, or its value(s) do not match.

**Error**
  The file does not exist or is a directory, a glob matches no file or more than one, a malformed
  offset expression, an offset outside the file, ``end`` before ``start``, an odd number of strings
  in the region, an empty key, an invalid separator (or one that is not a whole number of code
  units), an unknown encoding, a value not valid in it, an invalid regex or placeholder, or an
  invalid ``wildcard_mode``.
