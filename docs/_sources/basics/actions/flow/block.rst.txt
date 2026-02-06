block
=====

Group related actions together, optionally with conditional execution.

Usage Examples
--------------

**Basic Grouping**

.. code-block:: yaml

   actions:
     - block:
         description: "Evidence File Setup"
         actions:
           - command:
               command: "mkdir /evidence"
           - command:
               command: "touch /evidence/test.txt"
           - test: file_created

**Conditional Execution**

.. code-block:: yaml

   actions:
     - block:
         when:
           - exists:
               text: "Save"
         description: "Save if button available"
         actions:
           - click:
               target:
                 text: "Save"
           - idle:
               duration: 1.0

**Nested Blocks**

.. code-block:: yaml

   actions:
     - block:
         description: "File Deletion Test"
         actions:
           - block:
               description: "Select File"
               actions:
                 - click:
                     target:
                       text: "test.txt"
           - block:
               description: "Delete File"
               actions:
                 - keyboard:
                     combination: ["delete"]

**Delayed Execution**

.. code-block:: yaml

   actions:
     - block:
         delay: 2.0
         description: "Wait 2s then click OK"
         actions:
           - click:
               target:
                 text: "OK"

Parameters
----------

.. list-table::
   :widths: 20 15 65
   :header-rows: 1

   * - Parameter
     - Type
     - Description
   * - ``actions``
     - list
     - Actions to execute in the block (required)
   * - ``when``
     - list
     - Conditions for block execution (``exists``/``not_exists``)
   * - ``description``
     - string
     - Human-readable description (optional)
   * - ``delay``
     - float
     - Optional delay (seconds) before executing block actions

Notes
-----

- Blocks provide logical grouping and organization
- Conditional execution checks GUI state before running actions
- Nested blocks allow hierarchical action organization
- Variables created in blocks persist to parent scope

See Also
--------

- :doc:`loop` for iterating over actions
- :doc:`wait_until` for conditional waiting
