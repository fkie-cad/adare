dir_content
===========

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: File System
:Function Name: ``dir_content``

**Tests if a directory contains the expected files and folders.**

This test function verifies that a directory contains exactly the expected set of files and folders. It will fail if expected items are missing or if additional unexpected items are present.

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
     - **Required.** The directory path to examine. Supports glob patterns for dynamic path resolution.
   * - ``files``
     - list
     - **Required.** List of expected file and folder names that should be present in the directory.

Usage Example
-------------

Basic Usage
~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: verify_project_structure
       function: dir_content
       parameter:
         dst: "/home/user/new_project"
         files:
           - "src"
           - "docs"
           - "README.md"
           - "package.json"
       description: "Verify project was created with correct structure"

After File Operations
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   actions:
     - click:
         target:
           text: "Create Files"

   tests:
     - name: check_generated_files
       function: dir_content
       parameter:
         dst: "/home/user/output"
         files:
           - "report.pdf"
           - "data.csv"
           - "summary.txt"
       description: "Verify all expected files were generated"

Common Use Cases
----------------

**Project Structure Validation**
  Verify that project creation tools generate the correct directory structure

**Build Output Verification**
  Confirm that build processes create all expected output files

**Installation Content Verification**
  Ensure software installation creates the correct files and directories

**Extraction Verification**
  Verify that archive extraction produces the expected content

**Template Expansion**
  Confirm that template systems generate all expected files

**Forensic Analysis**
  Monitor changes in directory contents to detect artifact creation/deletion

Return Values
-------------

**Success**
  Returns success when the directory contains exactly the expected files (no more, no less)

**Failure**
  Returns failure when:

  - Expected files/folders are missing from the directory
  - Additional unexpected files/folders are present in the directory
  - Both missing and additional items are found

**Execution Error**
  Returns execution error when:

  - The directory path cannot be resolved or doesn't exist
  - Permission denied reading the directory
  - Path resolution fails due to glob pattern ambiguity
  - System I/O errors occur

Example Results
---------------

.. code-block:: yaml

   # Success case
   result: success
   message: "Directory content matches expected files"

   # Failure case - missing files
   result: failed
   details:
     - "expected missing files: ['README.md', 'package.json']"

   # Failure case - additional files
   result: failed
   details:
     - "additional files: ['temp.log', 'backup.bak']"

   # Failure case - both missing and additional
   result: failed
   details:
     - "expected missing files: ['config.yml']"
     - "additional files: ['debug.log']"

   # Execution error case
   result: execution_error
   error: "PermissionError: [Errno 13] Permission denied"
   context: "Cannot read directory content for /root/protected_dir"

