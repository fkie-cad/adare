system_service_status
======================

.. role:: status-dev
   :class: status-dev

:Status: :status-dev:`● Development`
:Category: Linux System
:Function Name: ``system_service_status``

**Tests if a systemd service has expected status (Linux only).**

This test function checks the status of a systemd service using the ``systemctl`` command and validates that it matches the expected status. It supports checking for active, inactive, failed, and other systemd service states.

Parameters
----------

.. list-table::
   :widths: 20 15 65
   :header-rows: 1

   * - Parameter
     - Type
     - Description
   * - ``service_name``
     - string
     - **Required.** The name of the systemd service to check (e.g., "nginx", "systemd-resolved").
   * - ``expected_status``
     - string
     - **Required.** The expected service status (e.g., "active", "inactive", "failed").

Usage Example
-------------

Active Service Check
~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: test_service_active
       function: linux.system_service_status
       parameter:
         service_name: 'systemd-resolved'
         expected_status: 'active'
       description: "Test system_service_status with active service"

Inactive Service Check
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: test_service_inactive
       function: linux.system_service_status
       parameter:
         service_name: 'nonexistent-service'
         expected_status: 'inactive'
       description: "Test system_service_status with inactive service"

Variable-Based Service Names
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   variables:
     web_service:
       type: string
       value: "nginx"
       description: "Web server service"

   tests:
     - name: test_web_service_running
       function: linux.system_service_status
       parameter:
         service_name: '{{web_service}}'
         expected_status: 'active'
       description: "Test web service is running"

Common Use Cases
----------------

**System Service Monitoring**
  Verify that critical system services are running as expected

**Service Health Checks**
  Ensure services haven't failed or stopped unexpectedly

**Post-Installation Validation**
  Confirm that newly installed services are properly started

**Security Service Verification**
  Check that security-related services like firewalls are active

**Container Runtime Validation**
  Verify that Docker, containerd, or other container services are running

Service Status Values
---------------------

**Common Status Values:**
  - ``active`` - Service is running and operational
  - ``inactive`` - Service is stopped
  - ``failed`` - Service failed to start or crashed
  - ``activating`` - Service is in the process of starting
  - ``deactivating`` - Service is in the process of stopping

**Platform Requirements:**
  - Linux operating system with systemd
  - Access to ``systemctl`` command
  - Appropriate permissions to query service status

Return Values
-------------

**Success**
  Returns success when the service status matches the expected status

**Failure**
  Returns failure when:
  - Service status doesn't match expected status
  - Service doesn't exist

**Execution Error**
  Returns execution error when:
  - Not running on Linux system
  - ``systemctl`` command not available or fails
  - Timeout occurs while checking service status
  - Permission denied accessing service information

Example Results
---------------

.. code-block:: yaml

   # Success case
   result: success
   details:
     - "service systemd-resolved is active"

   # Failure case - status mismatch
   result: failed
   details:
     - "service nginx status mismatch. Expected: active, Got: inactive"

   # Execution error case - wrong platform
   result: execution_error
   error: "This test only runs on Linux"

   # Execution error case - timeout
   result: execution_error
   error: "Timeout checking service status for slow-service"