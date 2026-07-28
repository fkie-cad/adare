loop
====

Repeat actions multiple times or iterate over a list of values.

Usage Examples
--------------

**Counter-Based Loop**

.. code-block:: yaml

   actions:
     - loop:
         times: 5
         description: "Create 5 numbered files"
         actions:
           - command:
               command: "echo 'File {{index}}' > /tmp/file_{{index}}.txt"
               shell: true

**List Iteration**

.. code-block:: yaml

   variables:
     filenames:
       type: list
       value: ["alpha.txt", "beta.txt", "gamma.txt"]

   actions:
     - loop:
         items: "{{filenames}}"
         description: "Process each filename"
         actions:
           - command:
               command: "touch /tmp/{{item}}"
               shell: true

**Custom Item Variable**

.. code-block:: yaml

   actions:
     - loop:
         items: "{{file_list}}"
         item_var: filename
         actions:
           - pull:
               src: "/tmp/{{filename}}"
               dst: "{{filename}}"

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
     - Actions to execute each iteration (required)
   * - ``times``
     - integer
     - Number of times to repeat (mutually exclusive with ``items``)
   * - ``items``
     - list/string
     - List to iterate over (mutually exclusive with ``times``)
   * - ``item_var``
     - string
     - Custom variable name for current item (default: ``item``)
   * - ``description``
     - string
     - Human-readable description (optional)

Loop Variables
--------------

Automatic variables available in loop actions:

- ``{{index}}``: Current iteration number (0-based)
- ``{{total}}``: Total number of iterations
- ``{{item}}``: Current list item (or custom name via ``item_var``)

Notes
-----

- Exactly one of ``times`` or ``items`` must be specified
- Variables created in loop iterations persist to parent scope
- Use ``continue`` action to skip remaining actions in current iteration
- A failing action or test stops the loop at that iteration; the run summary reports
  how many iterations completed

Run Summary
-----------

Everything a loop executes is counted in the closing run summary, including the
``test:`` entries inside the body. A ten-iteration loop with four assertions per
iteration reports all forty of them, and the nesting is shown so the structure of
the run stays readable::

   📊 Actions: 134/134 passed (4 top-level + 130 in a loop of 10 iterations)
   🧪 Tests: 41/41 passed (1 top-level + 40 in a loop of 10 iterations)

The totals are recomputed from the run's persisted events (``action_events`` and
``test_events`` in the project database), so they match what a query against the
database reports. A failed assertion in any iteration is counted as a failure and
the run summary is red, even when the surrounding top-level actions all succeeded.

See Also
--------

- :doc:`continue` for skipping iterations
- :doc:`block` for grouping actions
- :doc:`../variable/save_variable` for accumulating values across iterations
