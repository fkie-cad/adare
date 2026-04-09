pause
=====

Pause playbook execution and wait for user confirmation before continuing.

Usage Example
-------------

.. code-block:: yaml

   actions:
     - command:
         command: "setup_test_environment.sh"

     # Pause for manual inspection
     - pause:
         message: "Verify test environment before continuing"
         description: "Manual verification checkpoint"

     # Continue with tests after user confirms
     - test: verify_setup

Parameters
----------

.. list-table::
   :widths: 20 15 65
   :header-rows: 1

   * - Parameter
     - Type
     - Description
   * - ``message``
     - string
     - Message displayed to user during pause (optional)
   * - ``name``
     - string
     - Name for this pause point (optional)
   * - ``description``
     - string
     - Human-readable description (optional)

Notes
-----

- Execution halts until user manually resumes
- Useful for debugging, manual verification, or interactive testing
- User can inspect VM state before continuing
- Not recommended for automated/production experiments

See Also
--------

- :doc:`../flow/idle` for automatic delays
- :doc:`screenshot` for capturing screen state
