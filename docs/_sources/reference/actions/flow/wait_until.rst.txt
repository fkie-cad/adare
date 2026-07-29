wait_until
==========

Wait for a condition to become true before continuing playbook execution.

Usage Examples
--------------

**Wait for Element**

.. code-block:: yaml

   actions:
     - wait_until:
         condition:
           exists:
             text: "Documents"
         timeout: 30.0
         description: "Wait for Documents folder to appear"

**Wait for Element to Disappear**

.. code-block:: yaml

   actions:
     - wait_until:
         condition:
           not_exists:
             text: "Loading..."
         timeout: 45.0
         description: "Wait for loading indicator to disappear"

**Complex Boolean Logic**

.. code-block:: yaml

   actions:
     # AND logic
     - wait_until:
         condition:
           all:
             - exists:
                 text: "Ready"
             - not_exists:
                 text: "Loading"
         timeout: 30.0

     # OR logic
     - wait_until:
         condition:
           any:
             - exists:
                 text: "Save"
             - exists:
                 text: "Export"
         timeout: 20.0

Parameters
----------

.. list-table::
   :widths: 20 15 65
   :header-rows: 1

   * - Parameter
     - Type
     - Description
   * - ``condition``
     - WaitCondition
     - Condition to wait for (required)
   * - ``timeout``
     - float
     - Maximum wait time in seconds (default: 60.0)
   * - ``check_interval``
     - float
     - Delay between condition checks (default: 0.0)
   * - ``initial_delay``
     - float
     - Delay before first check (default: 5.0)
   * - ``description``
     - string
     - Human-readable description (optional)

Condition Types
---------------

- ``exists``: Wait for GUI element to appear
- ``not_exists``: Wait for GUI element to disappear
- ``all``: All sub-conditions must be true (AND)
- ``any``: Any sub-condition must be true (OR)
- ``negate``: Condition must be false (NOT)

Skip Conditions
---------------

Control when wait_until checks for the target condition based on screen activity.

**Pixel Change Constraints**

.. code-block:: yaml

   # Wait for screen to stabilize before checking
   - wait_until:
       condition:
         exists: {text: "Ready"}
       skip:
         pixel_change:
           above: 0.01        # Skip check if change > 1%
           strategy: 'once'   # Latch once satisfied
           idle: 1.0          # Wait 1s after stability
       timeout: 30.0

   # Wait for screen activity before checking
   - wait_until:
       condition:
         exists: {text: "Processing"}
       skip:
         pixel_change:
           below: 0.005       # Skip check if change < 0.5%
       timeout: 60.0

**Parameters:**

- ``above``: Skip if change % > value (wait for stability)
- ``below``: Skip if change % < value (wait for activity)
- ``strategy``: 'once' (latch) or 'continuous' (always enforce). Default: 'once'
- ``idle``: Seconds to wait after constraint satisfied before checking condition

Match Caching (Performance)
---------------------------

A successful ``exists``/``not_exists`` match is cached for reuse by exactly the next
target-resolution attempt anywhere in the playbook - not for the rest of the run.
That next attempt (e.g. a ``click`` on an identical target: same
image/text/position/strategy/offset) automatically reuses the cached match instead of
re-running CV detection - no flag needed. Actions that don't resolve a target
(keyboard input, a pause, a fixed-coordinate drag) don't consume this slot; only
another target resolution does - whether that's the consuming action itself or an
unrelated ``wait_until`` check that runs first and claims the slot instead, causing
the original cache entry to be dropped as stale. Set ``use_cache: false`` on a target
to opt out of auto-reuse and force fresh detection. See :doc:`../gui/click` for the
full pattern, the opt-out example, and the exact boundary condition.

Notes
-----

- GUI elements located via image matching or text OCR
- Timeout causes action failure if condition not met
- Use ``check_interval`` to reduce CPU usage during long waits

See Also
--------

- :doc:`../gui/click` for clicking elements after waiting
- :doc:`idle` for fixed-duration delays
