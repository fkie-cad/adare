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

    SPATIAL_COHERENCE_TOLERANCE = 3  # keypoints must be within 3x icon size

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
            screenshot_img, icon_img, alpha_mask = ImageDecoder.decode_images(screenshot_bytes, icon_bytes)
        except ImageDecodingError as e:
            log.error(f"SIFT: {e}")
            return FeatureMatchingResult([], [], "sift")

        screenshot_gray, icon_gray = ImageDecoder.convert_to_grayscale(screenshot_img, icon_img)

        # Extract screenshot shape for bounds checking
        screenshot_shape = screenshot_gray.shape  # (height, width)

        # Initialize SIFT detector
        sift = cv2.SIFT_create()

        # Find keypoints and descriptors (alpha mask excludes transparent pixels)
        kp1, des1 = sift.detectAndCompute(icon_gray, alpha_mask)
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

            # Spatial coherence: reject if keypoints span too large an area
            dst_flat = dst_pts.reshape(-1, 2)
            extent_x = float(np.max(dst_flat[:, 0]) - np.min(dst_flat[:, 0]))
            extent_y = float(np.max(dst_flat[:, 1]) - np.min(dst_flat[:, 1]))
            icon_h, icon_w = icon_gray.shape
            max_allowed = max(icon_w, icon_h) * SIFTMatcher.SPATIAL_COHERENCE_TOLERANCE

            if extent_x > max_allowed or extent_y > max_allowed:
                log.warning(
                    f"CLAUDE: SIFT rejecting match - keypoints span {extent_x:.0f}x{extent_y:.0f} "
                    f"but icon is only {icon_w}x{icon_h} (max allowed: {max_allowed:.0f})"
                )
                return FeatureMatchingResult([], [], "sift")

            # Calculate center using homography
            try:
                center = HomographyCalculator.calculate_center_from_homography(
                    src_pts, dst_pts, icon_gray.shape, screenshot_shape=screenshot_shape
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
        try:
            screenshot_img, icon_img, alpha_mask = ImageDecoder.decode_images(screenshot_bytes, icon_bytes)
        except ImageDecodingError as e:
            log.error(f"ORB: {e}")
            return FeatureMatchingResult([], [], "orb")

        screenshot_gray, icon_gray = ImageDecoder.convert_to_grayscale(screenshot_img, icon_img)

        # Extract screenshot shape for bounds checking
        screenshot_shape = screenshot_gray.shape  # (height, width)

        # Initialize ORB detector
        orb = ORBMatcher._create_orb_detector()

        # Find keypoints and descriptors (alpha mask excludes transparent pixels)
        kp1, des1 = orb.detectAndCompute(icon_gray, alpha_mask)
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
            src_pts, dst_pts, good_matches, icon_gray.shape, min_matches, max_matches, screenshot_shape
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
        max_matches: int,
        screenshot_shape: Tuple[int, int]
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
                    cluster_src, cluster_dst, cluster_matches, icon_shape, screenshot_shape
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

        except (ValueError, AttributeError, IndexError) as e:
            log.error(f"CLAUDE: ORB clustering failed: {e}")
            return [], []
        except Exception as e:
            log.error(f"CLAUDE: Unexpected ORB clustering error: {e}", exc_info=True)
            return [], []

    SPATIAL_COHERENCE_TOLERANCE = 3  # keypoints must be within 3x icon size

    @staticmethod
    def _process_cluster(
        cluster_src: np.ndarray,
        cluster_dst: np.ndarray,
        cluster_matches: List,
        icon_shape: Tuple[int, int],
        screenshot_shape: Tuple[int, int]
    ) -> Tuple[Optional[Tuple[int, int]], float]:
        """Process a single cluster to find icon center and similarity."""
        # Spatial coherence: reject clusters where keypoints span too large an area
        cluster_extent_x = float(np.max(cluster_dst[:, 0]) - np.min(cluster_dst[:, 0]))
        cluster_extent_y = float(np.max(cluster_dst[:, 1]) - np.min(cluster_dst[:, 1]))
        icon_h, icon_w = icon_shape
        max_allowed = max(icon_w, icon_h) * ORBMatcher.SPATIAL_COHERENCE_TOLERANCE

        if cluster_extent_x > max_allowed or cluster_extent_y > max_allowed:
            log.warning(
                f"CLAUDE: Rejecting match - keypoints span {cluster_extent_x:.0f}x{cluster_extent_y:.0f} "
                f"but icon is only {icon_w}x{icon_h} (max allowed: {max_allowed:.0f})"
            )
            return None, 0.0

        if len(cluster_src) >= CVConstants.MIN_HOMOGRAPHY_POINTS:
            # Use homography for larger clusters
            center = HomographyCalculator.calculate_center_from_homography(
                cluster_src.reshape(-1, 1, 2),
                cluster_dst.reshape(-1, 1, 2),
                icon_shape,
                CVConstants.ORB_HOMOGRAPHY_THRESHOLD,
                screenshot_shape
            )

            if center is not None:
                avg_distance = float(np.mean([m.distance for m in cluster_matches]))
                similarity = max(0.0, 1.0 - (avg_distance / CVConstants.ORB_MAX_DISTANCE_NORMALIZE))
                log.info(f"CLAUDE: ORB cluster match at {center} with {len(cluster_src)} features, similarity: {similarity:.3f}")
                return center, similarity

        elif len(cluster_src) >= 2:
            # Use centroid for small clusters
            center = HomographyCalculator.calculate_centroid(cluster_dst)

            # Validate centroid is within bounds
            screenshot_h, screenshot_w = screenshot_shape
            if not (0 <= center[0] < screenshot_w and 0 <= center[1] < screenshot_h):
                log.warning(f"CLAUDE: Rejecting centroid at {center} - outside bounds (0-{screenshot_w}, 0-{screenshot_h})")
                return None, 0.0

            avg_distance = float(np.mean([m.distance for m in cluster_matches]))
            similarity = max(0.0, 1.0 - (avg_distance / CVConstants.ORB_MAX_DISTANCE_NORMALIZE))
            log.info(f"CLAUDE: ORB centroid match at {center} with {len(cluster_src)} features, similarity: {similarity:.3f}")
            return center, similarity

        return None, 0.0


class TemplateMatcher:
    """Multi-scale template matching for icon detection.

    Tries 1x scale first for early exit (common case). Falls back to other
    scales only if 1x finds nothing. Supports alpha mask for icons with
    transparency via TM_CCORR_NORMED.
    """

    SCALES = [1.0, 0.9, 1.1, 0.8, 1.2, 0.75, 1.25, 0.5, 1.5, 2.0]
    NMS_OVERLAP_THRESHOLD = 0.3

    @staticmethod
    def find_icon_locations(
        screenshot_bytes: bytes,
        icon_bytes: bytes,
        threshold: float = CVConstants.DEFAULT_TEMPLATE_THRESHOLD
    ) -> FeatureMatchingResult:
        """Find icon locations using multi-scale template matching.

        Tries 1x scale first. If matches are found, returns immediately without
        trying other scales (early exit optimization). Only falls back to other
        scales if 1x finds nothing.
        """
        log.info(f"CLAUDE: Template matching starting with threshold={threshold}")

        try:
            screenshot_img, icon_img, alpha_mask = ImageDecoder.decode_images(screenshot_bytes, icon_bytes)
        except ImageDecodingError as e:
            log.error(f"Template: {e}")
            return FeatureMatchingResult([], [], "template")

        icon_h, icon_w = icon_img.shape[:2]
        screenshot_h, screenshot_w = screenshot_img.shape[:2]

        log.info(f"CLAUDE: Template matching - Screenshot: {screenshot_w}x{screenshot_h}, Icon: {icon_w}x{icon_h}")

        # Determine matching method based on alpha mask presence
        if alpha_mask is not None:
            method = cv2.TM_CCORR_NORMED
            log.info("CLAUDE: Using TM_CCORR_NORMED with alpha mask")
        else:
            method = cv2.TM_CCOEFF_NORMED

        candidates: List[Tuple[int, int, int, int, float]] = []  # (x, y, w, h, similarity)

        for scale in TemplateMatcher.SCALES:
            scaled_w = max(1, int(icon_w * scale))
            scaled_h = max(1, int(icon_h * scale))

            if scaled_w >= screenshot_w or scaled_h >= screenshot_h:
                continue

            resized_icon = cv2.resize(icon_img, (scaled_w, scaled_h), interpolation=cv2.INTER_AREA)

            if alpha_mask is not None:
                resized_mask = cv2.resize(alpha_mask, (scaled_w, scaled_h), interpolation=cv2.INTER_NEAREST)
                result = cv2.matchTemplate(screenshot_img, resized_icon, method, mask=resized_mask)
            else:
                result = cv2.matchTemplate(screenshot_img, resized_icon, method)

            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

            if max_val >= threshold:
                log.info(f"CLAUDE: Scale {scale:.2f} - best match: {max_val:.3f} at {max_loc}")

            locations = np.where(result >= threshold)
            for y, x in zip(locations[0], locations[1]):
                if x >= 0 and y >= 0 and x + scaled_w <= screenshot_w and y + scaled_h <= screenshot_h:
                    candidates.append((int(x), int(y), scaled_w, scaled_h, float(result[y, x])))

            # Early exit: if 1x scale found matches, skip remaining scales
            if scale == 1.0 and candidates:
                log.info(f"CLAUDE: Found {len(candidates)} matches at 1x scale, skipping other scales")
                break

        log.info(f"CLAUDE: Total candidates before NMS: {len(candidates)}")

        if not candidates:
            log.info("CLAUDE: Template matching found no matches")
            return FeatureMatchingResult([], [], "template")

        # Non-Maximum Suppression to remove duplicate/overlapping matches
        filtered = TemplateMatcher._non_maximum_suppression(candidates)

        # Convert to center coordinates
        valid_points = []
        valid_similarities = []
        for x, y, w, h, sim in filtered:
            center_x = x + w // 2
            center_y = y + h // 2
            valid_points.append((center_x, center_y))
            valid_similarities.append(sim)
            log.info(f"CLAUDE: Valid match at ({center_x}, {center_y}) with similarity {sim:.3f}")

        log.info(f"CLAUDE: Template matching found {len(valid_points)} valid matches after NMS")
        return FeatureMatchingResult(valid_points, valid_similarities, "template")

    @staticmethod
    def _non_maximum_suppression(
        candidates: List[Tuple[int, int, int, int, float]]
    ) -> List[Tuple[int, int, int, int, float]]:
        """Remove overlapping matches, keeping highest similarity."""
        if not candidates:
            return []

        # Sort by similarity descending
        sorted_candidates = sorted(candidates, key=lambda c: c[4], reverse=True)
        kept: List[Tuple[int, int, int, int, float]] = []

        for candidate in sorted_candidates:
            cx, cy, cw, ch, csim = candidate
            is_duplicate = False

            for kx, ky, kw, kh, ksim in kept:
                # Calculate IoU (Intersection over Union)
                ix1 = max(cx, kx)
                iy1 = max(cy, ky)
                ix2 = min(cx + cw, kx + kw)
                iy2 = min(cy + ch, ky + kh)

                if ix1 < ix2 and iy1 < iy2:
                    intersection = (ix2 - ix1) * (iy2 - iy1)
                    union = cw * ch + kw * kh - intersection
                    iou = intersection / union if union > 0 else 0

                    if iou > TemplateMatcher.NMS_OVERLAP_THRESHOLD:
                        is_duplicate = True
                        break

            if not is_duplicate:
                kept.append(candidate)

        return kept
