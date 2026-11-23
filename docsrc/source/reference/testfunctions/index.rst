Test Functions
==============

.. role:: status-tested
   :class: status-tested

.. role:: status-dev
   :class: status-dev

.. role:: status-planned
   :class: status-planned

ADARE provides a comprehensive set of test functions to validate forensic artifacts and system states. This reference documents all available test functions organized by testsets.

Test Function Status Legend
---------------------------

- :status-tested:`●` **Tested**: Fully implemented and tested in production
- :status-dev:`●` **Development**: Implemented but under active development
- :status-planned:`●` **Planned**: Planned for future implementation

Available Testsets
------------------

ADARE organizes test functions into logical testsets based on their purpose and functionality.
The screen checks of the ``visual`` testset (``visual.exists``, ``visual.count_equals``, ...)
run on the host and are described in :doc:`/guide/icon-library`. Not sure which function fits
a goal? See :doc:`/guide/choosing-testfunctions`.

.. list-table::
   :widths: 20 15 65
   :header-rows: 1

   * - Testset
     - Functions
     - Description
   * - :doc:`standard/index`
     - 13
     - File system operations: existence, file counts and sizes, content, hashes, permissions and timestamps
   * - :doc:`json/index`
     - 5
     - JSON data validation, key existence checking, value comparison and counting, and array element verification
   * - :doc:`jsonl/index`
     - 3
     - JSON Lines (NDJSON) files: lines that meet conditions, and matching line counts
   * - :doc:`csv/index`
     - 4
     - CSV rows: pattern matching with regex and timestamp support, row counts, and comparison with reference rows or files
   * - :doc:`excel/index`
     - 8
     - Excel workbooks: sheets, cells, rows and row counts, column headers, and comparison of sheets and workbooks
   * - :doc:`xml/index`
     - 7
     - XML data validation with XPath, namespace support, regex patterns, and timestamp tolerance
   * - :doc:`sqlite/index`
     - 3
     - SQLite database query execution, result validation and row counts, write-ahead log frames
   * - :doc:`linux/index`
     - 4
     - Linux system validation including services, processes, users, and logs
   * - :doc:`windows/index`
     - 2
     - Windows system validation including registry key and value operations
   * - :doc:`text/index`
     - 2
     - Occurrences of strings or byte sequences in any file (several encodings), matching line counts
   * - :doc:`ini/index`
     - 4
     - INI / key-file sections, keys and values (duplicates kept, BOM and UTF-16 aware)
   * - :doc:`plist/index`
     - 4
     - Property lists (XML and binary): keys, values and value counts
   * - :doc:`yaml/index`
     - 4
     - YAML files (also several documents): keys, values and value counts
   * - :doc:`toml/index`
     - 4
     - TOML files: keys, values and value counts
   * - :doc:`image/index`
     - 5
     - PNG text chunks, EXIF tags and image dimensions
   * - :doc:`binary/index`
     - 4
     - Binary containers without a parser: values at offsets (pointers followed), byte patterns in a region, key/value string tables

Usage in Playbooks
-------------------

Test functions are used in the ``tests`` section of ADARE playbooks:

.. code-block:: yaml

   tests:
     - name: check_file_exists
       function: file_exists
       parameter:
         dst: "/path/to/file.txt"
       description: "Verify the file was created"

     - name: check_content
       function: file_content_contains
       parameter:
         dst: "/path/to/logfile.log"
         content: "ERROR: Authentication failed"
       description: "Verify error was logged"


Files inside archives
---------------------

Every file test function can read a file inside a tar, zip, gzip, bzip2, xz, LZ4 or Snappy archive:
``dst: /home/user/backup.tar.gz!/etc/app/config.json``, ``dst: /home/user/store.jsonlz4!``.
See :doc:`/guide/archives`.

Checking that something is absent
---------------------------------

Use a count function with ``expected_count: 0`` (``json.value_count``,
``text.occurrence_count``, ``ini.value_count``, ``standard.file_count``, ...) or ``expect_to_fail: true`` on a
presence test. A missing or unreadable file is an ERROR either way, never a pass. See
:doc:`/guide/absence`.

.. _ordered-comparison:

Comparing numbers and timestamps
--------------------------------

Value functions (``json.value_matches``, ``yaml``/``toml``/``plist``/``ini.value_matches``,
``xml.element_text_matches``, ``xml.attribute_matches``, ``jsonl.value_in_any_line``,
``excel.cell_value_matches``, ``image.exif_value_matches``) compare by equality or regex by default.
With ``comparison_type`` (``equals``, ``not_equals``, ``greater``, ``less``, ``greater_equal``,
``less_equal``), ``value_type`` (``auto``, ``number``, ``timestamp``), ``tolerance`` or a time parameter
they compare the value with ``expected_value`` as a number or a point in time:

.. code-block:: yaml

   - name: written_after_noon
     function: json.value_matches
     parameter:
       dst: /home/user/data/session.json
       key_path: window.lastSaved
       expected_value: "2026-03-01T12:00:00Z"
       comparison_type: greater
       timestamp_epoch: 1970
       timestamp_unit: ms

Numbers compare exactly (``"10"`` is greater than ``9``). Timestamps are read as ISO 8601 or RFC 2822 text,
with ``time_format`` (a ``strptime`` format, used for both sides) for other text, and with
``timestamp_epoch`` (1970, 1601 or 2001) plus ``timestamp_unit`` (``s``, ``ms``, ``us``, ``ns``, ``100ns``)
for numeric counts; a timestamp without zone is in ``utc_offset`` (default UTC). ``tolerance`` (seconds for
timestamps) applies to ``equals``/``not_equals``.

Two values of the same file are compared with ``values_compare`` (``json``, ``yaml``, ``toml``, ``plist``,
``xml``): ``value(A) <comparison_type> value(B) + offset``, for "A earlier than B", "A within 5 s of B" or
"A = B + 1". Each side must select exactly one value.

A value that is no number or timestamp is an ERROR, not a failure: the test looked at the wrong field. A
``!re`` tag, a ``{{placeholder}}`` or ``regex_match`` together with these parameters is an ERROR as well.

Overview of all Test Functions
------------------------------

.. csv-table::
   :file: /_static/tables/testfunctions_all.csv
   :widths: auto
   :header-rows: 1
   :class: sdtable
   :name: testfunctions-all

.. note::
   :status-tested:`●` : Tested, :status-dev:`●` : In Development, :status-planned:`●` : Planned

.. toctree::
   :maxdepth: 2
   :caption: Test Functions
   :hidden:

   standard/index
   json/index
   jsonl/index
   csv/index
   excel/index
   xml/index
   sqlite/index
   linux/index
   windows/index
   text/index
   ini/index
   plist/index
   yaml/index
   toml/index
   image/index
   binary/index

