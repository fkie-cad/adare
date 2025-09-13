"""Adare CV Server - Computer vision and OCR capabilities."""

from fastmcp import FastMCP
import base64
import click
import logging
from typing import Dict, Any

from .constants import DEFAULT_PORT, DEFAULT_HOST, MCP_PATH, DEFAULT_MAX_RESULTS
from .feature_matching import SIFTMatcher, ORBMatcher, TemplateMatcher
from .ocr_processing import TextDetector

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
            except Exception as orb_error:
                log.warning(f"ORB failed: {orb_error}, trying other methods...")

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
            except Exception as sift_error:
                log.warning(f"SIFT failed: {sift_error}, falling back to template matching")

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

    except Exception as e:
        log.error(f"Icon search failed: {e}")
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
    except Exception as e:
        log.error(f"Get all text failed: {e}")
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
    format: str = "json"
) -> Dict[str, Any]:
    """Find text locations in provided screenshot data."""
    try:
        screenshot_bytes = base64.b64decode(screenshot_base64)
        return await TextDetector.find_text(text, screenshot_bytes, offset_x, offset_y, format)
    except Exception as e:
        log.error(f"Text search failed: {e}")
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
def main(port: int, host: str, debug: bool) -> None:
    """Start the Adare CV server."""

    # Configure logging
    log_level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    log.info(f"Starting Adare CV server on {host}:{port}")

    try:
        # Run FastMCP server
        mcp.run(
            transport="streamable-http",
            host=host,
            port=port,
            path=MCP_PATH
        )
    except Exception as e:
        log.error(f"CV server failed to start: {e}")
        raise


if __name__ == "__main__":
    main()