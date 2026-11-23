Choosing testfunctions
======================

One finding is one test, and each test calls one testfunction. ADARE has about seventy of
them, and several look alike: three ways to count lines, two to find a string, a presence
and a count test for every structured format. This page picks the right one for a goal
and says which neighbour *not* to use.

To search from the command line, describe the goal. The results say what each function
supports and does not, and which goals it is not for; ``adare test info`` then shows the
whole contract (parameters, allowed values, outcomes, limits, examples). Shared syntax such
as archives in ``dst`` is in :doc:`/reference/testfunctions/features`:

.. code-block:: bash

   adare test search "value was wiped from the cache"
   adare test info text.occurrence_count

The full list is in :doc:`/reference/testfunctions/index`.

Goal → testfunction
-------------------

Files and folders
~~~~~~~~~~~~~~~~~

.. list-table::
   :widths: 34 30 36
   :header-rows: 1

   * - Goal
     - Use
     - Not this one
   * - A file was created or saved
     - ``standard.file_exists``
     - ``standard.file_count``: only when the number matters
   * - A file was deleted or never written
     - ``standard.file_does_not_exist``
     - ``expect_to_fail`` on ``file_exists``: reads worse in results
   * - How many files match a glob (3 logs, at least one export, none left)
     - ``standard.file_count``
     - ``standard.file_exists``: passes on any match, cannot say "exactly 3"
   * - A file is empty, non-empty, or grew past a size
     - ``standard.file_size`` (``expected_size: 0``, ``comparison_type: greater``)
     - ``standard.file_content_equals`` with an empty ``content``: says less
   * - A folder exists, is gone, or holds given entries
     - ``standard.dir_exists``, ``standard.dir_does_not_exist``, ``standard.dir_content``
     - ``standard.file_exists``: a directory is not a file
   * - A file is byte-identical to a known one
     - ``standard.file_hash_matches``
     - ``standard.file_content_equals``: text only
   * - Modified, accessed or created time (MACB)
     - ``standard.file_timestamps``
     -
   * - Mode, owner or group (Linux)
     - ``standard.file_permissions``
     -

Strings and text files
~~~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :widths: 34 30 36
   :header-rows: 1

   * - Goal
     - Use
     - Not this one
   * - A value or marker was written into a text file
     - ``standard.file_content_contains``
     - ``text.occurrence_count``: only when you count or need binary/several encodings
   * - A value occurs *n* times, or was wiped, in any file (database, cache, binary,
       UTF-16)
     - ``text.occurrence_count`` (``expected_count: 0`` for wiped)
     - ``standard.file_content_contains``: one encoding, no count, no absence
   * - The content has a given shape (a regular expression)
     - ``standard.file_content_matches_regex``
     - ``standard.file_content_contains``: refuses a ``!re`` placeholder (ERROR)
   * - Exactly this content
     - ``standard.file_content_equals``
     -
   * - How many lines of a text file contain a string or match a regex
     - ``text.line_count``
     - ``text.occurrence_count``: counts occurrences, not lines
   * - An action left a line in the last lines of a plain-text log
     - ``linux.log_entry_exists``
     - ``text.line_count``: searches the whole file, and counts

Structured files
~~~~~~~~~~~~~~~~

The same three shapes repeat for JSON, INI, plist, YAML and TOML: ``contains_key`` (a key is
there), ``value_matches`` (a value) and ``value_count`` (how many values, ``0`` = absent).

.. list-table::
   :widths: 34 30 36
   :header-rows: 1

   * - Goal
     - Use
     - Not this one
   * - A setting has a value (JSON, INI, plist, YAML, TOML)
     - ``<format>.value_matches``
     - ``<format>.contains_key``: does not check the value
   * - A key was written, whatever its value
     - ``<format>.contains_key``; INI section: ``ini.section_exists``
     -
   * - A value is above/below a number, later/earlier than a time, or within a tolerance
     - ``<format>.value_matches`` with ``comparison_type`` / ``tolerance``
     - ``regex_match`` on digits: compares text, not numbers
   * - Two values of one file: A earlier than B, A within 5 s of B, A = B + 1
     - ``<format>.values_compare`` (JSON, YAML, TOML, plist, XML)
     - two ``value_matches`` tests: cannot relate the values to each other
   * - A value changed by an action: after greater than before
     - ``<format>.values_compare`` with ``other_dst``, a copy saved before the action
       (:ref:`before-after-action`)
     - a fixed ``expected_value``: breaks when the starting value differs
   * - A value stored encoded (base64, hex, percent-encoded, JSON in a string)
     - ``value_decode`` on ``<format>.value_matches`` (:ref:`ordered-comparison`)
     - ``regex_match`` on the encoded text
   * - How many entries, or a key/value is absent
     - ``<format>.value_count`` (``expected_count: 0``)
     - ``expect_to_fail`` on ``value_matches``: also passes when *another* value is there
   * - A JSON list contains an entry
     - ``json.array_contains``
     - ``json.value_count`` with ``list[*]``: when you need a count
   * - A JSONL record with several fields (``type=login`` and ``user=alice``)
     - ``jsonl.line_matches``
     - ``jsonl.value_in_any_line``: one field only
   * - One field value anywhere in a JSONL log
     - ``jsonl.value_in_any_line``
     -
   * - How many JSONL records were written
     - ``jsonl.line_count``
     - ``text.line_count``: does not parse JSON
   * - A CSV record exists / how often / whole file
     - ``csv.contains_line`` / ``csv.row_count`` / ``csv.compare_rows``, ``csv.compare_files``
     - ``text.line_count``: a quoted field with a line break is one CSV record
   * - An XML element text or setting; office document properties (author of a ``.docx``)
     - ``xml.element_text_matches``
     - ``xml.xpath_result_matches``: for typed (number, boolean) results
   * - An XML attribute / element count or absence / element exists
     - ``xml.attribute_matches`` / ``xml.element_count`` / ``xml.element_exists``
     -

Databases, spreadsheets, images, system state
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :widths: 34 30 36
   :header-rows: 1

   * - Goal
     - Use
     - Not this one
   * - The rows a SQL query returns
     - ``sqlite.query_result`` (``expected_result``)
     - ``text.occurrence_count`` on the ``.db``: misses WAL content, no row context
   * - How many rows, or a row is gone
     - ``sqlite.row_count`` (``expected_count: 0``)
     -
   * - A spreadsheet cell / a row exists / how many rows / a sheet exists
     - ``excel.cell_value_matches`` / ``excel.contains_row`` / ``excel.row_count`` /
       ``excel.sheet_exists``
     -
   * - Photo metadata (camera, time, GPS)
     - ``image.exif_value_matches``; stripped: ``image.exif_value_count`` with ``0``
     -
   * - PNG text chunk (software, comment)
     - ``image.png_text_matches``; absent: ``image.png_text_count`` with ``0``
     -
   * - Image width or height
     - ``image.dimensions_match``
     -
   * - Registry key or value (Windows)
     - ``windows.registry_key_exists``, ``windows.registry_value_matches``
     -
   * - Service, process or user account (Linux)
     - ``linux.system_service_status``, ``linux.process_running``, ``linux.user_exists``
     -
   * - Something is (not) shown on screen, or *n* times
     - ``visual.exists``, ``visual.not_exists``, ``visual.count_equals``
       (see :doc:`icon-library`)
     -

Pairs that are easy to mix up
-----------------------------

``text.occurrence_count`` or ``standard.file_content_contains``
   ``file_content_contains`` answers "is this string in this text file?" in one encoding.
   ``occurrence_count`` searches the raw bytes for the string in one or several encodings at
   once (``encoding: [utf-8, utf-16-le]``), counts non-overlapping occurrences and so also
   asserts absence (``expected_count: 0``). Use it for binary files: databases, caches,
   memory dumps. Neither takes a ``!re`` placeholder in ``content``; for patterns use
   ``standard.file_content_matches_regex`` or ``text.line_count`` with ``regex_match``.

``text.line_count``, ``csv.row_count`` or ``jsonl.line_count``
   All three count, but different units. ``text.line_count`` counts physical lines of a text
   file that contain a string or match a regex. ``csv.row_count`` counts CSV *records* that
   match an ``entry`` layout, so a quoted field with a line break is one record.
   ``jsonl.line_count`` parses each line as JSON and counts the records that meet all
   ``conditions`` (key paths and values). Row counts of other formats: ``sqlite.row_count``,
   ``excel.row_count``, ``xml.element_count``.

``standard.file_count`` or ``standard.file_exists``
   ``file_exists`` passes when at least one match of a glob is a file. ``file_count`` compares
   the number of matches (files, or directories with ``kind``) with ``expected_count``; a
   glob without a match counts ``0`` and is not an error, so ``expected_count: 0`` asserts
   that a whole group of files is gone.

``value_count`` or ``value_matches``
   ``value_matches`` asserts what a value is; with a wildcard path, ``wildcard_mode``
   decides whether one or all values must match. ``value_count`` asserts how many values
   there are (or how many equal ``expected_value``). Absence is ``value_count`` with
   ``expected_count: 0``, never ``value_matches`` with ``expect_to_fail``: the latter also
   passes when the key holds a different value.

``standard.file_size`` for empty files
   A file that exists but is empty is ``standard.file_size`` with ``expected_size: 0``;
   non-empty is ``comparison_type: greater`` with ``expected_size: 0``. ``file_exists``
   alone passes for an empty file.

Files inside archives
---------------------

Every file testfunction reads a member of an archive through ``!`` in ``dst``; you do not
need a separate "archive" test. ``backup.tar.gz!/etc/app/config.json`` is a member of a tar,
``syslog.2.gz!`` the decompressed content of a single-file archive (gzip, bzip2, xz, LZ4,
Snappy), ``store.jsonlz4!`` the JSON text of an LZ4 store, and
``report.docx!/docProps/core.xml`` the metadata of an office document:

.. code-block:: yaml

   tests:
     - name: author_of_report
       function: xml.element_text_matches
       parameter:
         dst: /home/user/Documents/report.docx!/docProps/core.xml
         xpath: ./dc:creator
         expected_value: analyst
         namespaces:
           dc: http://purl.org/dc/elements/1.1/

Formats, globs and the mapping form: :doc:`archives`.

Timestamps stored as numbers
----------------------------

Many artifacts store a time as a number: Unix seconds in a SQLite column, milliseconds in
a JSON file, 100-nanosecond steps since 1601 in Windows artifacts. Compare them with a
``!timestamp`` placeholder and its ``epoch`` and ``unit`` options instead of converting by
hand; ``after``/``before`` take the times measured with ``save_timestamp`` around the action:

.. code-block:: yaml

   tests:
     - name: visit_time_in_interval
       function: sqlite.query_result
       parameter:
         dst: /home/user/data/app.db
         query: SELECT visited FROM visits WHERE url = 'https://example.org/'
         expected_result:
           - visited: !timestamp
               after: '{{before_visit}}'
               before: '{{after_visit}}'
               epoch: 1970
               unit: us

Supported epochs and units, and a table of common formats: "Numeric timestamps" in
:doc:`/reference/actions`.

To compare a stored time with a fixed time or with another value of the same file, the value
functions take ``comparison_type``, ``timestamp_epoch`` and ``timestamp_unit`` directly; see
:ref:`ordered-comparison`.

Checking that something is absent
---------------------------------

Absence is a count of zero or an inverted presence test:

- a file or folder: ``standard.file_does_not_exist``, ``standard.dir_does_not_exist``, a
  group of files: ``standard.file_count`` with ``expected_count: 0``;
- a string in any file: ``text.occurrence_count`` with ``expected_count: 0``;
- a key, value, row or record: the format's count function with ``expected_count: 0``
  (``json.value_count``, ``csv.row_count``, ``sqlite.row_count``, ``xml.element_count``, ...);
- otherwise ``expect_to_fail: true`` on the presence test.

A missing or unreadable file is an ERROR either way, never a pass. Details and examples:
:doc:`absence`.
