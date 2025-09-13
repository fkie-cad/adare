"""Constants for the Adare MCP Server."""

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

# Result limits
DEFAULT_MAX_RESULTS = 50