Image
=====

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Functions: 5
:Category: Image Metadata

.. adare-testfunction-collection:: image

Reading the Metadata
--------------------

**PNG text chunks** are read by a standard-library chunk walker, not an image library: it checks the
signature, visits every chunk up to ``IEND`` (also chunks after the image data), verifies every chunk's
CRC and keeps duplicate keywords. ``tEXt`` is Latin-1, ``zTXt`` zlib-compressed Latin-1, ``iTXt`` UTF-8,
compressed or not (its language tag and translated keyword are ignored). Keywords are compared exactly.

**EXIF tags** are read with Pillow from IFD0, the Exif IFD and the GPS IFD (JPEG, PNG ``eXIf``, TIFF, WebP).
A tag is given by name as in Pillow's tag tables (``Make``, ``DateTimeOriginal``, ``GPSLatitude``) or by
number (``0x9003``, ``36867``). Values are compared by their text form:

* text as stored, trailing NUL bytes removed
* integers in decimal; rationals and floats as decimals: ``72`` (72/1), ``2.8`` (28/10), ``0.004`` (1/250), ``nan`` (x/0)
* sequences joined with ``", "``: a GPS coordinate is ``51, 30, 12.5``
* bytes as text when they are printable UTF-8, else lowercase hex (``0102ff``); the user comment (0x9286) without its 8-byte character-code prefix; the UTF-16 title/comment/author/keywords/subject tags (0x9C9B-0x9C9F) decoded
* a YAML number in ``expected_value`` is formatted the same way (``72``); write a sequence as text (``51, 30, 12.5``)

**Dimensions** are read with Pillow without decoding the pixel data.

Test Functions
--------------

.. csv-table::
   :file: ../../../_static/tables/testfunctions_image.csv
   :widths: 20, 10, 40, 30
   :header-rows: 1
   :class: sdtable
   :name: image-functions-table



.. toctree::
   :maxdepth: 1
   :hidden:

   png_text_matches
   png_text_count
   exif_value_matches
   exif_value_count
   dimensions_match
