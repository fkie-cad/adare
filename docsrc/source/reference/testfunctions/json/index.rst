JSON 
============

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Functions: 5
:Category: JSON Data Validation

.. adare-testfunction-collection:: json

Overview
--------

Key paths are dot paths from the root: ``*`` expands all values of an object, ``name[*]`` all elements of an array, ``name[0]`` / ``name[-1]`` one element; a leading ``[0]`` / ``[*]`` addresses a top-level array and ``['a.b']`` a key that contains dots. LZ4-compressed JSON is read through the archive separator (``dst: /home/user/data/store.jsonlz4!``), a file inside an archive with ``archive.zip!/member``.

Every JSON function takes ``encoding``: by default UTF-8/16/32 is detected with or without BOM; a name (``latin-1``) decodes BOM-less files with it. ``expected_value`` is required wherever a value is compared (``value_matches``, ``array_contains``); an invalid ``!re`` or unknown placeholder is an error.

Absence is checked with ``value_count`` and ``expected_count: 0``: it passes when the key path selects nothing (or no value matches), while a missing or invalid file is an error.

Test Functions
--------------

.. csv-table::
   :file: ../../../_static/tables/testfunctions_json.csv
   :widths: 20, 10, 40, 30
   :header-rows: 1
   :class: sdtable
   :name: json-functions-table



.. toctree::
   :maxdepth: 1
   :hidden:

   contains_key
   value_matches
   array_contains
   value_count
   values_compare
