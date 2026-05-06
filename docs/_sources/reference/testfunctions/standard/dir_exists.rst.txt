dir_exists
==========

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: File System
:Function Name: ``dir_exists``

**Tests if a directory exists at the specified path.**

This test function verifies that a directory is present at the given destination path. It's commonly used to confirm that user actions or system processes have successfully created directories.

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
     - **Required.** The directory path to check for existence. Supports glob patterns for dynamic path resolution.

Usage Example
-------------

Basic Usage
~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: verify_project_dir_created
       function: dir_exists
       parameter:
         dst: "/home/user/Projects/new_project"
       description: "Verify project directory was created"

After Directory Creation
~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   actions:
     - right_click:
         target:
           text: "Desktop"
     - click:
         target:
           text: "New Folder"
     - keyboard:
         text: "TestFolder"
     - keyboard:
         combination: ["enter"]

   tests:
     - name: folder_created_on_desktop
       function: dir_exists
       parameter:
         dst: "/home/user/Desktop/TestFolder"
       description: "Verify new folder was created on desktop"

Common Use Cases
----------------

**Directory Creation Verification**
  Confirm that directories have been successfully created by user actions

**Installation Verification**
  Verify that software installation created expected directory structures

**Project Setup Validation**
  Ensure project directories exist after initialization

**System Directory Monitoring**
  Detect creation of system directories like cache, temp, or log directories

**Forensic Analysis**
  Monitor for creation of directories that might contain artifacts

Return Values
-------------

**Success**
  Returns success when the directory exists at the specified path

**Failure**
  Returns failure when:

  - No directory exists at the specified path
  - The path exists but points to a file, not a directory

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
   message: "Directory exists at /home/user/Projects/new_project"

   # Failure case
   result: failed
   details:
     - "directory with path /home/user/missing_folder does not exist"

   # Execution error case
   result: execution_error
   error: "PermissionError: [Errno 13] Permission denied"
   context: "Cannot check directory existence for /root/protected_dir"

