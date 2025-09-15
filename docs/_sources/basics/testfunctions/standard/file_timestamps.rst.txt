file_timestamps
===============

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: File System
:Function Name: ``file_timestamps``

**Tests file timestamps with various comparison types and formats.**

This test function provides comprehensive timestamp validation for files, supporting multiple timestamp types, comparison operations, and flexible date/time formats. It's crucial for forensic analysis and system behavior validation.

Parameters
----------

.. list-table::
   :widths: 20 15 65
   :header-rows: 1

   * - Parameter
     - Type
     - Description
   * - ``dst``
     - string
     - **Required.** The file path to examine. Supports glob patterns for dynamic path resolution.
   * - ``timestamp_type``
     - string
     - **Optional.** Type of timestamp to check. Default: "modified". Options: "modified", "accessed", "created".
   * - ``comparison_type``
     - string
     - **Optional.** How to compare timestamps. Default: "equals". Options: "equals", "before", "after", "between", "within_last".
   * - ``expected_time``
     - string/number
     - **Optional.** Expected timestamp for "equals", "before", "after" comparisons.
   * - ``time_format``
     - string
     - **Optional.** strptime format for parsing timestamp strings.
   * - ``tolerance_seconds``
     - integer
     - **Optional.** Tolerance in seconds for "equals" comparison.
   * - ``start_time``
     - string/number
     - **Optional.** Start time for "between" comparison.
   * - ``end_time``
     - string/number
     - **Optional.** End time for "between" comparison.
   * - ``within_duration``
     - string
     - **Optional.** Duration string for "within_last" comparison (e.g., "1h", "30m", "2d").

Usage Examples
--------------

File Modification Time
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: verify_recent_modification
       function: file_timestamps
       parameter:
         dst: "/var/log/application.log"
         timestamp_type: "modified"
         comparison_type: "within_last"
         within_duration: "1h"
       description: "Verify log file was modified within the last hour"

Exact Timestamp Verification
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: verify_creation_time
       function: file_timestamps
       parameter:
         dst: "/tmp/generated_file.txt"
         timestamp_type: "created"
         comparison_type: "equals"
         expected_time: "2024-01-15 14:30:00"
         time_format: "%Y-%m-%d %H:%M:%S"
         tolerance_seconds: 30
       description: "Verify file was created at expected time (±30s)"

Time Range Validation
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: verify_access_window
       function: file_timestamps
       parameter:
         dst: "/home/user/document.pdf"
         timestamp_type: "accessed"
         comparison_type: "between"
         start_time: "2024-01-15 09:00:00"
         end_time: "2024-01-15 17:00:00"
         time_format: "%Y-%m-%d %H:%M:%S"
       description: "Verify file was accessed during business hours"

Timestamp Types
---------------

.. list-table::
   :widths: 20 30 50
   :header-rows: 1

   * - Type
     - Description
     - Platform Notes
   * - ``modified``
     - File modification time
     - Available on all platforms
   * - ``accessed``
     - File access time
     - May not be updated on all filesystems
   * - ``created``
     - File creation time
     - Windows: true creation time; Unix: change time or birth time

Comparison Types
----------------

.. list-table::
   :widths: 15 35 50
   :header-rows: 1

   * - Type
     - Parameters Required
     - Description
   * - ``equals``
     - ``expected_time``
     - Timestamp equals expected time (within tolerance)
   * - ``before``
     - ``expected_time``
     - Timestamp is before expected time
   * - ``after``
     - ``expected_time``
     - Timestamp is after expected time
   * - ``between``
     - ``start_time``, ``end_time``
     - Timestamp is between start and end times
   * - ``within_last``
     - ``within_duration``
     - Timestamp is within specified duration from now

Time Format Support
-------------------

**Unix Timestamps**
  Numeric timestamps (seconds since epoch):

  .. code-block:: yaml

     expected_time: 1705334400  # Unix timestamp

**ISO Format**
  Standard ISO date/time formats:

  .. code-block:: yaml

     expected_time: "2024-01-15T14:30:00"
     expected_time: "2024-01-15T14:30:00Z"

**Custom Formats**
  Use ``time_format`` for custom parsing:

  .. code-block:: yaml

     expected_time: "15/01/2024 2:30 PM"
     time_format: "%d/%m/%Y %I:%M %p"

**Common Formats**
  Built-in support for common formats:

  - ``%Y-%m-%d %H:%M:%S`` - "2024-01-15 14:30:00"
  - ``%Y-%m-%d`` - "2024-01-15"
  - ``%m/%d/%Y %H:%M:%S`` - "01/15/2024 14:30:00"

Duration Formats
----------------

For ``within_last`` comparisons, use these duration formats:

.. list-table::
   :widths: 20 30 50
   :header-rows: 1

   * - Unit
     - Format
     - Examples
   * - Seconds
     - ``Ns``
     - ``30s``, ``120s``
   * - Minutes
     - ``Nm``
     - ``5m``, ``45m``
   * - Hours
     - ``Nh``
     - ``2h``, ``24h``
   * - Days
     - ``Nd``
     - ``1d``, ``7d``, ``30d``

Common Use Cases
----------------

**Log File Monitoring**
  Verify log files are being updated regularly

**File Creation Tracking**
  Confirm files are created at expected times during processes

**Access Pattern Analysis**
  Monitor when files are accessed for security analysis

**Backup Verification**
  Ensure backup files have expected timestamps

**Process Timing Validation**
  Verify automated processes complete within expected timeframes

**Forensic Analysis**
  Analyze file timeline for investigation purposes

Return Values
-------------

**Success**
  Returns success when timestamp comparison passes

**Failure**
  Returns failure when timestamp comparison fails, showing expected vs actual times

**Execution Error**
  Returns execution error when:

  - File cannot be found or accessed
  - Invalid timestamp format or comparison type
  - Permission denied accessing file metadata
  - Path resolution fails

Example Results
---------------

.. code-block:: yaml

   # Success case
   result: success
   details:
     - "modified timestamp is within last 1h"

   # Failure case
   result: failed
   details:
     - "modified timestamp mismatch. Expected: 2024-01-15 14:30:00, Got: 2024-01-15 15:45:00"

   # Execution error case
   result: execution_error
   error: "ValueError: Cannot parse timestamp: invalid_date"
   context: "Timestamp parsing/comparison error"

