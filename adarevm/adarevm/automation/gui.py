"""
GUI automation tools using pyautogui and platform-specific helpers.
"""

import pyautogui
from io import BytesIO
import platform
import base64
import logging
import subprocess
from PIL import Image
from typing import Dict, List, Any, Optional

log = logging.getLogger(__name__)


def take_screenshot(x: int = None, y: int = None, width: int = None, height: int = None) -> Dict[str, Any]:
    """
    Take a screenshot and return the image data and offset in JSON-safe format.
    Uses maim for screenshot capture instead of pyautogui for better reliability.
    """
    try:
        # Build maim command
        maim_cmd = ["maim", "-f", "png"]

        # Add region parameters if specified
        if x is not None and y is not None and width is not None and height is not None:
            log.info(f"Taking screenshot with x={x}, y={y}, width={width}, height={height}")
            maim_cmd.extend(["-g", f"{width}x{height}+{x}+{y}"])
        else:
            log.info("Taking screenshot")

        # Capture screenshot using maim
        png_bytes = subprocess.check_output(maim_cmd, stderr=subprocess.PIPE)

        # Load image and convert to RGBA
        img = Image.open(BytesIO(png_bytes)).convert("RGBA")

        # Convert back to bytes
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        img_bytes = buffer.getvalue()

    except subprocess.CalledProcessError as e:
        log.error(f"maim command failed: {e.stderr.decode() if e.stderr else str(e)}")
        raise RuntimeError(f"Screenshot capture failed: {e.stderr.decode() if e.stderr else str(e)}")
    except FileNotFoundError:
        log.error("maim command not found - please install maim")
        raise RuntimeError("maim command not found - please install maim package")
    except Exception as e:
        log.error(f"Screenshot processing failed: {str(e)}")
        raise RuntimeError(f"Screenshot processing failed: {str(e)}")

    # Convert to base64
    img_base64 = base64.b64encode(img_bytes).decode("utf-8")

    # Return JSON-serializable dict
    return {
        "image": {
            "data": img_base64,
            "format": "png"
        },
        "offset": {
            "x": x if x is not None else 0,
            "y": y if y is not None else 0
        }
    }


def take_window_screenshots(window: str) -> List[Dict[str, Any]]:
    """
    Take screenshots of windows matching the search string.
    """
    screenshots = []
    if platform.system() == "Windows":
        # TODO: Implement Windows window screenshot
        log.warning("Window screenshot functionality is not implemented for Windows yet.")
        return take_screenshot()
    elif platform.system() == "Linux":
        try:
            from adarevm.platforms.linux import get_windows_by_search_string
            windows = get_windows_by_search_string(window)
            if not windows:
                return []
            for i, win in enumerate(windows):
                log.debug(f"Taking screenshot of window {i}: {win.name} at {win.rect}")
                x, y, width, height = win.rect
                screenshot = take_screenshot(x=x, y=y, width=width, height=height)
                screenshots.append(screenshot)
        except ImportError:
            log.error("x11helper not available on this system")
    else:
        raise NotImplementedError("Screenshot for this platform is not implemented yet.")
    return screenshots


def click(x: int, y: int) -> Dict[str, str]:
    """
    Simulate a mouse click at the specified coordinates.
    """
    log.info(f"GUI click called with x={x}, y={y}")
    pyautogui.click(x, y)
    return {"status": "success", "message": f"Clicked at ({x}, {y})"}


def right_click(x: int, y: int) -> Dict[str, str]:
    """
    Simulate a right mouse click at the specified coordinates.
    """
    log.info(f"GUI right_click called with x={x}, y={y}")
    pyautogui.rightClick(x, y)
    return {"status": "success", "message": f"Right clicked at ({x}, {y})"}


def double_click(x: int, y: int) -> Dict[str, str]:
    """
    Simulate a double mouse click at the specified coordinates.
    """
    log.info(f"GUI double_click called with x={x}, y={y}")
    pyautogui.doubleClick(x, y)
    return {"status": "success", "message": f"Double clicked at ({x}, {y})"}


def drag(x1: int, y1: int, x2: int, y2: int) -> Dict[str, str]:
    """
    Simulate a mouse drag from (x1, y1) to (x2, y2).
    """
    log.info(f"GUI drag called from ({x1}, {y1}) to ({x2}, {y2})")
    pyautogui.dragTo(x2, y2, duration=0.5)
    return {"status": "success", "message": f"Dragged from ({x1}, {y1}) to ({x2}, {y2})"}


def keyboard_action(action_type: str, key: str) -> Dict[str, str]:
    """
    Simulate a keyboard action.
    """
    if action_type == "press":
        log.info(f"GUI keyboard press called with key={key}")
        pyautogui.press(key)
    elif action_type == "type":
        log.info(f"GUI keyboard type called with key={key}")
        pyautogui.typewrite(key)
    elif action_type == "hotkey":
        log.info(f"GUI keyboard hotkey called with key={key}")
        pyautogui.hotkey(*key.split("+"))
    return {"status": "success", "message": f"Keyboard action {action_type} on {key}"}


def scroll(direction: str, amount: int) -> Dict[str, str]:
    """
    Simulate a scroll action.
    """
    if direction == "up":
        log.info(f"GUI scroll up called with amount={amount}")
        pyautogui.scroll(amount)
    elif direction == "down":
        log.info(f"GUI scroll down called with amount={amount}")
        pyautogui.scroll(-amount)
    return {"status": "success", "message": f"Scrolled {direction} by {amount}"}


def move_mouse(x: int, y: int) -> Dict[str, str]:
    """
    Move the mouse to the specified coordinates.
    """
    log.info(f"GUI move_mouse called with x={x}, y={y}")
    pyautogui.moveTo(x, y)
    return {"status": "success", "message": f"Moved to ({x}, {y})"}


def idle(duration: float) -> Dict[str, str]:
    """
    Simulate an idle action for the specified duration.
    Note: This should not be used in async contexts - use asyncio.sleep() instead.
    """
    log.info(f"GUI idle called for {duration} seconds")
    import time
    time.sleep(duration)
    return {"status": "success", "message": f"Idle for {duration} seconds"}