png_text_matches
================

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: Image Metadata
:Function Name: ``png_text_matches``

**Tests if a PNG text chunk (tEXt/zTXt/iTXt) with a keyword exists or matches an expected value.**

Without ``expected_value`` it passes when a text chunk with ``keyword`` exists; with it, when one such
chunk's text matches (``wildcard_mode: all``: every such chunk's text). All chunks up to ``IEND``
are read, also those after the image data, and every CRC is verified. For an absent keyword use
``png_text_count`` with ``expected_count: 0``.

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
     - **Required.** Chunk keyword, compared exactly (case-sensitive).
   * - ``expected_value``
     - string/int/float/bool
     - **Optional.** Expected text; a YAML number or boolean is compared as its text. A ``!re``/``!timestamp`` tag or ``{{placeholder}}`` is matched by type. Default: only check the keyword exists.
   * - ``regex_match``
     - boolean
     - **Optional.** Search ``expected_value`` as a regex (``re.search``, unanchored). Default: ``false``.
   * - ``wildcard_mode``
     - string
     - **Optional.** With several chunks for ``keyword``: ``any``: one must match; ``all``: every one must match. Ignored without ``expected_value``; other values are an error. Default: ``any``.

Usage Example
-------------

.. code-block:: yaml

   tests:
     - name: png_comment
       function: image.png_text_matches
       parameter:
         dst: /home/user/Pictures/photo.png
         keyword: Comment
         expected_value: exported by app

     - name: png_has_source
       function: image.png_text_matches
       parameter:
         dst: /home/user/Pictures/photo.png
         keyword: Source

     - name: png_every_comment_from_app
       function: image.png_text_matches
       parameter:
         dst: /home/user/Pictures/photo.png
         keyword: Comment
         expected_value: 'by app'
         regex_match: true
         wildcard_mode: all

Return Values
-------------

**Success**
  A chunk with the keyword exists (and its text matches).

**Failure**
  The file was read and has no chunk with the keyword (the details list the keywords found), or no
  such chunk's text matches (``wildcard_mode: all``: one does not match; the details list the
  non-matching texts).

**Error**
  The file does not exist, a glob matches no file or more than one, the file cannot be read, a bad
  PNG signature, a truncated chunk, a CRC mismatch in any chunk, a malformed or undecompressable text
  chunk, no ``IEND`` chunk, an invalid regex, or a ``wildcard_mode`` other than ``any``/``all``.
