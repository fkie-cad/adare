"""Image processing utilities for computer vision tasks."""

import logging
from typing import List, Tuple, Optional
import numpy as np
import cv2

from .constants import CVConstants
from .exceptions import ImageDecodingError, HomographyCalculationError

log = logging.getLogger(__name__)


class ImageDecoder:
    """Handles image decoding operations."""

    @staticmethod
    def decode_images(screenshot_bytes: bytes, icon_bytes: bytes) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        """Decode screenshot and icon from bytes."""
        try:
            screenshot_array = np.frombuffer(screenshot_bytes, np.uint8)
            icon_array = np.frombuffer(icon_bytes, np.uint8)

            screenshot_img = cv2.imdecode(screenshot_array, cv2.IMREAD_COLOR)
            icon_img = cv2.imdecode(icon_array, cv2.IMREAD_COLOR)

            if screenshot_img is None or icon_img is None:
                raise ImageDecodingError("Failed to decode images from bytes")

            log.info(f"CLAUDE: Screenshot size: {screenshot_img.shape[:2]}, Icon size: {icon_img.shape[:2]}")
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


class HomographyCalculator:
    """Handles homography calculations for feature matching."""

    @staticmethod
    def calculate_center_from_homography(
        src_pts: np.ndarray,
        dst_pts: np.ndarray,
        icon_shape: Tuple[int, int],
        ransac_threshold: float = CVConstants.SIFT_RANSAC_THRESHOLD
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

                return center_x, center_y

        except Exception as e:
            raise HomographyCalculationError(f"Homography calculation failed: {e}") from e

    @staticmethod
    def calculate_centroid(points: np.ndarray) -> Tuple[int, int]:
        """Calculate centroid of a set of points."""
        center_x = int(np.mean(points[:, 0]))
        center_y = int(np.mean(points[:, 1]))
        return center_x, center_y