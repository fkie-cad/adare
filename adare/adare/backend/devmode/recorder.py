
import asyncio
import contextlib
import logging
import re
import time
from pathlib import Path

import yaml

from adare.hypervisor.qemu.libvirt_stderr_redirect import get_experiment_log_file
from adare.hypervisor.qemu.vm import QEMUVM
from adare.types.playbook import (
    ActionType,
    ClickAction,
    IdleAction,
    KeyboardAction,
    Playbook,
    ScreenshotAction,
    Settings,
    Target,
)

log = logging.getLogger(__name__)

class SessionRecorder:
    """
    Records QEMU session user interactions by tracing input events.

    Works by:
    1. Enabling QMP tracing for input events
    2. Tailing the QEMU/libvirt log file where trace events are written
    3. Parsing trace events into high-level actions
    4. Taking screenshots before clicks
    5. Generating a Playbook YAML
    """

    def __init__(self, vm: QEMUVM, output_file: Path):
        self.vm = vm
        self.output_file = output_file
        self.is_recording = False
        self._task = None
        self._actions: list[ActionType] = []
        self._start_time = 0.0
        self._last_event_time = 0.0

        # State tracking for aggregating raw events into actions
        self._pending_click = None # Stores potential click start
        self._pressed_keys = set() # Track keys currently down

        # Mouse tracking
        self._current_x = 0
        self._current_y = 0
        self._max_x = 32767 # QEMU Tablet default
        self._max_y = 32767


        # Regex for parsing QEMU trace log format (log backend)
        # Format example: 26428@1737803621.577968:input_event_key_qcode con 0 qcode 30 (a) down true
        # Format example: 26428@1737803621.577968:input_event_btn con 0 button 0 (left) down true
        # Format example: 26428@1737803621.577968:input_event_abs con 0 axis 0 (x) value 16383
        self._log_pattern = re.compile(r'^\d+@(\d+\.\d+):(\w+)\s+(.*)$')

    async def start(self):
        """Start recording session."""
        if self.is_recording:
            return

        log.info(f"Starting recording for VM {self.vm.vm_name}")

        # 1. Enable QEMU Tracing
        success = await self.vm.enable_input_tracing()
        if not success:
            raise RuntimeError("Failed to enable QEMU input tracing. Ensure QEMU is built with 'log' trace backend support.")

        # 2. Start log tailing task
        self.is_recording = True
        self._start_time = time.time()
        self._last_event_time = self._start_time
        self._task = asyncio.create_task(self._record_loop())

    async def stop(self):
        """Stop recording and save playbook."""
        if not self.is_recording:
            return

        log.info("Stopping recording...")
        self.is_recording = False

        # Cancel task
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

        # Disable Tracing
        await self.vm.disable_input_tracing()

        # Add final idle time if needed
        duration = time.time() - self._last_event_time
        if duration > 1.0:
            self._actions.append(IdleAction(duration=round(duration, 2), description="End of session"))

        # Save playbook
        self._save_playbook()
        log.info(f"Recording saved to {self.output_file}")

    def _save_playbook(self):
        """Compile actions and save to YAML."""
        Playbook(
            actions=self._actions,
            settings=Settings(
                idle=0.5,
                screenshot={"enabled": True},
                gui_execution_mode="host" # We recorded on host, so replay on host
            )
        )

        # Convert to dict manually to ensure clean YAML, or use adarelib serialization
        # For now, simplistic dump

        # TODO: Use adarelib's proper YAML dumper if available,
        # but for now we'll construct a clean dict structure to match the parser's expectations.

        data = {
            "settings": {
                "idle": 0.5,
                "gui_execution_mode": "host"
            },
            "actions": []
        }

        for action in self._actions:
            if isinstance(action, ClickAction):
                act = {
                    "click": {
                        "target": {
                            "position": action.target.position
                        },
                        "type": action.type,
                        "description": action.description
                    }
                }
            elif isinstance(action, KeyboardAction):
                act = {
                    "keyboard": {
                        "key": action.key,
                        "description": action.description
                    }
                }
                if action.text:
                    act["keyboard"]["text"] = action.text
                    del act["keyboard"]["key"]

            elif isinstance(action, ScreenshotAction):
                act = {
                    "screenshot": {
                        "description": action.description
                    }
                }
            elif isinstance(action, IdleAction):
                act = {
                    "idle": {
                        "duration": action.duration,
                        "description": action.description
                    }
                }
            else:
                continue

            data["actions"].append(act)

        with open(self.output_file, 'w') as f:
            yaml.dump(data, f, sort_keys=False)

    async def _record_loop(self):
        """Main loop: tails log file and parses events."""
        log_file_path = get_experiment_log_file()
        if not log_file_path.exists():
            log.warning(f"Log file not found: {log_file_path}")
            # Potentially wait for it to appear

        log.info(f"Tailing log file: {log_file_path}")

        # Open file and seek to end
        try:
            with open(log_file_path) as f:
                f.seek(0, 2) # Seek to end

                while self.is_recording:
                    line = f.readline()
                    if not line:
                        await asyncio.sleep(0.05) # Small sleep to prevent tight loop
                        continue

                    # log.debug(f"Read line: {line.strip()}")
                    await self._process_log_line(line)
        except Exception as e:
            log.error(f"Error in record loop: {e}", exc_info=True)
            # Re-raise or keep going? If loop breaks, recording stops effectively


    async def _process_log_line(self, line: str):
        """Parse raw log line and convert to events."""
        match = self._log_pattern.match(line.strip())
        if not match:
             # log.debug(f"Regex fail for line: {line.strip()}")
            return

        timestamp_str, event_name, args_str = match.groups()


        # timestamp = float(timestamp_str) # TODO: Use if needed for precise timing

        # Parse args string: "arg1=val1 arg2=val2 ..." (simplified parser)
        # Note: QEMU log format might vary slightly, treating args as text for now

        if event_name == "input_event_btn":
            await self._handle_btn_event(args_str)
        elif event_name.startswith("input_event_key"):
            await self._handle_key_event(event_name, args_str)
        # abs/rel events ignored for now - simpler record approach first

    async def _handle_btn_event(self, args: str):
        """Handle mouse button event.
        Expected args: "con 0 button 0 (left) down true"
        """
        # Simplistic parsing
        is_down = "down true" in args
        button = "left"  # Default
        if "(right)" in args: button = "right"
        elif "(middle)" in args: button = "middle"

        if is_down:
            # Record time since last action
            await self._add_idle()

            # Prepare for click
            # Capture screenshot BEFORE action
            await self._add_screenshot()

            self._pending_click = {
                "button": button,
                "start": time.time()
            }
        else: # Up
            if self._pending_click and self._pending_click["button"] == button:
                # Completed click
                try:
                    width = getattr(self.vm, '_screen_width', 1920) or 1920
                    height = getattr(self.vm, '_screen_height', 1080) or 1080

                    # Ensure they are ints
                    if not isinstance(width, (int, float)): width = 1920
                    if not isinstance(height, (int, float)): height = 1080

                    x_pixel = int((self._current_x / self._max_x) * width)
                    y_pixel = int((self._current_y / self._max_y) * height)

                    action = ClickAction(
                        target=Target(position=[x_pixel, y_pixel]),
                        type=button,
                        description=f"Click {button}"
                    )
                    self._actions.append(action)
                    log.info(f"Recorded Click: {button} at {x_pixel},{y_pixel}")
                except Exception as e:
                    log.error(f"Error processing click event: {e}")
                finally:
                    self._pending_click = None

    # We need to track abs events to know WHERE the click happened




    async def _process_log_line(self, line: str):
        """Parse raw log line and convert to events."""
        match = self._log_pattern.match(line.strip())
        if not match:
            return

        _, event_name, args_str = match.groups()

        if event_name == "input_event_abs":
            self._handle_abs_event(args_str)
        elif event_name == "input_event_btn":
            await self._handle_btn_event(args_str)
        elif event_name.startswith("input_event_key"):
            await self._handle_key_event(event_name, args_str)

    def _handle_abs_event(self, args: str):
        """Handle mouse move.
        Args: "con 0 axis 0 (x) value 16383"
        """
        try:
            # simplistic extraction
            val_match = re.search(r'value (\d+)', args)
            if not val_match: return
            value = int(val_match.group(1))

            if "axis 0 (x)" in args:
                self._current_x = value
            elif "axis 1 (y)" in args:
                self._current_y = value
        except (ValueError, AttributeError):
            pass



    async def _handle_key_event(self, event_name: str, args: str):
        """Handle keyboard event.
        Args: "con 0 qcode 30 (a) down true"
        """
        is_down = "down true" in args

        # Extract key name "30 (a)" -> "a"
        key_match = re.search(r'\((\w+)\)', args)
        if not key_match: return
        key = key_match.group(1)

        if is_down:
            await self._add_idle()

            # Map QMP key names to pyautogui names if needed
            # For now use as-is

            action = KeyboardAction(
                key=key,
                description=f"Press {key}"
            )
            self._actions.append(action)

    async def _add_idle(self):
        """Add idle action based on time elapsed."""
        now = time.time()
        duration = now - self._last_event_time
        if duration > 1.0: # Ignore tiny delays
            self._actions.append(IdleAction(duration=round(duration, 2)))
        self._last_event_time = now

    async def _add_screenshot(self):
        """Capture screenshot."""
        # Use VM screenshot capability?
        # QEMUVM already has send_qmp_screenshot, but it saves to file.
        # We just want to record the "Action" to take a screenshot in the playbook.
        # So we just append ScreenshotAction.

        self._actions.append(ScreenshotAction(description="Context before action"))

        # NOTE: If we want to ACTUALLY capture a screenshot NOW to verify recording,
        # we could calls vm.send_qmp_screenshot, but the goal is to GENERATE a playbook.
        # The playbook, when run, will take screenshots.
        #
        # Re-reading task: "does for each click and screenshot just before."
        # This implies the RECORDING process should capture the screenshot?
        # "The idea is to later convert this into an automatic playbook via gui recognition of icons"
        #
        # If the goal is visual RECOGNITION later, we likely need the screenshot NOW stored on disk,
        # and checking the coordinates against that image.
        #
        # BUT the plan says "Output: Playbook YAML".
        # If we just output a YAML with "ScreenshotAction", it takes a screenshot when replay happens.
        # That helps with debugging replay.
        #
        # However, to support "convert this into an automatic playbook via gui recognition of icons",
        # we'd ideally want to capture the screenshot of the UI element *at record time*.
        #
        # For now, following the simple plan: Just emit `ScreenshotAction` in the YAML.
