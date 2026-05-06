log_entry_exists
================

.. role:: status-dev
   :class: status-dev

:Status: :status-dev:`● Development`
:Category: Linux System
:Function Name: ``log_entry_exists``

**Tests if a log file contains entries matching a specified pattern.**

This test function searches log files for entries matching a specified pattern or regular expression. It supports limiting the search scope and is useful for validating system events and application logging.

Parameters
----------

.. list-table::
   :widths: 20 15 65
   :header-rows: 1

   * - Parameter
     - Type
     - Description
   * - ``log_file``
     - string
     - **Required.** The path to the log file to search. Supports glob patterns.
   * - ``pattern``
     - string
     - **Required.** The pattern or regex to search for in the log file.
   * - ``max_lines``
     - integer
     - **Optional.** Maximum number of lines to search from the end of the file. Limits search scope for large log files.

Usage Example
-------------

Basic Log Pattern Search
~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: test_log_entry_systemd
       function: linux.log_entry_exists
       parameter:
         log_file: '/var/log/syslog'
         pattern: 'systemd'
         max_lines: 1000
       description: "Test log_entry_exists with systemd pattern"

Pattern Not Found
~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: test_log_entry_not_found
       function: linux.log_entry_exists
       expect_to_fail: true
       parameter:
         log_file: '/var/log/syslog'
         pattern: 'nonexistent-log-pattern-12345'
         max_lines: 100
       description: "Test log_entry_exists with non-existent pattern"

Application Log Validation
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: test_application_error_logged
       function: linux.log_entry_exists
       parameter:
         log_file: '/var/log/myapp/error.log'
         pattern: 'ERROR.*authentication failed'
         max_lines: 500
       description: "Test that authentication errors are logged"

Security Log Monitoring
~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: test_ssh_login_logged
       function: linux.log_entry_exists
       parameter:
         log_file: '/var/log/auth.log'
         pattern: 'sshd.*Accepted password'
         max_lines: 1000
       description: "Test that SSH logins are logged"

Variable-Based Log Paths
~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   variables:
     app_log:
       type: path
       value: "/var/log/nginx/access.log"
       description: "Web server access log"

   tests:
     - name: test_web_requests_logged
       function: linux.log_entry_exists
       parameter:
         log_file: '{{app_log}}'
         pattern: 'GET /api/'
         max_lines: 2000
       description: "Test that API requests are logged"

Common Use Cases
----------------

**System Event Validation**
  Verify that system events are properly logged to system logs

**Application Error Monitoring**
  Check that application errors and exceptions are being logged

**Security Audit Trail**
  Ensure security-related events like logins and access attempts are logged

**Performance Monitoring**
  Validate that performance metrics and warnings appear in logs

**Service Health Checking**
  Confirm that services are logging startup, shutdown, and operational events

Log Search Features
-------------------

**Pattern Matching:**
  - Supports literal string matching
  - Regular expression pattern matching
  - Case-sensitive pattern matching

**Search Optimization:**
  - ``max_lines`` parameter limits search scope for performance
  - Searches from the end of the log file (most recent entries first)
  - Useful for large log files to avoid long search times

**File Access:**
  - Supports standard log file paths
  - Glob pattern support for dynamic log file names
  - Handles log rotation and compressed logs

**Platform Requirements:**
  - Linux operating system
  - Read access to specified log files
  - Standard file system access

Return Values
-------------

**Success**
  Returns success when the pattern is found in the log file within the specified search scope

**Failure**
  Returns failure when:
  - Pattern is not found in the log file
  - Log file exists but doesn't contain matching entries
  - Search completes without finding the pattern

**Execution Error**
  Returns execution error when:
  - Log file doesn't exist or cannot be accessed
  - Permission denied reading the log file
  - File I/O errors occur during search
  - Invalid regular expression pattern provided

Example Results
---------------

.. code-block:: yaml

   # Success case
   result: success
   details:
     - "pattern 'systemd' found in log file /var/log/syslog"

   # Failure case - pattern not found
   result: failed
   details:
     - "pattern 'nonexistent-log-pattern-12345' not found in log file /var/log/syslog"

   # Execution error case - file not found
   result: execution_error
   error: "log file /var/log/missing.log does not exist"

   # Execution error case - permission denied
   result: execution_error
   error: "Permission denied accessing log file /var/log/secure"