"""
Target resolution logic for playbook actions.

Handles finding targets on screen using image/text matching and screenshot management.
"""

import base64
import csv
import logging
import re
import time
from pathlib import Path

from adare.backend.events.emitters import emit_action
from adare.types.step_actions import ExecuteAction, FindAction

from .base import ActionResult, get_target_info, serialize_target

log = logging.getLogger(__name__)


class TargetResolutionExecutor:
    """Handles target resolution and screenshot management."""

    def __init__(self, websocket_client, target_resolver, experiment_run_id: str | None = None,
                 debug_screenshots: bool = False, screenshots_dir: Path | None = None,
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
        self.current_action_prefix: str | None = None
        self._manifest_initialized = False

        # Cache for target resolution results: {'target_hash': str, 'result': MatchResult, 'timestamp': float, 'screenshot_path': str}
        self.last_match_cache = {}

    def _get_target_hash(self, target) -> str:
        """Generate a unique hash for a target definition."""
        # Create a hashable representation of the target criteria
        # We include strategy type but not memory address
        strategy_repr = target.strategy.__class__.__name__ if hasattr(target, 'strategy') and target.strategy else "None"

        # Combine key target attributes
        key_parts = [
            str(target.image) if hasattr(target, 'image') else "None",
            str(target.text) if hasattr(target, 'text') else "None",
            str(target.position) if hasattr(target, 'position') else "None",
            strategy_repr,
            str(target.offset) if hasattr(target, 'offset') else "None"
        ]
        return ":".join(key_parts)

    def cache_match(self, target, match_result, screenshot_path: str = None):
        """
        Cache a successful target match.

        Args:
            target: The Target definition used
            match_result: The result from target_resolver.resolve_target
            screenshot_path: Path to the screenshot where match was found
        """
        if not match_result:
            return

        target_hash = self._get_target_hash(target)
        self.last_match_cache[target_hash] = {
            'result': match_result,
            'timestamp': time.time(),
            'screenshot_path': screenshot_path
        }
        log.debug(f"Cached match for target {target_hash}")

    def get_cached_match(self, target):
        """
        Retrieve a cached match for the target if available.

        Args:
            target: The Target to look up

        Returns:
            Tuple of (Match object or None, screenshot_path or None, age_seconds or None)
        """
        target_hash = self._get_target_hash(target)
        if target_hash in self.last_match_cache:
            cache_entry = self.last_match_cache[target_hash]
            age = time.time() - cache_entry['timestamp']

            # Log debug info but don't commit to using it yet
            log.debug(f"Cache hit for target {target_hash} (age: {age:.2f}s)")
            return cache_entry['result'], cache_entry['screenshot_path'], age

        return None, None, None

    async def resolve_target_with_steps(self, target, parent_action_id: str = None,
                                       event_emitter = None, action_context: str = None) -> tuple[int, int] | None:
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
        find_step = None

        # Create target description (used for logging, whether events are emitted or not)
        target_desc = target.image or target.text or f"position {target.position}" if target else "target"

        # Determine explicit screenshot context if not provided
        if not action_context:
            if target.image:
                # Use image name without extension/path if possible
                try:
                    img_name = Path(target.image).stem
                    action_context = f"find_img_{img_name}"
                except (TypeError, ValueError):
                    action_context = "find_img"
            elif target.text:
                 # Truncate text for filename safety
                 safe_text = target.text[:20].replace(" ", "_")
                 action_context = f"find_text_{safe_text}"
            elif target.position:
                 action_context = f"find_pos_{target.position[0]}_{target.position[1]}"
            else:
                 action_context = "find_target"

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

        # Check cache first if requested or if result is fresh (heuristic for "directly after")
        cached_match, cached_screenshot_path, cached_age = self.get_cached_match(target)
        should_use_cache = False

        if cached_match:
            # Explicit request
            if hasattr(target, 'use_cache') and target.use_cache:
                should_use_cache = True
                log.info(f"Using cached target (explicit request, age: {cached_age:.2f}s)")

            # Heuristic: If match is very recent (WaitUntil just finished), it's safe to reuse
            # Limit to 5.0 seconds (generous buffer for processing implementation delays)
            elif cached_age is not None and cached_age < 5.0:
                 should_use_cache = True
                 log.info(f"Using cached target (fresh heuristic, age: {cached_age:.2f}s)")

        if should_use_cache and cached_match:
            # Use cached result effectively skipping new screenshot and expensive resolution
            return self._process_match_result(
                target, cached_match, cached_screenshot_path,
                start_time=time.time(), # Fake start time for result structure
                find_step=find_step, find_action_id=find_action_id,
                parent_action_id=parent_action_id, event_emitter=event_emitter,
                from_cache=True
            )

        try:
            # Get screenshot for target resolution
            start_time = time.time()
            screenshot_base64, screenshot_path = await self.get_current_screenshot_with_path(action_context=action_context)
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


            # Process the match result (calculate offsets, emit events, etc.)
            return self._process_match_result(
                target, match, screenshot_path, start_time,
                find_step, find_action_id, parent_action_id, event_emitter
            )



        except Exception as e:
            execution_time = time.time() - start_time if 'start_time' in locals() else 0
            log.error(f"Error resolving target: {e}", exc_info=True)

            # Emit find failure event
            if self.experiment_run_id and event_emitter:
                find_result = ActionResult(success=False, message=str(e), execution_time=execution_time)
                complete_event = event_emitter.create_action_complete_event(find_step, -1, find_action_id, find_result, parent_action_id)
                emit_action(self.experiment_run_id, complete_event, find_action_id)

            return None

    def _process_match_result(self, target, match, screenshot_path, start_time,
                             find_step, find_action_id, parent_action_id, event_emitter,
                             from_cache=False):
        """Helper to process match result, applying offsets and emitting events."""
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
                msg_suffix = " (CACHED)" if from_cache else ""
                log.info(f"Target found at ({coords[0]}, {coords[1]}){msg_suffix}")
            else:
                log.error("Target not found")

            # Include screenshot path in result data
            data = {}
            if screenshot_path:
                data['screenshot_path'] = screenshot_path

            if from_cache:
                data['cached'] = True

            # Include matched text for text-based targeting (shows what OCR actually detected)
            if match and match.text and match.method == 'text':
                data['matched_text'] = match.text

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

    async def execute_action_with_steps(self, action, execute_func, parent_action_id: str = None,
                                       event_emitter = None, action_context: str = None) -> ActionResult:
        """Execute an action with steps for target resolution and execution."""
        try:
            # Resolve target with find step (emitted as action event)
            coords = await self.resolve_target_with_steps(action.target, parent_action_id, event_emitter, action_context=action_context)
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
                log.info("Action executed successfully")
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

    async def get_current_screenshot(self) -> str | None:
        """
        Get current screenshot from WebSocket client.

        Returns:
            Base64 encoded screenshot data, None if failed
        """
        screenshot_data, _ = await self.get_current_screenshot_with_path()
        return screenshot_data

    async def get_current_screenshot_with_path(self, action_context: str | None = None) -> tuple[str | None, str | None]:
        """
        Get current screenshot from WebSocket client and save to disk.

        Args:
            action_context: Optional context string (e.g., 'click_{target}') for filename

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
                screenshot_base64 = result['image']['data'] if 'data' in result['image'] else result['image']

                # Save screenshot to disk if debug mode is enabled
                screenshot_path = await self._save_debug_screenshot(screenshot_base64, action_context)

                log.debug("Screenshot captured")
                return screenshot_base64, screenshot_path
            log.error("Screenshot result missing image data")
            return None, None

        except Exception as e:
            log.error(f"Failed to capture screenshot: {e}")
            return None, None

    async def _save_debug_screenshot(self, screenshot_base64: str, action_context: str | None = None) -> str | None:
        """
        Save screenshot to disk for debugging purposes.

        Args:
            screenshot_base64: Base64 encoded screenshot data
            action_context: Optional context string description for the filename

        Returns:
            Relative path to saved screenshot file, or None if not saved
        """
        if not self.debug_screenshots or not self.screenshots_dir:
            return None

        try:
            # Create screenshots directory if it doesn't exist
            self.screenshots_dir.mkdir(parents=True, exist_ok=True)

            # Prepend action prefix (e.g. "a03") to find-step contexts for playbook-level identification
            if self.current_action_prefix and action_context:
                prefix_match = re.match(r'(a\d+)', self.current_action_prefix)
                if prefix_match and not re.match(r'a\d', action_context):
                    action_context = f"{prefix_match.group(1)}_{action_context}"

            # Format: {counter:03d}_{sanitized_context}.png OR {counter:03d}.png
            context_part = ""
            if action_context:
                # Sanitize context (remove non-alphanumeric except specific separators)
                sanitized = re.sub(r'[^a-zA-Z0-9_\-]', '_', action_context)
                # Collapse multiple underscores
                sanitized = re.sub(r'_+', '_', sanitized).strip('_')
                if sanitized:
                    context_part = f"_{sanitized}"

            filename = f"{self.screenshot_counter:03d}{context_part}.png"
            filepath = self.screenshots_dir / filename

            # Increment counter for next screenshot
            self.screenshot_counter += 1

            # Decode and save the image
            image_data = base64.b64decode(screenshot_base64)
            with open(filepath, 'wb') as f:
                f.write(image_data)

            log.debug(f"Debug screenshot saved: {filepath}")

            # Append row to CSV manifest
            self._append_manifest_row(filename, action_context)

            # Return relative path (relative to run directory)
            return f"reporting/screenshots/{filename}"

        except Exception as e:
            log.error(f"Failed to save debug screenshot: {e}")
            return None

    def _append_manifest_row(self, filename: str, action_context: str | None = None) -> None:
        """Append a row to the screenshot manifest CSV.

        Parses action_index, action_type, detail, and phase from the action_context string
        and writes them alongside the counter, filename, and timestamp.
        """
        if not self.screenshots_dir:
            return

        manifest_path = self.screenshots_dir / "manifest.csv"

        try:
            # Write header on first call
            if not self._manifest_initialized:
                with open(manifest_path, 'w', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(["counter", "filename", "action_index", "action_type", "detail", "phase", "timestamp"])
                self._manifest_initialized = True

            # Parse fields from action_context (e.g. "a03_click_L_img_button" or "a03_find_img_button")
            action_index = ""
            action_type = ""
            detail = ""
            phase = "post"

            if action_context:
                # Extract action index (a00, a01, ...)
                idx_match = re.match(r'a(\d+)_?(.*)', action_context)
                if idx_match:
                    action_index = idx_match.group(1).lstrip('0') or "0"
                    remainder = idx_match.group(2)
                else:
                    remainder = action_context

                # Detect phase
                if remainder.startswith("find_"):
                    phase = "find"
                    remainder = remainder[5:]  # strip "find_"
                elif remainder == "initial":
                    phase = "initial"
                    action_type = "initial"
                    remainder = ""

                # Extract action type and detail from remainder
                if remainder and action_type != "initial":
                    # Known type prefixes to split on
                    type_patterns = [
                        (r'^(click_[LRD])_?(.*)', None),
                        (r'^(key_hotkey)_?(.*)', None),
                        (r'^(key_type)_?(.*)', None),
                        (r'^(key)_?(.*)', None),
                        (r'^(scroll)_?(.*)', None),
                        (r'^(cmd)_?(.*)', None),
                        (r'^(goto)_?(.*)', None),
                        (r'^(drag)_?(.*)', None),
                        # Find-step targets (no action type prefix — use target type)
                        (r'^(img)_?(.*)', None),
                        (r'^(text)_?(.*)', None),
                        (r'^(pos)_?(.*)', None),
                    ]
                    matched = False
                    for pattern, _ in type_patterns:
                        m = re.match(pattern, remainder)
                        if m:
                            action_type = action_type or m.group(1)
                            detail = m.group(2).strip('_') if m.group(2) else ""
                            matched = True
                            break
                    if not matched:
                        action_type = action_type or remainder
                        detail = ""

            counter = self.screenshot_counter - 1  # counter was already incremented
            with open(manifest_path, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([counter, filename, action_index, action_type, detail, phase, f"{time.time():.3f}"])

        except Exception as e:
            log.warning(f"Failed to write manifest row: {e}")
