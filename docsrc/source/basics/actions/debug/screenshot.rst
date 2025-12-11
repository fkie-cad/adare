screenshot
==========

Capture a screenshot of the guest VM screen for forensic evidence or debugging.

Usage Examples
--------------

**Full Screen Capture**

.. code-block:: yaml

   actions:
     - screenshot:
         name: "evidence_screen"
         description: "Capture current screen state"

**Screenshot with Timestamp**

.. code-block:: yaml

   actions:
     - screenshot:
         name: "deletion_{{timestamp}}"
         description: "Capture screen at deletion time"

**Region Capture**

.. code-block:: yaml

   actions:
     - screenshot:
         name: "dialog_capture"
         x: 100
         y: 100
         width: 400
         height: 300
         description: "Capture dialog box only"

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
     - Custom filename (without extension) (optional)
   * - ``x``
     - integer
     - X-coordinate of region top-left corner (optional)
   * - ``y``
     - integer
     - Y-coordinate of region top-left corner (optional)
   * - ``width``
     - integer
     - Width of region to capture (optional)
   * - ``height``
     - integer
     - Height of region to capture (optional)
   * - ``description``
     - string
     - Human-readable description (optional)

Notes
-----

- Screenshots saved to ``<run-directory>/screenshots/``
- Default format and quality from playbook settings
- Region capture requires all four parameters (x, y, width, height)
- Automatic screenshots can be enabled in settings (``screenshot.on_action``, ``screenshot.on_error``)
- Filenames support variable substitution

See Also
--------

- :doc:`pause` for interactive debugging
- Playbook settings for global screenshot configuration
