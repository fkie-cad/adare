Binary
======

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Functions: 4
:Category: Binary Containers

.. adare-testfunction-collection:: binary

Offset Expressions
------------------

Every ``offset``, ``start`` and ``end`` parameter takes an int or an offset expression:

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Expression
     - Meaning
   * - ``16``, ``0x10``
     - Absolute offset from the start of the file.
   * - ``-4``
     - Counted from the end: the last four bytes start at ``-4``.
   * - ``u32be@-4``
     - Read a big-endian u32 at ``-4`` and use it as the offset (a trailer pointer).
   * - ``u32be@-4+8``
     - That pointer plus 8 (``+N`` / ``-N`` add to the term before them).
   * - ``u32le@(u32le@0+4)``
     - Parentheses add inside the read position: the pointer stored 4 bytes after the one at 0.
   * - ``u32le@u32le@0``
     - Pointer to a pointer (at most 4 ``@`` reads per expression).
   * - ``find:6b6579``
     - Offset of the first occurrence of the hex bytes; ``find:6b6579+3`` points just past it.

Integer types for ``@``: ``u8``, ``i8``, ``u16le``, ``u16be``, ``i16le``, ``i16be``, ``u32le``,
``u32be``, ``i32le``, ``i32be``, ``u64le``, ``u64be``, ``i64le``, ``i64be``. Grammar::

   expr     := term (('+' | '-') NUMBER)*
   term     := ['-'] NUMBER | TYPE '@' operand | 'find:' HEX
   operand  := ['-'] NUMBER | TYPE '@' operand | '(' expr ')'

A negative number counts from the end where it is written (``-8+2`` is ``size - 6``). A malformed
expression, an offset outside the file, a pointer read past the end and a ``find:`` pattern that
does not occur are errors: the test never looked at the claimed value.

Results
-------

A test fails only when the file was read and the value, key or count does not match. A missing
file, a glob matching no file or more than one, an offset that cannot be resolved, a value that
cannot be decoded, a region over the read cap (``ADARE_ARCHIVE_MAX_BYTES``) and bad parameters are
errors. ``archive.tar!/member`` reads a file inside an archive. Absence is checked with
``pattern_count`` or ``pair_count`` and ``expected_count: 0``.

Test Functions
--------------

.. csv-table::
   :file: ../../../_static/tables/testfunctions_binary.csv
   :widths: 20, 10, 40, 30
   :header-rows: 1
   :class: sdtable
   :name: binary-functions-table



.. toctree::
   :maxdepth: 1
   :hidden:

   struct_value_matches
   pattern_count
   pair_value_matches
   pair_count
