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
        'canny_edge': 1.0,           # Highest - theme invariant, best for UI
        'multiscale_template': 0.95,  # High - pixel exact matching
        'sift': 0.90,                # Robust - gradient/complex icons
        'orb': 0.85,                 # Good - but prone to text false positives
        'template': 0.80             # Catch-all - relaxed threshold
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
    # downstream coordinates stay unchanged. 1.0 disables it.
    OCR_UPSCALE = float(os.environ.get("ADARE_OCR_UPSCALE", "2.0"))

    # Detection-side length limit passed to PaddleOCR. Must be large enough that
    # the upscaled image is NOT downscaled away for detection (which would defeat
    # the upscale). With limit_type "max" this is the longest allowed side.
    OCR_DET_LIMIT_SIDE_LEN = int(os.environ.get("ADARE_OCR_DET_LIMIT_SIDE_LEN", "2880"))
    OCR_DET_LIMIT_TYPE = os.environ.get("ADARE_OCR_DET_LIMIT_TYPE", "max")

# Result limits
DEFAULT_MAX_RESULTS = 50