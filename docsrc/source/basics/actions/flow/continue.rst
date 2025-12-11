continue
========

Skip remaining actions in the current loop iteration or block.

Usage Examples
--------------

**Continue in Loops**

.. code-block:: yaml

   actions:
     - loop:
         times: 5
         actions:
           - command:
               command: "echo {{index}}"
               capture:
                 variable: iteration_num
                 parser: "int(output.strip())"
           - continue:
               condition:
                 variable: iteration_num
                 equals: 3
               description: "Skip iteration 3"
           - command:
               command: "echo 'Processing {{iteration_num}}'"

**Continue in Blocks**

.. code-block:: yaml

   actions:
     - command:
         command: "echo 'skip'"
         capture:
           variable: action_flag
     - block:
         actions:
           - command:
               command: "echo 'First action'"
           - continue:
               condition:
                 variable: action_flag
                 equals: "skip"
           - command:
               command: "echo 'This will be skipped'"

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
     - Condition for continuing (optional - without it, always continues)
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

- Without a condition, continue always executes
- In loops: skips remaining actions in current iteration, proceeds to next iteration
- In blocks: skips remaining actions in block
- Exactly one operator must be specified per condition

See Also
--------

- :doc:`loop` for iteration
- :doc:`stop` for halting execution
- :doc:`../../advanced/playbook-patterns` for advanced patterns
