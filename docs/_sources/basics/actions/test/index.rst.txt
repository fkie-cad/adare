Test Actions
============

Execute forensic validation tests to verify artifacts and system states.

Available Actions
-----------------

.. toctree::
   :maxdepth: 1

   test

Overview
--------

Test actions execute validation tests defined in the playbook's ``tests`` section. Tests use specialized functions to verify:

- File existence and content
- Registry keys and values (Windows)
- Process and service states (Linux)
- JSON, XML, CSV data validation
- Database queries (SQLite)
- Timestamps and metadata

See :doc:`../../testfunctions/index` for comprehensive test function documentation.
