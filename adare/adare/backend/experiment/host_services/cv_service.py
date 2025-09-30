"""
Computer Vision Service for Host-Side Tests.

This service provides a clean abstraction over the MCP CV server,
allowing host-side tests to perform visual analysis (text/icon detection)
without directly coupling to the MCP client implementation.
"""

import logging
import base64
from pathlib import Path
from typing import List, Dict, Any, Optional

log = logging.getLogger(__name__)


class CVService:
    """
    Computer Vision service using MCP CV server for visual analysis.

    This service wraps the MCP client's CV tools (find_text, find_icon, get_all_text)
    and provides a clean, testable interface for host-side tests.
    """

    def __init__(self, mcp_client):
        """
        Initialize CV service.

        Args:
            mcp_client: MCP client instance with CV server tools
        """
        self.mcp_client = mcp_client

    async def find_text(
        self,
        text: str,
        screenshot_data: Dict[str, Any],
        format: str = "json"
    ) -> List[Dict[str, Any]]:
        """
        Find text in screenshot.

        Args:
            text: Text to search for
            screenshot_data: Screenshot dict with 'image' and 'offset' keys
            format: Output format ('json' or 'csv')

        Returns:
            List of location dicts with coordinates

        Raises:
            ValueError: If screenshot data is invalid
            RuntimeError: If CV server call fails
        """
        if not screenshot_data or 'image' not in screenshot_data:
            raise ValueError("Invalid screenshot data: missing 'image' key")

        try:
            log.debug(f"CV Service: Searching for text '{text}'")

            result = await self.mcp_client.call_tool(
                "find_text",
                text=text,
                screenshot_base64=screenshot_data['image']['data'],
                offset_x=screenshot_data.get('offset', {}).get('x', 0),
                offset_y=screenshot_data.get('offset', {}).get('y', 0),
                format=format
            )

            locations = result.get('locations', [])
            log.debug(f"CV Service: Found {len(locations)} matches for text '{text}'")

            return locations

        except KeyError as e:
            raise ValueError(f"Screenshot data missing required field: {e}")
        except Exception as e:
            log.error(f"CV Service: find_text failed: {e}", exc_info=True)
            raise RuntimeError(f"CV server text search failed: {e}")

    async def find_icon(
        self,
        icon_path: Path,
        screenshot_data: Dict[str, Any],
        threshold: float = 0.5,
        max_results: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Find icon/image in screenshot.

        Args:
            icon_path: Path to icon image file
            screenshot_data: Screenshot dict with 'image' and 'offset' keys
            threshold: Matching threshold (0.0 to 1.0)
            max_results: Maximum number of results to return

        Returns:
            List of location dicts with coordinates

        Raises:
            FileNotFoundError: If icon file doesn't exist
            ValueError: If screenshot data is invalid
            RuntimeError: If CV server call fails
        """
        if not icon_path.exists():
            raise FileNotFoundError(f"Icon file not found: {icon_path}")

        if not screenshot_data or 'image' not in screenshot_data:
            raise ValueError("Invalid screenshot data: missing 'image' key")

        try:
            log.debug(f"CV Service: Searching for icon '{icon_path.name}'")

            # Load and encode icon image
            icon_bytes = icon_path.read_bytes()
            icon_base64 = base64.b64encode(icon_bytes).decode('utf-8')

            result = await self.mcp_client.call_tool(
                "find_icon",
                icon_base64=icon_base64,
                screenshot_base64=screenshot_data['image']['data'],
                offset_x=screenshot_data.get('offset', {}).get('x', 0),
                offset_y=screenshot_data.get('offset', {}).get('y', 0),
                threshold=threshold,
                max_results=max_results
            )

            locations = result.get('locations', [])
            log.debug(f"CV Service: Found {len(locations)} matches for icon '{icon_path.name}'")

            return locations

        except (OSError, IOError) as e:
            raise FileNotFoundError(f"Failed to read icon file {icon_path}: {e}")
        except KeyError as e:
            raise ValueError(f"Screenshot data missing required field: {e}")
        except Exception as e:
            log.error(f"CV Service: find_icon failed: {e}", exc_info=True)
            raise RuntimeError(f"CV server icon search failed: {e}")

    async def get_all_text(
        self,
        screenshot_data: Dict[str, Any],
        format: str = "json"
    ) -> List[Dict[str, Any]]:
        """
        Extract all text from screenshot using OCR.

        Args:
            screenshot_data: Screenshot dict with 'image' and 'offset' keys
            format: Output format ('json' or 'csv')

        Returns:
            List of text detection dicts with text and coordinates

        Raises:
            ValueError: If screenshot data is invalid
            RuntimeError: If CV server call fails
        """
        if not screenshot_data or 'image' not in screenshot_data:
            raise ValueError("Invalid screenshot data: missing 'image' key")

        try:
            log.debug("CV Service: Extracting all text from screenshot")

            result = await self.mcp_client.call_tool(
                "get_all_text",
                screenshot_base64=screenshot_data['image']['data'],
                offset_x=screenshot_data.get('offset', {}).get('x', 0),
                offset_y=screenshot_data.get('offset', {}).get('y', 0),
                format=format
            )

            all_text = result.get('all_text', [])
            log.debug(f"CV Service: Extracted {len(all_text)} text elements")

            return all_text

        except KeyError as e:
            raise ValueError(f"Screenshot data missing required field: {e}")
        except Exception as e:
            log.error(f"CV Service: get_all_text failed: {e}", exc_info=True)
            raise RuntimeError(f"CV server text extraction failed: {e}")