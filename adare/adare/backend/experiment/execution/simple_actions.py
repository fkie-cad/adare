"""
Executors for simple playbook actions (GUI interactions and system operations).

Includes: click, drag, keyboard, idle, scroll, goto, screenshot, command,
save_timestamp, and pull actions.
"""

import logging
import time
import asyncio
from pathlib import Path
from typing import Optional

from adare.types.playbook import (
    ClickAction, DragAction, KeyboardAction, IdleAction, ScrollAction,
    GotoAction, ScreenshotAction, CommandAction, SaveTimestampAction, PullAction
)
from adare.types.step_actions import ExecuteAction
from adare.backend.events.emitters import emit_action
from .base import ActionResult, serialize_target

log = logging.getLogger(__name__)


class SimpleActionsExecutor:
    """Handles execution of simple playbook actions (GUI and system operations)."""

    def __init__(self, websocket_client, target_resolution_executor, experiment_run_id: Optional[str] = None,
                 playbook = None, execution_context: dict = None, vm = None,
                 experiment_run_directory: Optional[Path] = None):
        """
        Initialize simple actions executor.

        Args:
            websocket_client: Connected WebSocket client to adarevm
            target_resolution_executor: Target resolution executor for finding targets
            experiment_run_id: Experiment run ID for event emission
            playbook: Playbook reference for variable access
            execution_context: Execution context for variable resolution
            vm: VirtualBox VM instance for file operations
            experiment_run_directory: Run directory for artifacts
        """
        self.client = websocket_client
        self.target_resolution = target_resolution_executor
        self.experiment_run_id = experiment_run_id
        self.playbook = playbook
        self.execution_context = execution_context or {}
        self.vm = vm
        self.experiment_run_directory = experiment_run_directory

    def get_click_handler(self, click_type: str):
        """Get the appropriate click handler based on click type."""
        if click_type == 'right':
            return lambda x, y: self.client.right_click(x, y)
        elif click_type == 'double':
            return lambda x, y: self.client.double_click(x, y)
        else:  # 'left' or default
            return lambda x, y: self.client.click(x, y)

    async def execute_click(self, action: ClickAction, parent_event_id: str = None,
                           event_emitter = None) -> ActionResult:
        """Execute click action with steps."""
        handler = self.get_click_handler(action.type)
        return await self.target_resolution.execute_action_with_steps(
            action, handler, parent_event_id, event_emitter
        )

    async def execute_drag(self, action: DragAction, parent_event_id: str = None,
                          event_emitter = None) -> ActionResult:
        """Execute drag action - special handling for two targets."""
        try:
            # Resolve both targets (each will emit their own find steps with proper parent)
            src_coords = await self.target_resolution.resolve_target_with_steps(
                action.src, parent_event_id, event_emitter
            )
            dst_coords = await self.target_resolution.resolve_target_with_steps(
                action.dst, parent_event_id, event_emitter
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

            # Execute the drag
            start_time = time.time()
            result = await self.client.drag(src_coords[0], src_coords[1], dst_coords[0], dst_coords[1])
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
        """Execute keyboard action."""
        try:
            if action.key:
                # Single key press -> pyautogui.press()
                result = await self.client.keyboard("press", action.key)
            elif action.text:
                # Text typing -> pyautogui.typewrite()
                result = await self.client.keyboard("type", action.text)
            elif action.combination:
                # Key combinations -> pyautogui.hotkey()
                combo = "+".join(action.combination)
                result = await self.client.keyboard("hotkey", combo)
            else:
                return ActionResult(
                    success=False,
                    message="No key, text, or combination specified"
                )

            return ActionResult(
                success=result.get('status') == 'success',
                message=result.get('message', '')
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
        """Execute scroll action."""
        result = await self.client.scroll(action.direction, action.amount or 3)
        return ActionResult(success=result.get('status') == 'success')

    async def execute_goto(self, action: GotoAction, parent_event_id: str = None,
                          event_emitter = None) -> ActionResult:
        """Execute goto action with steps."""
        handler = self.get_click_handler('left')  # goto uses left click
        return await self.target_resolution.execute_action_with_steps(
            action, handler, parent_event_id, event_emitter
        )

    async def execute_screenshot(self, action: ScreenshotAction, parent_event_id: str = None,
                                event_emitter = None) -> ActionResult:
        """Execute screenshot action."""
        try:
            result = await self.client.screenshot(
                action.x, action.y, action.width, action.height
            )
            return ActionResult(
                success=result.get('status') == 'success',
                message=result.get('message', ''),
                data=result
            )
        except Exception as e:
            return ActionResult(success=False, message=str(e))

    async def execute_command(self, action: CommandAction, parent_event_id: str = None,
                             event_emitter = None) -> ActionResult:
        """Execute command action."""
        try:
            # Get the command (variables already resolved)
            command = action.command
            cwd = action.cwd
            env = action.env

            # Calculate WebSocket timeout with buffer for long-running commands
            websocket_timeout = None
            if action.timeout:
                # Add 10 second buffer to shell timeout for WebSocket communication
                websocket_timeout = action.timeout + 10

            # Execute raw shell command directly with options
            result = await self.client.execute_shell(
                shell_command=command,
                cwd=cwd,
                env=env,
                timeout=action.timeout,
                shell=action.shell,
                admin=action.admin,
                websocket_timeout=websocket_timeout
            )
            return ActionResult(
                success=result.get('status') == 'success',
                message=result.get('message', ''),
                data=result
            )
        except Exception as e:
            return ActionResult(success=False, message=str(e))

    async def execute_save_timestamp(self, action: SaveTimestampAction, parent_event_id: str = None,
                                    event_emitter = None) -> ActionResult:
        """Save current timestamp to execution context and variable registry."""
        try:
            current_timestamp = time.time()

            # Save to execution context for immediate use
            self.execution_context[action.variable] = current_timestamp

            # Also save to variable registry if available for metadata support
            if hasattr(self.playbook, 'variables') and self.playbook.variables:
                from adarelib.common.variables import Variable, VariableType
                import datetime
                timestamp_dt = datetime.datetime.utcfromtimestamp(current_timestamp)
                timestamp_var = Variable(timestamp_dt, VariableType.TIMESTAMP)
                self.playbook.variables.add(action.variable, timestamp_var)
                log.debug(f"Added timestamp variable '{action.variable}' to variable registry")

            log.info(f"Saved timestamp {current_timestamp} to variable {action.variable}")

            return ActionResult(
                success=True,
                message=f"Timestamp saved to {action.variable}",
                data={action.variable: current_timestamp}
            )
        except Exception as e:
            return ActionResult(success=False, message=str(e))

    async def execute_pull(self, action: PullAction, parent_event_id: str = None,
                          event_emitter = None) -> ActionResult:
        """Pull files/directories from VM to host artifacts directory."""
        try:
            if not self.vm:
                return ActionResult(
                    success=False,
                    message="VM instance not available for pull operation"
                )

            if not self.experiment_run_directory:
                return ActionResult(
                    success=False,
                    message="Experiment run directory not available for pull operation"
                )

            # Create artifacts directory if it doesn't exist
            artifacts_dir = Path(self.experiment_run_directory) / "artifacts"
            artifacts_dir.mkdir(exist_ok=True)
            log.info(f"CLAUDE: Pull operation - artifacts directory: {artifacts_dir}")

            # Determine destination path
            if action.dst:
                # Use custom destination relative to artifacts directory
                dest_path = artifacts_dir / action.dst
                log.info(f"CLAUDE: Pull operation - using custom destination: {action.src} -> {dest_path} (dst specified: {action.dst})")
            else:
                # Preserve full guest path structure relative to artifacts directory
                # Handle both Windows and Linux paths correctly
                guest_path = action.src

                # Handle Windows paths (remove drive letter and convert backslashes)
                if ':' in guest_path:
                    # Windows path like C:\Users\adare\Documents\prefetch.csv
                    # Split by : and take the part after it, then clean up
                    guest_path_cleaned = guest_path.split(':', 1)[1].lstrip('\\').lstrip('/')
                    dest_path = artifacts_dir / guest_path_cleaned.replace('\\', '/')
                else:
                    # Unix path like /tmp/output.txt
                    guest_path_cleaned = guest_path.lstrip('/')
                    dest_path = artifacts_dir / guest_path_cleaned

                log.info(f"CLAUDE: Pull operation - preserving structure: {action.src} -> {dest_path} (cleaned: {guest_path_cleaned})")

            # Create parent directories if they don't exist
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            log.info(f"CLAUDE: Pull operation - created parent directories for: {dest_path.parent}")

            # No internal execution step events needed - main action events handle the spinner

            # Execute the pull operation
            start_time = time.time()
            log.info(f"CLAUDE: Starting pull operation - VM copy_from_guest: guest_path='{action.src}' -> host_path='{dest_path}' (recursive=True)")
            success = await self.vm.copy_from_guest(
                guest_path=action.src,
                host_path=str(dest_path),
                recursive=True
            )
            execution_time = time.time() - start_time
            log.info(f"CLAUDE: Pull operation completed - success={success}, execution_time={execution_time:.2f}s")

            if success:
                log.info(f"CLAUDE: Pull SUCCESS - {action.src} -> {dest_path}")
                log.info(f"Successfully pulled {action.src} to {dest_path}")
                return ActionResult(
                    success=True,
                    message=f"Pulled {action.src} to artifacts/{dest_path.name}",
                    execution_time=execution_time,
                    data={
                        "source": action.src,
                        "destination": str(dest_path),
                        "artifacts_path": f"artifacts/{dest_path.name}"
                    }
                )
            else:
                log.error(f"CLAUDE: Pull FAILED - {action.src} -> {dest_path}")
                return ActionResult(
                    success=False,
                    message=f"Failed to pull {action.src}",
                    execution_time=execution_time
                )

        except Exception as e:
            log.error(f"CLAUDE: Pull EXCEPTION - {action.src} -> {getattr(locals().get('dest_path'), 'path', 'unknown')}: {e}")
            log.error(f"Error in pull operation: {e}")
            return ActionResult(
                success=False,
                message=f"Pull operation failed: {str(e)}"
            )

    async def execute_programmatic_pull(self, src_path: str, description: str = "Programmatic pull") -> ActionResult:
        """
        Execute a pull operation programmatically without a formal PullAction.

        This method is used for auto-pulls triggered by test failures or other
        programmatic scenarios where we need to pull files without explicit
        playbook pull actions.

        Args:
            src_path: Source path on VM to pull from
            description: Description for logging

        Returns:
            ActionResult with pull operation details
        """
        # Create a temporary PullAction for the pull operation
        pull_action = PullAction(
            src=src_path,
            description=description
        )

        # Execute using the existing execute_pull logic
        return await self.execute_pull(pull_action, parent_event_id=None, event_emitter=None)
