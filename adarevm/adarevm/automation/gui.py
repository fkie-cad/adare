"""
GUI automation tools using pyautogui and platform-specific helpers.
"""

from io import BytesIO
import platform
import base64
import logging
import subprocess
from PIL import Image
from typing import Dict, List, Any, Optional

log = logging.getLogger(__name__)

# Global configuration for screenshot method

# Global configuration for screenshot method
_use_maim_screenshot = False


def _check_gui_enabled() -> Optional[Dict[str, str]]:
    """
    Check if GUI automation is enabled via ADARE_GUI_MODE environment variable.
    Returns error dict if disabled, None if enabled.
    """
    import os
    mode = os.environ.get('ADARE_GUI_MODE', 'agent').lower()
    if mode in ('host', 'disabled'):
        return {
            "status": "error",
            "message": f"GUI automation disabled (ADARE_GUI_MODE={mode})"
        }
    return None


def set_screenshot_method(use_maim: bool):
    """Set the screenshot method to use."""
    global _use_maim_screenshot
    _use_maim_screenshot = use_maim
    log.info(f"Screenshot method set to: {'maim' if use_maim else 'pyautogui'}")


def _take_screenshot_maim(x: int = None, y: int = None, width: int = None, height: int = None) -> bytes:
    """Take screenshot using maim command."""
    # Build maim command
    maim_cmd = ["maim", "-f", "png"]

    # Add region parameters if specified
    if x is not None and y is not None and width is not None and height is not None:
        log.info(f"Taking screenshot with maim: x={x}, y={y}, width={width}, height={height}")
        maim_cmd.extend(["-g", f"{width}x{height}+{x}+{y}"])
    else:
        log.info("Taking screenshot with maim")

    # Capture screenshot using maim
    png_bytes = subprocess.check_output(maim_cmd, stderr=subprocess.PIPE)

    # Load image and convert to RGBA
    img = Image.open(BytesIO(png_bytes)).convert("RGBA")

    # Convert back to bytes
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def _take_screenshot_pyautogui(x: int = None, y: int = None, width: int = None, height: int = None) -> bytes:
    """Take screenshot using pyautogui."""
    # Check if GUI is enabled before import
    error = _check_gui_enabled()
    if error:
        raise RuntimeError(error["message"])

    try:
        import pyautogui
    except ImportError:
        raise RuntimeError(
            "pyautogui is not available. This is required for agent-based GUI execution. "
            "Either install pyautogui or use host-based execution mode."
        )

    if x is not None and y is not None and width is not None and height is not None:
        log.info(f"Taking screenshot with pyautogui: x={x}, y={y}, width={width}, height={height}")
        img = pyautogui.screenshot(region=(x, y, width, height))
    else:
        log.info("Taking screenshot with pyautogui")
        img = pyautogui.screenshot()

    # Convert to RGBA and then to bytes
    img = img.convert("RGBA")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def take_screenshot(x: int = None, y: int = None, width: int = None, height: int = None) -> Dict[str, Any]:
    """
    Take a screenshot and return the image data and offset in JSON-safe format.
    Uses either maim or pyautogui based on configuration (defaults to pyautogui).
    """
    # Check if GUI is enabled first (but only if defaulting to pyautogui)
    # If using maim, we might still allow screenshot even in host mode? 
    # Current requirement says "prevent loading of pyautogui".
    # Assuming host mode means NO agent-side GUI automation.
    
    error = _check_gui_enabled()
    if error and not _use_maim_screenshot:
        return error

    try:
        if _use_maim_screenshot:
            img_bytes = _take_screenshot_maim(x, y, width, height)
        else:
            img_bytes = _take_screenshot_pyautogui(x, y, width, height)

    except subprocess.CalledProcessError as e:
        log.error(f"maim command failed: {e.stderr.decode() if e.stderr else str(e)}")
        # For screenshot, we return error dict rather than raising if possible, 
        # but existing code raised RuntimeError. 
        # Requirement was "return in the websocket an not implemented!".
        # So we catch and return dict.
        return {"status": "error", "message": f"Screenshot capture failed: {e.stderr.decode() if e.stderr else str(e)}"}
    except FileNotFoundError:
        log.error("maim command not found - please install maim")
        return {"status": "error", "message": "maim command not found - please install maim package"}
    except RuntimeError as e:
         return {"status": "error", "message": str(e)}
    except Exception as e:
        log.error(f"Screenshot processing failed: {str(e)}")
        return {"status": "error", "message": f"Screenshot processing failed: {str(e)}"}

    # Convert to base64
    img_base64 = base64.b64encode(img_bytes).decode("utf-8")

    # Return JSON-serializable dict with status/message fields (matching other GUI actions)
    return {
        "status": "success",
        "message": "Screenshot captured successfully",
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
    error = _check_gui_enabled()
    if error:
        # Return list containing error for list return type? 
        # Or just raise? The signature says List[Dict]. 
        # We can cheat and return a list with one error dict.
        return [error]

    screenshots = []
    if platform.system() == "Windows":
        # TODO: Implement Windows window screenshot
        log.warning("Window screenshot functionality is not implemented for Windows yet.")
        return [take_screenshot()] # Reuse logic which checks enabled
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
            return [{"status": "error", "message": "x11helper not available"}]
    else:
         return [{"status": "error", "message": "Screenshot for this platform is not implemented yet."}]
    return screenshots


def click(x: int, y: int) -> Dict[str, str]:
    """
    Simulate a mouse click at the specified coordinates.
    """
    error = _check_gui_enabled()
    if error:
        return error

    try:
        import pyautogui
    except ImportError:
        return {
            "status": "error",
            "message": "pyautogui is not available. This is required for agent-based GUI execution."
        }

    log.info(f"GUI click called with x={x}, y={y}")
    pyautogui.click(x, y)
    return {"status": "success", "message": f"Clicked at ({x}, {y})"}


def right_click(x: int, y: int) -> Dict[str, str]:
    """
    Simulate a right mouse click at the specified coordinates.
    """
    error = _check_gui_enabled()
    if error:
        return error

    try:
        import pyautogui
    except ImportError:
        return {
            "status": "error",
            "message": "pyautogui is not available. This is required for agent-based GUI execution."
        }

    log.info(f"GUI right_click called with x={x}, y={y}")
    pyautogui.rightClick(x, y)
    return {"status": "success", "message": f"Right clicked at ({x}, {y})"}


def double_click(x: int, y: int) -> Dict[str, str]:
    """
    Simulate a double mouse click at the specified coordinates.
    """
    error = _check_gui_enabled()
    if error:
        return error

    try:
        import pyautogui
    except ImportError:
        return {
            "status": "error",
            "message": "pyautogui is not available. This is required for agent-based GUI execution."
        }

    log.info(f"GUI double_click called with x={x}, y={y}")
    pyautogui.doubleClick(x, y)
    return {"status": "success", "message": f"Double clicked at ({x}, {y})"}


def drag(x1: int, y1: int, x2: int, y2: int) -> Dict[str, str]:
    """
    Simulate a mouse drag from (x1, y1) to (x2, y2).
    """
    error = _check_gui_enabled()
    if error:
        return error

    try:
        import pyautogui
    except ImportError:
        return {
            "status": "error",
            "message": "pyautogui is not available. This is required for agent-based GUI execution."
        }

    log.info(f"GUI drag called from ({x1}, {y1}) to ({x2}, {y2})")
    pyautogui.dragTo(x2, y2, duration=0.5)
    return {"status": "success", "message": f"Dragged from ({x1}, {y1}) to ({x2}, {y2})"}


def keyboard_action(action_type: str, key: str) -> Dict[str, str]:
    """
    Simulate a keyboard action.
    """
    error = _check_gui_enabled()
    if error:
        return error

    try:
        import pyautogui
    except ImportError:
        return {
            "status": "error",
            "message": "pyautogui is not available. This is required for agent-based GUI execution."
        }

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
    error = _check_gui_enabled()
    if error:
        return error

    try:
        import pyautogui
    except ImportError:
        return {
            "status": "error",
            "message": "pyautogui is not available. This is required for agent-based GUI execution."
        }

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
    error = _check_gui_enabled()
    if error:
        return error

    try:
        import pyautogui
    except ImportError:
        return {
            "status": "error",
            "message": "pyautogui is not available. This is required for agent-based GUI execution."
        }

    log.info(f"GUI move_mouse called with x={x}, y={y}")
    pyautogui.moveTo(x, y)
    return {"status": "success", "message": f"Moved to ({x}, {y})"}


def idle(duration: float) -> Dict[str, str]:
    """
    Simulate an idle action for the specified duration.
    Note: This should not be used in async contexts - use asyncio.sleep() instead.
    """
    # Idle is safe to run even if GUI is disabled as it's just sleep
    log.info(f"GUI idle called for {duration} seconds")
    import time
    time.sleep(duration)
    return {"status": "success", "message": f"Idle for {duration} seconds"}