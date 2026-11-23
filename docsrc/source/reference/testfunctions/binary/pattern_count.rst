pattern_count
=============

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: Binary Containers
:Function Name: ``pattern_count``

**Tests how often a byte pattern, text or regex occurs within a region of a binary file.**

Counts the non-overlapping occurrences of ``pattern`` in the bytes ``[start, end)`` and passes when
the count satisfies ``comparison_type`` against ``expected_count``. ``start`` and ``end`` take
offset expressions (see :doc:`index`), so the region can be a block that a trailer points to.
``expected_count: 0`` asserts absence; a missing file is still an error, never a pass.

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
     - **Required.** Path to the file. A glob must match exactly one file; ``archive.tar!/member`` reads a file inside an archive. A region over the read cap (``ADARE_ARCHIVE_MAX_BYTES``) is an error.
   * - ``pattern``
     - string
     - **Required.** What to count; must not be empty. Interpreted according to ``pattern_type``.
   * - ``pattern_type``
     - string
     - **Optional.** ``bytes`` (default): ASCII characters stand for their byte and Python escapes (``\x00``, ``\n``) are decoded. ``hex``: hex digits, whitespace allowed (``00 00 01 00``). ``regex``: an ASCII regular expression over the raw bytes (``\xNN`` for other bytes; empty matches are not counted). ``text``: ``pattern`` encoded in ``encoding``.
   * - ``start``
     - int/string
     - **Optional.** Start of the region (default ``0``): an int (negative from the end) or an offset expression.
   * - ``end``
     - int/string
     - **Optional.** End of the region, exclusive (default: the end of the file). ``end`` before ``start`` is an error.
   * - ``encoding``
     - string
     - **Optional.** Encoding for ``text``. Default ``utf-8``; ``utf-16-le``, ``utf-16-be``, ... (``utf-16`` without byte order is an error).
   * - ``expected_count``
     - integer
     - **Optional.** Non-negative number to compare the count with. Default: ``1``. ``0`` asserts absence.
   * - ``comparison_type``
     - string
     - **Optional.** ``equals`` (default), ``greater``, ``less``, ``greater_equal`` or ``less_equal``. The default is exact, like every other count function: write ``comparison_type: greater_equal`` for "at least once".

Usage Example
-------------

.. code-block:: yaml

   tests:
     - name: two_sessions_in_metadata
       function: binary.pattern_count
       parameter:
         dst: /home/user/app/cache/entry.bin
         pattern: 'session-[0-9a-f]{8}'
         pattern_type: regex
         start: u32be@-4
         end: -4
         expected_count: 2

     - name: name_gone_from_records
       function: binary.pattern_count
       parameter:
         dst: /home/user/app/data/index.bin
         pattern: Report
         pattern_type: text
         encoding: utf-16-le
         start: 6
         expected_count: 0

Common Use Cases
----------------

**Records in one part of a file**
  Count record markers after a header or inside a metadata block only.

**A value is gone from a block**
  ``expected_count: 0`` on the region that held it, so other copies elsewhere in the file do not count.

See Also
--------

* :doc:`/reference/testfunctions/text/occurrence_count` — the whole file, several encodings at once.
* :doc:`struct_value_matches` — one value at an offset.

Return Values
-------------

**Success**
  The count comparison holds.

**Failure**
  The region was read and the count comparison does not hold.

**Error**
  The file does not exist or is a directory, a glob matches no file or more than one, an empty or
  invalid pattern (escape, hex, regex, not encodable), an unknown ``pattern_type`` or encoding, a
  ``!re`` / ``!timestamp`` placeholder as pattern, a malformed offset expression, an offset outside
  the file, ``end`` before ``start``, a region over the read cap, a negative ``expected_count`` or an
  unknown ``comparison_type``.
