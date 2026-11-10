scroll
======

Scroll the screen in a specified direction.

Usage Example
-------------

.. code-block:: yaml

   actions:
     - scroll:
         direction: "down"
         amount: 3
         description: "Scroll down 3 times"

     - scroll:
         direction: "up"
         amount: 1
         description: "Scroll up once"

Parameters
----------

.. list-table::
   :widths: 20 15 65
   :header-rows: 1

   * - Parameter
     - Type
     - Description
   * - ``direction``
     - string
     - Scroll direction: ``up``, ``down``, ``left``, or ``right`` (required)
   * - ``amount``
     - integer
     - Number of scroll increments (required)
   * - ``description``
     - string
     - Human-readable description (optional)
   * - ``verify``
     - mapping
     - Effect check after the input, one of ``exists: <target>`` / ``not_exists: <target>``; the step fails if it does not hold (optional)
   * - ``verify_timeout``
     - float
     - Seconds to poll ``verify`` (default 3.0)
   * - ``effect``
     - string
     - ``none``: no screen change expected, skips the automatic effect check (see :doc:`/guide/negative-results`)

Notes
-----

- Scroll amount is system-dependent (typically 3-5 lines per increment)
- Useful for navigating long lists or documents
- Consider using ``wait_until`` after scrolling to verify content visibility

See Also
--------

- :doc:`click` for clicking elements
- :doc:`../flow/wait_until` for waiting on elements after scrolling
