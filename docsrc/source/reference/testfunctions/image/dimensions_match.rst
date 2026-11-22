dimensions_match
================

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: Image Metadata
:Function Name: ``dimensions_match``

**Tests if an image has the expected width and/or height in pixels.**

Reads the size with Pillow (without decoding the pixel data) and checks only the dimensions given.

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
     - **Required.** Path to the image (any format Pillow reads). A glob must match exactly one file; ``archive.zip!/member`` reads a file inside an archive.
   * - ``width``
     - integer
     - **Optional.** Expected width in pixels (positive).
   * - ``height``
     - integer
     - **Optional.** Expected height in pixels (positive). Give at least one of ``width`` and ``height``.

Usage Example
-------------

.. code-block:: yaml

   tests:
     - name: thumbnail_size
       function: image.dimensions_match
       parameter:
         dst: /home/user/Pictures/thumbnail.png
         width: 256
         height: 256

Common Use Cases
----------------

**A screenshot or export was written**
  The saved image has the size of the screen or the chosen export size.

**A thumbnail was created**
  Cached thumbnails have a fixed size.

See Also
--------

* :doc:`exif_value_matches` — EXIF metadata of the image.
* :doc:`/reference/testfunctions/standard/file_size` — the file size in bytes.

Return Values
-------------

**Success**
  The given dimensions match.

**Failure**
  The file was read and a dimension differs (the details show the actual size).

**Error**
  The file does not exist, a glob matches no file or more than one, the file cannot be read or is
  not an image, neither ``width`` nor ``height`` is given, or one is not a positive integer.
