"""Constants for the Adare MCP Server."""

import os

# Default server configuration
DEFAULT_PORT = 13109
DEFAULT_HOST = "localhost"
MCP_PATH = "/mcp"


# Computer Vision Parameters
class CVConstants:
    """Computer Vision algorithm constants."""

    # Template Matching
    DEFAULT_TEMPLATE_THRESHOLD = 0.75

    # SIFT Parameters
    SIFT_MIN_MATCHES = 4
    SIFT_RATIO_THRESHOLD = 0.8
    SIFT_RANSAC_THRESHOLD = 5.0

    # ORB Parameters
    ORB_MIN_MATCHES = 2
    ORB_MAX_MATCHES = 10
    ORB_DISTANCE_THRESHOLD = 80.0
    ORB_FEATURES = 2000
    ORB_SCALE_FACTOR = 1.1
    ORB_LEVELS = 12
    ORB_EDGE_THRESHOLD = 15
    ORB_PATCH_SIZE = 15
    ORB_CLUSTERING_EPS = 30
    ORB_HOMOGRAPHY_THRESHOLD = 3.0
    ORB_MAX_DISTANCE_NORMALIZE = 100.0

    # ORB Adaptive Parameters for Small Icons
    ORB_SMALL_ICON_NLEVELS = 6  # Pyramid levels for small icons
    ORB_SMALL_ICON_EDGE_THRESHOLD = 5  # Edge threshold for small icons

    # SVG Conversion Parameters
    SVG_SMALL_ICON_THRESHOLD = 100  # Icons smaller than this are upscaled
    SVG_UPSCALE_FACTOR = 4  # Upscale small icons by this factor
    SVG_BACKGROUND_COLOR = None  # Transparent background (enables trimming)
    SVG_COMPOSITE_BACKGROUND = None  # Preserve alpha for masked matching (disabled compositing)
    SVG_TRIM_TRANSPARENT_PIXELS = True  # Trim transparent padding from SVG icons

    # Clustering thresholds
    SMALL_CLUSTER_SIZE = 6
    MIN_HOMOGRAPHY_POINTS = 4

    # Multi-Scale Template Matching (Stage 1: Precision Gate)
    MULTISCALE_TEMPLATE_THRESHOLD = 0.9  # High precision threshold for exact matches
    MULTISCALE_TEMPLATE_FALLBACK_THRESHOLD = 0.8  # Skip ORB/SIFT if match >= 0.8
    MULTISCALE_TEMPLATE_SCALE_RANGE = (0.1, 10.0)  # 10% to 1000% (extreme scale range)
    MULTISCALE_TEMPLATE_SCALE_STEP_FINE = 0.05  # Steps below 1.0x: 0.1, 0.2, ..., 0.9
    MULTISCALE_TEMPLATE_SCALE_STEP_COARSE = 0.5  # Steps above 1.0x: 1.5, 2.0, ..., 10.0
    MULTISCALE_TEMPLATE_MIN_ICON_SIZE = 10  # Minimum 10x10 pixels (prevents misdetections)

    # Mask Validation (prevents inf/nan from small/uniform masked regions)
    MULTISCALE_TEMPLATE_MIN_MASK_OPAQUE_PIXELS_ABSOLUTE = 25  # Hard minimum (relaxed from 50)
    MULTISCALE_TEMPLATE_MIN_MASK_OPAQUE_RATIO = 0.10  # 10% of total pixels must be opaque (adaptive)
    MULTISCALE_TEMPLATE_MIN_STD_DEV = 10.0  # Minimum standard deviation for texture detection (replaces variance check)
    MULTISCALE_TEMPLATE_MIN_MASK_OPAQUE_RATIO_DEGENERATE = 0.05  # Reject masks <5% opaque (safety net)
    MULTISCALE_TEMPLATE_ALLOW_PARTIAL_INF_NAN = True  # Use np.isfinite to handle partial inf/nan in result matrix
    # MULTISCALE_TEMPLATE_MIN_MASK_VARIANCE = 0.5  # DEPRECATED: Use MIN_STD_DEV instead (mathematically incorrect normalization)

    # Laplacian Variance Gatekeeper (Stage 2: ORB Suitability)
    LAPLACIAN_VARIANCE_THRESHOLD = 0.5  # Normalized per-pixel variance
    # Note: Requires empirical tuning on representative icon set

    # Canny Edge-Based Multi-Scale Matching (Stage 0: Edge-First Detection)
    CANNY_EDGE_THRESHOLD = 0.80  # High confidence for edge-based matches
    CANNY_EDGE_FALLBACK_THRESHOLD = 0.75  # Skip to Stage 2+ if match >= 0.75
    CANNY_EDGE_BLUR_KERNEL = (3, 3)  # Gaussian blur before edge detection
    CANNY_EDGE_AUTO_THRESHOLD_LOWER = 0.66  # Multiplier for lower threshold (median * 0.66)
    CANNY_EDGE_AUTO_THRESHOLD_UPPER = 1.33  # Multiplier for upper threshold (median * 1.33)
    CANNY_EDGE_DILATE_ITERATIONS = 1  # Dilate edges by 1 iteration (3x3 kernel)
    CANNY_EDGE_SCALE_RANGE = (0.1, 10.0)  # Scale range for edge-based matching (same as Stage 1)
    CANNY_EDGE_SCALE_STEP_FINE = 0.1  # Steps below 1.0x: 0.1, 0.2, ..., 0.9
    CANNY_EDGE_SCALE_STEP_COARSE = 0.5  # Steps above 1.0x: 1.5, 2.0, ..., 10.0
    CANNY_EDGE_MIN_ICON_SIZE = 14  # Minimum 15x15 pixels (edges need more pixels than intensity matching)

    # Non-Maximum Suppression (NMS) for Multi-Match Detection
    NMS_OVERLAP_THRESHOLD = 0.5  # IoU threshold for considering matches as duplicates

    # Method Weighting for Aggregation (priority-based confidence)
    METHOD_WEIGHTS = {
        'canny_edge': 1.0,  # Highest - theme invariant, best for UI
        'multiscale_template': 0.95,  # High - pixel exact matching
        'sift': 0.90,  # Robust - gradient/complex icons
        'orb': 0.85,  # Good - but prone to text false positives
        'template': 0.80,  # Catch-all - relaxed threshold
    }
    SIFT_NORMALIZATION_THRESHOLD = 20.0  # 20+ matches = 1.0 confidence
    ENABLE_AGGREGATION = True  # Feature toggle for multi-method aggregation


# Debug Visualization
class DebugConstants:
    """Debug visualization constants."""

    # Match box annotation
    MATCH_BOX_COLOR = (0, 255, 0)  # Green in BGR
    MATCH_BOX_THICKNESS = 2

    # Text annotation
    TEXT_COLOR = (255, 255, 255)  # White in BGR
    TEXT_SCALE = 0.6
    TEXT_THICKNESS = 1
    TEXT_FONT = 0  # cv2.FONT_HERSHEY_SIMPLEX

    # Early termination indicator
    EARLY_TERM_COLOR = (0, 0, 255)  # Red in BGR

    # Summary text
    SUMMARY_COLOR = (255, 255, 255)  # White in BGR


# OCR Parameters
class OCRConstants:
    """OCR processing constants."""

    MAX_WORKERS = 1
    CSV_HEADER = "text,x,y,confidence"
    DEBUG_CSV_HEADER = "operation,timestamp,screenshot_file,text,confidence,center_x,center_y,box_x1,box_y1,box_x2,box_y2,box_x3,box_y3,box_x4,box_y4"

    # PaddleOCR detection parameters
    # unclip_ratio: Controls how much the detection box is expanded.
    # Smaller value (e.g. 1.2) helps separate close text instances.
    # Default is usually around 1.5.
    OCR_DET_UNCLIP_RATIO = 1.8
    OCR_DET_DB_THRESH = 0.3
    OCR_DET_BOX_THRESH = 0.6

    # Pre-OCR upscaling. PaddleOCR downscales internally for detection and
    # recognizes tiny crops (e.g. a wrapped "4.17.0" desktop-icon label) poorly.
    # Upscaling the screenshot before predict() recovers small text; detection
    # boxes are rescaled back to original screenshot-pixel space so all
    # downstream coordinates stay unchanged.
    #
    # The upscale factor is chosen ADAPTIVELY per image: scale up only enough to
    # reach OCR_TARGET_SIDE (the resolution PaddleOCR's detector performs best
    # at), never beyond OCR_UPSCALE (the cap), and never at all if the image is
    # already >= the target. A flat, unconditional upscale factor is unsafe: on
    # a 1920x1080+ screenshot a flat 2x sends the image (already well above the
    # detector's sweet spot) past the detection-side-length limit, which forces
    # PaddleOCR to silently downscale it back down for detection - destroying
    # recall on ordinary desktop UI text. Scaling only what actually needs it
    # keeps small crops/labels (the original motivating case) fixed without
    # regressing normal-sized screenshots.
    OCR_UPSCALE = float(os.environ.get("ADARE_OCR_UPSCALE", "2.0"))
    OCR_TARGET_SIDE = int(os.environ.get("ADARE_OCR_TARGET_SIDE", "2048"))

    # Floor for the detection-side length passed to PaddleOCR. The effective
    # value used at call time is max(this floor, the actual processed image's
    # longest side) so the image we hand PaddleOCR is NEVER downscaled away for
    # detection (which would silently defeat any upscaling above), regardless of
    # source resolution. With limit_type "max" this is the longest allowed side.
    OCR_DET_LIMIT_SIDE_LEN = int(os.environ.get("ADARE_OCR_DET_LIMIT_SIDE_LEN", "2880"))
    OCR_DET_LIMIT_TYPE = os.environ.get("ADARE_OCR_DET_LIMIT_TYPE", "max")

    # The rapidocr profile only upscales when the adaptive factor above is at
    # least this large. 1080p frames (factor 2048/1920 = 1.07) are therefore
    # never resampled; small crops and sub-HD frames still are.
    OCR_MIN_UPSCALE = 1.5

    # Per-frame OCR result cache (LRU entries). Keyed by sha256(screenshot bytes)
    # + the engine fingerprint, so a hit returns exactly what a fresh run would.
    OCR_CACHE_SIZE = 64


class OCRProfiles:
    """Pinned OCR profiles: engine, model files (sha256) and parameters.

    OCR decides where the client clicks, so any change here changes experiment
    results. Changing a value means a new profile name, a regenerated golden test
    (``tests/test_ocr_engines.py``) and an A/B over real experiments.
    """

    ENGINE_RAPIDOCR = "rapidocr"
    ENGINE_PADDLE = "paddle"
    ENGINES = (ENGINE_RAPIDOCR, ENGINE_PADDLE)
    LANGS = ("latin", "en")

    DEFAULT_ENGINE = ENGINE_RAPIDOCR
    DEFAULT_LANG = "latin"
    DEFAULT_THREADS = 4

    # Profile names recorded in run provenance (ocr*.yml).
    RAPIDOCR_PROFILE = {"latin": "rapidocr-v5m-latin", "en": "rapidocr-v5m-en"}
    PADDLE_PROFILE = "paddle-legacy"

    # RapidOCR model files, pinned by sha256. Same files and hashes as rapidocr
    # 3.10.0's default_models.yaml; the URL is versioned, so it never moves.
    # The PP-OCRv5 rec ONNX models carry their character dictionary in the model
    # metadata, so there is no separate dictionary file to pin.
    RAPIDOCR_MODEL_BASE_URL = "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.10.0/onnx/PP-OCRv5"
    RAPIDOCR_DET_MODEL = (
        "det/ch_PP-OCRv5_det_mobile.onnx",
        "4d97c44a20d30a81aad087d6a396b08f786c4635742afc391f6621f5c6ae78ae",
    )
    RAPIDOCR_REC_MODELS = {
        "latin": (
            "rec/latin_PP-OCRv5_rec_mobile.onnx",
            "b20bd37c168a570f583afbc8cd7925603890efbcdc000a59e22c269d160b5f5a",
        ),
        "en": (
            "rec/en_PP-OCRv5_rec_mobile.onnx",
            "c3461add59bb4323ecba96a492ab75e06dda42467c9e3d0c18db5d1d21924be8",
        ),
    }

    # RapidOCR parameters (benchmarked 2026-11-01 on 60 T2F screenshots).
    # Detection never downscales: limit_type "max" with a side limit far above any
    # screen equals the planned max(1920, image side) for every frame up to 8192 px.
    RAPIDOCR_PARAMS = {
        "Global.use_cls": False,
        "Global.max_side_len": 8192,
        "Global.text_score": 0.5,
        "Det.limit_type": "max",
        "Det.limit_side_len": 8192,
        "Det.thresh": 0.3,
        "Det.box_thresh": 0.6,
        "Det.unclip_ratio": 1.8,
        "Det.use_dilation": False,
    }

    # PaddleOCR (legacy) picks these models for lang='en' with default settings.
    PADDLE_DET_MODEL = "PP-OCRv5_server_det"
    PADDLE_REC_MODEL = "en_PP-OCRv5_mobile_rec"

    # Leading-glyph tolerance (rapidocr profiles only): a line also matches with
    # one leading run of 1-2 non-word glyphs stripped (">Bookmarks Menu",
    # "• Other", "★All"). The Latin model reads tree arrows as ">".
    LEADING_GLYPH_PATTERN = r"^\s*[^\w\s]{1,2}\s*"


# Result limits
DEFAULT_MAX_RESULTS = 50
