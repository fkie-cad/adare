"""
Screenshot Service for Host-Side Tests.

This service provides screenshot capabilities via WebSocket to the VM,
abstracting away the WebSocket client details for host-side tests.
"""

import logging
from typing import Any

log = logging.getLogger(__name__)


class ScreenshotService:
    """
    Screenshot service using WebSocket communication with VM.

    This service wraps the WebSocket client's screenshot functionality
    and provides a clean interface for host-side tests to capture
    screen images from the VM.
    """

    def __init__(self, websocket_client):
        """
        Initialize screenshot service.

        Args:
            websocket_client: WebSocket client connected to adarevm
        """
        self.client = websocket_client

    async def take(self, window: str | None = None) -> dict[str, Any]:
        """
        Take screenshot from VM.

        Args:
            window: Optional window name/title to capture specific window.
                   If None, captures full screen.

        Returns:
            Screenshot dict with structure:
            {
                'image': {'data': base64_str, 'format': 'png'},
                'offset': {'x': int, 'y': int}
            }

        Raises:
            RuntimeError: If screenshot capture fails
            ValueError: If window is specified but not found
        """
        try:
            if window:
                log.debug(f"Screenshot Service: Capturing window '{window}'")
                screenshots = await self.client.take_window_screenshots(window)

                if not screenshots:
                    raise ValueError(f"Window not found: {window}")

                # Return first matching window screenshot
                screenshot = screenshots[0]
                log.debug(f"Screenshot Service: Captured window '{window}' at offset ({screenshot.get('offset', {}).get('x', 0)}, {screenshot.get('offset', {}).get('y', 0)})")
                return screenshot
            log.debug("Screenshot Service: Capturing full screen")
            screenshot = await self.client.take_screenshot()
            log.debug("Screenshot Service: Full screen captured")
            return screenshot

        except ValueError:
            # Re-raise ValueError as-is (window not found)
            raise
        except Exception as e:
            log.error(f"Screenshot Service: Capture failed: {e}", exc_info=True)
            raise RuntimeError(f"Screenshot capture failed: {e}") from e

    async def take_region(
        self,
        x: int,
        y: int,
        width: int,
        height: int
    ) -> dict[str, Any]:
        """
        Take screenshot of specific screen region.

        Args:
            x: X coordinate of top-left corner
            y: Y coordinate of top-left corner
            width: Width of region
            height: Height of region

        Returns:
            Screenshot dict with structure:
            {
                'image': {'data': base64_str, 'format': 'png'},
                'offset': {'x': int, 'y': int}
            }

        Raises:
            ValueError: If region coordinates are invalid
            RuntimeError: If screenshot capture fails
        """
        if width <= 0 or height <= 0:
            raise ValueError(f"Invalid region size: {width}x{height}")

        try:
            log.debug(f"Screenshot Service: Capturing region ({x}, {y}, {width}x{height})")

            # Use WebSocket client's screenshot with region parameters
            screenshot = await self.client.take_screenshot(
                x=x,
                y=y,
                width=width,
                height=height
            )

            log.debug(f"Screenshot Service: Region captured at offset ({screenshot.get('offset', {}).get('x', 0)}, {screenshot.get('offset', {}).get('y', 0)})")
            return screenshot

        except Exception as e:
            log.error(f"Screenshot Service: Region capture failed: {e}", exc_info=True)
            raise RuntimeError(f"Region screenshot capture failed: {e}") from e

    async def take_all_windows(self, window_pattern: str) -> list[dict[str, Any]]:
        """
        Take screenshots of all windows matching a pattern.

        Args:
            window_pattern: Window name/title pattern to match

        Returns:
            List of screenshot dicts, one per matching window

        Raises:
            RuntimeError: If screenshot capture fails
        """
        try:
            log.debug(f"Screenshot Service: Capturing all windows matching '{window_pattern}'")
            screenshots = await self.client.take_window_screenshots(window_pattern)

            if not screenshots:
                log.warning(f"Screenshot Service: No windows found matching '{window_pattern}'")
                return []

            log.debug(f"Screenshot Service: Captured {len(screenshots)} windows")
            return screenshots

        except Exception as e:
            log.error(f"Screenshot Service: Window capture failed: {e}", exc_info=True)
            raise RuntimeError(f"Window screenshot capture failed: {e}") from e
