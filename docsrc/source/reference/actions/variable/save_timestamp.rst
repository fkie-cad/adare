save_timestamp
==============

Record the current Unix timestamp to a variable for later use in tests or comparisons.

Usage Example
-------------

.. code-block:: yaml

   actions:
     # Save timestamp before operation
     - save_timestamp:
         variable: "deletion_start"
         description: "Record when file deletion began"

     # Perform operation
     - command:
         command: "rm /tmp/testfile.txt"

     # Save timestamp after operation
     - save_timestamp:
         variable: "deletion_end"
         description: "Record when deletion completed"

Parameters
----------

.. list-table::
   :widths: 20 15 65
   :header-rows: 1

   * - Parameter
     - Type
     - Description
   * - ``variable``
     - string
     - Variable name to store the timestamp (required)
   * - ``description``
     - string
     - Human-readable description (optional)

Notes
-----

- Timestamp is stored as Unix epoch time (seconds since January 1, 1970 UTC)
- Can be used with timestamp filters in tests (``format``, ``tolerance``, ``timezone``)
- Commonly used to validate timing of forensic artifacts

See Also
--------

- :doc:`save_variable` for storing other types of values
- Variable filters for timestamp formatting and comparison
