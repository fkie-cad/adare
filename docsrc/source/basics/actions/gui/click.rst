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

Target Selection Strategies
----------------------------

When multiple matches are found for a target, you can use strategies to select which one to click.

**ClosestToStrategy - Find Target Near Another Element**

Click elements based on proximity to reference targets (text or images). Useful when the same icon appears multiple times but you want the one near specific text.

**Find icon closest to text:**

.. code-block:: yaml

   actions:
     - click:
         target:
           image: "delete_icon.png"
           strategy:
             ClosestToStrategy:
               text: "File1.txt"
         description: "Click delete icon nearest to File1.txt"

**Find text closest to image:**

.. code-block:: yaml

   actions:
     - click:
         target:
           text: "OK"
           strategy:
             ClosestToStrategy:
               image: "warning_icon.png"
         description: "Click OK button near warning icon"

**Limit search distance (optimization):**

.. code-block:: yaml

   actions:
     - click:
         target:
           image: "submit_button.png"
           strategy:
             ClosestToStrategy:
               text: "Form Title"
               max_distance: 200
         description: "Click submit button within 200 pixels of form title"

The ``max_distance`` parameter (in pixels):

- Filters out matches beyond the specified distance
- Enables performance optimization by cropping the screenshot before CV processing
- Action fails if no matches found within the distance limit

**Fixed coordinates (backwards compatible):**

.. code-block:: yaml

   actions:
     - click:
         target:
           image: "button.png"
           strategy:
             ClosestToStrategy:
               x: 500
               y: 300
         description: "Click button closest to coordinates (500, 300)"

**Other Selection Strategies**

- ``SweepStrategy``: Select nth occurrence in reading order (top-to-bottom, left-to-right)
- ``BestConfidenceStrategy``: Select match with highest confidence score (default for images)
- ``TopLeftStrategy``: Select top-left match (default for text)
- ``TopRightStrategy``, ``BottomLeftStrategy``, ``BottomRightStrategy``: Corner-based selection
- ``LargestStrategy``, ``SmallestStrategy``: Select by bounding box area

**Example with SweepStrategy:**

.. code-block:: yaml

   actions:
     - click:
         target:
           text: "Documents"
           strategy:
             SweepStrategy:
               index: 2
         description: "Click the second occurrence of Documents"

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
