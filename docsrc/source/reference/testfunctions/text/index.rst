Text
====

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Functions: 3
:Category: Text and Binary Content

The **Text** testset counts content in any file: occurrences of a string or byte sequence in the raw bytes (binary files included), lines of a text file that contain a string or match a regex, and the order of such lines.

Overview
--------

``occurrence_count`` searches the raw bytes and never decodes the file, so it works on databases, caches and other binary files. A string can be searched in several encodings at once (``encoding: [utf-8, utf-16-le]``); ``content_type: bytes`` and ``content_type: hex`` search exact byte sequences.

``line_count`` decodes the file as text (a BOM selects UTF-8/16/32, BOM-less UTF-16 is detected, otherwise UTF-8 or the given ``encoding``) and counts the lines that contain ``content``.

``lines_in_order`` decodes the file the same way and checks that lines matching several patterns occur in the given order (a service started, then a file was opened, then deleted).

Absence is checked with ``expected_count: 0``. A missing file, a glob matching no file or more than one, an unreadable or undecodable file and bad parameters are errors; a test fails only when the file was read and the count does not hold.

Test Functions
--------------

.. csv-table::
   :file: ../../../_static/tables/testfunctions_text.csv
   :widths: 20, 10, 40, 30
   :header-rows: 1
   :class: sdtable
   :name: text-functions-table



.. toctree::
   :maxdepth: 1
   :hidden:

   occurrence_count
   line_count
   lines_in_order
