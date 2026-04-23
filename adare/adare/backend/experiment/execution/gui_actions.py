"""
Mixin for GUI-related playbook actions.

Includes: click, drag, keyboard, idle, scroll, goto, screenshot actions.
"""

import asyncio
import base64
import logging
import time
from pathlib import Path

from adare.backend.events.emitters import emit_action
from adare.types.playbook import (
    ClickAction,
    DragAction,
    GotoAction,
    IdleAction,
    KeyboardAction,
    ScreenshotAction,
    ScrollAction,
)
from adare.types.step_actions import ExecuteAction

from .base import ActionResult

log = logging.getLogger(__name__)


class GUIActionsMixin:
    """Mixin providing GUI action execution methods for SimpleActionsExecutor."""

    async def execute_click(self, action: ClickAction, parent_event_id: str = None,
                           event_emitter = None) -> ActionResult:
        """Execute click action with steps."""
        handler = self.get_click_handler(action.type)

        # Determine context identifier
        target_name = "target"
        if action.target.text:
            target_name = f"text_{action.target.text[:15]}"
        elif action.target.image:
             try:
                 target_name = f"img_{Path(action.target.image).stem}"
             except (TypeError, ValueError):
                 target_name = "img"
        elif action.target.position:
            target_name = "pos"

        action_context = f"click_{action.type}_{target_name}"

        return await self.target_resolution.execute_action_with_steps(
            action, handler, parent_event_id, event_emitter, action_context=action_context
        )

    async def execute_drag(self, action: DragAction, parent_event_id: str = None,
                          event_emitter = None) -> ActionResult:
        """Execute drag action - special handling for two targets."""
        try:
            # Resolve both targets (each will emit their own find steps with proper parent)
            src_coords = await self.target_resolution.resolve_target_with_steps(
                action.src, parent_event_id, event_emitter, action_context="drag_start"
            )
            dst_coords = await self.target_resolution.resolve_target_with_steps(
                action.dst, parent_event_id, event_emitter, action_context="drag_end"
            )

            if not src_coords or not dst_coords:
                return ActionResult(success=False, message="Could not resolve targets")

            # Create and emit execution step
            execute_action_id = f"execute_step_{int(time.time()*1000)}"

            if self.experiment_run_id and event_emitter:
                # Create execution step action
                execute_step = ExecuteAction(
                    description=f"dragging from ({src_coords[0]}, {src_coords[1]}) to ({dst_coords[0]}, {dst_coords[1]})",
                    coordinates=src_coords  # Use source coordinates
                )

                # Emit execution start event
                start_event = event_emitter.create_action_start_event(execute_step, -1, execute_action_id, parent_event_id)
                emit_action(self.experiment_run_id, start_event, execute_action_id)

            # Execute the drag via GUI executor
            start_time = time.time()
            result = await self.gui_executor.drag(src_coords[0], src_coords[1], dst_coords[0], dst_coords[1])
            execution_time = time.time() - start_time
            success = result.get('status') == 'success'

            # Emit execution complete event
            if self.experiment_run_id and event_emitter:
                execute_result = ActionResult(
                    success=success,
                    message=result.get('message', ''),
                    execution_time=execution_time,
                    coordinates=dst_coords,  # Use destination coordinates as final result
                    data={'source_coordinates': src_coords, 'dest_coordinates': dst_coords}
                )
                complete_event = event_emitter.create_action_complete_event(execute_step, -1, execute_action_id, execute_result, parent_event_id)
                emit_action(self.experiment_run_id, complete_event, execute_action_id)

            return ActionResult(
                success=success,
                message=result.get('message', ''),
                coordinates=src_coords,
                data={'source': action.src, 'destination': action.dst, 'source_coordinates': src_coords, 'dest_coordinates': dst_coords}
            )

        except Exception as e:
            log.error(f"Error executing drag action: {e}", exc_info=True)
            return ActionResult(success=False, message=str(e))

    async def execute_keyboard(self, action: KeyboardAction, parent_event_id: str = None,
                              event_emitter = None) -> ActionResult:
        """Execute keyboard action via GUI executor."""
        try:
            if action.key:
                # Single key press -> pyautogui.press()
                result = await self.gui_executor.keyboard("press", action.key)
            elif action.text:
                # Text typing -> pyautogui.typewrite()
                result = await self.gui_executor.keyboard("type", action.text)
            elif action.combination:
                # Key combinations -> pyautogui.hotkey()
                combo = "+".join(action.combination)
                result = await self.gui_executor.keyboard("hotkey", combo)
            else:
                return ActionResult(
                    success=False,
                    message="No key, text, or combination specified"
                )

            # Prepare data for result
            result_data = {}
            if action.key:
                result_data['key'] = action.key
            elif action.text:
                result_data['text'] = action.text
            elif action.combination:
                result_data['combination'] = action.combination

            return ActionResult(
                success=result.get('status') == 'success',
                message=result.get('message', ''),
                data=result_data
            )
        except Exception as e:
            log.error(f"Error executing keyboard action: {e}", exc_info=True)
            return ActionResult(success=False, message=str(e))

    async def execute_idle(self, action: IdleAction, parent_event_id: str = None,
                          event_emitter = None) -> ActionResult:
        """Execute idle action locally without involving the VM."""
        try:
            log.info(f"Starting idle action for {action.duration} seconds (local)")

            # Execute idle locally using asyncio.sleep instead of WebSocket call
            await asyncio.sleep(action.duration)

            log.info(f"Idle action completed locally ({action.duration}s)")

            return ActionResult(
                success=True,
                message=f"Idle completed ({action.duration}s)"
            )
        except Exception as e:
            log.error(f"Idle action failed: {e}")
            return ActionResult(success=False, message=str(e))

    async def execute_scroll(self, action: ScrollAction, parent_event_id: str = None,
                            event_emitter = None) -> ActionResult:
        """Execute scroll action via GUI executor."""
        result = await self.gui_executor.scroll(action.direction, action.amount or 3)
        return ActionResult(success=result.get('status') == 'success')

    async def execute_goto(self, action: GotoAction, parent_event_id: str = None,
                          event_emitter = None) -> ActionResult:
        """Execute goto action with steps."""
        handler = self.get_click_handler('left')  # goto uses left click
        return await self.target_resolution.execute_action_with_steps(
            action, handler, parent_event_id, event_emitter, action_context="goto"
        )

    async def execute_screenshot(self, action: ScreenshotAction, parent_event_id: str = None,
                                event_emitter = None) -> ActionResult:
        """
        Execute screenshot action via GUI executor.

        Explicit screenshots are always saved (regardless of --debug-screenshots flag).
        If action.name is provided, uses custom name; otherwise uses sequential numbering.
        """
        try:
            # Build region dict if coordinates specified
            region = None
            if action.x is not None and action.y is not None and action.width is not None and action.height is not None:
                region = {'x': action.x, 'y': action.y, 'width': action.width, 'height': action.height}

            result = await self.gui_executor.screenshot(region)

            screenshot_path = None
            # Save explicit screenshot (always, not just in debug mode)
            if result and 'image' in result:
                try:
                    # Extract base64 data from result
                    if 'data' in result['image']:
                        screenshot_base64 = result['image']['data']
                    else:
                        screenshot_base64 = result['image']

                    # Save screenshot with custom naming logic
                    screenshot_path = await self._save_explicit_screenshot(screenshot_base64, action.name)
                except Exception as save_error:
                    # Don't fail the action if screenshot save fails, but log it
                    log.warning(f"Failed to save screenshot: {save_error}")

            return ActionResult(
                success=result.get('status') == 'success',
                message=result.get('message', ''),
                data={**result, 'screenshot_path': screenshot_path} if screenshot_path else result
            )
        except Exception as e:
            return ActionResult(success=False, message=str(e))

    async def _save_explicit_screenshot(self, screenshot_base64: str, custom_name: str | None = None) -> str | None:
        """
        Save explicit screenshot to disk with custom naming.

        Args:
            screenshot_base64: Base64 encoded screenshot data
            custom_name: Optional custom name for the file (without extension)

        Returns:
            Relative path to saved screenshot (relative to run directory), or None if screenshots_dir not set
        """
        from .simple_actions import sanitize_filename

        # Use screenshots directory from target_resolution executor
        screenshots_dir = self.target_resolution.screenshots_dir
        if not screenshots_dir:
            log.warning("Screenshots directory not set, cannot save explicit screenshot")
            return None

        try:
            # Create screenshots directory if it doesn't exist
            screenshots_dir.mkdir(parents=True, exist_ok=True)

            # Generate filename
            if custom_name:
                # Use custom name (sanitized)
                sanitized_name = sanitize_filename(custom_name)

                # Handle duplicate names by adding counter suffix
                if sanitized_name in self.custom_screenshot_counters:
                    # Name already used, increment counter and add suffix
                    self.custom_screenshot_counters[sanitized_name] += 1
                    counter = self.custom_screenshot_counters[sanitized_name]
                    filename = f"{sanitized_name}_{counter:03d}.png"
                else:
                    # First use of this name, check if file exists
                    base_filepath = screenshots_dir / f"{sanitized_name}.png"
                    if base_filepath.exists():
                        # File exists, start counter at 1
                        self.custom_screenshot_counters[sanitized_name] = 1
                        filename = f"{sanitized_name}_001.png"
                    else:
                        # File doesn't exist, use base name and initialize counter
                        self.custom_screenshot_counters[sanitized_name] = 0
                        filename = f"{sanitized_name}.png"
            else:
                # Use sequential numbering for unnamed screenshots
                filename = f"screenshot_{self.explicit_screenshot_counter:03d}.png"
                self.explicit_screenshot_counter += 1

            filepath = screenshots_dir / filename

            # Decode and save the image
            image_data = base64.b64decode(screenshot_base64)
            with open(filepath, 'wb') as f:
                f.write(image_data)

            log.info(f"Explicit screenshot saved: {filepath}")

            # Return relative path (relative to run directory)
            relative_path = f"reporting/screenshots/{filename}"
            return relative_path

        except Exception as e:
            log.error(f"Failed to save explicit screenshot: {e}")
            return None
