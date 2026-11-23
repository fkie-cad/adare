JSONL
=====

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Functions: 4
:Category: JSON Lines Data

The **JSONL** testset checks JSON Lines files (also called NDJSON): one JSON document per line, as written by event logs, history files and line-oriented exports.

Overview
--------

Every line is parsed on its own; blank lines are skipped and, by default, lines that are not valid JSON are ignored (``skip_malformed: false`` makes the first one an error). Key paths are dot paths inside each line's object: ``*`` expands all values of an object and ``name[*]`` all elements of an array. When a path yields several values, one matching value is enough.

``value_in_any_line`` checks one field, ``line_matches`` several fields of the same line (in one line or in all lines), ``line_count`` counts the lines that meet the conditions, and ``lines_in_order`` checks that records meeting several condition sets occur in the given order. Absence is checked with ``line_count`` and ``expected_count: 0``.

Files are decoded with a BOM (UTF-8/16/32) or BOM-less UTF-16 when present, otherwise as UTF-8 or the given ``encoding``. LZ4-compressed or archived files are read through the archive separator (``dst: /home/user/data/events.jsonl.gz!``). A missing file, a glob matching no file or more than one and an undecodable file are errors.

Test Functions
--------------

.. csv-table::
   :file: ../../../_static/tables/testfunctions_jsonl.csv
   :widths: 20, 10, 40, 30
   :header-rows: 1
   :class: sdtable
   :name: jsonl-functions-table



.. toctree::
   :maxdepth: 1
   :hidden:

   line_matches
   line_count
   value_in_any_line
   lines_in_order
