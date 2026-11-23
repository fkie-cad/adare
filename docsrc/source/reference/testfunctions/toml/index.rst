TOML
====

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Functions: 4
:Category: TOML Data

.. adare-testfunction-collection:: toml

Overview
--------

Tables are dictionaries: ``[server]`` with ``port = 8080`` is ``server.port``. An array of tables (``[[items]]``) is an array: ``items[*].name`` selects every entry, ``items[0].name`` the first. A quoted table or key name with dots (``["app.window"]``) uses quotes in brackets: ``['app.window'].width``. Files are read as UTF-8.

Values keep their TOML types (integers, floats, booleans, strings). Dates and times become ISO 8601 strings: ``1979-05-27`` (local date), ``07:32:00`` (local time), ``1979-05-27T07:32:00`` (local date-time), ``1979-05-27T07:32:00-08:00`` (offset date-time; ``Z`` becomes ``+00:00``).

Absence is checked with ``value_count`` and ``expected_count: 0``: it passes when the key path selects
nothing, while a missing or invalid file is an error. A missing file, a glob matching no file or more
than one, an unreadable or invalid file and bad parameters are errors; a test fails only when the file
was read and its content does not match.

Test Functions
--------------

.. csv-table::
   :file: ../../../_static/tables/testfunctions_toml.csv
   :widths: 20, 10, 40, 30
   :header-rows: 1
   :class: sdtable
   :name: toml-functions-table



.. toctree::
   :maxdepth: 1
   :hidden:

   contains_key
   value_matches
   value_count
   values_compare
