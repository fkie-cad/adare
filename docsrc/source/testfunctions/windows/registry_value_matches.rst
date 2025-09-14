registry_value_matches
======================

.. role:: status-dev
   :class: status-dev

:Status: :status-dev:`● Development`
:Category: Windows System
:Function Name: ``registry_value_matches``

**Tests if Windows registry value matches expected value with type validation (Windows only).**

This test function checks if a Windows Registry value exists and matches the expected value and data type. It supports various registry data types including strings, DWORD, binary data, and others.

Parameters
----------

.. list-table::
   :widths: 20 15 65
   :header-rows: 1

   * - Parameter
     - Type
     - Description
   * - ``key_path``
     - string
     - **Required.** Full registry path including hive.
   * - ``value_name``
     - string
     - **Required.** Name of the registry value to check.
   * - ``expected_value``
     - string/int/bytes
     - **Required.** Expected value content.
   * - ``value_type``
     - string
     - **Optional.** Expected registry value type (e.g., "REG_SZ", "REG_DWORD").

Usage Example
-------------

String Value Validation
~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: test_registry_value_string
       function: windows.registry_value_matches
       parameter:
         key_path: 'HKEY_CURRENT_USER\\Software\\TestApp'
         value_name: 'StringValue'
         expected_value: 'TestStringValue'
         value_type: 'REG_SZ'
       description: "Test registry_value_matches with string value"

DWORD Value Validation
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: test_registry_value_dword
       function: windows.registry_value_matches
       parameter:
         key_path: 'HKEY_CURRENT_USER\\Software\\TestApp'
         value_name: 'DwordValue'
         expected_value: 42
         value_type: 'REG_DWORD'
       description: "Test registry_value_matches with DWORD value"

System Registry Value Check
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: test_registry_value_system
       function: windows.registry_value_matches
       parameter:
         key_path: 'HKEY_LOCAL_MACHINE\\Software\\Microsoft\\Windows\\CurrentVersion'
         value_name: 'CurrentVersion'
         expected_value: '10.0'
         value_type: 'REG_SZ'
       description: "Test registry_value_matches with system value"

Without Type Validation
~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: test_registry_value_no_type
       function: windows.registry_value_matches
       parameter:
         key_path: 'HKEY_CURRENT_USER\\Software\\TestApp'
         value_name: 'AnyValue'
         expected_value: 'SomeValue'
       description: "Test registry value without type validation"

Variable-Based Registry Values
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   variables:
     app_version_key:
       type: string
       value: "HKEY_LOCAL_MACHINE\\Software\\MyApp"
       description: "Application version registry key"

   tests:
     - name: test_app_version
       function: windows.registry_value_matches
       parameter:
         key_path: '{{app_version_key}}'
         value_name: 'Version'
         expected_value: '2.1.0'
         value_type: 'REG_SZ'
       description: "Test application version in registry"

Common Use Cases
----------------

**Application Configuration Validation**
  Verify that application settings are correctly stored in the registry

**System Configuration Verification**
  Check system-wide configuration values in the registry

**Software Installation Validation**
  Ensure installation processes set correct registry values

**Version Information Verification**
  Validate software version numbers stored in registry

**Security Settings Validation**
  Check that security-related registry values are set correctly

Registry Value Types
--------------------

**Supported Value Types:**
  - ``REG_SZ`` - String value
  - ``REG_DWORD`` - 32-bit integer value
  - ``REG_BINARY`` - Binary data
  - ``REG_EXPAND_SZ`` - Expandable string value
  - ``REG_MULTI_SZ`` - Multi-string value
  - ``REG_QWORD`` - 64-bit integer value

**Value Comparison:**
  - String values: Direct string comparison
  - DWORD/QWORD values: Numeric comparison
  - Binary values: Byte-by-byte comparison
  - Multi-string values: Array comparison

**Type Validation:**
  - Optional type checking with ``value_type`` parameter
  - Validates both value content and registry data type
  - Fails if type doesn't match expected type

**Platform Requirements:**
  - Windows operating system
  - Python ``winreg`` module availability
  - Appropriate permissions to read registry values

Return Values
-------------

**Success**
  Returns success when the registry value exists, matches the expected value, and (if specified) matches the expected type

**Failure**
  Returns failure when:
  - Registry value does not exist
  - Value content doesn't match expected value
  - Value type doesn't match expected type (if specified)
  - Registry key doesn't exist

**Execution Error**
  Returns execution error when:
  - Not running on Windows system
  - ``winreg`` module not available
  - Permission denied accessing registry key/value
  - Invalid registry path or value name
  - Registry access errors

Example Results
---------------

.. code-block:: yaml

   # Success case - value matches
   result: success
   details:
     - "registry value 'StringValue' matches expected: TestStringValue (type: REG_SZ)"

   # Failure case - value mismatch
   result: failed
   details:
     - "registry value 'StringValue' mismatch. Expected: 'TestValue', Got: 'ActualValue'"

   # Failure case - type mismatch
   result: failed
   details:
     - "registry value 'DwordValue' type mismatch. Expected: REG_DWORD, Got: REG_SZ"

   # Failure case - value not found
   result: failed
   details:
     - "registry value 'NonExistentValue' not found in key"

   # Execution error case - key not found
   result: execution_error
   error: "registry key does not exist: HKEY_CURRENT_USER\\Software\\NonExistentApp"