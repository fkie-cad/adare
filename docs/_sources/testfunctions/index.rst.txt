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
     - 11
     - File system operations, content validation, permissions, and metadata testing
   * - :doc:`json/index`
     - 3
     - JSON data validation, key existence checking, value comparison, and array element verification
   * - :doc:`csv/index`
     - 1
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


Overvies of all Test Functions
-------------------------------

.. csv-table::
   :file: ../_static/tables/testfunctions_all.csv
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

