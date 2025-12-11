click
=====

Click on GUI elements using image recognition, text matching, or coordinates.

Usage Examples
--------------

**Click by Image**

.. code-block:: yaml

   actions:
     - click:
         target:
           image: "save_button.png"
           confidence: 0.8
         description: "Click the Save button"

**Click by Text**

.. code-block:: yaml

   actions:
     - click:
         target:
           text: "OK"
           case_sensitive: false
         description: "Click OK dialog button"

**Click at Coordinates**

.. code-block:: yaml

   actions:
     - click:
         target:
           coordinates: [150, 300]
         description: "Click at specific location"

Parameters
----------

.. list-table::
   :widths: 20 15 65
   :header-rows: 1

   * - Parameter
     - Type
     - Description
   * - ``target``
     - Target
     - Element to click - image, text, or coordinates (required)
   * - ``type``
     - string
     - Click type: ``left``, ``right``, or ``double`` (default: ``left``)
   * - ``description``
     - string
     - Human-readable description (optional)

Target Options
--------------

- ``image``: Path to reference image with optional ``confidence`` (0.0-1.0)
- ``text``: Text to find with optional ``case_sensitive`` flag
- ``coordinates``: [x, y] pixel coordinates
- ``strategy``: Selection strategy when multiple matches found (SweepStrategy, BestConfidenceStrategy, etc.)

Notes
-----

- Image files should be in the experiment directory
- Text matching uses OCR (Tesseract)
- Coordinates are relative to top-left corner
- Use ``wait_until`` before clicking if element may not be immediately visible

See Also
--------

- :doc:`../flow/wait_until` for waiting on elements
- :doc:`keyboard` for keyboard input
- :doc:`drag` for drag-and-drop operations
