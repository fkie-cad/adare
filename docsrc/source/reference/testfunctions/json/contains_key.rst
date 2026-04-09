contains_key
============

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: JSON Data
:Function Name: ``contains_key``

**Tests if a JSON file contains specified key path (supports dot notation like "user.profile.name").**

This test function verifies that a specific key path exists within a JSON file structure. It uses dot notation to navigate nested JSON objects and is commonly used to validate JSON structure and key presence.

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
     - **Required.** The key path to check using dot notation (e.g., "user.profile.name").

Usage Example
-------------

Basic Usage
~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: test_json_contains_key_root_level
       function: json.contains_key
       parameter:
         dst: '/home/adare/test_json/config.json'
         key_path: 'app_name'
       description: "Test json_contains_key with root level key"

Nested Key Path
~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: test_json_contains_key_nested
       function: json.contains_key
       parameter:
         dst: '/home/adare/test_json/config.json'
         key_path: 'database.host'
       description: "Test json_contains_key with nested key"

Deep Nested Key Path
~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: test_json_contains_key_deep_nested
       function: json.contains_key
       parameter:
         dst: '/home/adare/test_json/nested.json'
         key_path: 'level1.level2.level3.value'
       description: "Test json_contains_key with deeply nested key"

Common Use Cases
----------------

**Configuration Validation**
  Verify that JSON configuration files contain required settings

**API Response Validation**
  Check that API responses contain expected fields and structure

**Log Structure Verification**
  Ensure log files maintain expected JSON structure

**Data Integrity Checking**
  Validate that JSON data files contain required keys

Return Values
-------------

**Success**
  Returns success when the key path exists in the JSON file, along with the value at that path

**Failure**
  Returns failure when:

  - The key path does not exist in the JSON structure
  - The JSON file contains invalid JSON syntax
  - The file does not exist

**Execution Error**
  Returns execution error when:

  - Permission denied accessing the file
  - Path resolution fails due to glob pattern issues
  - System I/O errors occur

Example Results
---------------

.. code-block:: yaml

   # Success case
   result: success
   message: 'key path "user.profile.name" exists with value: "John Doe"'

   # Failure case - key not found
   result: failed
   details:
     - 'key path "user.settings.theme" does not exist'

   # Failure case - invalid JSON
   result: failed
   details:
     - "Invalid JSON in file /tmp/config.json: Expecting ',' delimiter: line 3 column 15 (char 42)"

   # Execution error case
   result: execution_error
   error: "PermissionError: [Errno 13] Permission denied"
   context: "Cannot read JSON file /root/protected.json"