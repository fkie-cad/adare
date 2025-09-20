file_content_contains
======================

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: File System
:Function Name: ``file_content_contains``

**Tests if file content contains specified string or byte pattern.**

This test function reads a file and checks if it contains the specified content. It supports both string-based and byte-based pattern matching, making it versatile for text files and binary files.

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
     - **Required.** The content to search for within the file.
   * - ``content_type``
     - string
     - **Optional.** Either "string" (default) or "bytes". Determines how content is interpreted.
   * - ``encoding``
     - string
     - **Optional.** Text encoding to use when reading the file for string content (default: "utf-8"). Ignored for byte content. Common values: "utf-8", "utf-16", "latin-1", "ascii".

Usage Example
-------------

Text Content Search
~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: verify_error_in_log
       function: file_content_contains
       parameter:
         dst: "/var/log/application.log"
         content: "Authentication failed for user"
         content_type: "string"
       description: "Verify authentication error appears in log"

Binary Content Search
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: check_binary_signature
       function: file_content_contains
       parameter:
         dst: "/tmp/generated_file.bin"
         content: "\\x50\\x4B\\x03\\x04"  # ZIP file signature
         content_type: "bytes"
       description: "Verify file contains ZIP signature"

Log Monitoring
~~~~~~~~~~~~~~

.. code-block:: yaml

   actions:
     - click:
         target:
           text: "Process Data"

   tests:
     - name: verify_processing_logged
       function: file_content_contains
       parameter:
         dst: "/var/log/processor.log"
         content: "Data processing completed successfully"
       description: "Verify processing completion was logged"

Windows UTF-16 Log Analysis
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: check_windows_event_log
       function: file_content_contains
       parameter:
         dst: "C:\\Windows\\Logs\\application.log"
         content: "Service started successfully"
         content_type: "string"
         encoding: "utf-16"
       description: "Search for service start message in UTF-16 encoded log"

Common Use Cases
----------------

**Log File Analysis**
  Search for specific events, errors, or messages in log files

**Configuration Validation**
  Verify that configuration files contain required settings or values

**Generated Content Verification**
  Ensure generated files contain expected content or markers

**Error Detection**
  Monitor files for error messages or failure indicators

**Binary File Analysis**
  Search for specific byte patterns or signatures in binary files

**Process Monitoring**
  Verify that processes write expected status or completion messages

**Forensic Analysis**
  Search for specific patterns that might indicate malicious activity or data presence

Content Type Details
--------------------

**String Content (default)**
  - File is read as text using the specified encoding (default: UTF-8) with error handling
  - Search is performed on the decoded string content
  - Suitable for text files, logs, configuration files
  - Use the encoding parameter to handle different character encodings

**Byte Content**
  - File is read in binary mode
  - Content parameter is parsed for escape sequences (\\x41, \\n, \\t, etc.)
  - Search is performed on raw byte data
  - Suitable for binary files, executables, or specific byte pattern detection

Escape Sequence Examples
~~~~~~~~~~~~~~~~~~~~~~~~

When using ``content_type: "bytes"``, you can use Python-style escape sequences:

.. code-block:: yaml

   # Search for null-terminated string
   content: "admin\\x00"

   # Search for newline patterns
   content: "\\r\\n\\r\\n"

   # Search for specific hex patterns
   content: "\\xFF\\xFE"

Return Values
-------------

**Success**
  Returns success when the specified content is found within the file

**Failure**
  Returns failure when:

  - The specified content is not found in the file
  - File is empty and content is expected

**Execution Error**
  Returns execution error when:

  - The file cannot be found or read
  - Permission denied reading the file
  - Path resolution fails due to glob pattern ambiguity
  - Unicode decoding errors occur (for string content - try specifying correct encoding parameter)

Example Results
---------------

.. code-block:: yaml

   # Success case - string content
   result: success
   details:
     - "string content found in file"

   # Success case - byte content
   result: success
   details:
     - "byte pattern found in file"

   # Failure case
   result: failed
   details:
     - "string content not found in file"

   # Execution error case
   result: execution_error
   error: "FileNotFoundError"
   context: "file with path /missing/log.txt does not exist"

