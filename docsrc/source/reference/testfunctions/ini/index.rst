INI
===

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Functions: 4
:Category: INI Configuration

The **INI** testset checks sections, keys and values of INI-style configuration files with a tolerant line parser.

Overview
--------

The parser accepts what applications actually write, instead of rejecting or rewriting it:

* ``[name]`` starts a section (the name is stripped; a comment after the closing bracket is allowed). Keys before the first header belong to section ``''``.
* Lines whose first non-blank character is ``;`` or ``#`` are comments; blank lines are skipped.
* The first ``=`` splits key and value, both stripped. Values are raw: quotes, inline comments and ``%(name)s`` stay as written (``a = "x" ; note`` has the value ``"x" ; note``). There are no continuation lines.
* Lines without ``=`` (that are not headers or comments) are ignored, so a bare word is not a key.
* Duplicate sections and duplicate keys are all kept: ``value_count`` counts them, ``value_matches`` passes when one occurrence matches, and keys of a section that appears twice are searched together.
* ``case_sensitive: false`` compares section and key names case-insensitively; values are always compared as given.
* ``encoding`` defaults to auto: a byte order mark wins, BOM-less UTF-16 is recognised, everything else is read as UTF-8.

Absence is checked with ``value_count`` and ``expected_count: 0``. A missing file, a glob matching no
file or more than one, an unreadable or undecodable file and bad parameters are errors; a test fails
only when the file was read and its content does not match.

Test Functions
--------------

.. csv-table::
   :file: ../../../_static/tables/testfunctions_ini.csv
   :widths: 20, 10, 40, 30
   :header-rows: 1
   :class: sdtable
   :name: ini-functions-table



.. toctree::
   :maxdepth: 1
   :hidden:

   section_exists
   contains_key
   value_matches
   value_count
