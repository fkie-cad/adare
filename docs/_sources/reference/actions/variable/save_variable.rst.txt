save_variable
=============

Store values in variables during playbook execution - either static values or computed from Jinja2 expressions.

Usage Examples
--------------

**Static Values**

.. code-block:: yaml

   actions:
     # String value
     - save_variable:
         name: my_var
         value: "hello world"
         description: "Store a static string"

     # Numeric values
     - save_variable:
         name: counter
         value: 0

     # List value
     - save_variable:
         name: items
         value: [1, 2, 3]

**Expression Evaluation**

.. code-block:: yaml

   actions:
     # Increment counter
     - save_variable:
         name: counter
         value: "{{ counter + 1 }}"
         description: "Increment counter"

     # Transform existing variable
     - save_variable:
         name: upper_name
         value: "{{ username | upper }}"
         description: "Convert username to uppercase"

     # Construct paths
     - save_variable:
         name: full_path
         value: "{{ base_dir }}/{{ filename }}"
         description: "Build file path from components"

**Use in Loops**

.. code-block:: yaml

   actions:
     - save_variable:
         name: total
         value: 0

     - loop:
         times: 5
         actions:
           - save_variable:
               name: total
               value: "{{ total + index }}"

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
     - Variable name to store the value (required)
   * - ``value``
     - any
     - Static value or Jinja2 expression (required)
   * - ``description``
     - string
     - Human-readable description (optional)

Type Coercion
-------------

When using Jinja2 expressions, the result is automatically converted to the appropriate type:

- ``"123"`` → integer ``123``
- ``"3.14"`` → float ``3.14``
- ``"true"`` / ``"false"`` → boolean ``True`` / ``False``
- Lists and dicts preserve their structure
- Other values remain as strings

Notes
-----

- Jinja2 expressions are detected by the presence of ``{{`` and ``}}``
- Static values (not wrapped in ``{{ }}``) are stored as-is
- Variables are stored in both execution context and variable registry
- Undefined variables in expressions raise clear errors (StrictUndefined mode)

See Also
--------

- :doc:`save_timestamp` for recording timestamps
- :doc:`../command/command` for capturing command output
- :doc:`../flow/loop` for iteration with automatic variables
