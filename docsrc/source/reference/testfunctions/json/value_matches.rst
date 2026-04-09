value_matches
=============

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: JSON Data
:Function Name: ``value_matches``

**Tests if JSON value at key path matches expected value using placeholders (supports wildcards [*] and * with any/all modes).**

This test function validates that a JSON value at a specified key path matches an expected value. It supports advanced features including wildcard matching, regular expressions, and placeholder comparison for flexible value validation.

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
     - **Required.** The JSON file path to check. Supports glob patterns for dynamic path resolution.
   * - ``key_path``
     - string
     - **Required.** The key path using dot notation. Supports wildcards: ``[*]`` for arrays, ``*`` for all object keys.
   * - ``expected_value``
     - string/int/float/bool/null
     - **Required.** The expected value to match against. Supports placeholders and regex patterns.
   * - ``regex_match``
     - boolean
     - **Optional.** Enable regex matching for string values. Default: ``false``.
   * - ``wildcard_mode``
     - string
     - **Optional.** Mode for wildcard matching: ``any`` (at least one match) or ``all`` (all must match). Default: ``any``.

Usage Example
-------------

Basic Value Matching
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: test_json_value_matches_string
       function: json.value_matches
       parameter:
         dst: '/home/adare/test_json/config.json'
         key_path: 'app_name'
         expected_value: 'TestApplication'
       description: "Test json_value_matches with string value"

Integer and Boolean Values
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: test_json_value_matches_integer
       function: json.value_matches
       parameter:
         dst: '/home/adare/test_json/config.json'
         key_path: 'database.port'
         expected_value: 5432
       description: "Test json_value_matches with integer value"

     - name: test_json_value_matches_boolean_true
       function: json.value_matches
       parameter:
         dst: '/home/adare/test_json/config.json'
         key_path: 'debug_mode'
         expected_value: true
       description: "Test json_value_matches with boolean true"

Wildcard Array Matching
~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: test_json_value_matches_array_wildcard_any
       function: json.value_matches
       parameter:
         dst: '/home/adare/test_json/users.json'
         key_path: 'users[*].active'
         expected_value: true
         wildcard_mode: 'any'
       description: "Test json_value_matches with array wildcard [*] in any mode"

Object Wildcard Matching
~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: test_json_value_matches_object_wildcard_any
       function: json.value_matches
       parameter:
         dst: '/home/adare/test_json/config.json'
         key_path: 'database.*'
         expected_value: 'localhost'
         wildcard_mode: 'any'
       description: "Test json_value_matches with object wildcard * in any mode"

Regex Matching
~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: test_json_value_matches_regex
       function: json.value_matches
       parameter:
         dst: '/home/adare/test_json/config.json'
         key_path: 'version'
         expected_value: '^\d+\.\d+\.\d+$'
         regex_match: true
       description: "Test json_value_matches with regex pattern"

Advanced Regex with Wildcard
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: test_json_value_matches_wildcard_email_regex
       function: json.value_matches
       parameter:
         dst: '/home/adare/test_json/users.json'
         key_path: 'users[*].email'
         expected_value: !re '^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
         wildcard_mode: 'any'
       description: "Test json_value_matches with wildcard and direct email regex"

Common Use Cases
----------------

**Configuration Validation**
  Validate specific configuration values in JSON files

**API Response Testing**
  Verify API response values match expected results

**Data Quality Assurance**
  Ensure JSON data values conform to expected formats

**Wildcard Data Validation**
  Validate multiple array elements or object properties at once

**Pattern Matching**
  Use regex to validate string formats like emails, URLs, or IDs

Wildcard Behavior
-----------------

**Array Wildcards (``[*]``)**
  - ``users[*].name`` matches all user names in the users array
  - Use with ``wildcard_mode: "any"`` to require at least one match
  - Use with ``wildcard_mode: "all"`` to require all elements match

**Object Wildcards (``*``)**
  - ``config.*.enabled`` matches the ``enabled`` field in all config objects
  - Useful for validating properties across dynamic object keys

Return Values
-------------

**Success**
  Returns success when the value matches the expected criteria

**Failure**
  Returns failure when:

  - The key path does not exist
  - The value doesn't match the expected value
  - Wildcard mode requirements are not met (e.g., "all" mode with some non-matches)
  - Regex pattern doesn't match
  - Invalid JSON syntax

**Execution Error**
  Returns execution error when:

  - Invalid regex pattern provided
  - Permission denied accessing the file
  - System I/O errors occur

Example Results
---------------

.. code-block:: yaml

   # Success case - exact match
   result: success
   message: "value matches expected: active"

   # Success case - wildcard any mode
   result: success
   details:
     - 'wildcard path "users[*].status" matched 3/5 values (mode: any)'
     - "matching values: element[0]: active, element[2]: active, element[4]: active"

   # Success case - wildcard all mode
   result: success
   details:
     - 'wildcard path "servers.*.enabled" matched all 4 values (mode: all)'
     - 'all values equal: "true"'

   # Failure case - value mismatch
   result: failed
   details:
     - 'expected "active", got "inactive"'

   # Failure case - wildcard all mode
   result: failed
   details:
     - 'wildcard path "users[*].status" matched 3/5 values (mode: all)'
     - 'expected: "active"'
     - "non-matching values: element[1]: inactive, element[3]: pending"

   # Execution error case
   result: execution_error
   error: "Invalid regex pattern: [unclosed - re.error: unterminated character set at position 0"