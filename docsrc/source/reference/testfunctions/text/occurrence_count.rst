occurrence_count
================

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: Text and Binary Content
:Function Name: ``occurrence_count``

**Tests how often a string or byte sequence occurs in a (text or binary) file.**

Counts the non-overlapping occurrences of ``content`` in the raw bytes of the file and passes when the count satisfies ``comparison_type`` against ``expected_count``. The file is not decoded, so binary files work. ``expected_count: 0`` asserts that a value is gone; a missing file is still an error, never a pass.

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
     - **Required.** Path to the file. A glob must match exactly one file; ``archive.zip!/member`` reads a file inside an archive. Files over the read cap (``ADARE_ARCHIVE_MAX_BYTES``) are an error.
   * - ``content``
     - string
     - **Required.** What to find; must not be empty. Interpreted according to ``content_type``.
   * - ``expected_count``
     - integer
     - **Required.** Non-negative number to compare the count with. ``0`` asserts absence.
   * - ``content_type``
     - string
     - **Optional.** ``string`` (default): ``content`` encoded in each of ``encodings``. ``bytes``: ASCII characters stand for their byte and Python escapes (``\x00``, ``\n``, ``\\``) are decoded; a non-ASCII character or an unknown escape is an error (write ``\xNN``, or use ``string`` with an encoding). ``hex``: hex digits, whitespace allowed (``4d 5a 90 00``).
   * - ``encodings``
     - list
     - **Optional.** Encodings for ``string`` mode. A list of names, default ``[utf-8]``, or a single name. The counts of the distinct encoded forms are summed; a match on bytes already counted for an earlier form is skipped. ``utf-16`` / ``utf-32`` search both byte orders without BOM. Forms are matched at any byte offset.
   * - ``case_sensitive``
     - boolean
     - **Optional.** ``false`` matches each character in any of its one-character case forms (``a`` / ``A``, ``ä`` / ``Ä``); case mappings to several characters (sharp s to ``SS``) are not matched. ``string`` mode only. Default: ``true``.
   * - ``comparison_type``
     - string
     - **Optional.** ``equals``, ``greater``, ``less``, ``greater_equal`` or ``less_equal``. Default: ``equals``.

Usage Example
-------------

.. code-block:: yaml

   tests:
     - name: token_wiped_from_cache
       function: text.occurrence_count
       parameter:
         dst: /home/user/data/cache.bin
         content: secret-token
         encodings: [utf-8, utf-16-le]
         expected_count: 0

     - name: header_bytes_once
       function: text.occurrence_count
       parameter:
         dst: /home/user/data/blob.dat
         content: "4d 5a 90 00"
         content_type: hex
         expected_count: 1

Notes
-----

* In YAML, ``content: "\x00ab"`` (double quotes) is decoded by YAML itself; in single quotes
  (``'\x00ab'``) the escape reaches ``content_type: bytes`` unchanged and is decoded there. Both
  give the same bytes.
* A one-character pattern found in several encodings can overlap (the UTF-8 ``a`` is part of the
  UTF-16 ``a``); each encoding is counted on its own.

Return Values
-------------

**Success**
  The count comparison holds.

**Failure**
  The file was read and the count comparison does not hold.

**Error**
  The file does not exist or is a directory, a glob matches no file or more than one, the file
  cannot be read or exceeds the read cap, empty ``content``, an unknown ``content_type`` or
  encoding, ``content`` not encodable in a listed encoding, an invalid escape or hex string,
  ``case_sensitive: false`` outside ``string`` mode, a negative or non-integer
  ``expected_count``, or an unknown ``comparison_type``.
