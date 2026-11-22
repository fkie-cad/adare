exif_value_matches
==================

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: Image Metadata
:Function Name: ``exif_value_matches``

**Tests if an EXIF tag (IFD0, Exif or GPS IFD) equals or matches an expected value.**

Reads EXIF data with Pillow and compares the tag's text form (see :doc:`index`) with ``expected_value``.
A tag present in several IFDs passes when one occurrence matches (``wildcard_mode: all``: every
occurrence); a missing tag fails. For an absent tag
use ``exif_value_count`` with ``expected_count: 0``.

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
     - **Required.** Path to the image (JPEG, PNG, TIFF, WebP). A glob must match exactly one file; ``archive.zip!/member`` reads a file inside an archive.
   * - ``tag``
     - string/int
     - **Required.** Tag name (``Make``, ``DateTimeOriginal``, ``GPSLatitude``) or number (``0x9003``, ``36867``). Main-table names are looked up in IFD0 and the Exif IFD, GPS names in the GPS IFD, numbers in all three. An unknown name is an error.
   * - ``expected_value``
     - string/int/float/bool
     - **Required.** Compared with the value's text form; a YAML number is formatted the same way (``2.8``); write a sequence as text (``51, 30, 12.5``). A ``!re``/``!timestamp`` tag or ``{{placeholder}}`` is matched by type.
   * - ``regex_match``
     - boolean
     - **Optional.** Search ``expected_value`` as a regex (``re.search``, unanchored). Default: ``false``.
   * - ``wildcard_mode``
     - string
     - **Optional.** With the tag in several IFDs (a number is looked up in all three): ``any``: one must match; ``all``: every one must match. Other values are an error. Default: ``any``.

Usage Example
-------------

.. code-block:: yaml

   tests:
     - name: exif_capture_time
       function: image.exif_value_matches
       parameter:
         dst: /home/user/Pictures/photo.jpg
         tag: DateTimeOriginal
         expected_value: "2024:05:01 12:00:00"

     - name: exif_latitude
       function: image.exif_value_matches
       parameter:
         dst: /home/user/Pictures/photo.jpg
         tag: GPSLatitude
         expected_value: '51, 30, 12.5'

     - name: exif_software_everywhere
       function: image.exif_value_matches
       parameter:
         dst: /home/user/Pictures/photo.jpg
         tag: Software
         expected_value: '^Editor '
         regex_match: true
         wildcard_mode: all

Return Values
-------------

**Success**
  The tag matches (with several occurrences: one of them, or every one with ``wildcard_mode: all``).

**Failure**
  The file was read and the tag is missing, no occurrence matches, or (``wildcard_mode: all``) one
  does not match; the details list the non-matching values.

**Error**
  The file does not exist, a glob matches no file or more than one, the file cannot be read, is not
  an image or has corrupt EXIF data, an unknown tag name or invalid tag number, an invalid regex, or a
  ``wildcard_mode`` other than ``any``/``all``.
