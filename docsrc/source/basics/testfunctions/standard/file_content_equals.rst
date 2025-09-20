file_content_equals
====================

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: File System
:Function Name: ``file_content_equals``

**Tests if file content exactly equals the given content.**

This test function reads a file and performs an exact comparison with the expected content. It's useful for validating generated files, configuration output, or ensuring files contain precise expected content.

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
     - **Required.** The file path to read and test. Supports glob patterns for dynamic path resolution.
   * - ``content``
     - string
     - **Required.** The expected content that the file should contain exactly.
   * - ``encoding``
     - string
     - **Optional.** Text encoding to use when reading the file (default: "utf-8"). Common values: "utf-8", "utf-16", "latin-1", "ascii".

Usage Example
-------------

Configuration File Validation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: verify_config_generated
       function: file_content_equals
       parameter:
         dst: "/etc/myapp/settings.conf"
         content: |
           [database]
           host=localhost
           port=5432
           name=myapp
       description: "Verify configuration file was generated correctly"

Generated Script Validation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: check_backup_script
       function: file_content_equals
       parameter:
         dst: "/home/user/backup.sh"
         content: |
           #!/bin/bash
           tar -czf backup_$(date +%Y%m%d).tar.gz /home/user/documents
           echo "Backup completed"
       description: "Verify backup script was generated with correct content"

Small File Validation
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: verify_status_file
       function: file_content_equals
       parameter:
         dst: "/tmp/process_status.txt"
         content: "COMPLETED"
       description: "Verify process completed successfully"

Windows UTF-16 File Testing
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: verify_windows_file
       function: file_content_equals
       parameter:
         dst: "C:\\Users\\user\\output.txt"
         content: "Windows file content"
         encoding: "utf-16"
       description: "Verify file created by PowerShell echo command"

Common Use Cases
----------------

**Generated File Validation**
  Verify that automated processes create files with exact expected content

**Configuration File Testing**
  Ensure configuration files are generated with precise settings

**Template Output Verification**
  Confirm template processing produces exact expected output

**Status File Monitoring**
  Validate that processes write correct status information

**Export Validation**
  Verify that data export produces files with expected content

**Script Generation**
  Ensure code generators create scripts with precise syntax

Comparison Behavior
-------------------

**Whitespace Handling**
  The comparison trims leading and trailing whitespace from both actual and expected content

**Line Ending Normalization**
  Different line endings (\\n, \\r\\n) are handled appropriately

**Placeholder Support**
  The function can handle placeholder patterns for dynamic content validation

**Diff Generation**
  On failure, the function provides detailed diff output showing differences between expected and actual content

**Encoding Support**
  The function supports various text encodings. Use the encoding parameter to handle files created with different character encodings (UTF-8, UTF-16, etc.)

Return Values
-------------

**Success**
  Returns success when file content exactly matches the expected content (after whitespace trimming)

**Failure**
  Returns failure when:

  - File content differs from expected content
  - File is empty but content is expected
  - File contains content but empty content is expected

**Execution Error**
  Returns execution error when:

  - The file cannot be found or read
  - Permission denied reading the file
  - Path resolution fails due to glob pattern ambiguity
  - Unicode decoding errors occur (try specifying correct encoding parameter)

Example Results
---------------

.. code-block:: yaml

   # Success case
   result: success
   message: "Direct content comparison"

   # Failure case with diff
   result: failed
   details:
     - "Content comparison failed"
     - |
       Diff:
       --- expected
       +++ actual
       @@ -1,2 +1,2 @@
       -port=8080
       +port=3000

   # Execution error case
   result: execution_error
   error: "UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff"
   context: "Cannot read file /tmp/binary_file.dat"

