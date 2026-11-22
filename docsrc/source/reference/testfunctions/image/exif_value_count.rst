exif_value_count
================

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: Image Metadata
:Function Name: ``exif_value_count``

**Tests the number of occurrences of an EXIF tag, optionally only those with a matching value (0 = absent).**

Each IFD that has the tag counts once (only occurrences whose text form matches ``expected_value``, if
given). ``expected_count: 0`` asserts the tag was not written, for example that location data was removed
on export; a missing or corrupt file is still an error, never a pass.

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
     - **Required.** Path to the image. A glob must match exactly one file; ``archive.zip!/member`` reads a file inside an archive.
   * - ``tag``
     - string/int
     - **Required.** Tag name or number (same lookup as ``exif_value_matches``).
   * - ``expected_count``
     - integer
     - **Required.** Non-negative number to compare the count with. ``0`` asserts absence.
   * - ``expected_value``
     - string/int/float/bool
     - **Optional.** Only count occurrences whose value matches (same formatting as ``exif_value_matches``). Default: count every occurrence.
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
     - name: exif_no_location
       function: image.exif_value_count
       parameter:
         dst: /home/user/Pictures/photo.jpg
         tag: GPSLatitude
         expected_count: 0

Common Use Cases
----------------

**Photo metadata was stripped**
  ``expected_count: 0`` on a GPS or camera tag after an export that removes metadata.

See Also
--------

* :doc:`exif_value_matches` — the value of a tag.
* :doc:`png_text_count` — PNG text chunks.
* :doc:`/guide/absence` — checking that something is absent.

Return Values
-------------

**Success**
  The count comparison holds.

**Failure**
  The file was read and the count comparison does not hold.

**Error**
  The file does not exist, a glob matches no file or more than one, the file cannot be read, is not
  an image or has corrupt EXIF data, an unknown tag name or invalid tag number, a negative or
  non-integer ``expected_count``, an unknown ``comparison_type``, or an invalid regex.
