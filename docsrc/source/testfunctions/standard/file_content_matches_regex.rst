file_content_matches_regex
===========================

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: File System
:Function Name: ``file_content_matches_regex``

**Tests if file content matches a given regular expression.**

This test function reads a file and checks if its content matches the provided regular expression pattern. It's useful for validating log entries, configuration values, or any structured text content.

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
   * - ``regex``
     - string
     - **Required.** The regular expression pattern to match against the file content.

Usage Example
-------------

Log File Validation
~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: verify_error_logged
       function: file_content_matches_regex
       parameter:
         dst: "/var/log/application.log"
         regex: "ERROR.*Authentication failed.*user:.*"
       description: "Verify authentication error was logged with user details"

Configuration Validation
~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: check_config_value
       function: file_content_matches_regex
       parameter:
         dst: "/etc/myapp/config.ini"
         regex: "port\\s*=\\s*8080"
       description: "Verify port is configured correctly"

Multi-line Pattern Matching
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: verify_sql_query
       function: file_content_matches_regex
       parameter:
         dst: "/tmp/generated_query.sql"
         regex: "SELECT\\s+\\*\\s+FROM\\s+users\\s+WHERE\\s+active\\s*=\\s*1"
       description: "Verify correct SQL query was generated"

Common Use Cases
----------------

**Log Analysis**
  Validate that specific events, errors, or patterns appear in log files

**Configuration Verification**
  Ensure configuration files contain expected values or settings

**Generated Content Validation**
  Verify that automated processes generate content with expected patterns

**Data Format Verification**
  Confirm that exported data follows expected formats

**Template Output Validation**
  Ensure template processing produces content matching expected patterns

**Forensic Analysis**
  Search for specific patterns in files that might indicate malicious activity

Regular Expression Tips
-----------------------

**Case Sensitivity**
  Regex matching is case-sensitive by default. Use ``(?i)`` for case-insensitive matching:

  .. code-block:: yaml

     regex: "(?i)error.*authentication"

**Multiline Matching**
  Use ``.*`` to match across lines, or specific line break patterns:

  .. code-block:: yaml

     regex: "START.*END"  # Matches across multiple lines

**Escaping Special Characters**
  Escape regex special characters with backslashes:

  .. code-block:: yaml

     regex: "\\$\\{.*\\}"  # Matches ${...} patterns

Return Values
-------------

**Success**
  Returns success when the file content matches the regular expression

**Failure**
  Returns failure when:

  - The file content does not match the regular expression
  - The file exists but is empty and the regex expects content

**Execution Error**
  Returns execution error when:

  - The file cannot be found or read
  - The regular expression pattern is invalid
  - Permission denied reading the file
  - Path resolution fails due to glob pattern ambiguity

Example Results
---------------

.. code-block:: yaml

   # Success case
   result: success
   message: "File content matches regex pattern"

   # Failure case
   result: failed
   details:
     - "file content does not match regex expression"

   # Execution error - invalid regex
   result: execution_error
   error: "re.error: unterminated character set at position 10"
   context: "Invalid regex pattern: [abc"

   # Execution error - file not found
   result: execution_error
   error: "FileNotFoundError"
   context: "file with path /missing/file.log does not exist"

