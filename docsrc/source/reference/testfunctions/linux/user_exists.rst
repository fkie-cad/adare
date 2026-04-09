user_exists
===========

.. role:: status-dev
   :class: status-dev

:Status: :status-dev:`● Development`
:Category: Linux System
:Function Name: ``user_exists``

**Tests if a user account exists on the Linux system.**

This test function checks if a specified user account exists on the Linux system using the system's user database. It validates user account presence for security and configuration verification.

Parameters
----------

.. list-table::
   :widths: 20 15 65
   :header-rows: 1

   * - Parameter
     - Type
     - Description
   * - ``username``
     - string
     - **Required.** The username to check for existence on the system.

Usage Example
-------------

Existing User Check
~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: test_user_exists
       function: linux.user_exists
       parameter:
         username: 'adare'
       description: "Test user_exists with existing user"

Non-Existent User Check
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: test_user_does_not_exist
       function: linux.user_exists
       expect_to_fail: true
       parameter:
         username: 'nonexistent-user-12345'
       description: "Test user_exists with non-existent user"

Variable-Based Username
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   variables:
     app_user:
       type: string
       value: "nginx"
       description: "Application service user"

   tests:
     - name: test_service_user_exists
       function: linux.user_exists
       parameter:
         username: '{{app_user}}'
       description: "Test that service user account exists"

Common Use Cases
----------------

**Service Account Validation**
  Verify that service accounts for applications are properly created

**User Account Auditing**
  Check for the presence of expected user accounts during security audits

**Post-Installation Verification**
  Confirm that installation scripts properly created required user accounts

**System Configuration Validation**
  Ensure that system users required for specific functionality exist

**Security Compliance Checking**
  Validate that required administrative or service accounts are present

User Account Detection
----------------------

**Account Validation:**
  - Uses Linux user database (typically ``/etc/passwd``)
  - Supports system users and regular user accounts
  - Cross-references with user ID information

**Platform Requirements:**
  - Linux operating system
  - Access to user account information
  - Python ``pwd`` module support (Unix systems)

Return Values
-------------

**Success**
  Returns success when the specified user account exists on the system

**Failure**
  Returns failure when:
  - User account does not exist
  - Username is not found in the system user database

**Execution Error**
  Returns execution error when:
  - Not running on Linux system
  - Unix modules not available (``pwd`` module missing)
  - Permission denied accessing user information
  - System error occurs while checking user accounts

Example Results
---------------

.. code-block:: yaml

   # Success case
   result: success
   details:
     - "user 'adare' exists on system"

   # Failure case - user not found
   result: failed
   details:
     - "user 'nonexistent-user-12345' does not exist on system"

   # Execution error case - wrong platform
   result: execution_error
   error: "This test only runs on Linux"

   # Execution error case - missing modules
   result: execution_error
   error: "Unix modules not available for user validation"