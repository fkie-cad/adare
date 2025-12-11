idle
====

Pause playbook execution for a specified duration.

Usage Examples
--------------

.. code-block:: yaml

   actions:
     # Fixed delay
     - idle:
         duration: 2.5
         description: "Wait for application to load"

     # Variable delay
     - idle:
         duration: "{{ load_time }}"
         description: "Wait for configurable load time"

Parameters
----------

.. list-table::
   :widths: 20 15 65
   :header-rows: 1

   * - Parameter
     - Type
     - Description
   * - ``duration``
     - float
     - Delay duration in seconds (required)
   * - ``description``
     - string
     - Human-readable description (optional)

Notes
-----

- Duration supports variable substitution
- Useful for waiting on UI rendering, network operations, or system processes
- For conditional waiting, use ``wait_until`` instead

See Also
--------

- :doc:`wait_until` for waiting on specific conditions
- :doc:`../debug/pause` for interactive pauses
