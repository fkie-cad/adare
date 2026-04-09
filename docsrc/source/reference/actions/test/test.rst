test
====

Execute a validation test defined in the ``tests`` section of the playbook.

Usage Example
-------------

.. code-block:: yaml

   tests:
     - name: file_created
       function: file_exists
       parameter:
         dst: "/tmp/testfile.txt"
       description: "Verify test file exists"

   actions:
     - command:
         command: "touch /tmp/testfile.txt"
         description: "Create test file"

     # Run the test
     - test: file_created

     # Alternative syntax with description
     - test:
         name: file_created
         description: "Validate file creation"

Parameters
----------

.. list-table::
   :widths: 20 15 65
   :header-rows: 1

   * - Parameter
     - Type
     - Description
   * - ``name``
     - string
     - Name of the test to execute (required)
   * - ``description``
     - string
     - Human-readable description (optional)

Notes
-----

- Tests must be defined in the ``tests`` section before use
- Test execution validates forensic artifacts
- Failed tests can trigger auto-pull of evidence files (if ``auto_pull_on_test_failure`` enabled)
- Use ``expect_to_fail: true`` in test definition for negative assertions

See Also
--------

- :doc:`../../testfunctions/index` for available test functions
- Test configuration in playbook settings
