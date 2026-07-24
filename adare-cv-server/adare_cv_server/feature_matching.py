"""Feature matching algorithms for icon detection."""

import logging
from typing import List, Tuple, Optional
import numpy as np
import cv2
from sklearn.cluster import DBSCAN

from .constants import CVConstants
from .image_processing import ImageDecoder, FeatureMatchingResult, HomographyCalculator, non_maximum_suppression
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
        log.info(f"SIFT detection starting with min_matches={min_matches}, ratio_threshold={ratio_threshold}")

        try:
            # Decode images
            decoded = ImageDecoder.decode_images(screenshot_bytes, icon_bytes)
        except ImageDecodingError as e:
            log.error(f"SIFT: {e}")
            return FeatureMatchingResult([], [], "sift")

        screenshot_img, icon_img = decoded
        screenshot_gray, icon_gray = ImageDecoder.convert_to_grayscale(screenshot_img, icon_img)

        # Extract screenshot shape for bounds checking
        screenshot_shape = screenshot_gray.shape  # (height, width)

        # Initialize SIFT detector
        sift = cv2.SIFT_create()

        # Find keypoints and descriptors
        kp1, des1 = sift.detectAndCompute(icon_gray, None)
        kp2, des2 = sift.detectAndCompute(screenshot_gray, None)

        log.info(f"Icon keypoints: {len(kp1) if kp1 else 0}, Screenshot keypoints: {len(kp2) if kp2 else 0}")

        if des1 is None or des2 is None:
            log.warning("No descriptors found - images may be too simple or uniform")
            return FeatureMatchingResult([], [], "sift")

        # Match features
        matcher = cv2.BFMatcher()
        matches = matcher.knnMatch(des1, des2, k=2)

        log.info(f"Initial matches found: {len(matches)}")

        # Apply Lowe's ratio test
        good_matches = SIFTMatcher._apply_ratio_test(matches, ratio_threshold)

        log.info(f"Good matches after ratio test: {len(good_matches)} (need >= {min_matches})")

        if len(good_matches) >= min_matches:
            # Get matched keypoints
            src_pts = np.float32([kp1[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
            dst_pts = np.float32([kp2[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)

            # Calculate center using homography
            try:
                center = HomographyCalculator.calculate_center_from_homography(
                    src_pts, dst_pts, icon_gray.shape, screenshot_shape=screenshot_shape
                )
                log.info(f"SIFT match found at center: {center}")
                return FeatureMatchingResult([center], [float(len(good_matches))], "sift")
            except HomographyCalculationError as e:
                log.warning(f"{e}")
        else:
            log.info("Not enough good matches for reliable detection")

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
        log.info(f"ORB detection starting with min_matches={min_matches}, max_matches={max_matches}, distance_threshold={distance_threshold}")

        # Decode images
        decoded = ImageDecoder.decode_images(screenshot_bytes, icon_bytes)
        if decoded is None:
            return FeatureMatchingResult([], [], "orb")

        screenshot_img, icon_img = decoded
        screenshot_gray, icon_gray = ImageDecoder.convert_to_grayscale(screenshot_img, icon_img)

        # Extract screenshot shape for bounds checking
        screenshot_shape = screenshot_gray.shape  # (height, width)

        # Initialize ORB detector with adaptive parameters
        orb = ORBMatcher._create_orb_detector(icon_gray)

        # Find keypoints and descriptors
        kp1, des1 = orb.detectAndCompute(icon_gray, None)
        kp2, des2 = orb.detectAndCompute(screenshot_gray, None)

        log.info(f"Icon keypoints: {len(kp1) if kp1 else 0}, Screenshot keypoints: {len(kp2) if kp2 else 0}")

        if des1 is None or des2 is None:
            log.warning("No descriptors found - images may be too simple or uniform")
            return FeatureMatchingResult([], [], "orb")

        # Match and filter features
        good_matches = ORBMatcher._match_and_filter_features(des1, des2, distance_threshold)

        log.info(f"Good matches after distance filter: {len(good_matches)}")

        if len(good_matches) < min_matches:
            log.info(f"Not enough good matches ({len(good_matches)} < {min_matches})")
            return FeatureMatchingResult([], [], "orb")

        # Extract matched keypoint coordinates
        src_pts = np.array([kp1[m.queryIdx].pt for m in good_matches])
        dst_pts = np.array([kp2[m.trainIdx].pt for m in good_matches])

        # Find multiple instances using clustering
        locations, similarities = ORBMatcher._find_multiple_instances(
            src_pts, dst_pts, good_matches, icon_gray.shape, min_matches, max_matches, screenshot_shape
        )

        log.info(f"ORB found {len(locations)} valid matches")
        return FeatureMatchingResult(locations, similarities, "orb")

    @staticmethod
    def _create_orb_detector(icon_img: np.ndarray) -> cv2.ORB:
        """Create ORB detector with adaptive parameters for small icons.

        Small icons (<100px) use reduced pyramid levels and edge threshold
        to prevent over-downsampling and preserve central features.
        """
        # Adaptive parameters based on icon size
        icon_h, icon_w = icon_img.shape[:2]
        icon_size = min(icon_h, icon_w)

        if icon_size < CVConstants.SVG_SMALL_ICON_THRESHOLD:
            # Small icon: reduce pyramid levels, relax edge threshold
            nlevels = CVConstants.ORB_SMALL_ICON_NLEVELS
            edgeThreshold = CVConstants.ORB_SMALL_ICON_EDGE_THRESHOLD
            log.info(f"Small icon ({icon_size}px), using nlevels={nlevels}, edgeThreshold={edgeThreshold}")
        else:
            # Large icon/screenshot: use default parameters
            nlevels = CVConstants.ORB_LEVELS
            edgeThreshold = CVConstants.ORB_EDGE_THRESHOLD

        return cv2.ORB_create(
            nfeatures=CVConstants.ORB_FEATURES,
            scaleFactor=CVConstants.ORB_SCALE_FACTOR,
            nlevels=nlevels,
            edgeThreshold=edgeThreshold,
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
                log.info("Few matches found, skipping clustering - treating as single icon")
                labels = np.zeros(len(dst_pts))
            else:
                clustering = DBSCAN(eps=CVConstants.ORB_CLUSTERING_EPS, min_samples=min_matches).fit(dst_pts)
                labels = clustering.labels_

            unique_labels = set(labels)
            if -1 in unique_labels:
                unique_labels.remove(-1)  # Remove noise cluster

            log.info(f"Found {len(unique_labels)} potential clusters")

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
            log.error(f"ORB clustering failed: {e}")
            return [], []
        except Exception as e:
            log.error(f"Unexpected ORB clustering error: {e}", exc_info=True)
            return [], []

    @staticmethod
    def _process_cluster(
        cluster_src: np.ndarray,
        cluster_dst: np.ndarray,
        cluster_matches: List,
        icon_shape: Tuple[int, int],
        screenshot_shape: Tuple[int, int]
    ) -> Tuple[Optional[Tuple[int, int]], float]:
        """Process a single cluster to find icon center and similarity."""
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
                log.info(f"ORB cluster match at {center} with {len(cluster_src)} features, similarity: {similarity:.3f}")
                return center, similarity

        elif len(cluster_src) >= 2:
            # Use centroid for small clusters
            center = HomographyCalculator.calculate_centroid(cluster_dst)

            # Validate centroid is within bounds
            screenshot_h, screenshot_w = screenshot_shape
            if not (0 <= center[0] < screenshot_w and 0 <= center[1] < screenshot_h):
                log.warning(f"Rejecting centroid at {center} - outside bounds (0-{screenshot_w}, 0-{screenshot_h})")
                return None, 0.0

            avg_distance = float(np.mean([m.distance for m in cluster_matches]))
            similarity = max(0.0, 1.0 - (avg_distance / CVConstants.ORB_MAX_DISTANCE_NORMALIZE))
            log.info(f"ORB centroid match at {center} with {len(cluster_src)} features, similarity: {similarity:.3f}")
            return center, similarity

        return None, 0.0


class TemplateMatcher:
    """Template matching for icon detection."""

    @staticmethod
    def find_icon_locations(
        screenshot_bytes: bytes,
        icon_bytes: bytes,
        threshold: float = CVConstants.DEFAULT_TEMPLATE_THRESHOLD,
        icon_mask: Optional[np.ndarray] = None
    ) -> FeatureMatchingResult:
        """Find best icon location using template matching.

        Args:
            screenshot_bytes: Screenshot image bytes
            icon_bytes: Icon image bytes
            threshold: Similarity threshold (0.0-1.0)
            icon_mask: Optional mask (255=include, 0=ignore transparent pixels)

        Returns only the single best match (highest similarity) above threshold.
        """
        log.info(f"Template matching starting with threshold={threshold}")

        # Decode images
        decoded = ImageDecoder.decode_images(screenshot_bytes, icon_bytes)
        if decoded is None:
            return FeatureMatchingResult([], [], "template")

        screenshot_img, icon_img = decoded

        # Get dimensions
        icon_h, icon_w = icon_img.shape[:2]
        screenshot_h, screenshot_w = screenshot_img.shape[:2]

        log.info(f"Template matching - Screenshot: {screenshot_w}x{screenshot_h}, Icon: {icon_w}x{icon_h}")

        # Validate mask quality if present (prevents inf/nan from edge cases)
        if icon_mask is not None:
            # Check minimum opaque pixel count
            opaque_count = np.sum(icon_mask > 0)
            if opaque_count < CVConstants.MULTISCALE_TEMPLATE_MIN_MASK_OPAQUE_PIXELS_ABSOLUTE:
                log.warning(f"Template matching skipped - mask too sparse "
                           f"({opaque_count} opaque pixels < {CVConstants.MULTISCALE_TEMPLATE_MIN_MASK_OPAQUE_PIXELS_ABSOLUTE})")
                return FeatureMatchingResult([], [], "template")

            # Check variance in opaque region
            icon_gray = cv2.cvtColor(icon_img, cv2.COLOR_BGR2GRAY)
            opaque_region = icon_gray[icon_mask > 0]
            if len(opaque_region) > 0:
                variance = np.var(opaque_region.astype(np.float32))
                std_dev = np.sqrt(variance)

                if std_dev < CVConstants.MULTISCALE_TEMPLATE_MIN_STD_DEV:
                    log.warning(f"Template matching skipped - masked region too uniform "
                               f"(std_dev: {std_dev:.1f} < {CVConstants.MULTISCALE_TEMPLATE_MIN_STD_DEV})")
                    return FeatureMatchingResult([], [], "template")

        # Template matching with optional mask
        result = cv2.matchTemplate(screenshot_img, icon_img, cv2.TM_CCOEFF_NORMED, mask=icon_mask)

        # Find best match only (highest similarity)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

        # Validate results for inf/nan (edge case with masked matching)
        if np.isinf(max_val) or np.isnan(max_val):
            log.warning(f"Template matching failed - invalid similarity "
                       f"(inf/nan detected, likely edge case with masked region)")
            return FeatureMatchingResult([], [], "template")

        log.info(f"Template matching best similarity: {max_val:.3f} at {max_loc}")

        # Return best match if above threshold
        if max_val >= threshold:
            # Validate that icon fits within bounds
            x, y = max_loc
            if x >= 0 and y >= 0 and x + icon_w <= screenshot_w and y + icon_h <= screenshot_h:
                # Convert to center coordinates (convert to Python int for JSON serialization)
                center_x = int(x + icon_w // 2)
                center_y = int(y + icon_h // 2)

                if icon_mask is not None:
                    log.info(f"Template matching used mask "
                            f"(ignored {np.sum(icon_mask == 0)} transparent pixels)")

                log.info(f"Template matching found best match at ({center_x}, {center_y}) with similarity {max_val:.3f}")
                return FeatureMatchingResult(
                    [(center_x, center_y)], [float(max_val)], "template",
                    scales=[1.0], sizes=[(icon_w, icon_h)]
                )
            else:
                log.warning(f"Best match at ({x}, {y}) would extend outside bounds, no match")
                return FeatureMatchingResult([], [], "template")
        else:
            log.info(f"Best similarity {max_val:.3f} below threshold {threshold}, no match")
            return FeatureMatchingResult([], [], "template")


class CannyEdgeMatcher:
    """Canny edge-based multi-scale template matching for lighting-invariant detection.

    This matcher converts both the screenshot and icon to edge maps using Canny edge
    detection, then performs multi-scale template matching. This approach is robust to:
    - Lighting variations (different brightness, tint, gradients)
    - Color theme changes (light/dark mode)
    - Background color interference

    The edge-based approach focuses on structural outline rather than pixel intensities,
    making it ideal for UI icons that may appear in different color schemes.
    """

    _debug_output_dir: Optional[any] = None  # Class variable for debug output directory

    @classmethod
    def set_debug_output_dir(cls, output_dir: any) -> None:
        """Set directory for saving debug images."""
        cls._debug_output_dir = output_dir

    @staticmethod
    def find_icon_locations(
        screenshot_bytes: bytes,
        icon_bytes: bytes,
        threshold: float = CVConstants.CANNY_EDGE_THRESHOLD,
        fallback_threshold: float = CVConstants.CANNY_EDGE_FALLBACK_THRESHOLD,
        scale_range: tuple = CVConstants.CANNY_EDGE_SCALE_RANGE,
        scale_step_fine: float = CVConstants.CANNY_EDGE_SCALE_STEP_FINE,
        scale_step_coarse: float = CVConstants.CANNY_EDGE_SCALE_STEP_COARSE,
        min_icon_size: int = CVConstants.CANNY_EDGE_MIN_ICON_SIZE,
    ) -> FeatureMatchingResult:
        """Find icon locations using Canny edge detection + multi-scale template matching.

        Args:
            screenshot_bytes: Screenshot image bytes
            icon_bytes: Icon image bytes
            threshold: Similarity threshold for exact matches (default: 0.85)
            fallback_threshold: Similarity threshold to skip remaining stages (default: 0.75)
            scale_range: (min_scale, max_scale) tuple for multi-scale search (default: 0.1-10.0x)
            scale_step_fine: Scale increment below 1.0x (default: 0.1)
            scale_step_coarse: Scale increment above 1.0x (default: 0.5)
            min_icon_size: Minimum icon size in pixels (default: 15x15)

        Returns:
            FeatureMatchingResult with locations, similarities, and method name
        """
        try:
            # Decode images (no need for alpha channel - edges don't use masks)
            decoded = ImageDecoder.decode_images(screenshot_bytes, icon_bytes)
            if decoded is None:
                log.warning("Canny edge matching - failed to decode images")
                return FeatureMatchingResult([], [], "canny_edge")

            screenshot_img, icon_img = decoded

            # Convert to grayscale
            screenshot_gray = cv2.cvtColor(screenshot_img, cv2.COLOR_BGR2GRAY)
            icon_gray = cv2.cvtColor(icon_img, cv2.COLOR_BGR2GRAY)

            # Preprocess: Gaussian blur to reduce noise
            screenshot_blurred = cv2.GaussianBlur(
                screenshot_gray,
                CVConstants.CANNY_EDGE_BLUR_KERNEL,
                0
            )
            icon_blurred = cv2.GaussianBlur(
                icon_gray,
                CVConstants.CANNY_EDGE_BLUR_KERNEL,
                0
            )

            # Apply Canny edge detection with auto-thresholding
            screenshot_edges = CannyEdgeMatcher._apply_canny_auto(screenshot_blurred)
            icon_edges = CannyEdgeMatcher._apply_canny_auto(icon_blurred)

            # Optional: dilate edges for more robust matching
            if CVConstants.CANNY_EDGE_DILATE_ITERATIONS > 0:
                kernel = np.ones((3, 3), np.uint8)
                screenshot_edges = cv2.dilate(
                    screenshot_edges,
                    kernel,
                    iterations=CVConstants.CANNY_EDGE_DILATE_ITERATIONS
                )
                icon_edges = cv2.dilate(
                    icon_edges,
                    kernel,
                    iterations=CVConstants.CANNY_EDGE_DILATE_ITERATIONS
                )

            # Get dimensions
            screenshot_h, screenshot_w = screenshot_edges.shape
            icon_h, icon_w = icon_edges.shape

            log.info(f"Canny edge detection - Screenshot: {screenshot_w}x{screenshot_h}, "
                    f"Icon: {icon_w}x{icon_h}")

            # Check if icon edges are too sparse (not enough structure for matching)
            icon_edge_density = np.sum(icon_edges > 0) / (icon_w * icon_h)
            if icon_edge_density < 0.05:  # Less than 5% edge pixels
                log.info(f"Canny edge matching skipped - icon edges too sparse "
                        f"(density: {icon_edge_density:.3f} < 0.05)")
                return FeatureMatchingResult([], [], "canny_edge")

            # Generate scale list (fine steps below 1.0x, coarse steps above)
            min_scale, max_scale = scale_range
            scales = []

            # Fine steps below 1.0x
            current_scale = min_scale
            while current_scale < 1.0:
                scales.append(current_scale)
                current_scale += scale_step_fine

            # Always test 1.0x
            scales.append(1.0)

            # Coarse steps above 1.0x
            current_scale = 1.0 + scale_step_coarse
            while current_scale <= max_scale:
                scales.append(current_scale)
                current_scale += scale_step_coarse

            log.info(f"Canny edge multi-scale matching - testing {len(scales)} scales "
                    f"from {min_scale}x to {max_scale}x (fine: {scale_step_fine}, coarse: {scale_step_coarse})")

            # Multi-scale template matching - collect ALL matches above threshold
            all_matches = []  # List of {location, similarity, scale, size}
            best_scale_found = 1.0  # Track best scale for debug visualization
            early_termination_occurred = False  # Track early termination

            for scale in scales:
                # Calculate scaled dimensions
                new_w = int(icon_w * scale)
                new_h = int(icon_h * scale)

                # Skip if scaled icon is too small
                if new_w < min_icon_size or new_h < min_icon_size:
                    log.info(f"Skipping scale {scale:.2f}x - icon would be {new_w}x{new_h} "
                            f"(below minimum {min_icon_size}x{min_icon_size})")
                    continue

                # Skip if resized icon is larger than screenshot
                if new_h > screenshot_h or new_w > screenshot_w:
                    log.info(f"Skipping scale {scale:.2f}x - icon would be {new_w}x{new_h}, "
                            f"screenshot is {screenshot_w}x{screenshot_h}")
                    continue

                # Resize icon edges
                resized_icon_edges = cv2.resize(
                    icon_edges,
                    (new_w, new_h),
                    interpolation=cv2.INTER_LINEAR
                )

                # Re-threshold to ensure binary edge map after resize
                _, resized_icon_edges = cv2.threshold(
                    resized_icon_edges,
                    128,
                    255,
                    cv2.THRESH_BINARY
                )

                # Template matching on edge maps
                result = cv2.matchTemplate(
                    screenshot_edges,
                    resized_icon_edges,
                    cv2.TM_CCOEFF_NORMED
                )

                # Find ALL locations where similarity >= fallback_threshold
                match_locations = np.where(result >= fallback_threshold)

                # Check for valid matches at this scale
                if len(match_locations[0]) > 0:
                    for y_idx, x_idx in zip(match_locations[0], match_locations[1]):
                        similarity = result[y_idx, x_idx]

                        # Validate results (check for inf/nan)
                        if np.isinf(similarity) or np.isnan(similarity):
                            continue

                        # Calculate center coordinates in original screenshot space
                        # (y_idx, x_idx) is top-left in result matrix
                        center_x = int(x_idx + new_w // 2)
                        center_y = int(y_idx + new_h // 2)

                        all_matches.append({
                            'location': (center_x, center_y),
                            'similarity': float(similarity),
                            'scale': scale,
                            'size': (new_w, new_h)  # Size in screenshot coordinates
                        })

                        log.info(f"Canny edge match at scale {scale:.2f}x ({new_w}x{new_h} pix.): "
                                f"similarity {similarity:.3f} at ({center_x}, {center_y})")

                # Early termination only for EXACT matches (>0.95)
                best_in_scale = np.max(result) if result.size > 0 else -1
                if best_in_scale > 0.95:
                    best_scale_found = scale  # Track scale for debug
                    early_termination_occurred = True
                    log.info(f"Early termination at scale {scale:.2f}x - "
                            f"found exact match ({best_in_scale:.3f})")
                    break

            if not all_matches:
                log.info(f"Stage 0 (Canny edge) - no matches above fallback threshold "
                        f"{fallback_threshold}, continuing to Stage 1")
                return FeatureMatchingResult([], [], "canny_edge")

            # Apply NMS to remove overlapping duplicates
            locations = [m['location'] for m in all_matches]
            similarities = [m['similarity'] for m in all_matches]
            sizes = [m['size'] for m in all_matches]
            scales = [m['scale'] for m in all_matches]

            # Create lookup dict for scales/sizes by location
            match_metadata = {
                loc: {'scale': scale, 'size': size}
                for loc, scale, size in zip(locations, scales, sizes)
            }

            filtered_locations, filtered_similarities = non_maximum_suppression(
                locations, similarities, sizes, overlap_threshold=CVConstants.NMS_OVERLAP_THRESHOLD
            )

            if not filtered_locations:
                log.info("Stage 0 (Canny edge) - all matches suppressed by NMS")
                return FeatureMatchingResult([], [], "canny_edge")

            # Retrieve scales and sizes for filtered locations
            filtered_scales = [match_metadata[loc]['scale'] for loc in filtered_locations]
            filtered_sizes = [match_metadata[loc]['size'] for loc in filtered_locations]

            # Sort by similarity (descending) and return
            sorted_matches = sorted(
                zip(filtered_locations, filtered_similarities, filtered_scales, filtered_sizes),
                key=lambda x: x[1],
                reverse=True
            )

            final_locations = [m[0] for m in sorted_matches]
            final_similarities = [m[1] for m in sorted_matches]
            final_scales = [m[2] for m in sorted_matches]
            final_sizes = [m[3] for m in sorted_matches]

            # Track best scale for debug (find scale of best match)
            if not early_termination_occurred and all_matches:
                # Find the match with highest similarity in all_matches
                best_match = max(all_matches, key=lambda m: m['similarity'])
                best_scale_found = best_match['scale']

            # Determine success level
            best_similarity = final_similarities[0]
            if best_similarity >= threshold:
                log.info(f"Stage 0 (Canny edge) found {len(final_locations)} matches "
                        f"(best: {best_similarity:.3f} >= threshold {threshold})")
            else:
                log.info(f"Stage 0 (Canny edge) found {len(final_locations)} matches "
                        f"(best: {best_similarity:.3f} >= fallback {fallback_threshold})")

            # Save debug visualizations if enabled
            if CannyEdgeMatcher._debug_output_dir:
                from datetime import datetime
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
                CannyEdgeMatcher._save_debug_images(
                    screenshot_edges=screenshot_edges,
                    icon_edges=icon_edges,
                    final_locations=final_locations,
                    final_similarities=final_similarities,
                    screenshot_bgr=screenshot_img,
                    icon_bgr=icon_img,
                    best_scale=best_scale_found,
                    timestamp=timestamp,
                    early_termination=early_termination_occurred
                )

            return FeatureMatchingResult(
                final_locations, final_similarities, "canny_edge",
                scales=final_scales, sizes=final_sizes
            )

        except Exception as e:
            log.warning(f"Canny edge matching failed with error: {str(e)}")
            return FeatureMatchingResult([], [], "canny_edge")

    @staticmethod
    def _apply_canny_auto(image_gray: np.ndarray) -> np.ndarray:
        """Apply Canny edge detection with automatic threshold selection.

        Uses median-based auto-thresholding:
        - Lower threshold: median * 0.66
        - Upper threshold: median * 1.33

        This adapts to different image contrast levels.

        Args:
            image_gray: Grayscale image (already blurred)

        Returns:
            Binary edge map (255 = edge, 0 = non-edge)
        """
        # Calculate median for auto-thresholding
        median = np.median(image_gray)

        # Calculate thresholds
        lower = int(max(0, median * CVConstants.CANNY_EDGE_AUTO_THRESHOLD_LOWER))
        upper = int(min(255, median * CVConstants.CANNY_EDGE_AUTO_THRESHOLD_UPPER))

        # Apply Canny edge detection
        edges = cv2.Canny(image_gray, lower, upper)

        return edges

    @classmethod
    def _save_debug_images(
        cls,
        screenshot_edges: np.ndarray,
        icon_edges: np.ndarray,
        final_locations: List[Tuple[int, int]],
        final_similarities: List[float],
        screenshot_bgr: np.ndarray,
        icon_bgr: np.ndarray,
        best_scale: float,
        timestamp: str,
        early_termination: bool
    ) -> None:
        """Save Canny edge debug visualizations if debug dir is set.

        Saves 5 images:
        1. Screenshot edges (grayscale)
        2. Icon edges (grayscale)
        3. Screenshot with match boxes (BGR with annotations)
        4. Side-by-side comparison (edges | original)
        5. Icon at best scale with edges overlay

        Args:
            screenshot_edges: Edge map of screenshot
            icon_edges: Edge map of icon template
            final_locations: List of (x, y) match centers
            final_similarities: List of similarity scores
            screenshot_bgr: Original screenshot (BGR)
            icon_bgr: Original icon (BGR)
            best_scale: Scale that produced best match
            timestamp: Timestamp string for filenames
            early_termination: Whether early termination was triggered
        """
        if not cls._debug_output_dir:
            return

        try:
            from .constants import DebugConstants
            from pathlib import Path

            # Ensure output directory exists
            output_dir = Path(cls._debug_output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)

            # 1. Save screenshot edges (grayscale)
            screenshot_edges_path = output_dir / f"canny_edges_screenshot_{timestamp}.png"
            cv2.imwrite(str(screenshot_edges_path), screenshot_edges)
            log.info(f"Saved screenshot edges to {screenshot_edges_path}")

            # 2. Save icon edges (grayscale)
            icon_edges_path = output_dir / f"canny_edges_icon_{timestamp}.png"
            cv2.imwrite(str(icon_edges_path), icon_edges)
            log.info(f"Saved icon edges to {icon_edges_path}")

            # 3. Save screenshot with match boxes (annotated)
            annotated = screenshot_bgr.copy()
            icon_h, icon_w = icon_edges.shape

            # Draw all matches
            for i, (location, similarity) in enumerate(zip(final_locations, final_similarities)):
                center_x, center_y = location

                # Calculate box corners (scaled icon size)
                scaled_w = int(icon_w * best_scale)
                scaled_h = int(icon_h * best_scale)
                x1 = int(center_x - scaled_w // 2)
                y1 = int(center_y - scaled_h // 2)
                x2 = int(center_x + scaled_w // 2)
                y2 = int(center_y + scaled_h // 2)

                # Draw green box
                cv2.rectangle(
                    annotated,
                    (x1, y1),
                    (x2, y2),
                    DebugConstants.MATCH_BOX_COLOR,
                    DebugConstants.MATCH_BOX_THICKNESS
                )

                # Draw similarity score above box
                score_text = f"{similarity:.2f} @{best_scale:.1f}x"
                cv2.putText(
                    annotated,
                    score_text,
                    (x1, y1 - 5),
                    DebugConstants.TEXT_FONT,
                    DebugConstants.TEXT_SCALE,
                    DebugConstants.TEXT_COLOR,
                    DebugConstants.TEXT_THICKNESS
                )

            # Add summary in top-left corner
            summary_text = f"Stage 0: {len(final_locations)} matches found"
            cv2.putText(
                annotated,
                summary_text,
                (10, 30),
                DebugConstants.TEXT_FONT,
                0.7,
                DebugConstants.SUMMARY_COLOR,
                2
            )

            # Add early termination indicator if applicable
            if early_termination:
                cv2.putText(
                    annotated,
                    "EARLY TERM",
                    (10, 60),
                    DebugConstants.TEXT_FONT,
                    0.7,
                    DebugConstants.EARLY_TERM_COLOR,
                    2
                )

            matches_path = output_dir / f"canny_matches_{timestamp}.png"
            cv2.imwrite(str(matches_path), annotated)
            log.info(f"Saved annotated matches to {matches_path}")

            # 4. Save side-by-side comparison (edges | original)
            # Convert edges to BGR for concatenation
            screenshot_edges_bgr = cv2.cvtColor(screenshot_edges, cv2.COLOR_GRAY2BGR)
            comparison = np.hstack([screenshot_edges_bgr, screenshot_bgr])

            comparison_path = output_dir / f"canny_comparison_{timestamp}.png"
            cv2.imwrite(str(comparison_path), comparison)
            log.info(f"Saved edge comparison to {comparison_path}")

            # 5. Save icon at best scale with edges overlay
            # Scale icon to best match size
            scaled_w = int(icon_w * best_scale)
            scaled_h = int(icon_h * best_scale)

            if scaled_w > 0 and scaled_h > 0:
                # Resize icon
                scaled_icon_bgr = cv2.resize(
                    icon_bgr,
                    (scaled_w, scaled_h),
                    interpolation=cv2.INTER_LINEAR
                )

                # Resize and re-threshold edges
                scaled_icon_edges = cv2.resize(
                    icon_edges,
                    (scaled_w, scaled_h),
                    interpolation=cv2.INTER_LINEAR
                )
                _, scaled_icon_edges = cv2.threshold(
                    scaled_icon_edges,
                    128,
                    255,
                    cv2.THRESH_BINARY
                )

                # Create overlay: green edges on original icon
                overlay = scaled_icon_bgr.copy()
                overlay[scaled_icon_edges > 0] = DebugConstants.MATCH_BOX_COLOR

                # Blend: 70% original + 30% overlay
                blended = cv2.addWeighted(scaled_icon_bgr, 0.7, overlay, 0.3, 0)

                best_scale_path = output_dir / f"canny_best_scale_{timestamp}.png"
                cv2.imwrite(str(best_scale_path), blended)
                log.info(f"Saved best scale visualization to {best_scale_path}")

            log.info(f"Canny edge debug output complete ({timestamp})")

        except Exception as e:
            log.warning(f"Failed to save Canny edge debug images: {e}")


class MultiScaleTemplateMatcher:
    """Multi-scale template matching for precision-first detection.

    Stage 1 of the staged detection pipeline. Catches exact pixel matches at
    different scales before ORB can match text edges on cluttered screens.
    """

    @staticmethod
    def find_icon_locations(
        screenshot_bytes: bytes,
        icon_bytes: bytes,
        threshold: float = CVConstants.MULTISCALE_TEMPLATE_THRESHOLD,
        fallback_threshold: float = CVConstants.MULTISCALE_TEMPLATE_FALLBACK_THRESHOLD,
        scale_range: tuple = CVConstants.MULTISCALE_TEMPLATE_SCALE_RANGE,
        scale_step_fine: float = CVConstants.MULTISCALE_TEMPLATE_SCALE_STEP_FINE,
        scale_step_coarse: float = CVConstants.MULTISCALE_TEMPLATE_SCALE_STEP_COARSE,
        min_icon_size: int = CVConstants.MULTISCALE_TEMPLATE_MIN_ICON_SIZE,
        icon_mask: Optional[np.ndarray] = None
    ) -> FeatureMatchingResult:
        """Multi-scale template matching in grayscale with extended scale range.

        Args:
            screenshot_bytes: Screenshot image as bytes
            icon_bytes: Icon image as bytes
            threshold: High precision threshold for exact matches (default: 0.9)
            fallback_threshold: Fallback threshold to skip ORB/SIFT (default: 0.8)
            scale_range: Scale multipliers (default: 0.1x to 10x for extreme scale detection)
            scale_step_fine: Scale increment below 1.0x (default: 0.1 = 10% steps)
            scale_step_coarse: Scale increment above 1.0x (default: 0.5 = 50% steps)
            min_icon_size: Minimum scaled icon size in pixels (default: 10x10)

        Returns:
            FeatureMatchingResult with best match if >= fallback_threshold

        Behavior:
            - Tests all scales (early terminate if > 0.95)
            - Returns success if best_similarity >= fallback_threshold
            - Distinguishes "exact match" (>= threshold) vs "good match" (>= fallback_threshold)

        Performance:
            ~20ms per scale iteration
            Fine scales (0.1-1.0): 10 iterations = ~200ms
            Coarse scales (1.0-10.0): 19 iterations = ~380ms
            Total: ~560ms for 28 scales (vs ~100ms for 5 scales in legacy range)

        Note:
            Scales producing icons smaller than min_icon_size are automatically skipped.
            Use narrower scale_range (e.g., 0.8-1.2) for faster DPI-only detection.
        """
        log.info(f"Multi-scale template matching starting with threshold={threshold}, "
                f"fallback_threshold={fallback_threshold}, scale_range={scale_range}, "
                f"scale_step_fine={scale_step_fine}, scale_step_coarse={scale_step_coarse}, "
                f"min_icon_size={min_icon_size}")

        # Decode and convert to grayscale
        decoded = ImageDecoder.decode_images(screenshot_bytes, icon_bytes)
        if decoded is None:
            return FeatureMatchingResult([], [], "multiscale_template")

        screenshot_img, icon_img = decoded
        screenshot_gray = cv2.cvtColor(screenshot_img, cv2.COLOR_BGR2GRAY)
        icon_gray = cv2.cvtColor(icon_img, cv2.COLOR_BGR2GRAY)

        screenshot_h, screenshot_w = screenshot_gray.shape

        # Collect ALL matches above threshold
        all_matches = []  # List of {location, similarity, scale, size}

        # Generate non-uniform scale progression
        # Part 1: Fine steps for downscaling (0.1 to 1.0, step 0.1)
        scales_below_1 = np.round(np.arange(scale_range[0], 1.0, scale_step_fine), 2)

        # Part 2: Coarse steps for upscaling (1.0 to 10.0, step 0.5)
        scales_above_1 = np.round(np.arange(1.0, scale_range[1] + scale_step_coarse, scale_step_coarse), 2)

        # Combine and deduplicate (remove duplicate 1.0)
        all_scales = np.unique(np.concatenate([scales_below_1, scales_above_1]))

        log.info(f"Testing {len(all_scales)} scales (fine: {len(scales_below_1)}, "
                f"coarse: {len(scales_above_1)}, total unique: {len(all_scales)})")
        log.info(f"Scale range: {all_scales[0]:.2f}x to {all_scales[-1]:.2f}x")

        scales = all_scales

        for scale in scales:
            # Resize icon at current scale
            h, w = icon_gray.shape
            new_w = int(w * scale)
            new_h = int(h * scale)

            # Special case for 1.0x scale - always test original size
            if scale == 1.0:
                if new_w < min_icon_size or new_h < min_icon_size:
                    log.warning(f"Icon at 1.0x scale ({new_w}x{new_h}) is below minimum "
                               f"({min_icon_size}x{min_icon_size}), but testing anyway (original size)")
                # Skip size checks and proceed to template matching
            # Skip if scaled icon is too small (< min_icon_size x min_icon_size)
            elif new_w < min_icon_size or new_h < min_icon_size:
                log.info(f"Skipping scale {scale:.2f}x - icon would be {new_w}x{new_h} "
                        f"(below minimum {min_icon_size}x{min_icon_size})")
                continue

            # Skip if resized icon is larger than screenshot
            if new_h > screenshot_h or new_w > screenshot_w:
                log.info(f"Skipping scale {scale:.2f}x - icon would be {new_w}x{new_h}, "
                        f"screenshot is {screenshot_w}x{screenshot_h}")
                continue

            resized_icon = cv2.resize(icon_gray, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

            # Resize mask if present (proportional to icon scaling)
            resized_mask = None
            if icon_mask is not None:
                # INTER_NEAREST preserves binary nature of mask
                resized_mask = cv2.resize(icon_mask, (new_w, new_h), interpolation=cv2.INTER_NEAREST)

                # Threshold to ensure binary mask: 255 (opaque) or 0 (transparent)
                # Pixels with alpha > 128 = include in matching
                _, resized_mask = cv2.threshold(resized_mask, 128, 255, cv2.THRESH_BINARY)

                # Validate mask quality (prevents inf/nan from edge cases)
                # Check 1: Adaptive minimum opaque pixel count
                opaque_count = np.sum(resized_mask > 0)
                total_pixels = new_w * new_h

                # Adaptive threshold: max(absolute minimum, ratio-based minimum)
                min_opaque_pixels = max(
                    CVConstants.MULTISCALE_TEMPLATE_MIN_MASK_OPAQUE_PIXELS_ABSOLUTE,
                    int(CVConstants.MULTISCALE_TEMPLATE_MIN_MASK_OPAQUE_RATIO * total_pixels)
                )

                if opaque_count < min_opaque_pixels:
                    log.info(f"Skipping scale {scale:.2f}x ({new_w}x{new_h} pix.) - mask too sparse "
                            f"({opaque_count}/{total_pixels} opaque pixels, "
                            f"need >= {min_opaque_pixels} [{CVConstants.MULTISCALE_TEMPLATE_MIN_MASK_OPAQUE_RATIO*100:.0f}% ratio])")
                    continue

                # Check 2: Texture complexity in opaque region (prevent uniform/flat regions)
                opaque_region = resized_icon[resized_mask > 0]
                if len(opaque_region) > 0:
                    variance = np.var(opaque_region.astype(np.float32))
                    std_dev = np.sqrt(variance)

                    # Check if icon is too flat/uniform for reliable matching
                    # Flat icons typically have std_dev < 5-10
                    if std_dev < CVConstants.MULTISCALE_TEMPLATE_MIN_STD_DEV:
                        log.info(f"Skipping scale {scale:.2f}x ({new_w}x{new_h} pix.) - masked region too uniform "
                                f"(std_dev: {std_dev:.1f} < {CVConstants.MULTISCALE_TEMPLATE_MIN_STD_DEV}, "
                                f"opaque: {opaque_count}/{total_pixels} pixels)")
                        continue

                # Check 3: Prevent degenerate masks (ratio too low)
                opaque_ratio = opaque_count / total_pixels
                if opaque_ratio < CVConstants.MULTISCALE_TEMPLATE_MIN_MASK_OPAQUE_RATIO_DEGENERATE:
                    log.info(f"Skipping scale {scale:.2f}x ({new_w}x{new_h} pix.) - mask nearly empty "
                            f"({opaque_ratio*100:.1f}% opaque, need >= {CVConstants.MULTISCALE_TEMPLATE_MIN_MASK_OPAQUE_RATIO_DEGENERATE*100:.0f}%)")
                    continue

            # Template matching with optional mask
            result = cv2.matchTemplate(screenshot_gray, resized_icon, cv2.TM_CCOEFF_NORMED, mask=resized_mask)

            # Handle inf/nan in result matrix (can occur at specific positions where screenshot patches are uniform)
            # Filter out both inf and nan to find valid matches
            valid_mask = np.isfinite(result)
            valid_values = result[valid_mask]

            # Check if ALL positions are inf/nan (entire scale is invalid)
            if len(valid_values) == 0:
                inf_count = np.sum(np.isinf(result))
                nan_count = np.sum(np.isnan(result))
                total_positions = result.size

                log.warning(f"Skipping scale {scale:.2f}x ({new_w}x{new_h} pix.) - all positions invalid "
                           f"({inf_count} inf, {nan_count} nan out of {total_positions} positions)")
                continue

            # Log if partial inf/nan occurred (for debugging)
            invalid_count = result.size - len(valid_values)
            if invalid_count > 0:
                invalid_pct = (invalid_count / result.size) * 100
                log.info(f"Scale {scale:.2f}x ({new_w}x{new_h} pix.) had {invalid_count}/{result.size} invalid positions "
                        f"({invalid_pct:.1f}%, ignored)")

            # Find ALL locations where similarity >= fallback_threshold (among valid positions)
            # Create a filtered result with valid values only
            filtered_result = np.where(valid_mask, result, -np.inf)
            match_locations = np.where(filtered_result >= fallback_threshold)

            # Check for valid matches at this scale
            if len(match_locations[0]) > 0:
                for y_idx, x_idx in zip(match_locations[0], match_locations[1]):
                    similarity = result[y_idx, x_idx]

                    # Calculate center coordinates in original screenshot space
                    # (y_idx, x_idx) is top-left in result matrix
                    icon_h, icon_w = resized_icon.shape
                    center_x = int(x_idx + icon_w // 2)
                    center_y = int(y_idx + icon_h // 2)

                    all_matches.append({
                        'location': (center_x, center_y),
                        'similarity': float(similarity),
                        'scale': scale,
                        'size': (new_w, new_h)  # Size in screenshot coordinates
                    })

                    log.info(f"Multi-scale template match at scale {scale:.2f}x ({new_w}x{new_h} pix.): "
                            f"similarity {similarity:.3f} at ({center_x}, {center_y})")

            # Early termination only for EXACT matches (>0.95)
            best_in_scale = np.max(valid_values) if len(valid_values) > 0 else -1
            if best_in_scale > 0.95:
                log.info(f"Early termination at scale {scale:.2f}x - "
                        f"found exact match ({best_in_scale:.3f})")
                break

        # Log mask usage for debugging (counts refer to original icon, not scaled)
        if icon_mask is not None:
            original_transparent = np.sum(icon_mask == 0)
            original_total = icon_mask.size
            log.info(f"Multi-scale matching used mask "
                    f"(original icon: {original_transparent}/{original_total} transparent pixels)")

        if not all_matches:
            log.info(f"Stage 1 (multi-scale template) - no matches above fallback threshold "
                    f"{fallback_threshold}, continuing to ORB/SIFT")
            return FeatureMatchingResult([], [], "multiscale_template")

        # Apply NMS to remove overlapping duplicates
        locations = [m['location'] for m in all_matches]
        similarities = [m['similarity'] for m in all_matches]
        sizes = [m['size'] for m in all_matches]
        scales = [m['scale'] for m in all_matches]

        # Create lookup dict for scales/sizes by location
        match_metadata = {
            loc: {'scale': scale, 'size': size}
            for loc, scale, size in zip(locations, scales, sizes)
        }

        filtered_locations, filtered_similarities = non_maximum_suppression(
            locations, similarities, sizes, overlap_threshold=CVConstants.NMS_OVERLAP_THRESHOLD
        )

        if not filtered_locations:
            log.info("Stage 1 (multi-scale template) - all matches suppressed by NMS")
            return FeatureMatchingResult([], [], "multiscale_template")

        # Retrieve scales and sizes for filtered locations
        filtered_scales = [match_metadata[loc]['scale'] for loc in filtered_locations]
        filtered_sizes = [match_metadata[loc]['size'] for loc in filtered_locations]

        # Sort by similarity (descending) and return
        sorted_matches = sorted(
            zip(filtered_locations, filtered_similarities, filtered_scales, filtered_sizes),
            key=lambda x: x[1],
            reverse=True
        )

        final_locations = [m[0] for m in sorted_matches]
        final_similarities = [m[1] for m in sorted_matches]
        final_scales = [m[2] for m in sorted_matches]
        final_sizes = [m[3] for m in sorted_matches]

        # Determine success level
        best_similarity = final_similarities[0]
        if best_similarity >= threshold:
            log.info(f"Stage 1 (multi-scale template) found {len(final_locations)} matches "
                    f"(best: {best_similarity:.3f} >= threshold {threshold})")
        else:
            log.info(f"Stage 1 (multi-scale template) found {len(final_locations)} matches "
                    f"(best: {best_similarity:.3f} >= fallback {fallback_threshold})")

        return FeatureMatchingResult(
            final_locations, final_similarities, "multiscale_template",
            scales=final_scales, sizes=final_sizes
        )