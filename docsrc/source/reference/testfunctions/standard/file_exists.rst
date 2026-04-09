file_exists
===========

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: File System
:Function Name: ``file_exists``

**Tests if a file exists at the specified path.**

This test function verifies that a file is present at the given destination path. It's commonly used to confirm that user actions or system processes have successfully created files.

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
     - **Required.** The file path to check for existence. Supports glob patterns for dynamic path resolution.

Usage Example
-------------

Basic Usage
~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: verify_log_created
       function: file_exists
       parameter:
         dst: "/var/log/application.log"
       description: "Verify application log file was created"

With Glob Patterns
~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: verify_temp_file_created
       function: file_exists
       parameter:
         dst: "/tmp/temp_*.txt"
       description: "Verify temporary file was created with timestamp"

Common Use Cases
----------------

**File Creation Verification**
  Confirm that user actions or applications have created expected files

**Log File Monitoring**
  Verify that applications are generating log files as expected

**Configuration File Validation**
  Ensure configuration files exist after installation or setup

**Artifact Detection**
  Detect forensic artifacts created by user actions

Return Values
-------------

**Success**
  Returns success when the file exists at the specified path

**Failure**
  Returns failure when:

  - The file does not exist at the specified path
  - The path exists but points to a directory, not a file

**Execution Error**
  Returns execution error when:

  - Permission denied accessing the path
  - Path resolution fails due to glob pattern ambiguity
  - System I/O errors occur

Example Results
---------------

.. code-block:: yaml

   # Success case
   result: success
   message: "File exists at /var/log/application.log"

   # Failure case
   result: failed
   details:
     - "file with path /var/log/missing.log does not exist"

   # Execution error case
   result: execution_error
   error: "PermissionError: [Errno 13] Permission denied"
   context: "Cannot check file existence for /root/protected.log"

