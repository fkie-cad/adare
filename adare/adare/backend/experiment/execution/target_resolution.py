"""
Target resolution logic for playbook actions.

Handles finding targets on screen using image/text matching and screenshot management.
"""

import logging
import time
import base64
from pathlib import Path
from typing import Optional, Tuple

from adare.types.step_actions import FindAction, ExecuteAction
from adare.backend.events.emitters import emit_action
from .base import ActionResult, get_target_info, serialize_target

log = logging.getLogger(__name__)


class TargetResolutionExecutor:
    """Handles target resolution and screenshot management."""

    def __init__(self, websocket_client, target_resolver, experiment_run_id: Optional[str] = None,
                 debug_screenshots: bool = False, screenshots_dir: Optional[Path] = None,
                 gui_executor = None):
        """
        Initialize target resolution executor.

        Args:
            websocket_client: Connected WebSocket client to adarevm
            target_resolver: Target resolver for image/text targets
            experiment_run_id: Experiment run ID for event emission
            debug_screenshots: Whether to save screenshots for debugging
            screenshots_dir: Directory to save debug screenshots
            gui_executor: GUI executor for mode-aware screenshot operations
        """
        self.client = websocket_client
        self.target_resolver = target_resolver
        self.experiment_run_id = experiment_run_id
        self.debug_screenshots = debug_screenshots
        self.screenshots_dir = screenshots_dir
        self.gui_executor = gui_executor
        self.screenshot_counter = 0

    async def resolve_target_with_steps(self, target, parent_action_id: str = None,
                                       event_emitter = None) -> Optional[Tuple[int, int]]:
        """Resolve target with find step emitted as action event."""
        # Apply smart defaults if no strategy specified
        if target.strategy is None:
            from adare.types.playbook import BestConfidenceStrategy, TopLeftStrategy
            if target.image:
                target.strategy = BestConfidenceStrategy()
                log.debug("Applied default BestConfidence strategy for image target")
            elif target.text:
                target.strategy = TopLeftStrategy()
                log.debug("Applied default TopLeft strategy for text target")
            else:
                target.strategy = TopLeftStrategy()
                log.debug("Applied fallback TopLeft strategy for position target")

        # Create and emit find step events
        find_action_id = f"find_step_{int(time.time()*1000)}"

        # Create target description (used for logging, whether events are emitted or not)
        target_desc = target.image or target.text or f"position {target.position}" if target else "target"

        # Include strategy in description if available
        strategy_desc = ""
        if hasattr(target, 'strategy') and target.strategy:
            strategy_name = target.strategy.__class__.__name__
            strategy_desc = f" using {strategy_name}"

        if self.experiment_run_id and event_emitter:
            # Create find step action
            find_step = FindAction(
                description=f"finding {target_desc}{strategy_desc}",
                target_info=get_target_info(target)
            )

            # Emit find start event using existing unified pattern
            start_event = event_emitter.create_action_start_event(find_step, -1, find_action_id, parent_action_id)
            emit_action(self.experiment_run_id, start_event, find_action_id)

        try:
            # Get screenshot for target resolution
            start_time = time.time()
            screenshot_base64, screenshot_path = await self.get_current_screenshot_with_path()
            if not screenshot_base64:
                log.error("Failed to get screenshot for target resolution")

                # Emit find failure event
                if self.experiment_run_id and event_emitter:
                    execution_time = time.time() - start_time
                    find_result = ActionResult(success=False, message="Failed to get screenshot", execution_time=execution_time)
                    complete_event = event_emitter.create_action_complete_event(find_step, -1, find_action_id, find_result, parent_action_id)
                    emit_action(self.experiment_run_id, complete_event, find_action_id)

                return None

            # Log analysis step
            log.info(f"Analyzing screenshot for target: {target_desc}")

            # Resolve using MCP target resolver
            match = await self.target_resolver.resolve_target(target, screenshot_base64)
            execution_time = time.time() - start_time


            # Apply offset if target found and offset specified
            if match and hasattr(target, 'offset') and target.offset:
                coords = match.coordinates
                final_x, final_y = coords
                offset = target.offset
                
                # Determine anchor point based on base
                anchor_x, anchor_y = coords  # Default to center (coordinates from resolver are usually center)
                
                # If we have region info, we can be more precise about anchors
                if match.region:
                    rx, ry, rw, rh = match.region
                    
                    if offset.base == 'center':
                        anchor_x, anchor_y = rx + rw // 2, ry + rh // 2
                    elif offset.base == 'top-left':
                        anchor_x, anchor_y = rx, ry
                    elif offset.base == 'top-right':
                        anchor_x, anchor_y = rx + rw, ry
                    elif offset.base == 'bottom-left':
                        anchor_x, anchor_y = rx, ry + rh
                    elif offset.base == 'bottom-right':
                        anchor_x, anchor_y = rx + rw, ry + rh
                    elif offset.base == 'center-left':
                        anchor_x, anchor_y = rx, ry + rh // 2
                    elif offset.base == 'center-right':
                        anchor_x, anchor_y = rx + rw, ry + rh // 2
                    elif offset.base == 'top-center':
                        anchor_x, anchor_y = rx + rw // 2, ry
                    elif offset.base == 'bottom-center':
                        anchor_x, anchor_y = rx + rw // 2, ry + rh
                
                # Apply x/y offsets
                final_x = anchor_x + offset.x
                final_y = anchor_y + offset.y
                
                log.info(f"Applied offset {offset} to match at {coords}. Region: {match.region}. New coords: ({final_x}, {final_y})")
                match.coordinates = (final_x, final_y)

            # Emit find complete event
            if self.experiment_run_id and event_emitter:
                success = match is not None
                coords = match.coordinates if match else None

                # Log target found status
                if success:
                    log.info(f"Target found at ({coords[0]}, {coords[1]})")
                else:
                    log.error("Target not found")

                # Include screenshot path in result data
                data = {}
                if screenshot_path:
                    data['screenshot_path'] = screenshot_path

                find_result = ActionResult(
                    success=success,
                    message="Target found" if success else "Target not found",
                    execution_time=execution_time,
                    coordinates=coords,
                    data=data if data else None
                )
                complete_event = event_emitter.create_action_complete_event(find_step, -1, find_action_id, find_result, parent_action_id)
                emit_action(self.experiment_run_id, complete_event, find_action_id)

            return match.coordinates if match else None

        except Exception as e:
            execution_time = time.time() - start_time if 'start_time' in locals() else 0
            log.error(f"Error resolving target: {e}", exc_info=True)

            # Emit find failure event
            if self.experiment_run_id and event_emitter:
                find_result = ActionResult(success=False, message=str(e), execution_time=execution_time)
                complete_event = event_emitter.create_action_complete_event(find_step, -1, find_action_id, find_result, parent_action_id)
                emit_action(self.experiment_run_id, complete_event, find_action_id)

            return None

    async def execute_action_with_steps(self, action, execute_func, parent_action_id: str = None,
                                       event_emitter = None) -> ActionResult:
        """Execute an action with steps for target resolution and execution."""
        try:
            # Resolve target with find step (emitted as action event)
            coords = await self.resolve_target_with_steps(action.target, parent_action_id, event_emitter)
            if not coords:
                return ActionResult(
                    success=False,
                    message=f"Could not resolve target: {action.target}"
                )

            x, y = int(coords[0]), int(coords[1])

            # Create and emit execution step events
            execute_action_id = f"execute_step_{int(time.time()*1000)}"

            if self.experiment_run_id and event_emitter:
                # Create execution step action
                execute_step = ExecuteAction(
                    description=f"executing at ({x}, {y})",
                    coordinates=(x, y)
                )

                # Emit execution start event using existing unified pattern
                start_event = event_emitter.create_action_start_event(execute_step, -1, execute_action_id, parent_action_id)
                emit_action(self.experiment_run_id, start_event, execute_action_id)

            # Execute the action
            start_time = time.time()
            result = await execute_func(x, y)
            execution_time = time.time() - start_time
            execution_success = result.get('status') == 'success'

            # Log execution result
            if execution_success:
                log.info(f"Action executed successfully")
            else:
                log.error(f"Action execution failed: {result.get('message', 'Unknown error')}")

            # Emit execution complete event
            if self.experiment_run_id and event_emitter:
                execute_result = ActionResult(
                    success=execution_success,
                    message=result.get('message', ''),
                    execution_time=execution_time,
                    coordinates=(x, y)
                )
                complete_event = event_emitter.create_action_complete_event(execute_step, -1, execute_action_id, execute_result, parent_action_id)
                emit_action(self.experiment_run_id, complete_event, execute_action_id)

            return ActionResult(
                success=execution_success,
                message=result.get('message', ''),
                coordinates=(x, y),
                data={'target': serialize_target(action.target)}
            )

        except Exception as e:
            log.error(f"Error executing action with steps: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message=str(e),
                data={'target': serialize_target(action.target)}
            )

    async def get_current_screenshot(self) -> Optional[str]:
        """
        Get current screenshot from WebSocket client.

        Returns:
            Base64 encoded screenshot data, None if failed
        """
        screenshot_data, _ = await self.get_current_screenshot_with_path()
        return screenshot_data

    async def get_current_screenshot_with_path(self) -> Tuple[Optional[str], Optional[str]]:
        """
        Get current screenshot from WebSocket client and save to disk.

        Returns:
            Tuple of (base64_screenshot_data, relative_screenshot_path)
            Either can be None if failed
        """
        try:
            # Take new screenshot (use GUI executor if available for mode-aware screenshots)
            result = None
            if self.gui_executor:
                result = await self.gui_executor.screenshot()
                # Check for error status
                if result and result.get('status') == 'error':
                    log.warning(f"GUI executor screenshot failed: {result.get('message')}. Falling back to WebSocket.")
                    result = None # forcing fallback

            # Fallback to WebSocket if GUI executor didn't work (or wasn't available)
            if not result:
                log.debug("Using WebSocket client for screenshot")
                result = await self.client.screenshot()

            if result and 'image' in result:
                # Extract base64 data from result
                if 'data' in result['image']:
                    screenshot_base64 = result['image']['data']
                else:
                    screenshot_base64 = result['image']

                # Save screenshot to disk if debug mode is enabled
                screenshot_path = await self._save_debug_screenshot(screenshot_base64)

                log.debug("Screenshot captured")
                return screenshot_base64, screenshot_path
            else:
                log.error("Screenshot result missing image data")
                return None, None

        except Exception as e:
            log.error(f"Failed to capture screenshot: {e}")
            return None, None

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

            # Generate filename with counter (consistent with forensic reporter expectations)
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
