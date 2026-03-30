"""Image processing utilities for computer vision tasks."""

import logging
from datetime import datetime
from typing import List, Tuple, Optional, Dict, Any
import numpy as np
import cv2

from .constants import CVConstants
from .exceptions import ImageDecodingError, HomographyCalculationError

log = logging.getLogger(__name__)


class ImageDecoder:
    """Handles image decoding operations."""

    @staticmethod
    def decode_images(
        screenshot_bytes: bytes, icon_bytes: bytes
    ) -> Tuple[np.ndarray, np.ndarray, Optional[np.ndarray]]:
        """Decode screenshot and icon from bytes.

        Returns:
            (screenshot_img, icon_img, alpha_mask) where alpha_mask is a binary
            mask (uint8, 0/255) if the icon has transparent pixels, None otherwise.
        """
        try:
            screenshot_array = np.frombuffer(screenshot_bytes, np.uint8)
            icon_array = np.frombuffer(icon_bytes, np.uint8)

            screenshot_img = cv2.imdecode(screenshot_array, cv2.IMREAD_COLOR)
            icon_raw = cv2.imdecode(icon_array, cv2.IMREAD_UNCHANGED)

            if screenshot_img is None or icon_raw is None:
                raise ImageDecodingError("Failed to decode images from bytes")

            # Handle alpha channel in icon
            alpha_mask = None
            if len(icon_raw.shape) == 3 and icon_raw.shape[2] == 4:
                alpha_channel = icon_raw[:, :, 3]
                if np.any(alpha_channel < 255):
                    alpha_mask = np.where(alpha_channel > 0, np.uint8(255), np.uint8(0))
                    log.info("CLAUDE: Icon has transparency, created alpha mask")
                icon_img = cv2.cvtColor(icon_raw, cv2.COLOR_BGRA2BGR)
            else:
                icon_img = icon_raw

            log.info(f"CLAUDE: Screenshot size: {screenshot_img.shape[:2]}, Icon size: {icon_img.shape[:2]}")
            return screenshot_img, icon_img, alpha_mask

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

    def __init__(self, locations: List[Tuple[int, int]], similarities: List[float], method: str):
        self.locations = locations
        self.similarities = similarities
        self.method = method
        self.success = len(locations) > 0

    def apply_offset(self, offset_x: int, offset_y: int) -> 'FeatureMatchingResult':
        """Apply coordinate offset to all locations."""
        offset_locations = [(x + offset_x, y + offset_y) for x, y in self.locations]
        return FeatureMatchingResult(offset_locations, self.similarities, self.method)

    def limit_results(self, max_results: int) -> 'FeatureMatchingResult':
        """Limit results to max_results, sorted by similarity."""
        if max_results and self.locations:
            sorted_results = sorted(
                zip(self.locations, self.similarities),
                key=lambda item: item[1],
                reverse=True
            )[:max_results]

            if sorted_results:
                locations, similarities = zip(*sorted_results)
                return FeatureMatchingResult(list(locations), list(similarities), self.method)

        return self


class RegionValidator:
    """Validates feature-based matches by comparing the found region to the template.

    After ORB or SIFT finds a candidate location, crops that region from the
    screenshot and compares against the icon template using normalized cross-correlation
    as a structural similarity proxy. This catches false positives where keypoints
    match scattered features (e.g., wallpaper texture) rather than the actual icon.
    """

    DEFAULT_MIN_SIMILARITY = 0.3
    MIN_REGION_SIZE = 4  # minimum pixels in each dimension for a valid comparison

    @staticmethod
    def validate_match(
        screenshot_img: np.ndarray,
        icon_img: np.ndarray,
        center: Tuple[int, int],
        min_similarity: float = DEFAULT_MIN_SIMILARITY,
        alpha_mask: Optional[np.ndarray] = None
    ) -> Tuple[bool, float]:
        """Verify a feature match by comparing the found region to the template.

        Args:
            screenshot_img: Full screenshot image (BGR)
            icon_img: Icon template image (BGR)
            center: (x, y) center of the candidate match
            min_similarity: Minimum similarity score to accept
            alpha_mask: Optional binary mask for icon transparency

        Returns:
            (is_valid, score) tuple
        """
        icon_h, icon_w = icon_img.shape[:2]
        screenshot_h, screenshot_w = screenshot_img.shape[:2]
        x, y = center

        # Calculate crop region centered on the match
        x1 = max(0, x - icon_w // 2)
        y1 = max(0, y - icon_h // 2)
        x2 = min(screenshot_w, x1 + icon_w)
        y2 = min(screenshot_h, y1 + icon_h)

        region = screenshot_img[y1:y2, x1:x2]

        if region.size == 0:
            log.warning(f"CLAUDE: Region validation - empty region at ({x}, {y})")
            return False, 0.0

        # Check if region is too small for meaningful comparison
        region_h, region_w = region.shape[:2]
        if region_h < RegionValidator.MIN_REGION_SIZE or region_w < RegionValidator.MIN_REGION_SIZE:
            log.warning(f"CLAUDE: Region validation - region too small ({region_w}x{region_h}) at ({x}, {y})")
            return False, 0.0

        # Resize region to match icon dimensions if needed
        if region_h != icon_h or region_w != icon_w:
            region = cv2.resize(region, (icon_w, icon_h), interpolation=cv2.INTER_AREA)

        # Apply alpha mask to zero out transparent pixels if present
        if alpha_mask is not None:
            mask_3c = cv2.merge([alpha_mask, alpha_mask, alpha_mask])
            region = cv2.bitwise_and(region, mask_3c)
            icon_compare = cv2.bitwise_and(icon_img, mask_3c)
        else:
            icon_compare = icon_img

        # Convert to grayscale for comparison
        region_gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
        icon_gray = cv2.cvtColor(icon_compare, cv2.COLOR_BGR2GRAY)

        # Use normalized cross-correlation as structural similarity proxy
        result = cv2.matchTemplate(region_gray, icon_gray, cv2.TM_CCOEFF_NORMED)
        score = float(result[0][0])

        is_valid = score >= min_similarity
        log.info(
            f"CLAUDE: Region validation at ({x}, {y}): score={score:.3f}, "
            f"threshold={min_similarity}, valid={is_valid}"
        )
        return is_valid, score

    @staticmethod
    def filter_matches(
        screenshot_img: np.ndarray,
        icon_img: np.ndarray,
        result: 'FeatureMatchingResult',
        min_similarity: float = DEFAULT_MIN_SIMILARITY,
        alpha_mask: Optional[np.ndarray] = None
    ) -> 'FeatureMatchingResult':
        """Filter a FeatureMatchingResult, keeping only validated matches."""
        valid_locations = []
        valid_similarities = []

        for location, similarity in zip(result.locations, result.similarities):
            is_valid, score = RegionValidator.validate_match(
                screenshot_img, icon_img, location, min_similarity, alpha_mask
            )
            if is_valid:
                valid_locations.append(location)
                valid_similarities.append(similarity)
            else:
                log.warning(
                    f"CLAUDE: Rejecting {result.method} match at {location} - "
                    f"region score {score:.3f} below threshold {min_similarity}"
                )

        return FeatureMatchingResult(valid_locations, valid_similarities, result.method)


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
                            f"CLAUDE: Rejecting match at ({center_x}, {center_y}) - "
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


class IconSearchDebugger:
    """Saves debug output for icon search operations.

    When --debug-output-dir is set, saves annotated screenshots and CSV result
    files for each find_icon call, matching the OCR debug output pattern.
    """

    _debug_output_dir: Optional[Any] = None

    @classmethod
    def set_debug_output_dir(cls, output_dir: Any) -> None:
        """Set directory for saving debug images."""
        cls._debug_output_dir = output_dir

    @classmethod
    def save_search_result(
        cls,
        screenshot_bytes: bytes,
        candidates: List[Dict[str, Any]],
    ) -> None:
        """Save debug output for an icon search.

        Args:
            screenshot_bytes: Raw screenshot bytes for decoding and annotation
            candidates: List of dicts with keys: method, x, y, similarity,
                        region_score (optional float), accepted (bool)
        """
        if not cls._debug_output_dir:
            return

        try:
            timestamp = datetime.now().strftime("%H%M%S_%f")

            # Decode screenshot for annotation
            screenshot_array = np.frombuffer(screenshot_bytes, np.uint8)
            screenshot = cv2.imdecode(screenshot_array, cv2.IMREAD_COLOR)
            if screenshot is None:
                return

            annotated = screenshot.copy()
            for c in candidates:
                x, y = c['x'], c['y']
                color = (0, 255, 0) if c.get('accepted') else (0, 0, 255)
                cv2.circle(annotated, (x, y), 10, color, 2)
                label = f"{c['method']}:{c['similarity']:.2f}"
                cv2.putText(
                    annotated, label, (x + 12, y - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1
                )

            png_path = cls._debug_output_dir / f"find_icon_{timestamp}.png"
            cv2.imwrite(str(png_path), annotated)

            csv_path = cls._debug_output_dir / f"find_icon_{timestamp}.csv"
            with open(csv_path, 'w') as f:
                f.write("method,x,y,similarity,region_score,accepted\n")
                for c in candidates:
                    region_score = c.get('region_score', '')
                    if isinstance(region_score, float):
                        region_score = f"{region_score:.4f}"
                    f.write(
                        f"{c['method']},{c['x']},{c['y']},"
                        f"{c['similarity']:.4f},{region_score},"
                        f"{c.get('accepted', True)}\n"
                    )

            log.info(f"CLAUDE: Saved icon search debug to {png_path.name}")
        except (OSError, cv2.error) as e:
            log.warning(f"CLAUDE: Failed to save icon search debug output: {e}")
