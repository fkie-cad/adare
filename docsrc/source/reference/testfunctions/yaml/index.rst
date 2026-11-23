YAML
====

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Functions: 4
:Category: YAML Data

.. adare-testfunction-collection:: yaml

Overview
--------

A file with one document is addressed from its root. A file with several documents (separated by ``---``) is a top-level list with one entry per document: ``[0].kind`` is ``kind`` in the first document, ``[*].kind`` in all of them. An empty file has no keys. Files are read as UTF-8, or UTF-16 with a byte order mark.

Values keep their YAML 1.1 types: ``5`` is an integer, ``true``/``yes``/``on`` and ``false``/``no``/``off`` are booleans, ``null`` is ``None``. Dates and timestamps become ISO 8601 strings: ``2024-01-15``, ``2024-01-15T10:30:00``, and a ``Z`` zone becomes ``+00:00``. ``!!binary`` values become lowercase hex strings.

Absence is checked with ``value_count`` and ``expected_count: 0``: it passes when the key path selects
nothing, while a missing or invalid file is an error. A missing file, a glob matching no file or more
than one, an unreadable or invalid file and bad parameters are errors; a test fails only when the file
was read and its content does not match.

Test Functions
--------------

.. csv-table::
   :file: ../../../_static/tables/testfunctions_yaml.csv
   :widths: 20, 10, 40, 30
   :header-rows: 1
   :class: sdtable
   :name: yaml-functions-table



.. toctree::
   :maxdepth: 1
   :hidden:

   contains_key
   value_matches
   value_count
   values_compare
