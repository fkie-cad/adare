dir_does_not_exist
==================

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: File System
:Function Name: ``dir_does_not_exist``

**Tests if a directory does NOT exist at the specified path.**

This test function verifies that no directory is present at the given destination path. It's commonly used to confirm that directories have been successfully deleted or moved by user actions or system processes.

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
     - **Required.** The directory path to check for non-existence. Supports glob patterns for dynamic path resolution.

Usage Example
-------------

Basic Usage
~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: verify_temp_dir_cleaned
       function: dir_does_not_exist
       parameter:
         dst: "/tmp/build_temp"
       description: "Verify temporary build directory was cleaned up"

After Directory Deletion
~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   actions:
     - right_click:
         target:
           text: "old_project"
     - click:
         target:
           text: "Delete"
     - click:
         target:
           text: "Yes"

   tests:
     - name: old_project_deleted
       function: dir_does_not_exist
       parameter:
         dst: "/home/user/Projects/old_project"
       description: "Verify old project directory was deleted"

Common Use Cases
----------------

**Directory Deletion Verification**
  Confirm that directories have been successfully deleted by user actions

**Cleanup Validation**
  Verify that temporary directories are properly removed after processes

**Uninstall Verification**
  Ensure application directories are removed during uninstallation

**Move Operation Verification**
  Confirm that directories no longer exist at their original location after being moved

**System Maintenance**
  Verify cleanup of cache, log, or temporary directories

**Forensic Analysis**
  Detect when artifact-containing directories are removed

Return Values
-------------

**Success**
  Returns success when no directory exists at the specified path

**Failure**
  Returns failure when:

  - A directory exists at the specified path
  - The path exists and points to a directory (not a file)

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
   message: "Directory does not exist at /tmp/build_temp"

   # Failure case
   result: failed
   details:
     - "directory with path /home/user/Projects/old_project does exist"

   # Execution error case
   result: execution_error
   error: "PermissionError: [Errno 13] Permission denied"
   context: "Cannot check directory existence for /root/protected_dir"

