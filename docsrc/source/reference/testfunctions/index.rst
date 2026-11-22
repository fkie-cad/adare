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

ADARE organizes test functions into logical testsets based on their purpose and functionality:

.. list-table::
   :widths: 20 15 65
   :header-rows: 1

   * - Testset
     - Functions
     - Description
   * - :doc:`standard/index`
     - 12
     - File system operations, content validation, permissions, and metadata testing
   * - :doc:`json/index`
     - 4
     - JSON data validation, key existence checking, value comparison and counting, and array element verification
   * - :doc:`csv/index`
     - 2
     - CSV data validation and row pattern matching with regex and timestamp support
   * - :doc:`xml/index`
     - 6
     - XML data validation with XPath, namespace support, regex patterns, and timestamp tolerance
   * - :doc:`sqlite/index`
     - 1
     - SQLite database query execution and result validation
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
     - 3
     - Property lists (XML and binary): keys, values and value counts
   * - :doc:`yaml/index`
     - 3
     - YAML files (also several documents): keys, values and value counts
   * - :doc:`toml/index`
     - 3
     - TOML files: keys, values and value counts
   * - :doc:`image/index`
     - 5
     - PNG text chunks, EXIF tags and image dimensions


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

Every file test function can read a file inside a tar, zip, gzip, bzip2, xz or LZ4 archive:
``dst: /home/user/backup.tar.gz!/etc/app/config.json``, ``dst: /home/user/store.jsonlz4!``.
See :doc:`/guide/archives`.

Checking that something is absent
---------------------------------

Use a count function with ``expected_count: 0`` (``json.value_count``,
``text.occurrence_count``, ``ini.value_count``, ...) or ``expect_to_fail: true`` on a
presence test. A missing or unreadable file is an ERROR either way, never a pass. See
:doc:`/guide/absence`.

Overvies of all Test Functions
-------------------------------

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
   csv/index
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

