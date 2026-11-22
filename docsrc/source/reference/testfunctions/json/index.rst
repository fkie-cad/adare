JSON 
============

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Functions: 4
:Category: JSON Data Validation

The **JSON** testset provides comprehensive JSON file testing capabilities for ADARE experiments. This testset focuses on JSON structure validation, key existence checking, value comparison, and array element verification.

Overview
--------

The JSON testset enables detailed validation of JSON files and data structures. It includes functions to check for key existence using dot notation paths, validate values with support for wildcards and regular expressions, and verify array contents with flexible matching options.

Key paths are dot paths from the root: ``*`` expands all values of an object, ``name[*]`` all elements of an array, ``name[0]`` / ``name[-1]`` one element; a leading ``[0]`` / ``[*]`` addresses a top-level array and ``['a.b']`` a key that contains dots. LZ4-compressed JSON is read through the archive separator (``dst: /home/user/data/store.jsonlz4!``), a file inside an archive with ``archive.zip!/member``.

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
