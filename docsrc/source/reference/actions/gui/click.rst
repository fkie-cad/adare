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
- ``text``: Text to find with optional ``text_match`` configuration
- ``coordinates``: [x, y] pixel coordinates
- ``strategy``: Selection strategy when multiple matches found (SweepStrategy, BestConfidenceStrategy, etc.)
- ``use_cache``: bool, default ``false`` - reuse the match cached by the immediately
  preceding action (e.g. ``wait_until``) on an identical target (same
  image/text/position/strategy/offset), skipping a fresh screenshot + CV pass. Only
  valid for the single next action after the one that populated the cache. See
  `Reusing a wait_until Match (Performance)`_ below.

Advanced Text Matching
-----------------------

ADARE supports multiple text matching modes to handle OCR inaccuracies and enable flexible pattern matching.

**Substring Matching (Default)**

Simple case-insensitive substring matching. No configuration needed.

.. code-block:: yaml

   actions:
     - click:
         target:
           text: "Documents"
         description: "Click Documents (case-insensitive substring match)"

**Regex Pattern Matching**

Match text using regular expression patterns.

.. code-block:: yaml

   actions:
     - click:
         target:
           text: "File \\d+"
           text_match:
             mode: regex
             flags: [IGNORECASE]
         description: "Click text matching 'File 1', 'File 2', etc."

**Fuzzy Matching - Missing Characters Mode**

Tolerate missing characters that OCR often fails to detect.

**Allow any character to be missing:**

.. code-block:: yaml

   actions:
     - click:
         target:
           text: "More..."
           text_match:
             mode: fuzzy
             allow_missing_chars: true
             max_missing: 3
         description: "Match 'More' even if any characters are missing"

**Allow only specific characters to be missing (recommended):**

.. code-block:: yaml

   actions:
     - click:
         target:
           text: "More..."
           text_match:
             mode: fuzzy
             allow_missing_chars: "."
             max_missing: 3
         description: "Match 'More' when only dots are missing"

**Allow multiple specific characters to be missing:**

.. code-block:: yaml

   actions:
     - click:
         target:
           text: "Price: $19.99"
           text_match:
             mode: fuzzy
             allow_missing_chars: [".", "$", ":"]
             max_missing: 4
         description: "Match even if dots, dollar sign, or colon are missing"

**Fuzzy Matching - Percentage Similarity Mode**

Match text based on similarity threshold (0.0-1.0), useful for OCR character confusion.

.. code-block:: yaml

   actions:
     - click:
         target:
           text: "Settings"
           text_match:
             mode: fuzzy
             min_similarity: 0.85
         description: "Match 'Settinqs' (OCR confused 'g' with 'q')"

**Combined Regex + Fuzzy Matching**

Use regex patterns with fuzzy tolerance for maximum flexibility.

.. code-block:: yaml

   actions:
     - click:
         target:
           text: "Doc.*ents"
           text_match:
             mode: regex_fuzzy
             flags: [IGNORECASE]
             min_similarity: 0.8
         description: "Flexible pattern with error tolerance"

**Case-Sensitive Fuzzy Matching**

Enable case-sensitive comparison for fuzzy matching.

.. code-block:: yaml

   actions:
     - click:
         target:
           text: "LOGIN"
           text_match:
             mode: fuzzy
             min_similarity: 0.9
             case_sensitive: true
         description: "Case-sensitive fuzzy match for 'LOGIN'"

**Text Match Configuration Fields**

.. list-table::
   :widths: 20 15 65
   :header-rows: 1

   * - Field
     - Type
     - Description
   * - ``mode``
     - string
     - Matching mode: ``substring``, ``regex``, ``fuzzy``, ``regex_fuzzy`` (default: ``substring``)
   * - ``flags``
     - list
     - Regex flags: ``IGNORECASE``, ``MULTILINE``, ``DOTALL``, ``VERBOSE``
   * - ``allow_missing_chars``
     - bool/string/list
     - Allowed missing characters (fuzzy mode): ``true`` (any char), ``"."`` (only dots), ``[".", ","]`` (specific chars)
   * - ``max_missing``
     - int
     - Max missing chars allowed (requires ``allow_missing_chars``)
   * - ``min_similarity``
     - float
     - Minimum similarity ratio 0.0-1.0 (fuzzy mode)
   * - ``case_sensitive``
     - bool
     - Enable case-sensitive matching (default: false)

**Use Cases**

- **Missing dots**: OCR often misses periods, ellipses, decimal points
- **Version numbers**: Use regex to match dynamic version strings (e.g., ``v\\d+\\.\\d+``)
- **Character confusion**: OCR may confuse similar characters (O/0, l/1, rn/m)
- **Partial matches**: Fuzzy matching handles truncated or slightly modified text

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

Reusing a wait_until Match (Performance)
-----------------------------------------

CV detection (image/text matching) can take anywhere from ~200ms to over a second per
attempt. If a ``wait_until`` already confirmed a target is on screen, a following
``click`` on the *identical* target can skip re-running detection entirely by setting
``use_cache: true``:

.. code-block:: yaml

   actions:
     - wait_until:
         condition:
           exists:
             image: "save_button.png"
         timeout: 30.0
     - click:
         target:
           image: "save_button.png"
           use_cache: true
         description: "Click Save (reuses the wait_until match, skips re-detection)"

**Caveat:** the cache is only valid for the single action immediately following the one
that populated it (e.g. the ``wait_until`` right before this ``click``) - it is not a
whole-run cache. If any other action runs in between, or the same target pattern
(identical image/text/position/strategy/offset) is reused later in the playbook,
detection reruns from scratch rather than returning a stale match. This is only safe
when nothing on screen moves or changes between the ``wait_until`` success and the
``click``, and it is never used implicitly - you must opt in with ``use_cache: true``
on each target that should reuse it.

Notes
-----

- Image files should be in the experiment directory
- Text matching uses OCR (Tesseract)
- Coordinates are relative to top-left corner
- Use ``wait_until`` before clicking if element may not be immediately visible - see
  `Reusing a wait_until Match (Performance)`_ above to skip the redundant re-detection

See Also
--------

- :doc:`../flow/wait_until` for waiting on elements
- :doc:`keyboard` for keyboard input
- :doc:`drag` for drag-and-drop operations
