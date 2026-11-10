"""
Mixin for GUI-related playbook actions.

Includes: click, drag, keyboard, idle, scroll, goto, screenshot actions.
"""

import asyncio
import base64
import binascii
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

from adare.backend.events.emitters import emit_action
from adare.types.playbook import (
    ClickAction,
    ClickVerify,
    DragAction,
    GotoAction,
    IdleAction,
    KeyboardAction,
    ScreenshotAction,
    ScrollAction,
)
from adare.types.step_actions import ExecuteAction

from .base import ActionResult

if TYPE_CHECKING:
    from adare.backend.experiment.execution.executor_core import ActionsExecutorCore as _Host
else:
    _Host = object


log = logging.getLogger(__name__)


class GUIActionsMixin(_Host):
    """Mixin providing GUI action execution methods for SimpleActionsExecutor."""

    async def execute_click(self, action: ClickAction, parent_event_id: str = None, event_emitter=None) -> ActionResult:
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
        self.effect_probe.begin_action()

        verify = action.verify
        if verify is None:
            # No verify condition: one click, no retry; the automatic effect check still runs.
            result = await self.target_resolution.execute_action_with_steps(
                action, self._armed(action, handler), parent_event_id, event_emitter, action_context=action_context
            )
            return await self._apply_effect(action, result, action_context)

        return await self._execute_click_with_verify(
            action, verify, handler, parent_event_id, event_emitter, action_context
        )

    def _effect_checked(self, action) -> bool:
        """The automatic check runs unless it is off or the author marked the action ``effect: none``."""
        return self.effect_probe.enabled and getattr(action, 'effect', None) != 'none'

    def _armed(self, action, handler):
        """Wrap an ``(x, y)`` input handler so the "before" frame is fixed right before the input."""
        if not self._effect_checked(action):
            return handler

        async def run(x, y):
            await self.effect_probe.arm([(x, y)])
            return await handler(x, y)

        return run

    async def _apply_effect(self, action, result: ActionResult, label: str) -> ActionResult:
        """After the input: ``verify:`` if the action has one, else the automatic effect check."""
        if not result.success:
            return result
        data = dict(result.data or {})
        verify = getattr(action, 'verify', None)
        if verify is not None:
            timeout = getattr(action, 'verify_timeout', 3.0)
            verified = await self._verify_holds(verify, timeout)
            data.update(verified=verified, effect='verified' if verified else 'unchanged')
            result.data = data
            if not verified:
                result.success = False
                result.message = f"{label}: verify {self._describe_verify(verify)} not satisfied within {timeout}s"
            return result
        if getattr(action, 'effect', None) == 'none':
            data['effect'] = 'none'
        elif self.effect_probe.enabled:
            data.update(await self.effect_probe.settle(label))
        result.data = data
        if data.get('effect') == 'unchanged' and self.effect_probe.mode == 'strict':
            result.success = False
            result.message = (
                f"{label}: no screen change near the input within {self.effect_probe.settle_timeout}s "
                "(settings.effect_check: strict; mark the action `effect: none` if that is expected)"
            )
        return result

    @staticmethod
    def _describe_verify(verify: ClickVerify) -> str:
        want_exists = verify.exists is not None
        target = verify.exists if want_exists else verify.not_exists
        described = (target.text or target.image or target.position) if target else None
        return f"{'exists' if want_exists else 'not_exists'} {described!r}"

    async def _execute_click_with_verify(
        self, action: ClickAction, verify: ClickVerify, handler, parent_event_id, event_emitter, action_context: str
    ) -> ActionResult:
        """Click, check ``verify``, and re-resolve + re-click up to ``action.retries`` times.

        Every attempt resolves the target afresh (the one-shot match cache is bypassed for
        retries), so a widget that moved is found again. A failed attempt that never produced
        a click (target not found, QMP error) is not retried: retry is for a click that was
        delivered but had no effect.
        """
        attempts = 1 + max(0, action.retries)
        last_result: ActionResult | None = None
        for attempt in range(1, attempts + 1):
            if attempt > 1:
                # Force a fresh detection: the screen changed since the previous attempt.
                action.target.use_cache = False
                log.warning(f"Click verify failed; retry {attempt - 1}/{action.retries} for {action_context}")
            result: ActionResult = await self.target_resolution.execute_action_with_steps(
                action, handler, parent_event_id, event_emitter, action_context=f"{action_context}_try{attempt}"
            )
            last_result = result
            if not result.success:
                return result

            if await self._click_verified(action, verify):
                result.data = {
                    **(result.data or {}),
                    'click_attempts': attempt,
                    'verified': True,
                    'effect': 'verified',
                }
                return result

        want_exists = verify.exists is not None
        target = verify.exists if want_exists else verify.not_exists
        described = (target.text or target.image or target.position) if target else None
        return ActionResult(
            success=False,
            message=(
                f"Click verify failed after {attempts} attempt(s): "
                f"{'exists' if want_exists else 'not_exists'} {described!r} not satisfied "
                f"within {action.verify_timeout}s"
            ),
            coordinates=last_result.coordinates if last_result else None,
            data={
                **((last_result.data if last_result else None) or {}),
                'click_attempts': attempts,
                'verified': False,
                'effect': 'unchanged',
            },
        )

    async def _click_verified(self, action: ClickAction, verify: ClickVerify) -> bool:
        """Poll ``verify`` for up to ``action.verify_timeout`` seconds (at least one check)."""
        return await self._verify_holds(verify, action.verify_timeout)

    async def _verify_holds(self, verify: ClickVerify, verify_timeout: float) -> bool:
        """Poll a ``verify:`` condition for up to ``verify_timeout`` seconds (at least one check)."""
        want_exists = verify.exists is not None
        target = verify.exists if want_exists else verify.not_exists
        if target is None:
            return True
        if target.strategy is None:
            from adare.types.playbook import BestConfidenceStrategy, TopLeftStrategy

            target.strategy = BestConfidenceStrategy() if target.image else TopLeftStrategy()

        deadline = time.monotonic() + max(0.0, verify_timeout)
        while True:
            screenshot_base64, _ = await self.target_resolution.get_current_screenshot_with_path(
                action_context="verify"
            )
            if screenshot_base64:
                self.target_resolution.begin_resolution()
                match = await self.target_resolution.target_resolver.resolve_target(target, screenshot_base64)
                if (match is not None) == want_exists:
                    return True
            else:
                log.warning("Verify: could not take a screenshot")
            if time.monotonic() >= deadline:
                return False
            await asyncio.sleep(min(0.5, max(0.0, deadline - time.monotonic())))

    async def execute_drag(self, action: DragAction, parent_event_id: str = None, event_emitter=None) -> ActionResult:
        """Execute drag action - special handling for two targets."""
        self.effect_probe.begin_action()
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
            execute_action_id = f"execute_step_{int(time.time() * 1000)}"

            if self.experiment_run_id and event_emitter:
                # Create execution step action
                execute_step = ExecuteAction(
                    description=f"dragging from ({src_coords[0]}, {src_coords[1]}) to ({dst_coords[0]}, {dst_coords[1]})",
                    coordinates=src_coords,  # Use source coordinates
                )

                # Emit execution start event
                start_event = event_emitter.create_action_start_event(
                    execute_step, -1, execute_action_id, parent_event_id
                )
                emit_action(self.experiment_run_id, start_event, execute_action_id)

            # Execute the drag via GUI executor
            if self._effect_checked(action):
                await self.effect_probe.arm([tuple(src_coords), tuple(dst_coords)])
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
                    data={'source_coordinates': src_coords, 'dest_coordinates': dst_coords},
                )
                complete_event = event_emitter.create_action_complete_event(
                    execute_step, -1, execute_action_id, execute_result, parent_event_id
                )
                emit_action(self.experiment_run_id, complete_event, execute_action_id)

            drag_result = ActionResult(
                success=success,
                message=result.get('message', ''),
                coordinates=src_coords,
                # Keep data JSON-serializable: store the targets' descriptors
                # (text/image) rather than the Target objects themselves, which
                # are not JSON-encodable and break DB persistence of the result.
                data={
                    'source': action.src.text or action.src.image,
                    'destination': action.dst.text or action.dst.image,
                    'source_coordinates': src_coords,
                    'dest_coordinates': dst_coords,
                },
            )
            return await self._apply_effect(action, drag_result, 'drag')

        except Exception as e:
            log.error(f"Error executing drag action: {e}", exc_info=True)
            return ActionResult(success=False, message=str(e))

    async def execute_keyboard(
        self, action: KeyboardAction, parent_event_id: str = None, event_emitter=None
    ) -> ActionResult:
        """Execute keyboard action via GUI executor."""
        # Evaluate optional `when` conditions before acting (mirrors execute_block).
        # Skipping is treated as success, matching FlowControlExecutor.execute_block, but is
        # recorded (`skipped`): a negative test after it cannot tell "absent" from "never done".
        self.effect_probe.begin_action()
        if action.when:
            from adare.backend.experiment.target_resolver import MCPConditionChecker

            try:
                screenshot_base64, _ = await self.target_resolution.get_current_screenshot_with_path()
                checker = MCPConditionChecker(self.target_resolution.target_resolver)
                self.target_resolution.begin_resolution()
                conditions_met = await checker.check_conditions(action.when, screenshot_base64)
                if not conditions_met:
                    return ActionResult(
                        success=True, message="Keyboard conditions not met, skipping", data={'skipped': True}
                    )
            except (RuntimeError, OSError, ValueError, TypeError, KeyError) as e:
                log.error(f"Error checking keyboard conditions: {e}")
                return ActionResult(success=False, message=f"Condition check failed: {str(e)}")

        try:
            if (action.key or action.text or action.combination) and self._effect_checked(action):
                await self.effect_probe.arm()
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
                return ActionResult(success=False, message="No key, text, or combination specified")

            # Prepare data for result
            result_data = {}
            if action.key:
                result_data['key'] = action.key
            elif action.text:
                result_data['text'] = action.text
            elif action.combination:
                result_data['combination'] = action.combination

            keyboard_result = ActionResult(
                success=result.get('status') == 'success', message=result.get('message', ''), data=result_data
            )
            return await self._apply_effect(action, keyboard_result, 'keyboard')
        except Exception as e:
            log.error(f"Error executing keyboard action: {e}", exc_info=True)
            return ActionResult(success=False, message=str(e))

    async def execute_idle(self, action: IdleAction, parent_event_id: str = None, event_emitter=None) -> ActionResult:
        """Execute idle action locally without involving the VM."""
        try:
            log.info(f"Starting idle action for {action.duration} seconds (local)")

            # Execute idle locally using asyncio.sleep instead of WebSocket call
            await asyncio.sleep(action.duration)

            log.info(f"Idle action completed locally ({action.duration}s)")

            return ActionResult(success=True, message=f"Idle completed ({action.duration}s)")
        except (asyncio.CancelledError, OSError) as e:
            log.error(f"Idle action failed: {e}")
            return ActionResult(success=False, message=str(e))

    async def execute_scroll(
        self, action: ScrollAction, parent_event_id: str = None, event_emitter=None
    ) -> ActionResult:
        """Execute scroll action via GUI executor."""
        self.effect_probe.begin_action()
        if self._effect_checked(action):
            await self.effect_probe.arm()  # scrolls where the pointer is: the last pointer box
        result = await self.gui_executor.scroll(action.direction, action.amount or 3)
        scroll_result = ActionResult(success=result.get('status') == 'success', message=result.get('message', ''))
        return await self._apply_effect(action, scroll_result, 'scroll')

    async def execute_goto(self, action: GotoAction, parent_event_id: str = None, event_emitter=None) -> ActionResult:
        """Execute goto action with steps."""
        handler = self.get_click_handler('left')  # goto uses left click
        self.effect_probe.begin_action()
        result = await self.target_resolution.execute_action_with_steps(
            action, self._armed(action, handler), parent_event_id, event_emitter, action_context="goto"
        )
        return await self._apply_effect(action, result, 'goto')

    async def execute_screenshot(
        self, action: ScreenshotAction, parent_event_id: str = None, event_emitter=None
    ) -> ActionResult:
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
                    screenshot_base64 = result['image']['data'] if 'data' in result['image'] else result['image']

                    # Save screenshot with custom naming logic
                    screenshot_path = await self._save_explicit_screenshot(screenshot_base64, action.name)
                except (OSError, ValueError, KeyError) as save_error:
                    # Don't fail the action if screenshot save fails, but log it
                    log.warning(f"Failed to save screenshot: {save_error}")

            return ActionResult(
                success=result.get('status') == 'success',
                message=result.get('message', ''),
                data={**result, 'screenshot_path': screenshot_path} if screenshot_path else result,
            )
        except (RuntimeError, OSError, KeyError, ValueError) as e:
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
            return f"reporting/screenshots/{filename}"

        except (OSError, ValueError, binascii.Error) as e:
            log.error(f"Failed to save explicit screenshot: {e}")
            return None
