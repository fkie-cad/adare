*********
CV Server
*********

The CV server (``adare-cv-server``) is a standalone process that provides
computer vision capabilities for ADARE experiments. It runs on the **host
machine**, not inside the VM, keeping heavy OpenCV and OCR
dependencies out of the guest.

.. contents:: On this page
   :local:
   :depth: 2


Architecture
============

The server is built on `FastMCP <https://github.com/jlowin/fastmcp>`_ and
exposes its tools via the Model Context Protocol (MCP) over a streamable
HTTP transport. By default it listens on ``localhost:13109/mcp``.

The host-side ``MCPServerManager``
(``adare.backend.experiment.mcp_server_manager``) starts the CV server as a
subprocess before experiment execution. If a server is already running on
the configured port, the manager attaches to it rather than starting a
duplicate.

Four MCP tools are registered:

- ``find_icon`` -- locate an icon image within a screenshot.
- ``find_text`` -- find a text string within a screenshot.
- ``get_all_text`` -- extract all visible text from a screenshot.
- ``get_engine_info`` -- describe the OCR profile (engine, models + sha256,
  parameters); recorded per run as ``ocr.yml``.


Detection Methods
=================

Icon detection (``find_icon``) uses a three-stage cascade. Each stage is
tried in order; as soon as one succeeds, the result is returned.

Template Matching (primary)
---------------------------

The fastest and most reliable method for GUI icons. Uses OpenCV
``matchTemplate`` with normalised cross-correlation (``TM_CCOEFF_NORMED``).
A threshold (default 0.8) controls the minimum match quality. Template
matching works well when the icon appears at the same scale and orientation
as the reference image.

Implemented in ``TemplateMatcher`` (``adare_cv_server.feature_matching``).

SIFT Feature Matching (second)
------------------------------

Scale-Invariant Feature Transform. Detects keypoints and computes
descriptors in both the icon and the screenshot, then matches them using a
brute-force matcher with Lowe's ratio test (default ratio 0.8). Matched
keypoints are clustered (DBSCAN) and a homography is computed to determine
the icon's position.

SIFT handles scale changes and minor rotations, making it useful when the
icon may appear at a different size than the reference. Candidates are
validated by ``RegionValidator``, which crops the matched region and
compares it to the template via normalised cross-correlation to reject
false positives from scattered keypoint matches.

Implemented in ``SIFTMatcher`` (``adare_cv_server.feature_matching``).

ORB Feature Matching (third)
-----------------------------

Oriented FAST and Rotated BRIEF. Faster than SIFT but more prone to false
positives. Uses a brute-force matcher with Hamming distance and the same
DBSCAN clustering and homography pipeline. Candidates are also validated by
``RegionValidator``.

ORB is the final feature-based fallback before returning no matches.

Implemented in ``ORBMatcher`` (``adare_cv_server.feature_matching``).

Region Validation
-----------------

After SIFT or ORB proposes a candidate location, ``RegionValidator``
(``adare_cv_server.image_processing``) crops that region from the
screenshot, resizes it to match the icon dimensions, and computes a
normalised cross-correlation score. Candidates below the minimum similarity
threshold (default 0.3) are rejected. This step catches false positives
where keypoints match background texture rather than the actual icon.

Icons with transparency are handled by applying an alpha mask that zeros
out transparent pixels before comparison.


Text Detection
==============

OCR decides where ADARE clicks, so the OCR engine is part of an experiment's
reproducibility: engine, model files and parameters form a pinned **profile**,
and every run records the profile that served it.

.. list-table:: OCR profiles
   :header-rows: 1
   :widths: 22 78

   * - Profile
     - Engine
   * - ``rapidocr-v5m-latin`` (default)
     - RapidOCR on onnxruntime (CPU on Linux, Windows and macOS): PP-OCRv5
       mobile detection + mobile *Latin* recognition (umlauts and accents),
       with leading-glyph tolerance. ``rapidocr-v5m-en`` uses the English
       recognizer instead (``--ocr-lang en``).
   * - ``paddle-legacy``
     - The previous PaddleOCR path (PP-OCRv5 server detection + English mobile
       recognition), byte-for-byte unchanged. Needs the ``paddle`` extra of
       ``adare-cv-server``; kept until existing experiments are A/B-validated.

Measured on 60 real 1080p screenshots (M4 Max, CPU): RapidOCR takes
0.2-0.3 s per frame with ~1 GB peak memory, PaddleOCR 11.3 s and 6-21 GB;
word recall 97.4% vs 95.1%; exact lines on rendered German UI text 92% vs 76%.

**Selection.** The engine is chosen once per server process:
``adare-cv-server --ocr-engine {rapidocr,paddle} --ocr-lang {latin,en}``
(environment fallbacks ``ADARE_OCR_ENGINE`` / ``ADARE_OCR_LANG``). The client
always passes both explicitly: the global default comes from
``ADARE_OCR_ENGINE`` / ``ADARE_OCR_LANG`` (or ``~/.adare/config.json``), and an
experiment can pin its own in ``metadata.yml``:

.. code-block:: yaml

   environments: [ubuntu2404]
   ocr:
     engine: paddle   # keep this experiment on the legacy profile
     # lang: latin    # rapidocr only: latin (default) or en

``ADARE_OCR_THREADS`` sets the onnxruntime threads per server (default 4); it
changes speed only, not results.

**Model pinning.** RapidOCR model files are pinned by sha256
(``OCRProfiles`` in ``adare_cv_server.constants``). On first use they are
downloaded to RapidOCR's model directory (or ``ADARE_OCR_MODEL_DIR``) and
verified; an existing file with another hash is a hard error, never silently
re-downloaded. OpenCV is pinned too (workspace ``constraint-dependencies``):
the ``cv2`` version alone changed RapidOCR output on 10 of 60 benchmark frames.

**Provenance.** After the server starts, the client calls the
``get_engine_info`` tool and writes ``<run>/ocr.yml`` (``ocr-<machine>.yml``
per machine of a multi-machine run): profile, engine and package versions,
model names + sha256, parameters, language, glyph tolerance and the
cv-server version. It also loads the models, so a model problem surfaces at
run start rather than at the first click.

**Per-frame cache.** ``OCRProcessor`` (``adare_cv_server.ocr_processing``)
keeps an LRU of 64 results keyed by sha256 of the screenshot bytes plus the
profile fingerprint, and identical concurrent requests share one computation.
The client OCRs the same frame repeatedly (multi-leaf ``wait_until``,
``when`` conditions, ``ClosestTo`` reference + target, failure evidence,
polling an unchanged screen); a hit returns exactly what a fresh run would.
OCR itself runs on a single-worker thread pool, off the async server loop.

**Leading-glyph tolerance** (rapidocr profiles only). A line also matches
when one leading run of one or two non-word glyphs is stripped
(``>Bookmarks Menu``, ``• Other``, ``★All``): the Latin model reads tree
arrows as ``>``. The reported text stays the line as read. It is off for
``paddle-legacy``.

**Known differences** between the profiles: about one in six anchored-line
queries can resolve differently; RapidOCR's mobile detector merges two words
up to ~30 px apart into one line (PaddleOCR splits from 30 px), which moves
the click centre of a substring query to the middle of the merged line.

The ``find_text`` tool supports four matching modes:

- **substring** (default) -- case-insensitive substring search.
- **regex** -- regular expression matching with configurable flags
  (``IGNORECASE``, ``MULTILINE``, ``DOTALL``, ``VERBOSE``).
- **fuzzy** -- tolerates OCR inaccuracies via Levenshtein distance.
  Supports ``allow_missing_chars`` (allow specific characters to be absent,
  useful for punctuation that OCR often drops), ``max_missing`` (maximum
  number of missing characters), and ``min_similarity`` (ratio threshold).
- **regex_fuzzy** -- regex match first, then fuzzy similarity check on the
  matched text.

The ``get_all_text`` tool returns every text detection with its bounding box
centre coordinates and confidence score. Output can be JSON or CSV.


Host-Side Operation
===================

All CV processing happens on the host. The workflow is:

1. The host requests a screenshot from the guest agent via the
   ``screenshot`` WebSocket tool call.
2. The guest agent captures the screen (PyAutoGUI) and returns the image
   as base64-encoded PNG.
3. The host forwards the screenshot (still base64-encoded) to the CV
   server via an MCP tool call (``find_icon``, ``find_text``, or
   ``get_all_text``).
4. The CV server decodes the image, runs the detection algorithm, and
   returns coordinates and confidence scores.
5. The host uses the coordinates for subsequent GUI actions (clicking a
   found icon or text element).

This design keeps the VM image clean -- no OpenCV, OCR engine, or large
model files are needed inside the guest, preserving forensic integrity.


Integration with Playbooks
===========================

Playbook actions reference visual targets by type:

- **Image targets** -- a PNG icon file. The host reads the file, base64
  encodes it, and sends it alongside the screenshot to ``find_icon``.
- **Text targets** -- a string or regex pattern. Sent to ``find_text``
  with the matching mode and parameters specified in the playbook YAML.

The ``CVService`` (``adare.backend.experiment.host_services.cv_service``)
provides a clean abstraction over the MCP client, used by host-side test
executors and the target resolver (``target_resolver.py``) to convert
playbook targets into screen coordinates.

Debug output can be enabled with the ``--debug-output-dir`` flag when
starting the CV server. This saves annotated screenshots (with bounding
boxes drawn on detected regions) and CSV files with all detection
results, useful for diagnosing false positives or missed detections.

Experiment and diff runs start the server with ``--exit-with-parent``: it
watches the ``adare`` process that started it and exits once that process is
gone, so a crashed or killed run does not leave a server holding its port and
its OCR models in memory. Dev sessions start it without the flag, because their
server deliberately outlives the ``adare dev`` command that started it; it is
stopped by ``adare dev stop``/``remove``.
