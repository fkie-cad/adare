"""Image processing utilities for computer vision tasks."""

import logging
from dataclasses import dataclass
from typing import List, Tuple, Optional
import numpy as np
import cv2

from .constants import CVConstants
from .exceptions import ImageDecodingError, HomographyCalculationError

log = logging.getLogger(__name__)


class ImageDecoder:
    """Handles image decoding operations."""

    @staticmethod
    def preprocess_icon(icon_bytes: bytes) -> bytes:
        """Preprocess icon bytes for detection pipeline.

        Converts SVG icons to PNG with transparent background and trims
        transparent padding. Non-SVG images pass through unchanged.

        This should be called ONCE at pipeline entry to avoid redundant
        conversions across multiple detection stages.

        Args:
            icon_bytes: Raw icon bytes (SVG, PNG, JPG, etc.)

        Returns:
            Preprocessed icon bytes (PNG if SVG, original otherwise)

        Performance:
            - SVG icons: ~20-60ms (conversion + trimming)
            - PNG/JPG icons: <1ms (no-op)
        """
        return ImageDecoder._preprocess_image_bytes(icon_bytes)

    @staticmethod
    def _is_svg(image_bytes: bytes) -> bool:
        """Detect if image bytes represent SVG format.

        Checks for SVG magic bytes: <?xml or <svg
        """
        if not image_bytes or len(image_bytes) < 5:
            return False

        header = image_bytes[:200].decode('utf-8', errors='ignore').strip().lower()
        return header.startswith('<?xml') or header.startswith('<svg')

    @staticmethod
    def _convert_svg_to_png(svg_bytes: bytes) -> bytes:
        """Convert SVG to PNG using CairoSVG with adaptive scaling.

        Small icons (<100px) are upscaled 4x to improve feature detection.
        Uses transparent background to enable automatic padding trimming.

        Returns PNG bytes ready for cv2.imdecode().
        Raises ImageDecodingError if conversion fails.
        """
        try:
            import cairosvg
            import xml.etree.ElementTree as ET

            log.info("Converting SVG to PNG for OpenCV processing")

            # Parse SVG to detect original dimensions
            try:
                root = ET.fromstring(svg_bytes)
                width = root.get('width')
                height = root.get('height')

                # Extract numeric dimensions (handle "48px", "48", etc.)
                if width and height:
                    w = float(''.join(c for c in width if c.isdigit() or c == '.'))
                    h = float(''.join(c for c in height if c.isdigit() or c == '.'))

                    # Upscale small icons for better feature detection
                    if w < CVConstants.SVG_SMALL_ICON_THRESHOLD or h < CVConstants.SVG_SMALL_ICON_THRESHOLD:
                        scale_factor = CVConstants.SVG_UPSCALE_FACTOR
                        output_width = int(w * scale_factor)
                        output_height = int(h * scale_factor)
                        log.info(f"Small icon detected ({w}x{h}), upscaling {scale_factor}x to {output_width}x{output_height}")
                    else:
                        output_width = None
                        output_height = None
                else:
                    output_width = None
                    output_height = None

            except Exception as e:
                log.warning(f"Could not parse SVG dimensions: {e}, using default conversion")
                output_width = None
                output_height = None

            # Convert with transparent background (enables padding trimming)
            png_bytes = cairosvg.svg2png(
                bytestring=svg_bytes,
                output_width=output_width,
                output_height=output_height,
                background_color=CVConstants.SVG_BACKGROUND_COLOR
            )

            log.info(f"SVG conversion successful, PNG size: {len(png_bytes)} bytes")

            # Trim transparent padding if enabled
            if CVConstants.SVG_TRIM_TRANSPARENT_PIXELS:
                png_bytes = ImageDecoder._trim_transparent_pixels(png_bytes)

            return png_bytes

        except ImportError:
            raise ImageDecodingError(
                "CairoSVG library is required for SVG support. "
                "Install with: poetry add cairosvg (or pip install cairosvg). "
                "System dependency: libcairo2 (apt install libcairo2-dev on Ubuntu/Debian)"
            )
        except Exception as e:
            raise ImageDecodingError(f"SVG conversion failed: {e}") from e

    @staticmethod
    def _trim_transparent_pixels(png_bytes: bytes) -> bytes:
        """Trim fully transparent rows/columns from PNG image.

        Removes transparent padding from SVG-converted icons to improve
        feature detection accuracy. Only trims fully transparent rows/columns
        where all pixels have alpha=0.

        Args:
            png_bytes: PNG image bytes (must have alpha channel)

        Returns:
            Trimmed PNG bytes (or original if no alpha channel or fully transparent)

        Performance: ~2-10ms for typical icon sizes

        Note:
            - Preserves at least 1x1 pixel if image is fully transparent
            - No-op for images without alpha channel
            - Very small trimmed images (<10px) keep minimum size
        """
        try:
            # Decode with alpha channel
            img_array = np.frombuffer(png_bytes, np.uint8)
            img = cv2.imdecode(img_array, cv2.IMREAD_UNCHANGED)

            if img is None:
                log.warning("Trimming failed - could not decode PNG")
                return png_bytes

            # Check if image has alpha channel (BGRA = 4 channels)
            if len(img.shape) < 3 or img.shape[2] != 4:
                log.info("No alpha channel detected, skipping trim")
                return png_bytes

            # Extract alpha channel (4th channel)
            alpha = img[:, :, 3]

            # Find rows/columns with any non-transparent pixels (alpha > 0)
            non_transparent_rows = np.any(alpha > 0, axis=1)
            non_transparent_cols = np.any(alpha > 0, axis=0)

            # Check if entire image is transparent
            if not np.any(non_transparent_rows) or not np.any(non_transparent_cols):
                log.warning("Image is fully transparent, preserving 1x1 pixel")
                # Return minimal 1x1 transparent pixel
                minimal_img = np.zeros((1, 1, 4), dtype=np.uint8)
                return cv2.imencode('.png', minimal_img)[1].tobytes()

            # Find bounding box of non-transparent content
            row_indices = np.where(non_transparent_rows)[0]
            col_indices = np.where(non_transparent_cols)[0]

            y_min, y_max = row_indices[0], row_indices[-1] + 1
            x_min, x_max = col_indices[0], col_indices[-1] + 1

            # Calculate trimmed dimensions
            trimmed_height = y_max - y_min
            trimmed_width = x_max - x_min

            original_height, original_width = img.shape[:2]

            # Enforce minimum size (prevent over-trimming tiny icons)
            MIN_ICON_SIZE = 10
            if trimmed_height < MIN_ICON_SIZE or trimmed_width < MIN_ICON_SIZE:
                log.warning(f"Trimmed size ({trimmed_width}x{trimmed_height}) "
                           f"below minimum {MIN_ICON_SIZE}px, keeping original")
                return png_bytes

            # Check if any trimming occurred
            if y_min == 0 and y_max == original_height and x_min == 0 and x_max == original_width:
                log.info("No transparent padding detected, no trimming needed")
                return png_bytes

            # Crop to content bounding box
            trimmed = img[y_min:y_max, x_min:x_max]

            # Composite against background color if configured
            if CVConstants.SVG_COMPOSITE_BACKGROUND:
                try:
                    # Extract BGR and alpha channels
                    bgr = trimmed[:, :, :3]  # First 3 channels (BGR)
                    alpha = trimmed[:, :, 3:4]  # 4th channel (alpha), keep dimensions

                    # Parse background color (hex to BGR)
                    bg_color = ImageDecoder._parse_background_color(
                        CVConstants.SVG_COMPOSITE_BACKGROUND
                    )

                    # Alpha blending: result = foreground * alpha + background * (1 - alpha)
                    alpha_norm = alpha.astype(np.float32) / 255.0  # Normalize to 0.0-1.0

                    # Create background with same shape as BGR
                    background = np.full_like(bgr, bg_color, dtype=np.uint8)

                    # Blend: fg * alpha + bg * (1 - alpha)
                    composited = (
                        bgr.astype(np.float32) * alpha_norm +
                        background.astype(np.float32) * (1 - alpha_norm)
                    ).astype(np.uint8)

                    # Use composited result (no alpha channel)
                    trimmed = composited

                    log.info(f"Composited against background {CVConstants.SVG_COMPOSITE_BACKGROUND}")

                except (ValueError, IndexError) as e:
                    log.warning(f"Background compositing failed: {e}, keeping alpha channel")
                    # Keep original trimmed image with alpha

            log.info(f"Trimmed transparent padding: {original_width}x{original_height} "
                    f"→ {trimmed_width}x{trimmed_height} "
                    f"(removed {original_width - trimmed_width}px horizontal, "
                    f"{original_height - trimmed_height}px vertical)")

            # Encode back to PNG bytes
            success, encoded = cv2.imencode('.png', trimmed)
            if not success:
                log.warning("PNG encoding failed after trimming, returning original")
                return png_bytes

            return encoded.tobytes()

        except Exception as e:
            log.warning(f"Trimming failed: {e}, returning original image")
            return png_bytes

    @staticmethod
    def _parse_background_color(color: str) -> tuple:
        """Parse hex color string to BGR tuple for OpenCV.

        Args:
            color: Hex color string like '#808080' or '#888'

        Returns:
            BGR tuple (B, G, R) for OpenCV

        Raises:
            ValueError: If color format is invalid
        """
        if not color or not isinstance(color, str):
            raise ValueError(f"Invalid color format: {color}")

        if color.startswith('#'):
            color = color[1:]

        # Handle 3-digit hex (#RGB → #RRGGBB)
        if len(color) == 3:
            color = ''.join([c*2 for c in color])

        if len(color) != 6:
            raise ValueError(f"Invalid hex color length: #{color} (expected 6 digits)")

        try:
            # Parse RGB and convert to BGR
            r = int(color[0:2], 16)
            g = int(color[2:4], 16)
            b = int(color[4:6], 16)
            return (b, g, r)  # OpenCV uses BGR order
        except ValueError as e:
            raise ValueError(f"Invalid hex color format: #{color}") from e

    @staticmethod
    def _preprocess_image_bytes(image_bytes: bytes) -> bytes:
        """Preprocess image bytes, converting SVG to PNG if needed.

        DEPRECATED for direct use - prefer calling preprocess_icon() from
        pipeline entry point to avoid redundant conversions.

        Returns processed bytes (PNG if SVG, unchanged otherwise).
        """
        if ImageDecoder._is_svg(image_bytes):
            log.debug("SVG detected, converting to PNG (consider using preprocess_icon() at pipeline entry to avoid redundant conversions)")
            return ImageDecoder._convert_svg_to_png(image_bytes)
        return image_bytes

    @staticmethod
    def decode_images_with_alpha(screenshot_bytes: bytes, icon_bytes: bytes) -> tuple:
        """Decode images, preserving icon alpha channel for masked matching.

        Args:
            screenshot_bytes: Screenshot image bytes
            icon_bytes: Icon image bytes (may have alpha)

        Returns:
            tuple: (screenshot_img, icon_img, icon_mask)
                - screenshot_img: BGR image (3 channels)
                - icon_img: BGR image (3 channels)
                - icon_mask: Single-channel uint8 mask (255=opaque, 0=transparent)
                            or None if icon has no alpha channel
        """
        try:
            # Preprocess: Convert SVG to PNG if needed
            screenshot_bytes = ImageDecoder._preprocess_image_bytes(screenshot_bytes)
            icon_bytes = ImageDecoder._preprocess_image_bytes(icon_bytes)

            screenshot_array = np.frombuffer(screenshot_bytes, np.uint8)
            icon_array = np.frombuffer(icon_bytes, np.uint8)

            # Screenshot: always BGR (no alpha needed)
            screenshot_img = cv2.imdecode(screenshot_array, cv2.IMREAD_COLOR)
            if screenshot_img is None:
                raise ImageDecodingError("Failed to decode screenshot image")

            # Icon: preserve alpha if present
            icon_img = cv2.imdecode(icon_array, cv2.IMREAD_UNCHANGED)
            if icon_img is None:
                raise ImageDecodingError("Failed to decode icon image")

            # Extract alpha channel if present
            icon_mask = None
            if len(icon_img.shape) == 3 and icon_img.shape[2] == 4:
                # BGRA format: split into BGR + alpha
                icon_mask = icon_img[:, :, 3]  # 4th channel = alpha
                icon_img = icon_img[:, :, :3]   # First 3 channels = BGR

                log.info(f"Icon alpha channel extracted as mask "
                        f"({np.sum(icon_mask < 255)} transparent pixels)")
            else:
                # BGR or grayscale: no alpha channel
                log.debug("Icon has no alpha channel, no mask needed")

            log.info(f"Screenshot size: {screenshot_img.shape[:2]}, Icon size: {icon_img.shape[:2]}")
            return screenshot_img, icon_img, icon_mask

        except ImageDecodingError:
            raise
        except Exception as e:
            raise ImageDecodingError(f"Image decoding failed: {e}") from e

    @staticmethod
    def decode_images(screenshot_bytes: bytes, icon_bytes: bytes) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        """Decode screenshot and icon from bytes.

        DEPRECATED: Use decode_images_with_alpha() for mask support.

        Old method that discards alpha channel. Kept for backward compatibility.
        """
        try:
            # Preprocess: Convert SVG to PNG if needed
            screenshot_bytes = ImageDecoder._preprocess_image_bytes(screenshot_bytes)
            icon_bytes = ImageDecoder._preprocess_image_bytes(icon_bytes)

            screenshot_array = np.frombuffer(screenshot_bytes, np.uint8)
            icon_array = np.frombuffer(icon_bytes, np.uint8)

            screenshot_img = cv2.imdecode(screenshot_array, cv2.IMREAD_COLOR)
            icon_img = cv2.imdecode(icon_array, cv2.IMREAD_COLOR)

            if screenshot_img is None or icon_img is None:
                raise ImageDecodingError("Failed to decode images from bytes")

            log.info(f"Screenshot size: {screenshot_img.shape[:2]}, Icon size: {icon_img.shape[:2]}")
            return screenshot_img, icon_img

        except ImageDecodingError:
            raise
        except Exception as e:
            raise ImageDecodingError(f"Image decoding failed: {e}") from e

    @staticmethod
    def convert_to_grayscale(screenshot_img: np.ndarray, icon_img: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Convert images to grayscale."""
        screenshot_gray = cv2.cvtColor(screenshot_img, cv2.COLOR_BGR2GRAY)
        icon_gray = cv2.cvtColor(icon_img, cv2.COLOR_BGR2GRAY)
        return screenshot_gray, icon_gray


class FeatureMatchingResult:
    """Result container for feature matching operations."""

    def __init__(
        self,
        locations: List[Tuple[int, int]],
        similarities: List[float],
        method: str,
        scales: Optional[List[float]] = None,
        sizes: Optional[List[Tuple[int, int]]] = None
    ):
        self.locations = locations
        self.similarities = similarities
        self.method = method
        self.scales = scales if scales is not None else [1.0] * len(locations)
        self.sizes = sizes if sizes is not None else [(0, 0)] * len(locations)
        self.success = len(locations) > 0

    def apply_offset(self, offset_x: int, offset_y: int) -> 'FeatureMatchingResult':
        """Apply coordinate offset to all locations."""
        offset_locations = [(x + offset_x, y + offset_y) for x, y in self.locations]
        return FeatureMatchingResult(
            offset_locations, self.similarities, self.method,
            self.scales, self.sizes
        )

    def limit_results(self, max_results: int) -> 'FeatureMatchingResult':
        """Limit results to max_results, sorted by similarity."""
        if max_results and self.locations:
            sorted_results = sorted(
                zip(self.locations, self.similarities, self.scales, self.sizes),
                key=lambda item: item[1],
                reverse=True
            )[:max_results]

            if sorted_results:
                locations, similarities, scales, sizes = zip(*sorted_results)
                return FeatureMatchingResult(
                    list(locations), list(similarities), self.method,
                    list(scales), list(sizes)
                )

        return self


@dataclass
class DetectionMatch:
    """Single detection match with metadata for aggregation.

    Used in multi-method aggregation pipeline to track matches from
    different detection methods before applying global NMS.
    """
    location: Tuple[int, int]      # Center coordinates (x, y)
    similarity: float              # Raw similarity (0.0-1.0)
    method: str                    # Source method name
    scale: float = 1.0             # Detected scale (1.0 = original size)
    size: Tuple[int, int] = (0, 0) # Bounding box (width, height) at detected scale
    weighted_similarity: float = 0.0  # similarity * method_weight (computed during aggregation)


def non_maximum_suppression(
    locations: List[Tuple[int, int]],
    similarities: List[float],
    sizes: List[Tuple[int, int]],
    overlap_threshold: float = 0.5
) -> Tuple[List[Tuple[int, int]], List[float]]:
    """Apply non-maximum suppression to remove overlapping detections.

    Keeps the match with highest similarity when IoU (Intersection over Union)
    exceeds overlap_threshold. This eliminates duplicate detections of the same
    icon at different scales or sub-pixel offsets.

    Args:
        locations: List of (x, y) center coordinates
        similarities: Corresponding similarity scores (must be same length as locations)
        sizes: Corresponding (width, height) for each detection
        overlap_threshold: IoU threshold for suppression (default: 0.5)
            - 0.5 = suppress if boxes overlap by 50%
            - Higher values = more aggressive suppression

    Returns:
        Tuple of (filtered_locations, filtered_similarities) with overlaps removed

    Algorithm:
        1. Sort matches by similarity (highest first)
        2. For each match, check IoU against all higher-confidence matches
        3. If IoU > threshold with a better match, suppress current match
        4. Return only non-suppressed matches

    Examples:
        >>> locations = [(100, 100), (105, 102), (500, 500)]
        >>> similarities = [0.9, 0.85, 0.8]
        >>> sizes = [(50, 50), (50, 50), (50, 50)]
        >>> filtered = non_maximum_suppression(locations, similarities, sizes)
        # Returns 2 matches: (100, 100) suppresses (105, 102), (500, 500) kept
    """
    if not locations or not similarities or not sizes:
        return [], []

    if len(locations) != len(similarities) or len(locations) != len(sizes):
        log.warning(f"NMS input length mismatch - locations: {len(locations)}, "
                   f"similarities: {len(similarities)}, sizes: {len(sizes)}")
        return locations, similarities

    # Convert to numpy arrays for efficient computation
    locations_arr = np.array(locations)
    similarities_arr = np.array(similarities)
    sizes_arr = np.array(sizes)

    # Sort by similarity (descending order)
    sorted_indices = np.argsort(similarities_arr)[::-1]

    # Track which matches to keep
    keep_mask = np.ones(len(locations), dtype=bool)

    for i, idx in enumerate(sorted_indices):
        if not keep_mask[idx]:
            continue  # Already suppressed

        # Check against all higher-confidence matches (already processed)
        for prev_idx in sorted_indices[:i]:
            if not keep_mask[prev_idx]:
                continue

            # Calculate IoU between idx and prev_idx
            iou = _calculate_iou(
                locations_arr[idx], sizes_arr[idx],
                locations_arr[prev_idx], sizes_arr[prev_idx]
            )

            # Suppress if IoU exceeds threshold
            if iou > overlap_threshold:
                keep_mask[idx] = False
                log.info(f"NMS suppressed match at {locations[idx]} "
                        f"(similarity {similarities[idx]:.3f}) - overlaps with "
                        f"{locations[prev_idx]} (similarity {similarities[prev_idx]:.3f}), IoU: {iou:.3f}")
                break

    # Return only non-suppressed matches
    kept_indices = np.where(keep_mask)[0]
    filtered_locations = [locations[i] for i in kept_indices]
    filtered_similarities = [similarities[i] for i in kept_indices]

    log.info(f"NMS kept {len(filtered_locations)} of {len(locations)} matches "
            f"(overlap_threshold: {overlap_threshold})")

    return filtered_locations, filtered_similarities


def _calculate_iou(
    center1: np.ndarray,
    size1: np.ndarray,
    center2: np.ndarray,
    size2: np.ndarray
) -> float:
    """Calculate Intersection over Union (IoU) for two bounding boxes.

    Args:
        center1: (x, y) center of first box
        size1: (width, height) of first box
        center2: (x, y) center of second box
        size2: (width, height) of second box

    Returns:
        IoU ratio (0.0 to 1.0)
    """
    # Convert centers to top-left coordinates
    x1_tl = center1[0] - size1[0] // 2
    y1_tl = center1[1] - size1[1] // 2
    x1_br = x1_tl + size1[0]
    y1_br = y1_tl + size1[1]

    x2_tl = center2[0] - size2[0] // 2
    y2_tl = center2[1] - size2[1] // 2
    x2_br = x2_tl + size2[0]
    y2_br = y2_tl + size2[1]

    # Calculate intersection
    x_left = max(x1_tl, x2_tl)
    y_top = max(y1_tl, y2_tl)
    x_right = min(x1_br, x2_br)
    y_bottom = min(y1_br, y2_br)

    if x_right < x_left or y_bottom < y_top:
        return 0.0  # No overlap

    intersection_area = (x_right - x_left) * (y_bottom - y_top)

    # Calculate union
    box1_area = size1[0] * size1[1]
    box2_area = size2[0] * size2[1]
    union_area = box1_area + box2_area - intersection_area

    if union_area == 0:
        return 0.0

    return intersection_area / union_area


class HomographyCalculator:
    """Handles homography calculations for feature matching."""

    @staticmethod
    def calculate_center_from_homography(
        src_pts: np.ndarray,
        dst_pts: np.ndarray,
        icon_shape: Tuple[int, int],
        ransac_threshold: float = CVConstants.SIFT_RANSAC_THRESHOLD,
        screenshot_shape: Optional[Tuple[int, int]] = None
    ) -> Optional[Tuple[int, int]]:
        """Calculate icon center using homography transformation."""
        try:
            M, _ = cv2.findHomography(
                src_pts, dst_pts,
                cv2.RANSAC,
                ransac_threshold
            )

            if M is not None:
                h, w = icon_shape
                corners = np.float32([[0,0], [w,0], [w,h], [0,h]]).reshape(-1, 1, 2)
                transformed_corners = cv2.perspectiveTransform(corners, M)

                center_x = int(np.mean(transformed_corners[:, 0, 0]))
                center_y = int(np.mean(transformed_corners[:, 0, 1]))

                # Validate bounds if screenshot_shape provided
                if screenshot_shape is not None:
                    screenshot_h, screenshot_w = screenshot_shape
                    # Check if center is within bounds
                    if not (0 <= center_x < screenshot_w and 0 <= center_y < screenshot_h):
                        log.warning(
                            f"Rejecting match at ({center_x}, {center_y}) - "
                            f"outside screenshot bounds (0-{screenshot_w}, 0-{screenshot_h})"
                        )
                        return None

                return center_x, center_y

        except Exception as e:
            raise HomographyCalculationError(f"Homography calculation failed: {e}") from e

    @staticmethod
    def calculate_centroid(points: np.ndarray) -> Tuple[int, int]:
        """Calculate centroid of a set of points."""
        center_x = int(np.mean(points[:, 0]))
        center_y = int(np.mean(points[:, 1]))
        return center_x, center_y


class IconComplexityAnalyzer:
    """Analyze icon texture complexity for ORB suitability.

    Used in Stage 2 of the staged detection pipeline to prevent ORB from
    matching flat icons against text edges on cluttered screens (false positives).
    """

    @staticmethod
    def calculate_laplacian_variance(icon_gray: np.ndarray) -> float:
        """Calculate size-normalized Laplacian variance.

        Args:
            icon_gray: Grayscale icon image

        Returns:
            Variance per pixel (size-normalized)

        Examples:
            - Solid flat icon: ~0.2-0.4
            - Gradient icon: ~0.4-0.6
            - Complex textured icon: ~0.8-2.0+
        """
        laplacian = cv2.Laplacian(icon_gray, cv2.CV_64F)
        variance = np.var(laplacian)

        # Normalize by icon size to make threshold size-invariant
        h, w = icon_gray.shape
        variance_per_pixel = variance / (w * h)

        return variance_per_pixel

    @staticmethod
    def should_use_orb(
        icon_gray: np.ndarray,
        threshold: float = CVConstants.LAPLACIAN_VARIANCE_THRESHOLD
    ) -> bool:
        """Determine if icon is complex enough for ORB.

        Args:
            icon_gray: Grayscale icon image
            threshold: Minimum variance threshold (default: 0.5)

        Returns:
            True if icon has enough texture for ORB, False for flat icons

        Note:
            Threshold may require empirical calibration on representative icon set.
            Start with 0.5 and adjust based on false positive/negative rates.
        """
        variance = IconComplexityAnalyzer.calculate_laplacian_variance(icon_gray)
        use_orb = variance > threshold

        log.info(f"Laplacian variance (per pixel): {variance:.3f}, "
                f"threshold: {threshold}, use_orb: {use_orb}")

        return use_orb