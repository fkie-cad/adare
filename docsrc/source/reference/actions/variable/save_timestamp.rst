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
- The time is read from the guest's clock, the clock that writes the artifacts
- Can be used with timestamp filters in tests (``format``, ``tolerance``, ``timezone``)
- A pair around an action bounds when its artifacts were written: use them as
  ``!timestamp {after: ..., before: ...}`` in a test instead of a tolerance
- Commonly used to validate timing of forensic artifacts

Guest clock log
---------------

Every run also samples the guest clock before and after each action
(``settings.clock_log``, on by default) and writes ``clock.jsonl`` and
``clock_summary.json`` to the run directory: the guest's offset from the host
clock, its timezone, and every jump (NTP stepping the clock, a restore). A run
whose summary is not ``stable`` has timestamps that are not comparable across
the jump. On QEMU the samples come from the guest agent socket (QGA), so they
leave no traces in the agent's logs.

See Also
--------

- :doc:`save_variable` for storing other types of values
- Variable filters for timestamp formatting and comparison
