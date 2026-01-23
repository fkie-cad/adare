"""
QEMU host-based GUI executor using QMP (QEMU Machine Protocol) commands.

This executor performs GUI actions directly on the host using QMP, eliminating
the need for X11 configuration in the guest VM.
"""

import asyncio
import base64
import logging
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional
from PIL import Image
import io

from .gui_executor_interface import AbstractGUIExecutor

log = logging.getLogger(__name__)


# Key mapping table: pyautogui key names → QMP qcodes
# Based on QEMU's qapi/ui.json key definitions
PYAUTOGUI_TO_QCODE = {
    # Letters (lowercase)
    'a': 'a', 'b': 'b', 'c': 'c', 'd': 'd', 'e': 'e', 'f': 'f', 'g': 'g',
    'h': 'h', 'i': 'i', 'j': 'j', 'k': 'k', 'l': 'l', 'm': 'm', 'n': 'n',
    'o': 'o', 'p': 'p', 'q': 'q', 'r': 'r', 's': 's', 't': 't', 'u': 'u',
    'v': 'v', 'w': 'w', 'x': 'x', 'y': 'y', 'z': 'z',

    # Numbers
    '0': '0', '1': '1', '2': '2', '3': '3', '4': '4',
    '5': '5', '6': '6', '7': '7', '8': '8', '9': '9',

    # Special keys
    'enter': 'ret',
    'return': 'ret',
    'esc': 'esc',
    'escape': 'esc',
    'backspace': 'backspace',
    'tab': 'tab',
    'space': 'spc',
    ' ': 'spc',

    # Modifiers
    'ctrl': 'ctrl',
    'control': 'ctrl',
    'alt': 'alt',
    'shift': 'shift',
    'super': 'meta_l',
    'win': 'meta_l',
    'meta': 'meta_l',

    # Function keys
    'f1': 'f1', 'f2': 'f2', 'f3': 'f3', 'f4': 'f4',
    'f5': 'f5', 'f6': 'f6', 'f7': 'f7', 'f8': 'f8',
    'f9': 'f9', 'f10': 'f10', 'f11': 'f11', 'f12': 'f12',

    # Arrow keys
    'up': 'up',
    'down': 'down',
    'left': 'left',
    'right': 'right',

    # Other common keys
    'home': 'home',
    'end': 'end',
    'pageup': 'pgup',
    'pagedown': 'pgdn',
    'delete': 'delete',
    'del': 'delete',
    'insert': 'insert',
    'capslock': 'caps_lock',

    # Punctuation/symbols
    '-': 'minus',
    '=': 'equal',
    '[': 'bracket_left',
    ']': 'bracket_right',
    ';': 'semicolon',
    "'": 'apostrophe',
    '`': 'grave_accent',
    '\\': 'backslash',
    ',': 'comma',
    '.': 'dot',
    '/': 'slash',
}


class QEMUHostGUIExecutor(AbstractGUIExecutor):
    """GUI executor using QMP commands for QEMU VMs (host-based)."""

    def __init__(self, vm, target_resolution_executor=None, experiment_run_id=None,
                 playbook=None, execution_context=None, experiment_run_directory=None, **kwargs):
        """
        Initialize QEMU host-based GUI executor.

        Args:
            vm: QEMUVM instance
            target_resolution_executor: Target resolution executor (to access debug settings)
            experiment_run_id: Experiment run ID for event emission
            playbook: Playbook reference
            execution_context: Execution context
            experiment_run_directory: Run directory for artifacts
            **kwargs: Additional parameters (for compatibility)
        """
        self.vm = vm

        # Extract debug screenshot settings from target_resolution_executor
        self.debug_screenshots = False
        self.screenshots_dir = None
        self.screenshot_counter = 0

        if target_resolution_executor:
            self.debug_screenshots = target_resolution_executor.debug_screenshots
            self.screenshots_dir = target_resolution_executor.screenshots_dir

        # Temp directory for PPM→PNG conversion (always needed for QMP)
        self._temp_screenshot_dir = Path(tempfile.gettempdir()) / "adare_qmp_screenshots"
        self._temp_screenshot_dir.mkdir(parents=True, exist_ok=True)

        log.debug(f"Initialized QEMUHostGUIExecutor (QMP-based, debug_screenshots={self.debug_screenshots})")

    async def screenshot(self, region: Optional[dict] = None) -> Dict[str, Any]:
        """
        Capture screenshot via QMP screendump.

        Args:
            region: Optional dict with x, y, width, height (cropping)

        Returns:
            Dict with 'status', 'image' (base64 PNG), optional 'message'
        """
        try:
            log.info("Capturing screenshot via QMP...")

            # Generate temp file path for PPM screenshot
            import time
            temp_ppm = self._temp_screenshot_dir / f"screenshot_{int(time.time() * 1000)}.ppm"

            # Capture screenshot via QMP
            success = await self.vm.send_qmp_screenshot(str(temp_ppm))

            if not success:
                return {'status': 'error', 'message': 'QMP screendump failed'}

            # Wait briefly for file to be written
            await asyncio.sleep(0.1)

            # Check file exists
            if not temp_ppm.exists():
                return {'status': 'error', 'message': f'Screenshot file not created: {temp_ppm}'}

            # Convert PPM to PNG and encode as base64
            png_base64 = await self._convert_ppm_to_png_base64(temp_ppm, region)

            # Save debug screenshot if enabled
            screenshot_path = await self._save_debug_screenshot(png_base64)

            # Cleanup temp file
            try:
                temp_ppm.unlink()
            except Exception as e:
                log.warning(f"Failed to cleanup temp screenshot: {e}")

            log.info("Screenshot captured successfully")

            return {
                'status': 'success',
                'image': {
                    'data': png_base64,
                    'format': 'png'
                },
                'message': 'Screenshot captured via QMP',
                'screenshot_path': screenshot_path
            }

        except Exception as e:
            log.error(f"QMP screenshot failed: {e}", exc_info=True)
            return {'status': 'error', 'message': str(e)}

    async def click(self, x: int, y: int, button_type: str = 'left') -> Dict[str, Any]:
        """
        Execute mouse click via QMP input-send-event.

        Args:
            x: X coordinate
            y: Y coordinate
            button_type: 'left', 'right', 'double', or 'middle'

        Returns:
            Dict with 'status', optional 'message'
        """
        try:
            log.info(f"Executing {button_type} click at ({x}, {y}) via QMP...")

            success = await self.vm.send_qmp_mouse_click(x, y, button_type)

            if not success:
                return {'status': 'error', 'message': 'QMP mouse click failed'}

            # Handle double click
            if button_type == 'double':
                # Second click for double-click
                await asyncio.sleep(0.05)  # Small delay between clicks
                await self.vm.send_qmp_mouse_click(x, y, 'left')

            log.info(f"Click executed successfully at ({x}, {y})")

            return {
                'status': 'success',
                'message': f'{button_type} click at ({x}, {y}) via QMP'
            }

        except Exception as e:
            log.error(f"QMP click failed: {e}", exc_info=True)
            return {'status': 'error', 'message': str(e)}

    async def drag(self, x1: int, y1: int, x2: int, y2: int) -> Dict[str, Any]:
        """
        Execute drag operation via QMP input-send-event.

        Args:
            x1: Start X coordinate
            y1: Start Y coordinate
            x2: End X coordinate
            y2: End Y coordinate

        Returns:
            Dict with 'status', optional 'message'
        """
        try:
            success = await self.vm.send_qmp_mouse_drag(x1, y1, x2, y2)

            if not success:
                return {'status': 'error', 'message': 'QMP drag failed'}

            return {
                'status': 'success',
                'message': f'Drag from ({x1}, {y1}) to ({x2}, {y2}) via QMP'
            }

        except Exception as e:
            log.error(f"QMP drag failed: {e}", exc_info=True)
            return {'status': 'error', 'message': str(e)}

    async def keyboard(self, action_type: str, value: str) -> Dict[str, Any]:
        """
        Execute keyboard action via QMP input-send-event.

        Args:
            action_type: 'press', 'type', or 'hotkey'
            value: Key name, text to type, or key combination (e.g., "ctrl+c")

        Returns:
            Dict with 'status', optional 'message'
        """
        try:
            if action_type == "press":
                # Single key press
                events = self._create_key_events(value)
            elif action_type == "type":
                # Type text (character by character)
                events = self._create_type_events(value)
            elif action_type == "hotkey":
                # Key combination (e.g., "ctrl+c")
                events = self._create_hotkey_events(value)
            else:
                return {'status': 'error', 'message': f'Unknown action type: {action_type}'}

            if not events:
                return {'status': 'error', 'message': f'Failed to create QMP events for: {value}'}

            success = await self.vm.send_qmp_keyboard(events)

            if not success:
                return {'status': 'error', 'message': 'QMP keyboard command failed'}

            return {
                'status': 'success',
                'message': f'Keyboard {action_type}({value}) via QMP'
            }

        except Exception as e:
            log.error(f"QMP keyboard failed: {e}", exc_info=True)
            return {'status': 'error', 'message': str(e)}

    async def scroll(self, direction: str, amount: int) -> Dict[str, Any]:
        """
        Execute scroll action via QMP input-send-event.

        Args:
            direction: 'up', 'down', 'left', or 'right'
            amount: Scroll amount

        Returns:
            Dict with 'status', optional 'message'
        """
        try:
            # Convert direction to wheel value
            # Positive = scroll up, Negative = scroll down
            if direction == 'up':
                wheel_value = amount
            elif direction == 'down':
                wheel_value = -amount
            else:
                # QMP wheel only supports vertical scrolling
                return {'status': 'error', 'message': f'Horizontal scrolling not supported via QMP'}

            success = await self.vm.send_qmp_scroll(wheel_value)

            if not success:
                return {'status': 'error', 'message': 'QMP scroll failed'}

            return {
                'status': 'success',
                'message': f'Scroll {direction} ({amount}) via QMP'
            }

        except Exception as e:
            log.error(f"QMP scroll failed: {e}", exc_info=True)
            return {'status': 'error', 'message': str(e)}

    # Helper methods

    async def _save_debug_screenshot(self, screenshot_base64: str) -> Optional[str]:
        """
        Save screenshot to disk for debugging purposes.

        Args:
            screenshot_base64: Base64 encoded screenshot data

        Returns:
            Relative path to saved screenshot file, or None if not saved
        """
        if not self.debug_screenshots or not self.screenshots_dir:
            return None

        try:
            # Create screenshots directory if it doesn't exist
            self.screenshots_dir.mkdir(parents=True, exist_ok=True)

            # Generate filename with counter (format: action_000.png, action_001.png, etc.)
            filename = f"action_{self.screenshot_counter:03d}.png"
            filepath = self.screenshots_dir / filename

            # Increment counter for next screenshot
            self.screenshot_counter += 1

            # Decode and save the image
            image_data = base64.b64decode(screenshot_base64)
            with open(filepath, 'wb') as f:
                f.write(image_data)

            log.debug(f"Debug screenshot saved: {filepath}")

            # Return relative path (relative to run directory)
            relative_path = f"reporting/screenshots/{filename}"
            return relative_path

        except Exception as e:
            log.error(f"Failed to save debug screenshot: {e}")
            return None

    async def _convert_ppm_to_png_base64(self, ppm_path: Path, region: Optional[dict] = None) -> str:
        """
        Convert PPM screenshot to PNG and encode as base64.

        Also updates VM's cached screen resolution for coordinate normalization.

        Args:
            ppm_path: Path to PPM file
            region: Optional dict for cropping (x, y, width, height)

        Returns:
            Base64-encoded PNG string
        """
        # Run in thread pool to avoid blocking
        def _convert():
            try:
                # Open PPM image
                img = Image.open(ppm_path)

                # Update VM's cached resolution for coordinate normalization
                # This must be done BEFORE cropping to get full screen dimensions
                self.vm.update_screen_resolution(img.width, img.height)

                # Crop if region specified
                if region:
                    x = region.get('x', 0)
                    y = region.get('y', 0)
                    width = region.get('width', img.width)
                    height = region.get('height', img.height)
                    img = img.crop((x, y, x + width, y + height))

                # Convert to PNG in memory
                png_buffer = io.BytesIO()
                img.save(png_buffer, format='PNG')
                png_bytes = png_buffer.getvalue()

                # Base64 encode
                png_base64 = base64.b64encode(png_bytes).decode('utf-8')
                return png_base64

            except Exception as e:
                log.error(f"PPM to PNG conversion failed: {e}", exc_info=True)
                raise

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _convert)

    def _pyautogui_key_to_qcode(self, key: str) -> Optional[str]:
        """
        Convert pyautogui key name to QMP qcode.

        Args:
            key: Pyautogui key name

        Returns:
            QMP qcode or None if not found
        """
        qcode = PYAUTOGUI_TO_QCODE.get(key.lower())
        if not qcode:
            log.warning(f"No QMP qcode mapping for key '{key}', using literal")
            # Try using the key as-is (might work for single characters)
            qcode = key.lower()
        return qcode

    def _create_key_events(self, key: str) -> list:
        """
        Create QMP events for single key press.

        Args:
            key: Key name

        Returns:
            List of QMP event dictionaries
        """
        qcode = self._pyautogui_key_to_qcode(key)
        if not qcode:
            return []

        return [
            {"type": "key", "data": {"down": True, "key": {"type": "qcode", "data": qcode}}},
            {"type": "key", "data": {"down": False, "key": {"type": "qcode", "data": qcode}}}
        ]

    def _create_type_events(self, text: str) -> list:
        """
        Create QMP events for typing text.

        Args:
            text: Text to type

        Returns:
            List of QMP event dictionaries
        """
        events = []
        for char in text:
            # Handle uppercase by adding shift
            if char.isupper():
                char_lower = char.lower()
                qcode = self._pyautogui_key_to_qcode(char_lower)
                if qcode:
                    # Shift down, key down, key up, shift up
                    events.extend([
                        {"type": "key", "data": {"down": True, "key": {"type": "qcode", "data": "shift"}}},
                        {"type": "key", "data": {"down": True, "key": {"type": "qcode", "data": qcode}}},
                        {"type": "key", "data": {"down": False, "key": {"type": "qcode", "data": qcode}}},
                        {"type": "key", "data": {"down": False, "key": {"type": "qcode", "data": "shift"}}}
                    ])
            else:
                # Regular character
                qcode = self._pyautogui_key_to_qcode(char)
                if qcode:
                    events.extend([
                        {"type": "key", "data": {"down": True, "key": {"type": "qcode", "data": qcode}}},
                        {"type": "key", "data": {"down": False, "key": {"type": "qcode", "data": qcode}}}
                    ])

        return events

    def _create_hotkey_events(self, combo: str) -> list:
        """
        Create QMP events for key combination.

        Args:
            combo: Key combination (e.g., "ctrl+c", "alt+f4")

        Returns:
            List of QMP event dictionaries
        """
        # Parse combination (split by '+')
        keys = [k.strip() for k in combo.split('+')]

        # Convert to qcodes
        qcodes = []
        for key in keys:
            qcode = self._pyautogui_key_to_qcode(key)
            if qcode:
                qcodes.append(qcode)
            else:
                log.warning(f"Failed to map key '{key}' in combination '{combo}'")
                return []

        # Create events: press all keys down, then release in reverse order
        events = []

        # Press down in order
        for qcode in qcodes:
            events.append(
                {"type": "key", "data": {"down": True, "key": {"type": "qcode", "data": qcode}}}
            )

        # Release in reverse order
        for qcode in reversed(qcodes):
            events.append(
                {"type": "key", "data": {"down": False, "key": {"type": "qcode", "data": qcode}}}
            )

        return events
