"""Feature matching algorithms for icon detection."""

import logging
from typing import List, Tuple, Optional
import numpy as np
import cv2
from sklearn.cluster import DBSCAN

from .constants import CVConstants
from .image_processing import ImageDecoder, FeatureMatchingResult, HomographyCalculator
from .exceptions import FeatureMatchingError, ImageDecodingError, HomographyCalculationError

log = logging.getLogger(__name__)


class SIFTMatcher:
    """SIFT-based feature matching for icon detection."""

    @staticmethod
    def find_icon_locations(
        screenshot_bytes: bytes,
        icon_bytes: bytes,
        min_matches: int = CVConstants.SIFT_MIN_MATCHES,
        ratio_threshold: float = CVConstants.SIFT_RATIO_THRESHOLD
    ) -> FeatureMatchingResult:
        """Find icon locations using SIFT feature matching - scale invariant."""
        log.info(f"CLAUDE: SIFT detection starting with min_matches={min_matches}, ratio_threshold={ratio_threshold}")

        try:
            # Decode images
            decoded = ImageDecoder.decode_images(screenshot_bytes, icon_bytes)
        except ImageDecodingError as e:
            log.error(f"SIFT: {e}")
            return FeatureMatchingResult([], [], "sift")

        screenshot_img, icon_img = decoded
        screenshot_gray, icon_gray = ImageDecoder.convert_to_grayscale(screenshot_img, icon_img)

        # Initialize SIFT detector
        sift = cv2.SIFT_create()

        # Find keypoints and descriptors
        kp1, des1 = sift.detectAndCompute(icon_gray, None)
        kp2, des2 = sift.detectAndCompute(screenshot_gray, None)

        log.info(f"CLAUDE: Icon keypoints: {len(kp1) if kp1 else 0}, Screenshot keypoints: {len(kp2) if kp2 else 0}")

        if des1 is None or des2 is None:
            log.warning("CLAUDE: No descriptors found - images may be too simple or uniform")
            return FeatureMatchingResult([], [], "sift")

        # Match features
        matcher = cv2.BFMatcher()
        matches = matcher.knnMatch(des1, des2, k=2)

        log.info(f"CLAUDE: Initial matches found: {len(matches)}")

        # Apply Lowe's ratio test
        good_matches = SIFTMatcher._apply_ratio_test(matches, ratio_threshold)

        log.info(f"CLAUDE: Good matches after ratio test: {len(good_matches)} (need >= {min_matches})")

        if len(good_matches) >= min_matches:
            # Get matched keypoints
            src_pts = np.float32([kp1[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
            dst_pts = np.float32([kp2[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)

            # Calculate center using homography
            try:
                center = HomographyCalculator.calculate_center_from_homography(
                    src_pts, dst_pts, icon_gray.shape
                )
                log.info(f"CLAUDE: SIFT match found at center: {center}")
                return FeatureMatchingResult([center], [float(len(good_matches))], "sift")
            except HomographyCalculationError as e:
                log.warning(f"CLAUDE: {e}")
        else:
            log.info("CLAUDE: Not enough good matches for reliable detection")

        return FeatureMatchingResult([], [], "sift")

    @staticmethod
    def _apply_ratio_test(matches: List, ratio_threshold: float) -> List:
        """Apply Lowe's ratio test to filter good matches."""
        good_matches = []
        for match_pair in matches:
            if len(match_pair) == 2:
                m, n = match_pair
                if m.distance < ratio_threshold * n.distance:
                    good_matches.append(m)
        return good_matches


class ORBMatcher:
    """ORB-based feature matching for icon detection."""

    @staticmethod
    def find_icon_locations(
        screenshot_bytes: bytes,
        icon_bytes: bytes,
        min_matches: int = CVConstants.ORB_MIN_MATCHES,
        max_matches: int = CVConstants.ORB_MAX_MATCHES,
        distance_threshold: float = CVConstants.ORB_DISTANCE_THRESHOLD
    ) -> FeatureMatchingResult:
        """Find multiple icon locations using ORB feature matching."""
        log.info(f"CLAUDE: ORB detection starting with min_matches={min_matches}, max_matches={max_matches}, distance_threshold={distance_threshold}")

        # Decode images
        decoded = ImageDecoder.decode_images(screenshot_bytes, icon_bytes)
        if decoded is None:
            return FeatureMatchingResult([], [], "orb")

        screenshot_img, icon_img = decoded
        screenshot_gray, icon_gray = ImageDecoder.convert_to_grayscale(screenshot_img, icon_img)

        # Initialize ORB detector
        orb = ORBMatcher._create_orb_detector()

        # Find keypoints and descriptors
        kp1, des1 = orb.detectAndCompute(icon_gray, None)
        kp2, des2 = orb.detectAndCompute(screenshot_gray, None)

        log.info(f"CLAUDE: Icon keypoints: {len(kp1) if kp1 else 0}, Screenshot keypoints: {len(kp2) if kp2 else 0}")

        if des1 is None or des2 is None:
            log.warning("CLAUDE: No descriptors found - images may be too simple or uniform")
            return FeatureMatchingResult([], [], "orb")

        # Match and filter features
        good_matches = ORBMatcher._match_and_filter_features(des1, des2, distance_threshold)

        log.info(f"CLAUDE: Good matches after distance filter: {len(good_matches)}")

        if len(good_matches) < min_matches:
            log.info(f"CLAUDE: Not enough good matches ({len(good_matches)} < {min_matches})")
            return FeatureMatchingResult([], [], "orb")

        # Extract matched keypoint coordinates
        src_pts = np.array([kp1[m.queryIdx].pt for m in good_matches])
        dst_pts = np.array([kp2[m.trainIdx].pt for m in good_matches])

        # Find multiple instances using clustering
        locations, similarities = ORBMatcher._find_multiple_instances(
            src_pts, dst_pts, good_matches, icon_gray.shape, min_matches, max_matches
        )

        log.info(f"CLAUDE: ORB found {len(locations)} valid matches")
        return FeatureMatchingResult(locations, similarities, "orb")

    @staticmethod
    def _create_orb_detector() -> cv2.ORB:
        """Create ORB detector with optimized settings for small icons."""
        return cv2.ORB_create(
            nfeatures=CVConstants.ORB_FEATURES,
            scaleFactor=CVConstants.ORB_SCALE_FACTOR,
            nlevels=CVConstants.ORB_LEVELS,
            edgeThreshold=CVConstants.ORB_EDGE_THRESHOLD,
            patchSize=CVConstants.ORB_PATCH_SIZE
        )

    @staticmethod
    def _match_and_filter_features(des1: np.ndarray, des2: np.ndarray, distance_threshold: float) -> List:
        """Match features and filter by distance threshold."""
        matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        matches = matcher.match(des1, des2)

        # Filter and sort matches
        good_matches = [m for m in matches if m.distance <= distance_threshold]
        return sorted(good_matches, key=lambda x: x.distance)

    @staticmethod
    def _find_multiple_instances(
        src_pts: np.ndarray,
        dst_pts: np.ndarray,
        good_matches: List,
        icon_shape: Tuple[int, int],
        min_matches: int,
        max_matches: int
    ) -> Tuple[List[Tuple[int, int]], List[float]]:
        """Find multiple icon instances using clustering."""
        try:
            # Determine clustering strategy
            if len(dst_pts) <= CVConstants.SMALL_CLUSTER_SIZE:
                log.info("CLAUDE: Few matches found, skipping clustering - treating as single icon")
                labels = np.zeros(len(dst_pts))
            else:
                clustering = DBSCAN(eps=CVConstants.ORB_CLUSTERING_EPS, min_samples=min_matches).fit(dst_pts)
                labels = clustering.labels_

            unique_labels = set(labels)
            if -1 in unique_labels:
                unique_labels.remove(-1)  # Remove noise cluster

            log.info(f"CLAUDE: Found {len(unique_labels)} potential clusters")

            valid_matches = []
            valid_similarities = []

            for label in unique_labels:
                cluster_mask = (labels == label)
                cluster_src = src_pts[cluster_mask]
                cluster_dst = dst_pts[cluster_mask]
                cluster_matches = [good_matches[i] for i, mask in enumerate(cluster_mask) if mask]

                center, similarity = ORBMatcher._process_cluster(
                    cluster_src, cluster_dst, cluster_matches, icon_shape
                )

                if center is not None:
                    valid_matches.append(center)
                    valid_similarities.append(similarity)

            # Sort by similarity and limit results
            if valid_matches:
                combined = list(zip(valid_matches, valid_similarities))
                combined.sort(key=lambda x: x[1], reverse=True)
                combined = combined[:max_matches]
                return [loc for loc, _ in combined], [sim for _, sim in combined]

            return [], []

        except Exception as e:
            log.error(f"CLAUDE: ORB clustering failed: {e}")
            return [], []

    @staticmethod
    def _process_cluster(
        cluster_src: np.ndarray,
        cluster_dst: np.ndarray,
        cluster_matches: List,
        icon_shape: Tuple[int, int]
    ) -> Tuple[Optional[Tuple[int, int]], float]:
        """Process a single cluster to find icon center and similarity."""
        if len(cluster_src) >= CVConstants.MIN_HOMOGRAPHY_POINTS:
            # Use homography for larger clusters
            center = HomographyCalculator.calculate_center_from_homography(
                cluster_src.reshape(-1, 1, 2),
                cluster_dst.reshape(-1, 1, 2),
                icon_shape,
                CVConstants.ORB_HOMOGRAPHY_THRESHOLD
            )

            if center is not None:
                avg_distance = np.mean([m.distance for m in cluster_matches])
                similarity = max(0.0, 1.0 - (avg_distance / CVConstants.ORB_MAX_DISTANCE_NORMALIZE))
                log.info(f"CLAUDE: ORB cluster match at {center} with {len(cluster_src)} features, similarity: {similarity:.3f}")
                return center, similarity

        elif len(cluster_src) >= 2:
            # Use centroid for small clusters
            center = HomographyCalculator.calculate_centroid(cluster_dst)
            avg_distance = np.mean([m.distance for m in cluster_matches])
            similarity = max(0.0, 1.0 - (avg_distance / CVConstants.ORB_MAX_DISTANCE_NORMALIZE))
            log.info(f"CLAUDE: ORB centroid match at {center} with {len(cluster_src)} features, similarity: {similarity:.3f}")
            return center, similarity

        return None, 0.0


class TemplateMatcher:
    """Template matching for icon detection."""

    @staticmethod
    def find_icon_locations(
        screenshot_bytes: bytes,
        icon_bytes: bytes,
        threshold: float = CVConstants.DEFAULT_TEMPLATE_THRESHOLD
    ) -> FeatureMatchingResult:
        """Find icon locations using template matching."""
        log.info(f"CLAUDE: Template matching starting with threshold={threshold}")

        # Decode images
        decoded = ImageDecoder.decode_images(screenshot_bytes, icon_bytes)
        if decoded is None:
            return FeatureMatchingResult([], [], "template")

        screenshot_img, icon_img = decoded

        # Get dimensions
        icon_h, icon_w = icon_img.shape[:2]
        screenshot_h, screenshot_w = screenshot_img.shape[:2]

        log.info(f"CLAUDE: Template matching - Screenshot: {screenshot_w}x{screenshot_h}, Icon: {icon_w}x{icon_h}")

        # Template matching
        result = cv2.matchTemplate(screenshot_img, icon_img, cv2.TM_CCOEFF_NORMED)

        # Find best match value for debugging
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
        log.info(f"CLAUDE: Template matching max similarity: {max_val:.3f} at {max_loc}")

        # Find locations above threshold
        locations = np.where(result >= threshold)
        points = list(zip(locations[1], locations[0]))  # (x, y)

        log.info(f"CLAUDE: Found {len(points)} points above threshold {threshold}")

        # Filter and convert to center coordinates
        valid_points, valid_similarities = TemplateMatcher._filter_valid_matches(
            points, result, icon_w, icon_h, screenshot_w, screenshot_h
        )

        log.info(f"CLAUDE: Template matching found {len(valid_points)} valid matches")
        return FeatureMatchingResult(valid_points, valid_similarities, "template")

    @staticmethod
    def _filter_valid_matches(
        points: List[Tuple[int, int]],
        result: np.ndarray,
        icon_w: int,
        icon_h: int,
        screenshot_w: int,
        screenshot_h: int
    ) -> Tuple[List[Tuple[int, int]], List[float]]:
        """Filter points to ensure icon fits within bounds and convert to center coordinates."""
        valid_points = []
        valid_similarities = []

        for x, y in points:
            # Check if the full icon would fit completely within bounds
            if x >= 0 and y >= 0 and x + icon_w <= screenshot_w and y + icon_h <= screenshot_h:
                # Return center coordinates instead of top-left corner
                center_x = x + icon_w // 2
                center_y = y + icon_h // 2
                valid_points.append((center_x, center_y))
                valid_similarities.append(float(result[y, x]))
                log.info(f"CLAUDE: Valid match at ({center_x}, {center_y}) with similarity {result[y, x]:.3f}")
            else:
                log.info(f"CLAUDE: Filtered out match at ({x}, {y}) - would extend outside bounds")

        return valid_points, valid_similarities