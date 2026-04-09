*********
CV Server
*********

The CV server (``adare-cv-server``) is a standalone process that provides
computer vision capabilities for ADARE experiments. It runs on the **host
machine**, not inside the VM, keeping heavy OpenCV and PaddleOCR
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

Three MCP tools are registered:

- ``find_icon`` -- locate an icon image within a screenshot.
- ``find_text`` -- find a text string within a screenshot.
- ``get_all_text`` -- extract all visible text from a screenshot.


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

Text detection uses PaddleOCR for optical character recognition. The
``OCRProcessor`` (``adare_cv_server.ocr_processing``) runs PaddleOCR in a
thread pool to avoid blocking the async server loop.

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

This design keeps the VM image clean -- no OpenCV, PaddleOCR, or large
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
