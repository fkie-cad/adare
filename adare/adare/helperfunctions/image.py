"""
Image Processing Helper Functions.
"""

import base64
import logging

try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None
    np = None

log = logging.getLogger(__name__)

#: Per-pixel grey-level difference below which a pixel counts as unchanged (compression noise)
PIXEL_NOISE_THRESHOLD = 25


def decode_base64_image(image_base64: str):
    """Decode a base64 PNG/JPEG/WebP screenshot into a BGR numpy array.

    Raises:
        ImportError: If opencv-python or numpy are not installed
        ValueError: If the data is not a decodable image
    """
    if cv2 is None or np is None:
        raise ImportError("opencv-python and numpy are required for image comparison")
    try:
        raw = base64.b64decode(image_base64)
    except (ValueError, TypeError) as e:
        raise ValueError(f"Invalid base64 image data: {e}") from e
    image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Failed to decode image data")
    return image


def count_changed_pixels(before, after, region: tuple[int, int, int, int] | None = None) -> int:
    """Number of pixels inside ``region`` (x, y, w, h) that differ between two decoded images.

    Only the region is compared, so change elsewhere (a taskbar clock, an animation) does
    not count. Differently sized frames (resolution change) count as fully changed.
    """
    if before.shape != after.shape:
        h, w = before.shape[:2]
        return (region[2] * region[3]) if region else w * h
    if region is not None:
        x, y, w, h = region
        before = before[y : y + h, x : x + w]
        after = after[y : y + h, x : x + w]
    gray = cv2.cvtColor(cv2.absdiff(before, after), cv2.COLOR_BGR2GRAY)
    return int(np.count_nonzero(gray > PIXEL_NOISE_THRESHOLD))


def encode_webp(image, quality: int = 80) -> bytes:
    """Encode a decoded image as WebP (evidence screenshots)."""
    ok, buffer = cv2.imencode('.webp', image, [cv2.IMWRITE_WEBP_QUALITY, quality])
    if not ok:
        raise ValueError("WebP encoding failed")
    return buffer.tobytes()


def calculate_pixel_change(img1_base64: str, img2_base64: str) -> float:
    """
    Calculate the percentage of pixels that changed between two base64 encoded images.

    Args:
        img1_base64: First image as base64 string
        img2_base64: Second image as base64 string

    Returns:
        float: Percentage of changed pixels (0.0 to 100.0)

    Raises:
        ImportError: If opencv-python or numpy are not installed
        ValueError: If images cannot be decoded or have different dimensions
    """
    if cv2 is None or np is None:
        raise ImportError("opencv-python and numpy are required for pixel change calculation")

    try:
        # Decode first image
        img1_bytes = base64.b64decode(img1_base64)
        img1_np = np.frombuffer(img1_bytes, dtype=np.uint8)
        img1 = cv2.imdecode(img1_np, cv2.IMREAD_COLOR)

        # Decode second image
        img2_bytes = base64.b64decode(img2_base64)
        img2_np = np.frombuffer(img2_bytes, dtype=np.uint8)
        img2 = cv2.imdecode(img2_np, cv2.IMREAD_COLOR)

        if img1 is None or img2 is None:
            raise ValueError("Failed to decode image data")

        if img1.shape != img2.shape:
            # If dimensions differ, try to resize img2 to match img1
            # This can happen if screen resolution changed, but for pixel diff we need same size
            log.warning(f"Image dimensions differ: {img1.shape} vs {img2.shape}. Resizing second image.")
            img2 = cv2.resize(img2, (img1.shape[1], img1.shape[0]))

        # Calculate absolute difference
        diff = cv2.absdiff(img1, img2)

        # Convert to grayscale
        gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)

        # Threshold to get binary "change" map (ignore minor noise < 25)
        _, thresh = cv2.threshold(gray, 25, 255, cv2.THRESH_BINARY)

        # Calculate percentage of non-zero (changed) pixels
        total_pixels = thresh.size
        changed_pixels = np.count_nonzero(thresh)

        return (changed_pixels / total_pixels) * 100

    except Exception as e:
        log.error(f"Error calculating pixel change: {e}")
        # Return 100% change on error to be safe (fail open)/fail safe depending on usage
        # But raising exception allows caller to handle it
        raise
