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
``!re`` tag or ``regex_match`` together with these parameters is an ERROR as well.

Saved variables
~~~~~~~~~~~~~~~

An ``expected_value`` that is exactly one placeholder, ``"{{ name }}"``, is the value saved in the variable
during the run: a number or text (``save_variable``, a ``command`` with ``capture``) or a point in time
(``save_timestamp``, read with its ``format`` and ``localtime``). ``values_compare`` takes a saved number
as ``offset`` the same way, and ``binary.struct_value_matches`` with an ordered ``comparison_type`` or
``tolerance``:

.. code-block:: yaml

   actions:
     - command:
         command: "wc -l < /data/app/history.log"
         capture:
           variable: lines_before
           parser: "int(output.strip())"
     - save_timestamp:
         variable: started
     # ... the action under test ...

   tests:
     - name: counter_grew
       function: json.value_matches
       parameter:
         dst: /data/app/state.json
         key_path: entries
         expected_value: "{{ lines_before }}"
         comparison_type: greater
     - name: saved_after_start
       function: json.value_matches
       parameter:
         dst: /data/app/state.json
         key_path: lastSaved
         expected_value: "{{ started }}"
         comparison_type: greater_equal

A variable not set before the test, a ``!re`` variable, a ``!timestamp`` with ``tolerance`` or an interval
(``after``/``before``; it compares on its own, without these parameters) and text around the placeholder
(``"at {{ started }}"``) are an ERROR.

Decoding a stored value
~~~~~~~~~~~~~~~~~~~~~~~

Applications often store a value encoded inside a field. ``value_decode`` decodes the value read from the
file before it is compared, in every value function above except ``excel`` and ``image``, and on both
sides of ``values_compare``. It is one step or a list applied in order:

.. list-table::
   :widths: 15 85
   :header-rows: 1

   * - Step
     - Effect
   * - ``url``
     - Percent-decoding (``%2F`` -> ``/``; a ``+`` stays a ``+``).
   * - ``base64``
     - Standard or URL-safe alphabet; missing ``=`` padding and whitespace are fine.
   * - ``hex``
     - Hex digits, whitespace between bytes allowed.
   * - ``utf16``
     - Bytes as UTF-16 text (a BOM gives the byte order, little-endian without one; trailing NULs dropped).
       Needs bytes: put ``base64`` or ``hex`` before it.
   * - ``json``
     - Parse JSON text and take the value at ``decoded_key_path`` (key path syntax of
       :doc:`json/value_matches`), which must select exactly one value. ``decoded_key_path`` is required.

Bytes left after the last step are compared as UTF-8 text, or as lowercase hex when they are no UTF-8. A
value a step cannot decode, an unknown step or ``json`` without ``decoded_key_path`` is an ERROR naming the
step.

.. code-block:: yaml

   - name: stored_session_id
     function: ini.value_matches
     parameter:
       dst: /data/app/settings.ini
       section: session
       key: state            # state = eyJpZCI6IDQyfQ== (base64 of {"id": 42})
       value_decode: [base64, json]
       decoded_key_path: id
       expected_value: "42"

.. _before-after-action:

Before and after an action
~~~~~~~~~~~~~~~~~~~~~~~~~~

To compare a value with what it was before an action, save a copy of the file at that point with a
``command`` action, then compare the file after the action with the copy: ``values_compare`` with
``other_dst`` reads ``other_key_path`` from a second file (loaded exactly like ``dst``; an
``archive!/member`` path works too, and a missing copy is an ERROR):

.. code-block:: yaml

   actions:
     - command:
         command: "cp /data/app/state.json /data/app/state.before.json"
     # ... the action under test ...
     - test: counter_grew

   tests:
     - name: counter_grew
       function: json.values_compare
       parameter:
         dst: /data/app/state.json
         key_path: counter
         other_dst: /data/app/state.before.json
         other_key_path: counter
         comparison_type: greater

For a SQLite database copy the ``-wal`` file along with it (``cp app.db app.db.before; cp app.db-wal
app.db.before-wal``), or take a consistent copy with ``sqlite3 /data/app/app.db ".backup
/data/app/app.before.db"``. On Windows use ``copy`` (``C:\Data\app\settings.json``). In host test mode
both files are pulled from the guest (with their sidecars) at the time of the test.

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

