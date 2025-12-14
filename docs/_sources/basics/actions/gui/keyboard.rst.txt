keyboard
========

Send keyboard input - type text, press special keys, or execute key combinations.

Usage Examples
--------------

**Type Text**

.. code-block:: yaml

   actions:
     - keyboard:
         text: "forensic evidence data"
         description: "Enter evidence data"

**Key Combinations**

.. code-block:: yaml

   actions:
     # Save shortcut
     - keyboard:
         combination: ["ctrl", "s"]
         description: "Save file"

     # Close application
     - keyboard:
         combination: ["alt", "f4"]
         description: "Close window"

**Special Keys**

.. code-block:: yaml

   actions:
     - keyboard:
         key: "enter"
         description: "Press Enter"

     - keyboard:
         key: "f5"
         description: "Refresh"

Parameters
----------

.. list-table::
   :widths: 20 15 65
   :header-rows: 1

   * - Parameter
     - Type
     - Description
   * - ``text``
     - string
     - Text to type (mutually exclusive with key/combination)
   * - ``key``
     - string
     - Single special key to press
   * - ``combination``
     - list
     - Key combination (e.g., ["ctrl", "s"])
   * - ``description``
     - string
     - Human-readable description (optional)

Available Special Keys
----------------------

- **Function keys**: ``f1``, ``f2``, ..., ``f12``
- **Arrow keys**: ``arrow_up``, ``arrow_down``, ``arrow_left``, ``arrow_right``
- **Navigation**: ``home``, ``end``, ``page_up``, ``page_down``
- **Editing**: ``insert``, ``delete``, ``backspace``
- **System**: ``escape``, ``enter``, ``tab``, ``space``
- **Modifiers**: ``ctrl``, ``alt``, ``shift``, ``cmd`` (Mac)

Notes
-----

- Exactly one of ``text``, ``key``, or ``combination`` must be specified
- Key combinations execute modifiers simultaneously
- Text typing simulates natural keystroke timing

See Also
--------

- :doc:`click` for mouse interactions
