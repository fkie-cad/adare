"""Adare CV Server - Computer vision and OCR capabilities."""

from fastmcp import FastMCP
import base64
import click
import logging
import cv2

from typing import Dict, Any, Optional, List, Union
from .constants import DEFAULT_PORT, DEFAULT_HOST, MCP_PATH, DEFAULT_MAX_RESULTS
from .feature_matching import SIFTMatcher, ORBMatcher, TemplateMatcher
from .ocr_processing import TextDetector
from .exceptions import FeatureMatchingError, ImageDecodingError, OCRProcessingError

log = logging.getLogger(__name__)

mcp = FastMCP(name="adare-cv-server")


@mcp.tool()
async def find_icon(
    icon_base64: str,
    screenshot_base64: str,
    offset_x: int = 0,
    offset_y: int = 0,
    threshold: float = 0.5,
    max_results: int = DEFAULT_MAX_RESULTS,
    use_sift: bool = True,
    sift_min_matches: int = 4,
    sift_ratio: float = 0.8,
    use_orb: bool = True,
    orb_min_matches: int = 2,
    orb_max_matches: int = 10,
    orb_distance_threshold: float = 80.0
) -> Dict[str, Any]:
    """Find icon locations in provided screenshot data using base64 encoded icon."""
    try:
        log.info(f"Starting icon search with base64 icon data (SIFT: {use_sift}, ORB: {use_orb})")
        screenshot_bytes = base64.b64decode(screenshot_base64)
        icon_bytes = base64.b64decode(icon_base64)

        # Try ORB first if enabled (since it can find multiple matches)
        if use_orb:
            try:
                log.info(f"Trying ORB feature matching...")
                result = ORBMatcher.find_icon_locations(
                    screenshot_bytes, icon_bytes,
                    orb_min_matches, orb_max_matches, orb_distance_threshold
                )
                if result.success:
                    log.info(f"ORB found {len(result.locations)} matches")
                    result = result.apply_offset(offset_x, offset_y).limit_results(max_results)
                    return {
                        "locations": result.locations,
                        "similarities": result.similarities,
                        "method_used": result.method
                    }
                else:
                    log.info("ORB found no matches, trying other methods...")
            except (FeatureMatchingError, cv2.error, ValueError) as orb_error:
                log.warning(f"ORB failed: {orb_error}, trying other methods...")
            except Exception as orb_error:
                log.warning(f"Unexpected ORB error: {orb_error}, trying other methods...", exc_info=True)

        # Try SIFT if ORB didn't find anything and SIFT is enabled
        if use_sift:
            try:
                log.info(f"Trying SIFT feature matching...")
                result = SIFTMatcher.find_icon_locations(
                    screenshot_bytes, icon_bytes, sift_min_matches, sift_ratio
                )
                if result.success:
                    log.info(f"SIFT found {len(result.locations)} matches")
                    result = result.apply_offset(offset_x, offset_y).limit_results(max_results)
                    return {
                        "locations": result.locations,
                        "similarities": result.similarities,
                        "method_used": result.method
                    }
                else:
                    log.info("SIFT found no matches, falling back to template matching")
            except (FeatureMatchingError, cv2.error, ValueError) as sift_error:
                log.warning(f"SIFT failed: {sift_error}, falling back to template matching")
            except Exception as sift_error:
                log.warning(f"Unexpected SIFT error: {sift_error}, falling back to template matching", exc_info=True)

        # Fall back to template matching
        log.info("Using template matching...")
        result = TemplateMatcher.find_icon_locations(screenshot_bytes, icon_bytes, threshold)
        result = result.apply_offset(offset_x, offset_y).limit_results(max_results)

        log.info(f"Found {len(result.locations)} total icon matches using {result.method}")
        return {
            "locations": result.locations,
            "similarities": result.similarities,
            "method_used": result.method
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