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
    DEFAULT_TEMPLATE_THRESHOLD = 0.8

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

    # Clustering thresholds
    SMALL_CLUSTER_SIZE = 6
    MIN_HOMOGRAPHY_POINTS = 4

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