contains_line
=============

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: CSV Data
:Function Name: ``contains_line``

**Tests if row in a CSV file exists that matches the given entry layout.**

This test function verifies that a CSV file contains a specific row matching the provided entry pattern. It supports exact value matching, regex patterns, and timestamp tolerance for flexible CSV data validation.

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
     - **Required.** The CSV file path to check. Supports glob patterns for dynamic path resolution.
   * - ``entry``
     - list
     - **Required.** Array of values representing the expected CSV row. Supports exact values, regex patterns, and placeholder matching.

Usage Example
-------------

Basic Exact Matching
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: test_csv_contains_line_exact_match
       function: csv.contains_line
       parameter:
         dst: '/home/adare/test_csv/users.csv'
         entry: ['1', 'John Doe', 'john@example.com', 'Admin']
       description: "Test csv_contains_line with exact match"

Mixed Data Types
~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: test_csv_contains_line_mixed_types
       function: csv.contains_line
       parameter:
         dst: '/home/adare/test_csv/access_logs.csv'
         entry: ['2024-01-15', '10:30:45', '192.168.1.100', 'GET', '/api/users', '200']
       description: "Test csv_contains_line with mixed data types"

Regex Pattern Matching
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: test_csv_contains_line_email_regex
       function: csv.contains_line
       parameter:
         dst: '/home/adare/test_csv/users.csv'
         entry: ['1', 'John Doe', '{{email_regex}}', 'Admin']
       description: "Test csv_contains_line with email regex pattern"

     - name: test_csv_contains_line_ip_regex
       function: csv.contains_line
       parameter:
         dst: '/home/adare/test_csv/access_logs.csv'
         entry: ['2024-01-15', '10:30:45', '{{ip_regex}}', 'GET', '/api/users', '200']
       description: "Test csv_contains_line with IP address regex pattern"

Direct Regex Patterns
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: test_csv_contains_line_decimal_regex
       function: csv.contains_line
       parameter:
         dst: '/home/adare/test_csv/transactions.csv'
         entry: ['TXN003', '3.0.1', 'completed', !re '\d+\.\d{2}']
       description: "Test csv_contains_line with decimal number regex"

Timestamp with Tolerance
~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: test_csv_contains_line_current_timestamp
       function: csv.contains_line
       parameter:
         dst: '/home/adare/test_csv/events.csv'
         entry: ['EVENT001', 'user_login', '{{ now | tolerance(30) | format("%Y-%m-%dT%H:%M:%S%z") }}', 'success']
       description: "Test csv_contains_line with current timestamp and tolerance"

Complex Pattern Combinations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: test_csv_contains_line_mixed_regex_timestamp
       function: csv.contains_line
       parameter:
         dst: '/home/adare/test_csv/events.csv'
         entry: ['{{uuid_regex}}', 'system_update', '{{ now | tolerance(30) | format("%Y-%m-%dT%H:%M:%S%z") }}', 'info']
       description: "Test csv_contains_line with both regex and timestamp"

     - name: test_csv_contains_line_all_regex_patterns
       function: csv.contains_line
       parameter:
         dst: '/home/adare/test_csv/transactions.csv'
         entry: ['{{uuid_regex}}', '{{version_regex}}', 'failed', !re '\d+\.\d{2}']
       description: "Test csv_contains_line with multiple regex patterns"

Expected Failure Cases
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: test_csv_contains_line_not_found
       function: csv.contains_line
       expect_to_fail: true
       parameter:
         dst: '/home/adare/test_csv/users.csv'
         entry: ['999', 'Nonexistent User', 'none@example.com', 'Guest']
       description: "Test csv_contains_line with non-existent entry"

     - name: test_csv_contains_line_wrong_column_count
       function: csv.contains_line
       expect_to_fail: true
       parameter:
         dst: '/home/adare/test_csv/users.csv'
         entry: ['1', 'John Doe']  # Missing columns
       description: "Test csv_contains_line with wrong column count"

Common Use Cases
----------------

**Log File Analysis**
  Validate that CSV log files contain specific entries with exact or pattern-based matching

**Data Integrity Verification**
  Ensure CSV data files contain expected records with proper formatting

**API Response Logging**
  Verify that API access logs contain specific request patterns and response codes

**User Data Validation**
  Check that user data exports contain expected user records with proper email formats

**Transaction Monitoring**
  Validate financial or system transaction logs contain expected entries with amounts and IDs

Pattern Matching Features
-------------------------

**Exact Value Matching**
  - Direct string comparison for precise matches
  - Supports all data types (strings, numbers, dates)

**Regex Pattern Matching**
  - Use variable placeholders like ``{{email_regex}}`` for reusable patterns
  - Direct regex with ``!re`` syntax for inline patterns
  - Common patterns: email validation, IP addresses, UUIDs, version numbers

**Timestamp Tolerance**
  - Use ``{{ now | tolerance(seconds) }}`` for time-based matching
  - Flexible formatting with ``format()`` filter
  - Useful for matching recently created records

**Column Count Validation**
  - Automatically validates that the entry has the correct number of columns
  - Fails if the expected entry doesn't match the CSV structure

Return Values
-------------

**Success**
  Returns success when a matching row is found in the CSV file

**Failure**
  Returns failure when:

  - No matching row is found for the given pattern
  - Column count mismatch between entry and CSV rows
  - Regex patterns don't match actual values
  - Timestamp values fall outside tolerance range
  - CSV parsing errors occur

**Execution Error**
  Returns execution error when:

  - Permission denied accessing the file
  - Invalid regex patterns provided
  - System I/O errors occur

Example Results
---------------

.. code-block:: yaml

   # Success case
   result: success

   # Failure case - no match found
   result: failed
   details:
     - "no matching row found for pattern: ['999', 'Nonexistent User', 'none@example.com', 'Guest']"
     - "analyzed 5 rows in CSV file"
     - "closest matches:"
     - "  [1] row 0: ['1', 'John Doe', 'john@example.com', 'Admin']"
     - "      failures: col0('1' != '999'), col1('John Doe' != 'Nonexistent User'), col2('john@example.com' != 'none@example.com'), col3('Admin' != 'Guest')"

   # Failure case - column count mismatch
   result: failed
   details:
     - "no matching row found for pattern: ['1', 'John Doe']"
     - "analyzed 5 rows in CSV file"
     - "closest matches:"
     - "  [1] row 0: ['1', 'John Doe', 'john@example.com', 'Admin']"
     - "      failures: column_count(4 != 2)"

   # Execution error case
   result: execution_error
   error: "PermissionError: [Errno 13] Permission denied"
   context: "Cannot read CSV file /root/protected.csv"