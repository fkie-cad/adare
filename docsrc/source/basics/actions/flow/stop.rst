stop
====

Stop playbook execution conditionally or unconditionally.

Usage Examples
--------------

**Unconditional Stop**

.. code-block:: yaml

   actions:
     - command:
         command: "whoami"
         capture:
           variable: current_user
     - stop:
         description: "Stop here for debugging"

**Conditional Stop**

.. code-block:: yaml

   actions:
     - command:
         command: "whoami"
         capture:
           variable: current_user
     - stop:
         condition:
           variable: current_user
           is_empty: true
         description: "Stop if username capture failed"

**Numeric Comparison**

.. code-block:: yaml

   actions:
     - command:
         command: "echo '150'"
         capture:
           variable: count
           parser: "int(output.strip())"
     - stop:
         condition:
           variable: count
           greater_than: 100
         description: "Stop if count exceeds threshold"

Parameters
----------

.. list-table::
   :widths: 20 15 65
   :header-rows: 1

   * - Parameter
     - Type
     - Description
   * - ``condition``
     - VariableCondition
     - Condition for stopping (optional - without it, always stops)
   * - ``description``
     - string
     - Human-readable description (optional)

Condition Operators
-------------------

- ``equals``: Direct equality (case-sensitive)
- ``contains``: Substring match
- ``matches``: Regex pattern match
- ``greater_than``: Numeric comparison (>)
- ``less_than``: Numeric comparison (<)
- ``is_empty``: Check if variable is None/empty

Notes
-----

- Without a condition, stop always executes
- When condition is true, playbook execution halts immediately
- Exactly one operator must be specified per condition
- Conditions evaluated on host machine

See Also
--------

- :doc:`continue` for skipping current iteration
- :doc:`../command/command` for capturing values to test
- :doc:`../../advanced/playbook-patterns` for complex patterns
