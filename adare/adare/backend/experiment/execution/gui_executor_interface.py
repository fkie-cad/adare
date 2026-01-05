"""
Abstract interface for GUI automation execution.

Defines the contract for GUI executors (agent-based and host-based).
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import logging

log = logging.getLogger(__name__)


class AbstractGUIExecutor(ABC):
    """Abstract interface for GUI automation execution."""

    @abstractmethod
    async def screenshot(self, region: Optional[dict] = None) -> Dict[str, Any]:
        """
        Capture screenshot.

        Args:
            region: Optional region dict with keys: x, y, width, height

        Returns:
            Dict with 'status', 'screenshot' (base64 PNG), optional 'message'
        """
        pass

    @abstractmethod
    async def click(self, x: int, y: int, button_type: str = 'left') -> Dict[str, Any]:
        """
        Execute mouse click.

        Args:
            x: X coordinate
            y: Y coordinate
            button_type: 'left', 'right', or 'middle'

        Returns:
            Dict with 'status', optional 'message'
        """
        pass

    @abstractmethod
    async def drag(self, x1: int, y1: int, x2: int, y2: int) -> Dict[str, Any]:
        """
        Execute drag operation.

        Args:
            x1: Start X coordinate
            y1: Start Y coordinate
            x2: End X coordinate
            y2: End Y coordinate

        Returns:
            Dict with 'status', optional 'message'
        """
        pass

    @abstractmethod
    async def keyboard(self, action_type: str, value: str) -> Dict[str, Any]:
        """
        Execute keyboard action.

        Args:
            action_type: 'key', 'type', or 'combination'
            value: Key name, text to type, or key combination

        Returns:
            Dict with 'status', optional 'message'
        """
        pass

    @abstractmethod
    async def scroll(self, direction: str, amount: int) -> Dict[str, Any]:
        """
        Execute scroll action.

        Args:
            direction: 'up', 'down', 'left', or 'right'
            amount: Scroll amount (positive integer)

        Returns:
            Dict with 'status', optional 'message'
        """
        pass
