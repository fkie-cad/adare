process_running
===============

.. role:: status-dev
   :class: status-dev

:Status: :status-dev:`● Development`
:Category: Linux System
:Function Name: ``process_running``

**Tests if a process is running with expected number of instances (Linux only).**

This test function checks if a specified process is running on the system and optionally validates the minimum number of instances. It uses process name matching to find running processes.

Parameters
----------

.. list-table::
   :widths: 20 15 65
   :header-rows: 1

   * - Parameter
     - Type
     - Description
   * - ``process_name``
     - string
     - **Required.** The name of the process to check for.
   * - ``min_instances``
     - integer
     - **Optional.** Minimum number of process instances expected. Default: 1.

Usage Example
-------------

Basic Process Check
~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: test_process_running_single
       function: linux.process_running
       parameter:
         process_name: 'systemd'
         min_instances: 1
       description: "Test process_running with single instance"

Multiple Instance Check
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: test_apache_workers
       function: linux.process_running
       parameter:
         process_name: 'apache2'
         min_instances: 3
       description: "Test that at least 3 Apache worker processes are running"

Expected Failure Cases
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: test_process_not_running
       function: linux.process_running
       expect_to_fail: true
       parameter:
         process_name: 'nonexistent-process-12345'
         min_instances: 1
       description: "Test process_running with non-existent process"

Variable-Based Process Names
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   variables:
     database_process:
       type: string
       value: "mysqld"
       description: "Database server process"

   tests:
     - name: test_database_running
       function: linux.process_running
       parameter:
         process_name: '{{database_process}}'
         min_instances: 1
       description: "Test database process is running"

Common Use Cases
----------------

**Service Process Monitoring**
  Verify that daemon processes are running for system services

**Application Health Checks**
  Ensure application processes haven't crashed or stopped

**Load Balancer Validation**
  Check that multiple worker processes are running for high-load services

**Container Process Verification**
  Validate that containerized applications have spawned expected processes

**Security Process Monitoring**
  Ensure security-related processes like antivirus or monitoring tools are active

Process Detection
-----------------

**Process Matching:**
  - Uses process name matching against running processes
  - Matches against the command name in the process list
  - Case-sensitive process name matching

**Instance Counting:**
  - Counts all processes matching the specified name
  - Validates that at least ``min_instances`` are running
  - Useful for services that spawn multiple worker processes

**Platform Requirements:**
  - Linux operating system
  - Access to process information (typically via ``/proc`` filesystem)
  - Appropriate permissions to read process information

Return Values
-------------

**Success**
  Returns success when the required number of process instances are found running

**Failure**
  Returns failure when:
  - Process is not running
  - Fewer instances are running than the minimum required
  - Process name doesn't match any running processes

**Execution Error**
  Returns execution error when:
  - Not running on Linux system
  - Permission denied accessing process information
  - System error occurs while checking processes

Example Results
---------------

.. code-block:: yaml

   # Success case
   result: success
   details:
     - "process systemd found running with 1 instances (minimum: 1)"

   # Failure case - process not found
   result: failed
   details:
     - "process nonexistent-process-12345 not found running (minimum instances: 1)"

   # Failure case - insufficient instances
   result: failed
   details:
     - "process apache2 found running with 1 instances (minimum: 3)"

   # Execution error case - wrong platform
   result: execution_error
   error: "This test only runs on Linux"