"""
GUI tool methods for AdareVMServer.

Provides screenshot, click, keyboard, scroll, drag, and other GUI automation
actions. GUI imports are lazy-loaded inside each method to avoid loading
pyautogui/PIL at startup -- critical for Wayland VMs running in host-GUI mode.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

from adarelib.websocket.protocol import EventType

log = logging.getLogger(__name__)


class GUIToolsMixin:
    """Mixin providing GUI automation tool methods."""

    async def _screenshot(self, websocket, x: int = None, y: int = None, width: int = None, height: int = None):
        """Take a screenshot."""
        from adarevm.automation.gui import take_screenshot
        await self.send_event(websocket, EventType.LOG, {"message": "Taking screenshot"})
        return take_screenshot(x, y, width, height)

    async def _click(self, websocket, x: int, y: int):
        """Simulate a mouse click."""
        from adarevm.automation.gui import click
        await self.send_event(websocket, EventType.GUI_CLICK, {
            "action": "click", "x": x, "y": y
        })
        return click(x, y)

    async def _right_click(self, websocket, x: int, y: int):
        """Simulate a right mouse click."""
        from adarevm.automation.gui import right_click
        await self.send_event(websocket, EventType.GUI_CLICK, {
            "action": "right_click", "x": x, "y": y
        })
        return right_click(x, y)

    async def _double_click(self, websocket, x: int, y: int):
        """Simulate a double mouse click."""
        from adarevm.automation.gui import double_click
        await self.send_event(websocket, EventType.GUI_CLICK, {
            "action": "double_click", "x": x, "y": y
        })
        return double_click(x, y)

    async def _drag(self, websocket, x1: int, y1: int, x2: int, y2: int):
        """Simulate a mouse drag."""
        from adarevm.automation.gui import drag
        await self.send_event(websocket, EventType.GUI_DRAG, {
            "from": {"x": x1, "y": y1}, "to": {"x": x2, "y": y2}
        })
        return drag(x1, y1, x2, y2)

    async def _keyboard(self, websocket, type: str, key: str):
        """Simulate keyboard actions."""
        from adarevm.automation.gui import keyboard_action
        await self.send_event(websocket, EventType.GUI_KEYPRESS, {
            "type": type, "key": key
        })
        return keyboard_action(type, key)

    async def _scroll(self, websocket, direction: str, amount: int):
        """Simulate scroll action."""
        from adarevm.automation.gui import scroll
        log.info(f"Scrolling {direction} by {amount}")
        result = scroll(direction, amount)
        await self.send_event(websocket, EventType.LOG, {"message": f"Scrolled {direction} by {amount}"})
        return result

    async def _goto(self, websocket, x: int, y: int):
        """Move mouse to coordinates."""
        from adarevm.automation.gui import move_mouse
        log.info(f"Moving mouse to ({x}, {y})")
        result = move_mouse(x, y)
        await self.send_event(websocket, EventType.LOG, {"message": f"Mouse moved to ({x}, {y})"})
        return result

    async def _idle(self, websocket, duration: float):
        """Simulate idle time."""
        await self.send_event(websocket, EventType.GUI_IDLE, {"duration": duration})
        await asyncio.sleep(duration)
        return {"status": "success", "message": f"Idle for {duration} seconds"}

    async def _screenshot_window(self, websocket, window: str):
        """Take screenshot of specific window."""
        from adarevm.automation.gui import take_window_screenshots
        log.info(f"Taking screenshot of window: {window}")
        await self.send_event(websocket, EventType.LOG, {"message": f"Taking screenshot of window: {window}"})
        try:
            result = take_window_screenshots(window)
            await self.send_event(websocket, EventType.LOG, {"message": f"Window screenshot completed: {len(result) if isinstance(result, list) else 1} images"})
            return result
        except ImportError as e:
            log.error(f"Platform module not available: {e}")
            await self.send_event(websocket, EventType.ERROR, {"message": f"Platform not supported: {e}"})
            return {"status": "error", "message": f"Platform not supported: {e}"}
        except OSError as e:
            log.error(f"Screenshot operation failed: {e}")
            await self.send_event(websocket, EventType.ERROR, {"message": f"Screenshot failed: {e}"})
            return {"status": "error", "message": f"Screenshot failed: {e}"}
        except Exception as e:
            log.error(f"Unexpected screenshot error: {e}", exc_info=True)
            await self.send_event(websocket, EventType.ERROR, {"message": f"Window screenshot failed: {e}"})
            return {"status": "error", "message": str(e)}
