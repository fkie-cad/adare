Property list (plist)
=====================

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Functions: 4
:Category: Property List Data

.. adare-testfunction-collection:: plist

Overview
--------

Property lists are dictionaries, arrays and scalar values. Keys in preference files often contain dots (``com.example.lastVersion``); address them with quotes in brackets: ``['com.example.lastVersion']``, also mid-path (``recent['com.example.doc'].name``).

``<date>`` values become ISO 8601 strings without zone (plist dates are UTC): ``2024-01-15T10:30:00``. ``<data>`` values become lowercase hex strings (``0a1bff``). ``<integer>``, ``<real>`` and ``<true/>``/``<false/>`` stay numbers and booleans.

Absence is checked with ``value_count`` and ``expected_count: 0``: it passes when the key path selects
nothing, while a missing or invalid file is an error. A missing file, a glob matching no file or more
than one, an unreadable or invalid file and bad parameters are errors; a test fails only when the file
was read and its content does not match.

Test Functions
--------------

.. csv-table::
   :file: ../../../_static/tables/testfunctions_plist.csv
   :widths: 20, 10, 40, 30
   :header-rows: 1
   :class: sdtable
   :name: plist-functions-table



.. toctree::
   :maxdepth: 1
   :hidden:

   contains_key
   value_matches
   value_count
   values_compare
