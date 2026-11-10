drag
====

Drag and drop GUI elements from source to destination.

Usage Example
-------------

.. code-block:: yaml

   actions:
     # Drag by coordinates
     - drag:
         src:
           coordinates: [100, 200]
         dst:
           coordinates: [300, 400]
         description: "Drag file to trash"

     # Drag by image
     - drag:
         src:
           image: "file_icon.png"
         dst:
           image: "trash_icon.png"
         description: "Drag file icon to trash"

Parameters
----------

.. list-table::
   :widths: 20 15 65
   :header-rows: 1

   * - Parameter
     - Type
     - Description
   * - ``src``
     - Target
     - Source element to drag from (required)
   * - ``dst``
     - Target
     - Destination to drag to (required)
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

Target Options
--------------

Both ``src`` and ``dst`` support:

- ``image``: Reference image path
- ``text``: Text to find via OCR
- ``coordinates``: [x, y] pixel coordinates

Notes
-----

- Drag operation simulates mouse press, move, and release
- Useful for file operations, UI rearrangement, and drag-drop interfaces

See Also
--------

- :doc:`click` for simple clicks
- :doc:`scroll` for scrolling operations
