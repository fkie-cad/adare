struct_value_matches
====================

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: Binary Containers
:Function Name: ``struct_value_matches``

**Tests a number, string, byte sequence or timestamp read at an offset of a binary file.**

Resolves ``offset`` (see :doc:`index` for offset expressions), reads one value of ``value_format``
there and passes when it compares to ``expected_value``. Only the bytes needed are read, so large
files work.

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
   * - ``offset``
     - int/string
     - **Required.** Where the value starts: an int (negative from the end) or an offset expression such as ``u32be@-4+8``.
   * - ``value_format``
     - string
     - **Required.** ``u8``, ``i8``, ``u16le`` ... ``i64be`` (integers), ``f32le``, ``f32be``, ``f64le``, ``f64be`` (floats), ``bytes:<n>`` (compared as lowercase hex), ``string:<n>`` (n bytes decoded with ``encoding``, trailing NULs dropped) or ``cstring`` (up to the first NUL; ``\x00\x00`` in UTF-16; at most 64 KiB).
   * - ``expected_value``
     - string/int/float
     - **Required.** Numbers and timestamps compare by value; strings as text (a number written here as its text); ``bytes:<n>`` as hex, whitespace ignored (``de ad be ef``). A ``!re`` tag or a ``{{placeholder}}`` compares the value's text; a ``!timestamp`` placeholder with ``epoch``/``unit`` reads a numeric field as a time.
   * - ``comparison_type``
     - string
     - **Optional.** ``equals`` (default), ``not_equals``, ``greater``, ``less``, ``greater_equal``, ``less_equal``. Ordered comparisons need numbers or timestamps; text and ``bytes`` take ``equals`` / ``not_equals`` only.
   * - ``tolerance``
     - number
     - **Optional.** For ``equals`` / ``not_equals`` of numbers or timestamps: the largest difference that still counts as equal (seconds for timestamps). Floats are compared exactly otherwise (an ``f32`` 1.1 is not 1.1).
   * - ``regex_match``
     - boolean
     - **Optional.** Treat a string ``expected_value`` as a regex searched (``re.search``) in the value's text. Default: ``false``.
   * - ``encoding``
     - string
     - **Optional.** Encoding of ``string`` / ``cstring`` values. Default ``utf-8``; ``utf-16-le``, ``utf-16-be``, ``latin-1``, ... (``utf-16`` without byte order is an error).
   * - ``value_type``
     - string
     - **Optional.** ``auto`` (default), ``number`` or ``timestamp``. ``auto`` compares as timestamps when ``timestamp_epoch`` or ``time_format`` is set, else as numbers, else as ISO 8601 / RFC 2822 timestamps.
   * - ``timestamp_epoch``
     - int
     - **Optional.** Read a number as time since 1 January of ``1970``, ``1601`` or ``2001``. A numeric ``expected_value`` is read the same way; an ISO 8601 one as written.
   * - ``timestamp_unit``
     - string
     - **Optional.** Unit of such numbers: ``s`` (default), ``ms``, ``us``, ``ns``, ``100ns``.
   * - ``utc_offset``
     - string
     - **Optional.** Zone of times without one, e.g. ``+02:00``. Default: UTC.
   * - ``time_format``
     - string
     - **Optional.** ``strptime`` format of a string timestamp (``%d.%m.%Y %H:%M``); ``expected_value`` is read with the same format.

Usage Example
-------------

.. code-block:: yaml

   tests:
     # the last 4 bytes hold the offset of the metadata block; its third u32 is a time
     - name: entry_modified_after_start
       function: binary.struct_value_matches
       parameter:
         dst: /home/user/app/cache/entry.bin
         offset: u32be@-4+8
         value_format: u32be
         timestamp_epoch: 1970
         expected_value: '2026-01-01T10:00:00Z'
         comparison_type: greater_equal

     # record 2 of an index of 32-byte records after a 6-byte header, name at +20
     - name: third_record_name
       function: binary.struct_value_matches
       parameter:
         dst: /home/user/app/data/index.bin
         offset: 90
         value_format: string:12
         expected_value: !re 'report-\d+'

     - name: hit_count_at_least_two
       function: binary.struct_value_matches
       parameter:
         dst: /home/user/app/cache/entry.bin
         offset: u32be@-4+4
         value_format: u32be
         expected_value: 2
         comparison_type: greater_equal

Common Use Cases
----------------

**A counter or flag changed**
  A header or metadata field (hit count, state flag) after an action in the GUI.

**A timestamp field**
  Times stored as numbers (``timestamp_epoch``/``timestamp_unit``) compared with the time of an action.

**A string in a block a trailer points to**
  ``cstring`` at ``u32be@-4+N`` finds the field even when the payload before it changes size.

See Also
--------

* :doc:`pair_value_matches` — a value in a key/value string table.
* :doc:`pattern_count` — how often a byte pattern occurs in a region.
* :doc:`/reference/testfunctions/text/occurrence_count` — a string anywhere in a file, several encodings.

Return Values
-------------

**Success**
  The value read compares to ``expected_value``.

**Failure**
  The file was read and the value does not match.

**Error**
  The file does not exist or is a directory, a glob matches no file or more than one, a malformed
  offset expression or value format, an offset or value outside the file, a ``find:`` pattern that
  does not occur, a ``cstring`` without terminator, a string not valid in ``encoding``, a NaN or
  infinite float, a value or ``expected_value`` that is no number or timestamp for an ordered
  comparison, an invalid regex or placeholder, or other bad parameters.
