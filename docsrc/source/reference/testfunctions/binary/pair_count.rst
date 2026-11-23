pair_count
==========

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: Binary Containers
:Function Name: ``pair_count``

**Tests how often a key (optionally with a value) occurs in a key/value string table of a binary file.**

Reads the table as :doc:`pair_value_matches` does and counts the entries of ``key`` (only those
whose value matches ``expected_value``, if given). ``expected_count: 0`` asserts that a metadata
element is absent; a missing file or an unreadable table is still an error, never a pass.

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
     - **Required.** Key to count.
   * - ``expected_count``
     - integer
     - **Required.** Non-negative number to compare the count with. ``0`` asserts absence.
   * - ``expected_value``
     - string/int/float/null
     - **Optional.** Only count entries whose value matches (as in ``pair_value_matches``). Default: ``null``, every entry of ``key`` counts and no value is decoded.
   * - ``start``
     - int/string
     - **Optional.** Offset of the first key (default ``0``): an int or an offset expression.
   * - ``end``
     - int/string
     - **Optional.** End of the table, exclusive (default: the end of the file).
   * - ``separator``
     - string
     - **Optional.** Bytes between the strings, ASCII and Python escapes. Default: NUL.
   * - ``encoding``
     - string
     - **Optional.** Encoding of keys and values. Default: ``utf-8``.
   * - ``regex_match``
     - boolean
     - **Optional.** Treat a string ``expected_value`` as a regex searched in each value. Default: ``false``.
   * - ``comparison_type``
     - string
     - **Optional.** ``equals`` (default), ``greater``, ``less``, ``greater_equal`` or ``less_equal``.

Usage Example
-------------

.. code-block:: yaml

   tests:
     - name: no_alternative_source
       function: binary.pair_count
       parameter:
         dst: /home/user/app/cache/entry.bin
         start: u32be@-4+16
         end: -4
         key: alt-source
         expected_count: 0

     - name: two_origins
       function: binary.pair_count
       parameter:
         dst: /home/user/app/cache/entry.bin
         start: u32be@-4+16
         end: -4
         key: origin
         expected_count: 2

Common Use Cases
----------------

**A metadata element was removed**
  ``expected_count: 0`` after a clean-up action.

See Also
--------

* :doc:`pair_value_matches` — the value of a key.
* :doc:`/guide/absence` — checking that something is absent.

Return Values
-------------

**Success**
  The count comparison holds.

**Failure**
  The table was read and the count comparison does not hold.

**Error**
  As for :doc:`pair_value_matches`, plus a negative ``expected_count`` or an unknown
  ``comparison_type``.
