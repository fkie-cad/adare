"""
Agent-based GUI executor using WebSocket communication with adarevm.

This executor delegates GUI actions to the adarevm agent running in the VM.
"""

import logging
from typing import Dict, Any, Optional

from .gui_executor_interface import AbstractGUIExecutor

log = logging.getLogger(__name__)


class AgentGUIExecutor(AbstractGUIExecutor):
    """GUI executor using WebSocket communication to adarevm agent (pyautogui)."""

    def __init__(self, websocket_client, **kwargs):
        """
        Initialize agent-based GUI executor.

        Args:
            websocket_client: Connected WebSocket client to adarevm
            **kwargs: Additional parameters (ignored, for compatibility)
        """
        self.client = websocket_client
        log.debug("Initialized AgentGUIExecutor (WebSocket-based)")

    async def screenshot(self, region: Optional[dict] = None) -> Dict[str, Any]:
        """
        Capture screenshot via WebSocket.

        Args:
            region: Optional dict with x, y, width, height

        Returns:
            Dict with 'status', 'image' (base64 PNG), optional 'message'
        """
        try:
            if region:
                result = await self.client.screenshot(
                    region.get('x'), region.get('y'),
                    region.get('width'), region.get('height')
                )
            else:
                result = await self.client.screenshot()
            return result
        except Exception as e:
            log.error(f"Agent screenshot failed: {e}", exc_info=True)
            return {'status': 'error', 'message': str(e)}

    async def click(self, x: int, y: int, button_type: str = 'left') -> Dict[str, Any]:
        """
        Execute mouse click via WebSocket.

        Args:
            x: X coordinate
            y: Y coordinate
            button_type: 'left', 'right', or 'double'

        Returns:
            Dict with 'status', optional 'message'
        """
        try:
            if button_type == 'right':
                result = await self.client.right_click(x, y)
            elif button_type == 'double':
                result = await self.client.double_click(x, y)
            else:  # 'left' or default
                result = await self.client.click(x, y)
            return result
        except Exception as e:
            log.error(f"Agent click failed: {e}", exc_info=True)
            return {'status': 'error', 'message': str(e)}

    async def drag(self, x1: int, y1: int, x2: int, y2: int) -> Dict[str, Any]:
        """
        Execute drag operation via WebSocket.

        Args:
            x1: Start X coordinate
            y1: Start Y coordinate
            x2: End X coordinate
            y2: End Y coordinate

        Returns:
            Dict with 'status', optional 'message'
        """
        try:
            result = await self.client.drag(x1, y1, x2, y2)
            return result
        except Exception as e:
            log.error(f"Agent drag failed: {e}", exc_info=True)
            return {'status': 'error', 'message': str(e)}

    async def keyboard(self, action_type: str, value: str) -> Dict[str, Any]:
        """
        Execute keyboard action via WebSocket.

        Args:
            action_type: 'press', 'type', or 'hotkey'
            value: Key name, text to type, or key combination (e.g., "ctrl+c")

        Returns:
            Dict with 'status', optional 'message'
        """
        try:
            result = await self.client.keyboard(action_type, value)
            return result
        except Exception as e:
            log.error(f"Agent keyboard failed: {e}", exc_info=True)
            return {'status': 'error', 'message': str(e)}

    async def scroll(self, direction: str, amount: int) -> Dict[str, Any]:
        """
        Execute scroll action via WebSocket.

        Args:
            direction: 'up', 'down', 'left', or 'right'
            amount: Scroll amount

        Returns:
            Dict with 'status', optional 'message'
        """
        try:
            result = await self.client.scroll(direction, amount)
            return result
        except Exception as e:
            log.error(f"Agent scroll failed: {e}", exc_info=True)
            return {'status': 'error', 'message': str(e)}
