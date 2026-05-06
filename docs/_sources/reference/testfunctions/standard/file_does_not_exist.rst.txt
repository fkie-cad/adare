file_does_not_exist
===================

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: File System
:Function Name: ``file_does_not_exist``

**Tests if a file does NOT exist at the specified path.**

This test function verifies that no file is present at the given destination path. It's commonly used to confirm that files have been successfully deleted or moved by user actions or system processes.

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
     - **Required.** The file path to check for non-existence. Supports glob patterns for dynamic path resolution.

Usage Example
-------------

Basic Usage
~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: verify_temp_deleted
       function: file_does_not_exist
       parameter:
         dst: "/tmp/temporary_file.txt"
       description: "Verify temporary file was cleaned up"

After File Deletion
~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   actions:
     - click:
         target:
           text: "Delete File"
     - click:
         target:
           text: "Confirm"

   tests:
     - name: file_deleted_successfully
       function: file_does_not_exist
       parameter:
         dst: "/home/user/document.pdf"
       description: "Verify file was deleted from filesystem"

Common Use Cases
----------------

**File Deletion Verification**
  Confirm that files have been successfully deleted by user actions

**Cleanup Validation**
  Verify that temporary files are properly removed after processes

**Move Operation Verification**
  Confirm that files no longer exist at their original location after being moved

**Uninstall Verification**
  Ensure application files are removed during uninstallation

**Forensic Analysis**
  Detect when artifacts are removed from the system

Return Values
-------------

**Success**
  Returns success when no file exists at the specified path

**Failure**
  Returns failure when:

  - A file exists at the specified path
  - The path exists and points to a file (not a directory)

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
   message: "File does not exist at /tmp/temporary_file.txt"

   # Failure case
   result: failed
   details:
     - "file with path /home/user/document.pdf does exist"

   # Execution error case
   result: execution_error
   error: "PermissionError: [Errno 13] Permission denied"
   context: "Cannot check file existence for /root/protected.log"

