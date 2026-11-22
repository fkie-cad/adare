png_text_count
==============

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: Image Metadata
:Function Name: ``png_text_count``

**Tests the number of PNG text chunks with a keyword, optionally only those with a matching text (0 = absent).**

Counts ``tEXt``, ``zTXt`` and ``iTXt`` chunks with ``keyword`` together (only those whose text matches
``expected_value``, if given) and compares the count with ``expected_count``. ``expected_count: 0`` asserts no
such chunk exists; a missing or corrupt file is still an error, never a pass.

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
     - **Required.** Path to the PNG file. A glob must match exactly one file; ``archive.zip!/member`` reads a file inside an archive.
   * - ``keyword``
     - string
     - **Required.** Chunk keyword, compared exactly.
   * - ``expected_count``
     - integer
     - **Required.** Non-negative number to compare the count with. ``0`` asserts absence.
   * - ``expected_value``
     - string/int/float/bool
     - **Optional.** Only count chunks whose text matches (same rules as ``png_text_matches``). Default: count every chunk with ``keyword``.
   * - ``regex_match``
     - boolean
     - **Optional.** Search ``expected_value`` as a regex. Default: ``false``.
   * - ``comparison_type``
     - string
     - **Optional.** ``equals``, ``greater``, ``less``, ``greater_equal`` or ``less_equal``. Default: ``equals``.

Usage Example
-------------

.. code-block:: yaml

   tests:
     - name: png_comment_stripped
       function: image.png_text_count
       parameter:
         dst: /home/user/Pictures/photo.png
         keyword: Comment
         expected_count: 0

Common Use Cases
----------------

**Metadata was stripped**
  ``expected_count: 0`` on a keyword after an export that removes metadata.

**A keyword is written once**
  No duplicate text chunks after a re-save.

See Also
--------

* :doc:`png_text_matches` — the text of a chunk.
* :doc:`exif_value_count` — EXIF tags.
* :doc:`/guide/absence` — checking that something is absent.

Return Values
-------------

**Success**
  The count comparison holds.

**Failure**
  The file was read and the count comparison does not hold.

**Error**
  The file does not exist, a glob matches no file or more than one, the file cannot be read or is
  not a well-formed PNG (signature, truncation, CRC, text chunk, ``IEND``), a negative or non-integer
  ``expected_count``, an unknown ``comparison_type``, or an invalid regex.
