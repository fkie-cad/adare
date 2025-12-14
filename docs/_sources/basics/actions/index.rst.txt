Actions Reference
=================

ADARE playbooks define forensic experiments through automated actions. This reference documents all available action types organized by category.

Action Categories
-----------------

.. list-table::
   :widths: 20 15 65
   :header-rows: 1

   * - Category
     - Actions
     - Description
   * - :doc:`gui/index`
     - 4
     - GUI interactions: clicks, keyboard input, drag-and-drop, scrolling
   * - :doc:`command/index`
     - 1
     - Shell command execution with output capture
   * - :doc:`test/index`
     - 1
     - Execute forensic validation tests
   * - :doc:`flow/index`
     - 6
     - Flow control: delays, loops, conditional execution, branching
   * - :doc:`variable/index`
     - 2
     - Variable management: timestamps, computed values
   * - :doc:`file/index`
     - 3
     - File transfer and filesystem state tracking
   * - :doc:`debug/index`
     - 2
     - Debugging: interactive pauses, screenshots

Quick Example
-------------

.. code-block:: yaml

   # Basic playbook demonstrating common actions
   settings:
     idle: 1.0

   variables:
     evidence_file:
       type: path
       value: "/home/adare/test.txt"

   actions:
     # Command execution
     - command:
         command: "touch {{evidence_file}}"
         description: "Create test file"

     # Capture timestamp
     - save_timestamp:
         variable: "creation_time"

     # GUI interaction
     - click:
         target:
           text: "File Manager"

     # Wait for condition
     - wait_until:
         condition:
           exists:
             text: "Documents"
         timeout: 30.0

     # Pull forensic evidence
     - pull:
         src: "{{evidence_file}}"

     # Run validation test
     - test: verify_file_exists

Detailed Documentation
----------------------

.. toctree::
   :maxdepth: 2

   gui/index
   command/index
   test/index
   flow/index
   variable/index
   file/index
   debug/index

See Also
--------

- :doc:`../experiments` for experiment workflow
- :doc:`../testfunctions/index` for available test functions
- :doc:`../../advanced/playbook-patterns` for advanced usage patterns
