"""Adare CV Server - Computer vision and OCR capabilities."""

from fastmcp import FastMCP
import base64
import click
import logging
import cv2

from typing import Dict, Any, Optional, List, Union, Tuple
from .constants import DEFAULT_PORT, DEFAULT_HOST, MCP_PATH, DEFAULT_MAX_RESULTS, CVConstants
from .feature_matching import SIFTMatcher, ORBMatcher, TemplateMatcher, MultiScaleTemplateMatcher, CannyEdgeMatcher
from .image_processing import ImageDecoder, IconComplexityAnalyzer, DetectionMatch, non_maximum_suppression
from .ocr_processing import TextDetector
from .exceptions import FeatureMatchingError, ImageDecodingError, OCRProcessingError

log = logging.getLogger(__name__)

mcp = FastMCP(name="adare-cv-server")


# ========== Aggregation Helper Functions ==========

def _normalize_similarity(similarity: float, method: str) -> float:
    """Normalize similarity scores to 0.0-1.0 range.

    SIFT returns match count (unbounded), so we normalize it.
    Other methods already return 0.0-1.0 similarities.

    Args:
        similarity: Raw similarity score
        method: Detection method name

    Returns:
        Normalized similarity (0.0-1.0)
    """
    if method == 'sift':
        # SIFT returns match count - normalize to 0.0-1.0
        # 20+ matches = 1.0 confidence (exceptional match)
        return min(1.0, similarity / CVConstants.SIFT_NORMALIZATION_THRESHOLD)
    else:
        # Already normalized (template, canny_edge, multiscale_template, orb)
        return similarity


def _get_method_weight(method: str) -> float:
    """Get method weight for aggregation.

    Args:
        method: Detection method name

    Returns:
        Weight (0.0-1.0), defaults to 0.8 for unknown methods
    """
    return CVConstants.METHOD_WEIGHTS.get(method, 0.8)


def _estimate_match_size(scale: float, original_icon_size: Tuple[int, int]) -> Tuple[int, int]:
    """Estimate bounding box size for a match at a given scale.

    Args:
        scale: Detected scale (1.0 = original size)
        original_icon_size: Original icon dimensions (width, height)

    Returns:
        Estimated size (width, height) at detected scale
    """
    original_w, original_h = original_icon_size
    return (int(original_w * scale), int(original_h * scale))


def _aggregate_matches(
    all_matches: List[DetectionMatch],
    max_results: int,
    icon_size: Tuple[int, int]
) -> Dict[str, Any]:
    """Aggregate matches from multiple detection methods.

    Applies global NMS to remove cross-method duplicates, then groups
    matches by location and tracks contributing methods.

    Args:
        all_matches: All detection matches from all methods
        max_results: Maximum number of results to return
        icon_size: Original icon size (width, height)

    Returns:
        Dict with structure:
            - locations: List of final (x, y) centers
            - similarities: List of weighted similarities
            - methods: List of primary method names
            - contributing_methods: List of all methods per location
            - method_used: "aggregated" (or method name if single)
    """
    if not all_matches:
        return {
            'locations': [],
            'similarities': [],
            'methods': [],
            'contributing_methods': [],
            'method_used': 'no_matches'
        }

    log.info(f"Aggregating {len(all_matches)} matches from {len(set(m.method for m in all_matches))} methods")

    # Extract data for NMS
    locations = [m.location for m in all_matches]
    weighted_sims = [m.weighted_similarity for m in all_matches]
    sizes = [m.size if m.size != (0, 0) else _estimate_match_size(m.scale, icon_size) for m in all_matches]

    # Apply global NMS to remove cross-method duplicates
    filtered_locations, filtered_similarities = non_maximum_suppression(
        locations, weighted_sims, sizes, overlap_threshold=CVConstants.NMS_OVERLAP_THRESHOLD
    )

    if not filtered_locations:
        log.info("All matches suppressed by global NMS")
        return {
            'locations': [],
            'similarities': [],
            'methods': [],
            'contributing_methods': [],
            'method_used': 'all_suppressed'
        }

    log.info(f"After global NMS: {len(filtered_locations)} unique locations "
             f"(suppressed {len(all_matches) - len(filtered_locations)} duplicates)")

    # Build lookup: location → all matches at that location
    location_to_matches = {}
    for match in all_matches:
        # Check if this match's location survived NMS
        if match.location in filtered_locations:
            if match.location not in location_to_matches:
                location_to_matches[match.location] = []
            location_to_matches[match.location].append(match)

    # Build final results
    final_locations = []
    final_similarities = []
    final_methods = []
    final_contributing_methods = []

    for loc in filtered_locations:
        matches_at_loc = location_to_matches.get(loc, [])

        if not matches_at_loc:
            continue

        # Sort by weighted similarity (highest first)
        matches_at_loc.sort(key=lambda m: m.weighted_similarity, reverse=True)

        # Primary match = highest weighted similarity
        primary = matches_at_loc[0]

        # Contributing methods = all unique methods at this location
        contributing = list(set(m.method for m in matches_at_loc))

        final_locations.append(loc)
        final_similarities.append(primary.weighted_similarity)
        final_methods.append(primary.method)
        final_contributing_methods.append(contributing)

    # Sort by similarity (descending)
    sorted_results = sorted(
        zip(final_locations, final_similarities, final_methods, final_contributing_methods),
        key=lambda x: x[1],
        reverse=True
    )

    # Limit to max_results
    if max_results and len(sorted_results) > max_results:
        sorted_results = sorted_results[:max_results]

    # Unpack
    if sorted_results:
        final_locations, final_similarities, final_methods, final_contributing_methods = zip(*sorted_results)
        final_locations = list(final_locations)
        final_similarities = list(final_similarities)
        final_methods = list(final_methods)
        final_contributing_methods = list(final_contributing_methods)
    else:
        final_locations = []
        final_similarities = []
        final_methods = []
        final_contributing_methods = []

    # Determine method_used
    unique_methods = set(final_methods)
    if len(unique_methods) == 1:
        method_used = list(unique_methods)[0]
    else:
        method_used = "aggregated"

    # Log top 3 matches with contributing methods
    top_matches = min(3, len(final_locations))
    if top_matches > 0:
        log.info(f"Top {top_matches} matches:")
        for i in range(top_matches):
            methods_str = ', '.join(final_contributing_methods[i])
            log.info(f"  {i+1}. {final_locations[i]} - similarity: {final_similarities[i]:.3f}, "
                     f"primary: {final_methods[i]}, contributors: [{methods_str}]")

    return {
        'locations': final_locations,
        'similarities': final_similarities,
        'methods': final_methods,
        'contributing_methods': final_contributing_methods,
        'method_used': method_used
    }


@mcp.tool()
async def find_icon(
    icon_base64: str,
    screenshot_base64: str,
    offset_x: int = 0,
    offset_y: int = 0,
    threshold: float = CVConstants.DEFAULT_TEMPLATE_THRESHOLD,
    max_results: int = DEFAULT_MAX_RESULTS,
    use_sift: bool = True,
    sift_min_matches: int = 4,
    sift_ratio: float = 0.8,
    use_orb: bool = True,
    orb_min_matches: int = 2,
    orb_max_matches: int = 10,
    orb_distance_threshold: float = 80.0
) -> Dict[str, Any]:
    """Find icon locations in provided screenshot data using base64 encoded icon.

    Multi-Method Aggregated Detection Pipeline:
        Stage 0: Canny edge-based multi-scale template matching
                 → Lighting-invariant detection using structural outlines
        Stage 1: Multi-scale template matching (0.9 threshold, 0.1-10.0x scale)
                 → Pixel-exact matching across extreme scale range
        Stage 2: Laplacian variance gatekeeper
                 → Determines if icon is complex enough for ORB
        Stage 3: ORB feature matching (textured icons only)
                 → Handles scaled/rotated complex icons
        Stage 4: SIFT fallback
                 → Most robust for gradient/complex icons
        Stage 5: Template matching at 0.75 threshold (catch-all)
                 → Relaxed threshold for difficult cases

    All applicable methods run and results are aggregated using weighted confidences.
    Global NMS removes cross-method duplicates.
    """
    try:
        log.info(f"Starting aggregated detection pipeline (SIFT: {use_sift}, ORB: {use_orb}, "
                 f"aggregation: {CVConstants.ENABLE_AGGREGATION})")
        screenshot_bytes = base64.b64decode(screenshot_base64)
        icon_bytes = base64.b64decode(icon_base64)

        # Preprocess icon once (SVG→PNG conversion + trimming if needed)
        # This ensures all stages use the same preprocessed icon
        icon_bytes = ImageDecoder.preprocess_icon(icon_bytes)

        # Decode images with alpha channel preservation for masked matching
        screenshot_img, icon_img, icon_mask = ImageDecoder.decode_images_with_alpha(
            screenshot_bytes, icon_bytes
        )

        log.info(f"Decoded images - screenshot: {screenshot_img.shape}, "
                f"icon: {icon_img.shape}, mask: {icon_mask.shape if icon_mask is not None else 'None'}")

        # Get original icon size for scale estimation
        icon_h, icon_w = icon_img.shape[:2]
        icon_size = (icon_w, icon_h)

        # Collect all matches from all methods
        all_matches: List[DetectionMatch] = []

        # ========== Stage 0: Canny Edge-Based Multi-Scale Template Matching ==========
        try:
            log.info("Stage 0 - Canny edge-based multi-scale template matching")
            result = CannyEdgeMatcher.find_icon_locations(
                screenshot_bytes,
                icon_bytes,
                threshold=CVConstants.CANNY_EDGE_THRESHOLD,
                fallback_threshold=CVConstants.CANNY_EDGE_FALLBACK_THRESHOLD,
            )

            if result.success:
                log.info(f"Stage 0 (Canny edge) found {len(result.locations)} match(es), adding to pool")
                method_weight = _get_method_weight(result.method)

                for i, (loc, sim, scale, size) in enumerate(zip(
                    result.locations, result.similarities, result.scales, result.sizes
                )):
                    normalized_sim = _normalize_similarity(sim, result.method)
                    all_matches.append(DetectionMatch(
                        location=loc,
                        similarity=normalized_sim,
                        method=result.method,
                        scale=scale,
                        size=size,
                        weighted_similarity=normalized_sim * method_weight
                    ))
            else:
                log.info("Stage 0 (Canny edge) found no matches")

        except FeatureMatchingError as e:
            log.warning(f"Stage 0 (Canny edge) failed: {str(e)}")
        except Exception as e:
            log.warning(f"Stage 0 (Canny edge) unexpected error: {str(e)}")

        # ========== Stage 1: Multi-Scale Template Matching (Precision Gate) ==========
        try:
            log.info("Stage 1 - Multi-scale template matching (precision gate)")
            result = MultiScaleTemplateMatcher.find_icon_locations(
                screenshot_bytes, icon_bytes, icon_mask=icon_mask
            )

            if result.success:
                log.info(f"Stage 1 (multi-scale template) found {len(result.locations)} match(es), adding to pool")
                method_weight = _get_method_weight(result.method)

                for i, (loc, sim, scale, size) in enumerate(zip(
                    result.locations, result.similarities, result.scales, result.sizes
                )):
                    normalized_sim = _normalize_similarity(sim, result.method)
                    all_matches.append(DetectionMatch(
                        location=loc,
                        similarity=normalized_sim,
                        method=result.method,
                        scale=scale,
                        size=size,
                        weighted_similarity=normalized_sim * method_weight
                    ))
            else:
                log.info("Stage 1 (multi-scale template) found no matches")

        except (FeatureMatchingError, cv2.error, ValueError) as e:
            log.warning(f"Stage 1 error: {e}")
        except Exception as e:
            log.warning(f"Stage 1 unexpected error: {e}", exc_info=True)

        # ========== Stage 2: Laplacian Variance Gatekeeper ==========
        should_use_orb_method = False
        if use_orb:
            try:
                decoded = ImageDecoder.decode_images(screenshot_bytes, icon_bytes)
                if decoded is not None:
                    _, icon_img_gray_check = decoded
                    icon_gray = cv2.cvtColor(icon_img_gray_check, cv2.COLOR_BGR2GRAY)
                    should_use_orb_method = IconComplexityAnalyzer.should_use_orb(icon_gray)

                    if should_use_orb_method:
                        log.info("Stage 2 - Icon is textured, will run Stage 3 (ORB)")
                    else:
                        log.info("Stage 2 - Icon is flat, skipping Stage 3 (ORB)")
            except (ImageDecodingError, cv2.error, ValueError) as e:
                log.warning(f"Stage 2 complexity check failed: {e}, skipping ORB")
                should_use_orb_method = False
            except Exception as e:
                log.warning(f"Stage 2 unexpected error: {e}, skipping ORB", exc_info=True)
                should_use_orb_method = False

        # ========== Stage 3: ORB Feature Matching (Textured Icons Only) ==========
        if should_use_orb_method:
            try:
                log.info("Stage 3 - ORB feature matching (textured icon)")
                result = ORBMatcher.find_icon_locations(
                    screenshot_bytes, icon_bytes,
                    orb_min_matches, orb_max_matches, orb_distance_threshold
                )

                if result.success:
                    log.info(f"Stage 3 (ORB) found {len(result.locations)} match(es), adding to pool")
                    method_weight = _get_method_weight(result.method)

                    for i, (loc, sim, scale, size) in enumerate(zip(
                        result.locations, result.similarities, result.scales, result.sizes
                    )):
                        normalized_sim = _normalize_similarity(sim, result.method)
                        all_matches.append(DetectionMatch(
                            location=loc,
                            similarity=normalized_sim,
                            method=result.method,
                            scale=scale,
                            size=size if size != (0, 0) else _estimate_match_size(scale, icon_size),
                            weighted_similarity=normalized_sim * method_weight
                        ))
                else:
                    log.info("Stage 3 (ORB) found no matches")

            except (FeatureMatchingError, cv2.error, ValueError) as e:
                log.warning(f"Stage 3 ORB failed: {e}")
            except Exception as e:
                log.warning(f"Stage 3 ORB unexpected error: {e}", exc_info=True)

        # ========== Stage 4: SIFT Fallback ==========
        if use_sift:
            try:
                log.info("Stage 4 - SIFT fallback (gradient/complex icons)")
                result = SIFTMatcher.find_icon_locations(
                    screenshot_bytes, icon_bytes, sift_min_matches, sift_ratio
                )

                if result.success:
                    log.info(f"Stage 4 (SIFT) found {len(result.locations)} match(es), adding to pool")
                    method_weight = _get_method_weight(result.method)

                    for i, (loc, sim, scale, size) in enumerate(zip(
                        result.locations, result.similarities, result.scales, result.sizes
                    )):
                        normalized_sim = _normalize_similarity(sim, result.method)
                        all_matches.append(DetectionMatch(
                            location=loc,
                            similarity=normalized_sim,
                            method=result.method,
                            scale=scale,
                            size=size if size != (0, 0) else _estimate_match_size(scale, icon_size),
                            weighted_similarity=normalized_sim * method_weight
                        ))
                else:
                    log.info("Stage 4 (SIFT) found no matches")

            except (FeatureMatchingError, cv2.error, ValueError) as e:
                log.warning(f"Stage 4 SIFT failed: {e}")
            except Exception as e:
                log.warning(f"Stage 4 SIFT unexpected error: {e}", exc_info=True)

        # ========== Stage 5: Template Matching at 0.75 Threshold (Catch-All) ==========
        try:
            log.info("Stage 5 - Template matching at relaxed threshold (catch-all)")
            result = TemplateMatcher.find_icon_locations(screenshot_bytes, icon_bytes, threshold, icon_mask=icon_mask)

            if result.success:
                log.info(f"Stage 5 (template) found {len(result.locations)} match(es), adding to pool")
                method_weight = _get_method_weight(result.method)

                for i, (loc, sim, scale, size) in enumerate(zip(
                    result.locations, result.similarities, result.scales, result.sizes
                )):
                    normalized_sim = _normalize_similarity(sim, result.method)
                    all_matches.append(DetectionMatch(
                        location=loc,
                        similarity=normalized_sim,
                        method=result.method,
                        scale=scale,
                        size=size,
                        weighted_similarity=normalized_sim * method_weight
                    ))
            else:
                log.info("Stage 5 (template) found no matches")

        except (FeatureMatchingError, cv2.error, ValueError) as e:
            log.warning(f"Stage 5 template failed: {e}")
        except Exception as e:
            log.warning(f"Stage 5 template unexpected error: {e}", exc_info=True)

        # ========== Aggregate All Results ==========
        if all_matches:
            log.info(f"Aggregating {len(all_matches)} matches from {len(set(m.method for m in all_matches))} methods")
            aggregated = _aggregate_matches(all_matches, max_results, icon_size)

            # Apply offset to final locations
            if offset_x != 0 or offset_y != 0:
                aggregated['locations'] = [(x + offset_x, y + offset_y) for x, y in aggregated['locations']]

            log.info(f"Final result: {len(aggregated['locations'])} unique matches after aggregation")
            return aggregated
        else:
            log.info("No matches from any method")
            return {
                'locations': [],
                'similarities': [],
                'methods': [],
                'contributing_methods': [],
                'method_used': 'no_matches'
            }

    except (ImageDecodingError, base64.binascii.Error, ValueError) as e:
        log.error(f"Icon search input error: {e}")
        return {
            "error": f"Invalid input data: {str(e)}",
            "matches": []
        }
    except Exception as e:
        log.error(f"Icon search failed: {e}", exc_info=True)
        return {
            "error": f"Icon search failed: {str(e)}",
            "locations": [],
            "similarities": [],
            "method_used": "error"
        }


@mcp.tool()
async def get_all_text(
    screenshot_base64: str,
    offset_x: int = 0,
    offset_y: int = 0,
    format: str = "json"
) -> Dict[str, Any]:
    """Get all detected text from screenshot data. Format can be 'json' or 'csv'."""
    try:
        screenshot_bytes = base64.b64decode(screenshot_base64)
        return await TextDetector.get_all_text(screenshot_bytes, offset_x, offset_y, format)
    except (OCRProcessingError, ImageDecodingError, base64.binascii.Error, ValueError) as e:
        log.error(f"Text detection input error: {e}")
        return {
            "error": f"Invalid input data: {str(e)}",
            "matches": []
        }
    except Exception as e:
        log.error(f"Get all text failed: {e}", exc_info=True)
        return {
            "error": f"Get all text failed: {str(e)}",
            "all_text": []
        }


@mcp.tool()
async def find_text(
    text: str,
    screenshot_base64: str,
    offset_x: int = 0,
    offset_y: int = 0,
    format: str = "json",
    match_mode: str = "substring",
    regex_flags: Optional[List[str]] = None,
    allow_missing_chars: Optional[Union[bool, str, List[str]]] = None,
    max_missing: Optional[int] = None,
    min_similarity: Optional[float] = None,
    case_sensitive: bool = False
) -> Dict[str, Any]:
    """Find text locations in provided screenshot data with advanced matching.

    Args:
        text: Text or pattern to search for
        screenshot_base64: Base64 encoded screenshot
        offset_x: X offset to add to coordinates
        offset_y: Y offset to add to coordinates
        format: Output format ("json" or "csv")
        match_mode: Matching mode ("substring", "regex", "fuzzy", "regex_fuzzy")
        regex_flags: List of regex flag names (IGNORECASE, MULTILINE, DOTALL, VERBOSE)
        allow_missing_chars: Allowed missing characters (fuzzy mode):
            - True: Allow any character to be missing
            - ".": Only allow this specific character to be missing
            - [".", ","]: Only allow these characters to be missing
        max_missing: Max missing chars allowed (requires allow_missing_chars)
        min_similarity: Minimum similarity ratio 0.0-1.0
        case_sensitive: Enable case-sensitive matching

    Returns:
        Dictionary with locations and confidences
    """
    try:
        screenshot_bytes = base64.b64decode(screenshot_base64)
        return await TextDetector.find_text(
            text,
            screenshot_bytes,
            offset_x,
            offset_y,
            format,
            match_mode,
            regex_flags,
            allow_missing_chars,
            max_missing,
            min_similarity,
            case_sensitive
        )
    except (OCRProcessingError, ImageDecodingError, base64.binascii.Error, ValueError) as e:
        log.error(f"Text search input error: {e}")
        return {
            "error": f"Invalid input data: {str(e)}",
            "matches": []
        }
    except Exception as e:
        log.error(f"Text search failed: {e}", exc_info=True)
        return {
            "error": f"Text search failed: {str(e)}",
            "locations": []
        }


def create_server():
    """Create the FastMCP server instance."""
    return mcp


@click.command()
@click.option('--port', type=int, default=DEFAULT_PORT, help='Port to run the MCP server on.')
@click.option('--host', type=str, default=DEFAULT_HOST, help='Host to bind the server to.')
@click.option('--debug', is_flag=True, help='Enable debug logging.')
@click.option('--debug-output-dir', type=click.Path(file_okay=False, dir_okay=True), help='Directory for debug output images.')
def main(port: int, host: str, debug: bool, debug_output_dir: str = None) -> None:
    """Start the Adare CV server."""

    # Configure logging
    log_level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    log.info(f"Starting Adare CV server on {host}:{port}")

    if debug_output_dir:
        from pathlib import Path
        output_path = Path(debug_output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        log.info(f"Debug output enabled. Saving images to: {output_path}")
        TextDetector.set_debug_output_dir(output_path)
        CannyEdgeMatcher.set_debug_output_dir(output_path)

    try:
        # Run FastMCP server
        mcp.run(
            transport="streamable-http",
            host=host,
            port=port,
            path=MCP_PATH
        )
    except Exception as e:
        log.error(f"CV server failed to start: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()