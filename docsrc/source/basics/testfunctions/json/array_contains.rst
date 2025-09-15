array_contains
==============

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: JSON Data
:Function Name: ``array_contains``

**Tests if JSON array at specified path contains expected element.**

This test function verifies that a JSON array contains a specific element. It supports both direct value matching and placeholder-based matching for flexible array content validation.

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
   * - ``array_path``
     - string
     - **Required.** The path to the JSON array using dot notation (e.g., "users" or "config.servers").
   * - ``expected_element``
     - string/int/float/bool/dict/list
     - **Required.** The element that should exist in the array. Supports placeholders for pattern matching.

Usage Example
-------------

Basic String Array Element
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: test_json_array_contains_string
       function: json.array_contains
       parameter:
         dst: '/home/adare/test_json/config.json'
         array_path: 'features'
         expected_element: 'logging'
       description: "Test json_array_contains with string element"

Numeric Array Element
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: test_json_array_contains_integer
       function: json.array_contains
       parameter:
         dst: '/home/adare/test_json/users.json'
         array_path: 'user_ids'
         expected_element: 123
       description: "Test json_array_contains with integer element"

Complex Object in Array
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: test_json_array_contains_object
       function: json.array_contains
       parameter:
         dst: '/home/adare/test_json/users.json'
         array_path: 'permissions'
         expected_element: {"action": "read", "resource": "users"}
       description: "Test json_array_contains with object element"

Expected Failure Cases
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: test_json_array_contains_not_found
       function: json.array_contains
       expect_to_fail: true
       parameter:
         dst: '/home/adare/test_json/config.json'
         array_path: 'features'
         expected_element: 'nonexistent_feature'
       description: "Test json_array_contains with non-existent element"

     - name: test_json_array_contains_not_array
       function: json.array_contains
       expect_to_fail: true
       parameter:
         dst: '/home/adare/test_json/config.json'
         array_path: 'app_name'
         expected_element: 'anything'
       description: "Test json_array_contains with non-array path"

Common Use Cases
----------------

**Permission Validation**
  Check if user roles or permissions arrays contain specific values

**Configuration Verification**
  Validate that configuration arrays include required elements

**Data Validation**
  Ensure arrays contain expected data elements or structures

**Log Analysis**
  Verify log arrays contain specific events or error types

**API Response Testing**
  Validate that API response arrays include expected items

Array Element Matching
-----------------------

**Direct Value Matching**
  - Compares elements using exact equality
  - Supports strings, numbers, booleans, and complex objects
  - Arrays and objects are compared by structure and content

**Placeholder Matching**
  - Use placeholders like ``{timestamp}`` for pattern-based matching
  - Enables flexible validation of formatted strings within arrays
  - Supports regex patterns and timestamp tolerance matching

Return Values
-------------

**Success**
  Returns success when the array contains the expected element

**Failure**
  Returns failure when:

  - The array path does not exist
  - The path exists but is not an array
  - The array does not contain the expected element
  - Invalid JSON syntax in the file
  - File does not exist

**Execution Error**
  Returns execution error when:

  - Permission denied accessing the file
  - Placeholder comparison encounters errors
  - System I/O errors occur

Example Results
---------------

.. code-block:: yaml

   # Success case - direct match
   result: success
   message: "array contains expected element: admin"

   # Success case - placeholder match
   result: success
   message: "array element [2] matches placeholder: timestamp format valid"

   # Failure case - element not found
   result: failed
   details:
     - "array does not contain expected element: manager"

   # Failure case - not an array
   result: failed
   details:
     - 'path "user.roles" is not an array, got str'

   # Failure case - path not found
   result: failed
   details:
     - 'array path "user.permissions" does not exist'

   # Execution error case
   result: execution_error
   error: "PermissionError: [Errno 13] Permission denied"
   context: "Cannot read JSON file /root/secure.json"