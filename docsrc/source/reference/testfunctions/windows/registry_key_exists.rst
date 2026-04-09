registry_key_exists
===================

.. role:: status-dev
   :class: status-dev

:Status: :status-dev:`● Development`
:Category: Windows System
:Function Name: ``registry_key_exists``

**Tests if Windows registry key exists (Windows only).**

This test function checks if a specified Windows Registry key exists using the Windows Registry API. It supports all major registry hives and both full and abbreviated hive names.

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
     - **Required.** Full registry path including hive (e.g., "HKEY_LOCAL_MACHINE\\Software\\Microsoft\\Windows\\CurrentVersion").

Usage Example
-------------

System Registry Key Check
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: test_registry_key_exists_system
       function: windows.registry_key_exists
       parameter:
         key_path: 'HKEY_LOCAL_MACHINE\\Software\\Microsoft\\Windows\\CurrentVersion'
       description: "Test registry_key_exists with system key"

Custom Application Key Check
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: test_registry_key_exists_custom
       function: windows.registry_key_exists
       parameter:
         key_path: 'HKEY_CURRENT_USER\\Software\\TestApp'
       description: "Test registry_key_exists with custom created key"

Non-Existent Key Check
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: test_registry_key_does_not_exist
       function: windows.registry_key_exists
       parameter:
         key_path: 'HKEY_CURRENT_USER\\Software\\NonExistentApp'
       description: "Test registry_key_exists with non-existent key"

Variable-Based Registry Paths
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   variables:
     app_registry_key:
       type: string
       value: "HKEY_LOCAL_MACHINE\\Software\\MyCompany\\MyApp"
       description: "Application registry key"

   tests:
     - name: test_app_registry_key
       function: windows.registry_key_exists
       parameter:
         key_path: '{{app_registry_key}}'
       description: "Test that application registry key exists"

Short Hive Names
~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: test_registry_short_hive
       function: windows.registry_key_exists
       parameter:
         key_path: 'HKLM\\Software\\Microsoft\\Windows\\CurrentVersion'
       description: "Test registry key with short hive name (HKLM)"

Common Use Cases
----------------

**Software Installation Validation**
  Verify that software installations created expected registry keys

**Configuration Validation**
  Check that application configuration keys exist in the registry

**System State Verification**
  Ensure required system registry keys are present

**Security Policy Validation**
  Verify that security-related registry keys exist

**Application Uninstall Verification**
  Confirm that registry keys were properly removed during uninstallation

Registry Hive Support
---------------------

**Supported Hives (Full Names):**
  - ``HKEY_CLASSES_ROOT`` - File associations and COM registration
  - ``HKEY_CURRENT_USER`` - Current user settings and preferences
  - ``HKEY_LOCAL_MACHINE`` - System-wide settings and configuration
  - ``HKEY_USERS`` - All user profiles on the system
  - ``HKEY_CURRENT_CONFIG`` - Current hardware configuration

**Supported Hives (Short Names):**
  - ``HKCR`` → ``HKEY_CLASSES_ROOT``
  - ``HKCU`` → ``HKEY_CURRENT_USER``
  - ``HKLM`` → ``HKEY_LOCAL_MACHINE``
  - ``HKU`` → ``HKEY_USERS``
  - ``HKCC`` → ``HKEY_CURRENT_CONFIG``

**Path Format:**
  - Use backslashes (``\\``) as path separators
  - Forward slashes (``/``) are automatically converted to backslashes
  - Case-insensitive hive names supported

**Platform Requirements:**
  - Windows operating system
  - Python ``winreg`` module availability
  - Appropriate permissions to access registry keys

Return Values
-------------

**Success**
  Returns success when the specified registry key exists and is accessible

**Failure**
  Returns failure when:
  - Registry key does not exist
  - Key path is invalid or malformed

**Execution Error**
  Returns execution error when:
  - Not running on Windows system
  - ``winreg`` module not available
  - Permission denied accessing registry key
  - Invalid registry hive specified
  - Registry path parsing errors

Example Results
---------------

.. code-block:: yaml

   # Success case
   result: success
   details:
     - "registry key exists: HKEY_LOCAL_MACHINE\\Software\\Microsoft\\Windows\\CurrentVersion"

   # Failure case - key not found
   result: failed
   details:
     - "registry key does not exist: HKEY_CURRENT_USER\\Software\\NonExistentApp"

   # Execution error case - wrong platform
   result: execution_error
   error: "This test only runs on Windows"

   # Execution error case - permission denied
   result: execution_error
   error: "Permission denied accessing registry key: HKEY_LOCAL_MACHINE\\Security\\Policy"

   # Execution error case - invalid hive
   result: execution_error
   error: "Invalid registry hive: INVALID_HIVE"