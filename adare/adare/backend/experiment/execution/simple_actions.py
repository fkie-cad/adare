"""
Executors for simple playbook actions (GUI interactions and system operations).

Includes: click, drag, keyboard, idle, scroll, goto, screenshot, command,
save_timestamp, and pull actions.
"""

import logging
import time
import asyncio
import base64
import re
from pathlib import Path
from typing import Optional, Dict, Any

from adare.types.playbook import (
    ClickAction, DragAction, KeyboardAction, IdleAction, ScrollAction,
    GotoAction, ScreenshotAction, CommandAction, SaveTimestampAction,
    SaveVariableAction, PullAction, SnapshotFilesystemAction, PullChangedFilesAction
)
from adare.types.step_actions import ExecuteAction
from adare.backend.events.emitters import emit_action
from adare.backend.experiment.filesystem_snapshot import (
    FilesystemSnapshot, calculate_diff
)
from .base import ActionResult, serialize_target

log = logging.getLogger(__name__)


def sanitize_filename(name: str) -> str:
    """
    Sanitize filename to remove invalid characters and ensure safety.

    Args:
        name: Desired filename (without extension)

    Returns:
        Sanitized filename safe for filesystem use
    """
    # Remove or replace invalid characters
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
    # Remove leading/trailing whitespace and dots
    sanitized = sanitized.strip(' .')
    # Limit length to 200 characters (leaves room for extension and path)
    sanitized = sanitized[:200]
    # If empty after sanitization, use fallback
    if not sanitized:
        sanitized = 'screenshot'
    return sanitized


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
            vm: VM instance for file operations and GUI execution mode
            experiment_run_directory: Run directory for artifacts
        """
        self.client = websocket_client
        self.target_resolution = target_resolution_executor
        self.experiment_run_id = experiment_run_id
        self.playbook = playbook
        self.execution_context = execution_context if execution_context is not None else {}
        self.vm = vm
        self.experiment_run_directory = experiment_run_directory
        self.explicit_screenshot_counter = 0  # Counter for explicit screenshot actions
        self.custom_screenshot_counters = {}  # Track counters for custom screenshot names

        # Initialize GUI executor based on VM type and playbook settings
        from .gui_executor_factory import resolve_gui_execution_mode, create_gui_executor
        playbook_settings = playbook.settings if playbook and hasattr(playbook, 'settings') else None
        # Get CLI override from config if available
        cli_override = None
        if execution_context and 'config' in execution_context:
            config = execution_context['config']
            if config and hasattr(config, 'gui_mode_override'):
                cli_override = config.gui_mode_override
        gui_mode = resolve_gui_execution_mode(vm, playbook_settings, cli_override=cli_override)
        self.gui_executor = create_gui_executor(
            mode=gui_mode,
            websocket_client=websocket_client,
            vm=vm,
            target_resolution_executor=target_resolution_executor,
            experiment_run_id=experiment_run_id,
            playbook=playbook,
            execution_context=execution_context,
            experiment_run_directory=experiment_run_directory
        )
        log.info(f"SimpleActionsExecutor initialized with GUI mode: {gui_mode.value}")

    def get_click_handler(self, click_type: str):
        """Get the appropriate click handler based on click type."""
        # Delegate to GUI executor
        return lambda x, y: self.gui_executor.click(x, y, click_type)

    def _process_capture(self, capture_spec, command_result):
        """
        Process command output capture based on capture specification.

        Args:
            capture_spec: CaptureSpec object defining what to capture
            command_result: Result dict from execute_shell containing stdout, stderr, returncode

        Returns:
            Captured and optionally parsed value

        Raises:
            ValueError: If capture processing fails
        """
        from adare.types.playbook import CaptureSpec

        # Extract the output based on source
        if capture_spec.source == 'stdout':
            raw_output = command_result.get('stdout', '')
        elif capture_spec.source == 'stderr':
            raw_output = command_result.get('stderr', '')
        elif capture_spec.source == 'returncode':
            raw_output = command_result.get('returncode', -1)
        elif capture_spec.source == 'all':
            raw_output = {
                'stdout': command_result.get('stdout', ''),
                'stderr': command_result.get('stderr', ''),
                'returncode': command_result.get('returncode', -1)
            }
        else:
            raise ValueError(f"Invalid capture source: {capture_spec.source}")

        # If no parser specified, strip whitespace from string outputs for cleaner variable usage
        if not capture_spec.parser:
            # Auto-strip stdout/stderr to avoid trailing newlines in variable substitution
            if capture_spec.source in ('stdout', 'stderr') and isinstance(raw_output, str):
                return raw_output.strip()
            return raw_output

        # Apply parser expression (user has full control with parser)
        return self._evaluate_parser(capture_spec.parser, raw_output)

    def _evaluate_parser(self, parser_expr: str, raw_output):
        """
        Safely evaluate parser expression with restricted context.

        Args:
            parser_expr: Python expression to evaluate
            raw_output: The output value to parse

        Returns:
            Parsed value

        Raises:
            ValueError: If parser evaluation fails
        """
        import json
        import re

        # Create safe evaluation context
        safe_context = {
            'output': raw_output,
            # Safe utilities
            'json': json,
            're': re,
            'int': int,
            'float': float,
            'str': str,
            'bool': bool,
            'len': len,
            'range': range,
            'enumerate': enumerate,
            'zip': zip,
            'list': list,
            'dict': dict,
            'tuple': tuple,
            'set': set,
            # String methods are available through output.strip(), etc.
        }

        try:
            # Evaluate the parser expression in safe context
            result = eval(parser_expr, {"__builtins__": {}}, safe_context)
            log.debug(f"Parser evaluation successful: '{parser_expr}' -> {result}")
            return result
        except SyntaxError as e:
            raise ValueError(f"Parser syntax error: {e}")
        except NameError as e:
            raise ValueError(f"Parser references undefined name: {e}")
        except Exception as e:
            raise ValueError(f"Parser evaluation failed: {e}")

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
             except:
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

    async def _save_explicit_screenshot(self, screenshot_base64: str, custom_name: Optional[str] = None) -> Optional[str]:
        """
        Save explicit screenshot to disk with custom naming.

        Args:
            screenshot_base64: Base64 encoded screenshot data
            custom_name: Optional custom name for the file (without extension)

        Returns:
            Relative path to saved screenshot (relative to run directory), or None if screenshots_dir not set
        """
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
            
            # Auto-detect raw PowerShell syntax and wrap it for execution
            # This is done here (not in CommandAction) so that the Action object retains 
            # the readable original command for logging purposes.
            shell_command_to_execute = command
            if shell_command_to_execute.lstrip().startswith(('$', '(')):
                import base64
                # UTF-16LE encoding is required for PowerShell Base64 commands
                encoded_cmd = base64.b64encode(shell_command_to_execute.encode('utf-16le')).decode('utf-8')
                # Use -EncodedCommand to avoid all quoting hell
                shell_command_to_execute = f"powershell -EncodedCommand {encoded_cmd}"
                log.debug(f"Auto-wrapped PowerShell command: {command[:50]}... -> powershell -EncodedCommand ...")

            result = await self.client.execute_shell(
                shell_command=shell_command_to_execute,
                cwd=cwd,
                env=env,
                timeout=action.timeout,
                shell=action.shell,
                admin=action.admin,
                websocket_timeout=websocket_timeout
            )

            # Determine command success
            command_succeeded = result.get('status') == 'success'

            # Process capture if specified
            if action.capture:
                try:
                    captured_value = self._process_capture(action.capture, result)

                    # Store in execution context for immediate use
                    self.execution_context[action.capture.variable] = captured_value

                    # Also store in variable registry if available
                    if hasattr(self.playbook, 'variables') and self.playbook.variables:
                        from adarelib.common.variables import Variable
                        captured_var = Variable.auto_infer(captured_value)
                        self.playbook.variables.add(action.capture.variable, captured_var)
                        log.info(f"Captured command output to variable '{action.capture.variable}'")

                except Exception as capture_error:
                    log.error(f"Failed to capture command output: {capture_error}", exc_info=True)
                    # Don't fail the entire command if capture fails
                    return ActionResult(
                        success=False,
                        message=f"Command succeeded but capture failed: {str(capture_error)}",
                        data=result
                    )

            # Handle allow_failure: treat failed commands as successful if allowed
            if not command_succeeded and action.allow_failure:
                log.warning(
                    f"Command failed with exit code {result.get('returncode', 'unknown')} "
                    f"but allow_failure=True, continuing execution. "
                    f"Command: {command}"
                )
                return ActionResult(
                    success=True,  # Report success to continue execution
                    message=f"Command failed (exit code {result.get('returncode', 'unknown')}) but failure allowed",
                    data=result
                )

            return ActionResult(
                success=command_succeeded,
                message=result.get('message', ''),
                data=result
            )
        except Exception as e:
            return ActionResult(success=False, message=str(e))

    async def execute_save_timestamp(self, action: SaveTimestampAction, parent_event_id: str = None,
                                    event_emitter = None) -> ActionResult:
        """Save current VM timestamp with timezone metadata to execution context and variable registry."""
        try:
            # Get timestamp from VM (not host) with timezone detection
            result = await self.client.get_timestamp(use_local=True)
            current_timestamp = result["timestamp"]  # Unix timestamp in UTC
            vm_timezone = result["timezone"]  # e.g., "+01:00" or "UTC"

            # Save to execution context for immediate use
            self.execution_context[action.variable] = current_timestamp

            # Also save to variable registry if available for metadata support
            if hasattr(self.playbook, 'variables') and self.playbook.variables:
                from adarelib.common.variables import Variable, VariableType
                import datetime
                timestamp_dt = datetime.datetime.fromtimestamp(current_timestamp, datetime.UTC)
                timestamp_var = Variable(
                    timestamp_dt,
                    VariableType.TIMESTAMP,
                    metadata={"timezone": vm_timezone}
                )
                self.playbook.variables.add(action.variable, timestamp_var)
                log.debug(f"Added timestamp variable '{action.variable}' with timezone '{vm_timezone}'")

            log.info(f"Saved timestamp {current_timestamp} to variable {action.variable}")

            return ActionResult(
                success=True,
                message=f"Timestamp saved to {action.variable}",
                data={action.variable: current_timestamp}
            )
        except Exception as e:
            return ActionResult(success=False, message=str(e))

    async def execute_save_variable(
        self,
        action: SaveVariableAction,
        parent_event_id: str = None,
        event_emitter = None
    ) -> ActionResult:
        """Save a static value or evaluated expression to execution context and variable registry."""
        import jinja2

        try:
            value = action.value

            # Check if value is a Jinja2 expression that needs evaluation
            if isinstance(value, str) and '{{' in value and '}}' in value:
                evaluated_value = self._evaluate_jinja_expression(value)
            else:
                # Static value - use as-is
                evaluated_value = value

            # Save to execution context for immediate use
            self.execution_context[action.name] = evaluated_value

            # Also save to variable registry if available
            if hasattr(self.playbook, 'variables') and self.playbook.variables:
                from adarelib.common.variables import Variable
                # Use auto_infer to determine the appropriate VariableType
                var = Variable.auto_infer(evaluated_value)
                self.playbook.variables.add(action.name, var)
                log.debug(f"Added variable '{action.name}' to variable registry with type {var.type}")

            log.info(f"Saved value to variable '{action.name}': {evaluated_value}")

            return ActionResult(
                success=True,
                message=f"Variable '{action.name}' set to: {evaluated_value}",
                data={action.name: evaluated_value}
            )
        except jinja2.TemplateError as e:
            return ActionResult(
                success=False,
                message=f"Jinja2 template error: {str(e)}"
            )
        except (ValueError, TypeError) as e:
            return ActionResult(
                success=False,
                message=f"Failed to evaluate expression: {str(e)}"
            )

    def _evaluate_jinja_expression(self, expression: str) -> Any:
        """Evaluate a Jinja2 expression using current execution context.

        Args:
            expression: Jinja2 template string like "{{ counter + 1 }}"

        Returns:
            Evaluated result with appropriate Python type
        """
        import jinja2

        # Create Jinja2 environment with StrictUndefined to catch missing variables
        env = jinja2.Environment(undefined=jinja2.StrictUndefined)

        # Add custom filters from variable registry if available
        if hasattr(self.playbook, 'variables') and self.playbook.variables:
            custom_filters = self.playbook.variables.get_all_jinja_filters()
            env.filters.update(custom_filters)

        template = env.from_string(expression)
        result_str = template.render(self.execution_context)

        # Attempt type coercion for common types
        return self._coerce_result_type(result_str)

    def _coerce_result_type(self, value: str) -> Any:
        """Attempt to coerce string result to appropriate Python type.

        Tries in order: int, float, bool, then keeps as string.
        """
        # Check for boolean
        if value.lower() == 'true':
            return True
        if value.lower() == 'false':
            return False

        # Check for integer
        try:
            return int(value)
        except ValueError:
            pass

        # Check for float
        try:
            return float(value)
        except ValueError:
            pass

        # Keep as string
        return value

    async def execute_pull(self, action: PullAction, parent_event_id: str = None,
                          event_emitter = None) -> ActionResult:
        """Pull files/directories from VM to host artifacts directory.

        Supports:
        - Single or multiple source files
        - Hypervisor (VBoxManage) or WebSocket transfer modes
        - Progress tracking for WebSocket transfers
        """
        try:
            if not self.vm:
                return ActionResult(
                    success=False,
                    message="VM instance not available for pull operation"
                )

            if not self.experiment_run_directory:
                return ActionResult(
                    success=False,
                    message="Experiment run directory not available"
                )

            # Create artifacts directory
            artifacts_dir = Path(self.experiment_run_directory) / "artifacts"
            artifacts_dir.mkdir(exist_ok=True)

            # Normalize src to list
            src_paths = action.src if isinstance(action.src, list) else [action.src]

            # Track results for multi-file transfer
            results = []
            failed_files = []
            total_files = len(src_paths)

            start_time = time.time()

            # Process each source file
            for file_idx, src_path in enumerate(src_paths, start=1):
                log.info(f"Pull {file_idx}/{total_files}: {src_path} (mode: {action.mode})")

                # Determine destination path
                dest_path = self._determine_dest_path(
                    src_path, action.dst, artifacts_dir, total_files, file_idx
                )

                # Execute transfer based on mode
                if action.mode == 'websocket':
                    file_result = await self._pull_via_websocket(
                        src_path, dest_path, file_idx, total_files, event_emitter
                    )
                else:  # hypervisor mode
                    file_result = await self._pull_via_hypervisor(
                        src_path, dest_path
                    )

                results.append(file_result)
                if not file_result["success"]:
                    failed_files.append(src_path)

            execution_time = time.time() - start_time

            # Determine overall success
            success = len(failed_files) == 0

            if success:
                message = f"Successfully pulled {total_files} file(s) via {action.mode}"
            else:
                message = (
                    f"Pulled {total_files - len(failed_files)}/{total_files} files. "
                    f"Failed: {', '.join(failed_files)}"
                )

            return ActionResult(
                success=success,
                message=message,
                execution_time=execution_time,
                data={
                    "mode": action.mode,
                    "total_files": total_files,
                    "successful_files": total_files - len(failed_files),
                    "failed_files": failed_files,
                    "file_results": results
                }
            )

        except Exception as e:
            log.error(f"Pull operation failed: {e}", exc_info=True)
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

    def _determine_dest_path(self, src_path: str, custom_dst: Optional[str],
                            artifacts_dir: Path, total_files: int,
                            file_idx: int) -> Path:
        """Determine destination path for a file."""
        if custom_dst and total_files == 1:
            # Single file with custom destination
            return artifacts_dir / custom_dst
        elif custom_dst and total_files > 1:
            # Multiple files with custom destination prefix
            filename = Path(src_path).name
            return artifacts_dir / custom_dst / filename
        else:
            # Preserve guest path structure
            guest_path = src_path
            if ':' in guest_path:  # Windows path
                guest_path_cleaned = guest_path.split(':', 1)[1].lstrip('\\').lstrip('/')
                return artifacts_dir / guest_path_cleaned.replace('\\', '/')
            else:  # Unix path
                guest_path_cleaned = guest_path.lstrip('/')
                return artifacts_dir / guest_path_cleaned

    async def _pull_via_websocket(self, src_path: str, dest_path: Path,
                                  file_idx: int, total_files: int,
                                  event_emitter) -> Dict[str, Any]:
        """Pull file via WebSocket with chunked transfer."""
        try:
            # Progress callback for logging
            def progress_callback(chunk_idx, total_chunks, bytes_xfer, total_bytes):
                log.info(
                    f"Transfer progress [{file_idx}/{total_files}]: "
                    f"chunk {chunk_idx + 1}/{total_chunks} "
                    f"({bytes_xfer}/{total_bytes} bytes, "
                    f"{(bytes_xfer/total_bytes*100):.1f}%)"
                )

            result = await self.client.pull_file_chunked(
                guest_path=src_path,
                host_path=dest_path,
                progress_callback=progress_callback
            )

            return {
                "success": True,
                "source": src_path,
                "destination": str(dest_path),
                "file_size": result["file_size"],
                "chunks": result["chunks_transferred"],
                "metadata": result.get("metadata", {})
            }

        except Exception as e:
            log.error(f"WebSocket pull failed for {src_path}: {e}")
            return {
                "success": False,
                "source": src_path,
                "error": str(e)
            }

    async def _pull_via_hypervisor(self, src_path: str, dest_path: Path) -> Dict[str, Any]:
        """Pull file via VBoxManage (existing method)."""
        try:
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            success = await self.vm.copy_from_guest(
                guest_path=src_path,
                host_path=str(dest_path),
                recursive=True
            )

            if success:
                file_size = dest_path.stat().st_size if dest_path.is_file() else 0
                return {
                    "success": True,
                    "source": src_path,
                    "destination": str(dest_path),
                    "file_size": file_size
                }
            else:
                return {
                    "success": False,
                    "source": src_path,
                    "error": "VBoxManage copy_from_guest returned False"
                }

        except Exception as e:
            log.error(f"Hypervisor pull failed for {src_path}: {e}")
            return {
                "success": False,
                "source": src_path,
                "error": str(e)
            }

    async def execute_snapshot_filesystem(self, action: SnapshotFilesystemAction,
                                          parent_event_id: str = None,
                                          event_emitter = None) -> ActionResult:
        """
        Execute filesystem snapshot action.

        Captures filesystem state (file list + timestamps) and stores in variable.
        Uses native WebSocket tool instead of shelling out to Python.
        """
        from datetime import datetime, timezone

        try:
            # Determine OS type from VM
            os_type = None
            if self.vm and hasattr(self.vm, 'guest_os'):
                os_type = self.vm.guest_os

            if not os_type:
                return ActionResult(
                    success=False,
                    message="Cannot determine VM OS type for filesystem snapshot"
                )

            log.info(f"Capturing filesystem snapshot for {os_type} (variable: {action.variable})")

            # Set appropriate timeout for snapshot (can take several minutes for large drives)
            snapshot_timeout = action.timeout if action.timeout else 600.0  # Default 10 minutes

            # Use native WebSocket tool instead of shell command
            result = await self.client.get_filesystem_snapshot(
                root_path=action.root_path or '/',
                timeout=snapshot_timeout + 60  # Add buffer for WebSocket timeout
            )

            # Check result status
            if result.get('status') != 'success':
                error_msg = result.get('message', 'Unknown error')

                # Enhanced error handling for MFT privilege issues
                if 'Administrator privileges required' in error_msg:
                    return ActionResult(
                        success=False,
                        message=(
                            "MFT snapshot requires Administrator privileges. "
                            "Please ensure adarevm is running as Administrator in the VM."
                        )
                    )

                return ActionResult(
                    success=False,
                    message=f"Snapshot failed: {error_msg}"
                )

            # Extract files directly from result (already parsed JSON)
            files = result.get('snapshot', {})
            log.info(f"Snapshot captured {len(files)} files")

            # Create snapshot object
            snapshot = FilesystemSnapshot(
                files=files,
                timestamp=datetime.now(timezone.utc).isoformat(),
                os_type=os_type
            )

            # Store in execution context
            self.execution_context[action.variable] = snapshot

            # Also store in variable registry if available
            if hasattr(self.playbook, 'variables') and self.playbook.variables:
                from adarelib.common.variables import Variable
                snapshot_var = Variable(value=snapshot, type='object')
                self.playbook.variables.add(action.variable, snapshot_var)
                log.info(f"Stored snapshot in variable '{action.variable}'")

            return ActionResult(
                success=True,
                message=f"Captured filesystem snapshot ({len(files)} files) in variable '{action.variable}'",
                data={
                    'variable': action.variable,
                    'file_count': len(files),
                    'os_type': os_type
                }
            )

        except Exception as e:
            log.error(f"Error executing snapshot_filesystem action: {e}", exc_info=True)
            return ActionResult(success=False, message=str(e))

    async def execute_pull_changed_files(self, action: PullChangedFilesAction,
                                        parent_event_id: str = None,
                                        event_emitter = None) -> ActionResult:
        """
        Execute pull_changed_files action.

        Retrieves two snapshots from variable registry, calculates diff,
        and pulls all changed/added files in batch.
        """
        try:
            # 1. Retrieve snapshots from execution context
            snapshot_before = self.execution_context.get(action.snapshot_before)
            snapshot_after = self.execution_context.get(action.snapshot_after)

            # Validate snapshots exist
            if snapshot_before is None:
                return ActionResult(
                    success=False,
                    message=f"Snapshot variable '{action.snapshot_before}' not found in execution context"
                )

            if snapshot_after is None:
                return ActionResult(
                    success=False,
                    message=f"Snapshot variable '{action.snapshot_after}' not found in execution context"
                )

            # Validate snapshot types
            if not isinstance(snapshot_before, FilesystemSnapshot):
                return ActionResult(
                    success=False,
                    message=f"Variable '{action.snapshot_before}' is not a FilesystemSnapshot object"
                )

            if not isinstance(snapshot_after, FilesystemSnapshot):
                return ActionResult(
                    success=False,
                    message=f"Variable '{action.snapshot_after}' is not a FilesystemSnapshot object"
                )

            log.info(
                f"Computing diff between snapshots: "
                f"{action.snapshot_before} ({len(snapshot_before.files)} files) -> "
                f"{action.snapshot_after} ({len(snapshot_after.files)} files)"
            )

            # 2. Calculate diff
            diff = calculate_diff(snapshot_before, snapshot_after)

            # 3. Build file list based on include flags
            files_to_pull = []

            if action.include_modified:
                modified_paths = [item['path'] for item in diff['modified']]
                files_to_pull.extend(modified_paths)
                log.info(f"Including {len(modified_paths)} modified files")

            if action.include_added:
                added_paths = [item['path'] for item in diff['added']]
                files_to_pull.extend(added_paths)
                log.info(f"Including {len(added_paths)} added files")

            # Check if there are files to pull
            if not files_to_pull:
                log.info("No changed files to pull")
                return ActionResult(
                    success=True,
                    message="No changed files found between snapshots",
                    data={
                        'modified_count': len(diff['modified']),
                        'added_count': len(diff['added']),
                        'files_pulled': 0
                    }
                )

            log.info(f"Total files to pull: {len(files_to_pull)}")

            # 4. Ensure experiment run directory exists
            if not self.experiment_run_directory:
                return ActionResult(
                    success=False,
                    message="Experiment run directory not available"
                )

            # Create destination directory
            dest_dir = Path(self.experiment_run_directory) / "artifacts" / action.dst
            dest_dir.mkdir(parents=True, exist_ok=True)

            log.info(f"Destination directory: {dest_dir}")

            # 5. Execute transfer based on mode
            start_time = time.time()

            if action.mode == 'websocket':
                # Use batch chunked transfer
                result = await self._pull_changed_files_websocket(
                    files_to_pull, dest_dir, event_emitter
                )
            else:  # hypervisor mode
                result = await self._pull_changed_files_hypervisor(
                    files_to_pull, dest_dir
                )

            execution_time = time.time() - start_time

            # 6. Prepare result
            success = result['success_count'] > 0

            if result['failed_count'] == 0:
                message = (
                    f"Successfully pulled {result['success_count']} changed files "
                    f"via {action.mode} ({result['total_bytes']} bytes)"
                )
            else:
                message = (
                    f"Pulled {result['success_count']}/{len(files_to_pull)} files "
                    f"({result['failed_count']} failed)"
                )

            return ActionResult(
                success=success,
                message=message,
                execution_time=execution_time,
                data={
                    'mode': action.mode,
                    'snapshot_before': action.snapshot_before,
                    'snapshot_after': action.snapshot_after,
                    'total_files': len(files_to_pull),
                    'success_count': result['success_count'],
                    'failed_count': result['failed_count'],
                    'total_bytes': result['total_bytes'],
                    'failures': result['failures'],
                    'modified_count': len(diff['modified']) if action.include_modified else 0,
                    'added_count': len(diff['added']) if action.include_added else 0,
                    'destination': str(dest_dir)
                }
            )

        except Exception as e:
            log.error(f"Error executing pull_changed_files action: {e}", exc_info=True)
            return ActionResult(success=False, message=str(e))

    async def _pull_changed_files_websocket(self, file_paths: list, dest_dir: Path,
                                           event_emitter) -> Dict[str, Any]:
        """Pull changed files via WebSocket with batch chunked transfer."""
        try:
            # Progress callback for logging
            def progress_callback(file_idx, total_files, file_path,
                                chunk_idx, total_chunks, bytes_xfer, file_size):
                # Calculate overall progress percentage
                overall_progress = (file_idx - 1) / total_files * 100
                file_progress = bytes_xfer / file_size * 100 if file_size > 0 else 0

                log.info(
                    f"Transfer progress: file {file_idx}/{total_files} "
                    f"({overall_progress:.1f}% overall) - "
                    f"chunk {chunk_idx + 1}/{total_chunks} "
                    f"({bytes_xfer}/{file_size} bytes, {file_progress:.1f}%)"
                )

            # Call batch pull method
            result = await self.client.pull_multiple_files_chunked(
                guest_paths=file_paths,
                host_dest_dir=dest_dir,
                progress_callback=progress_callback
            )

            return result

        except Exception as e:
            log.error(f"WebSocket batch pull failed: {e}")
            return {
                'success_count': 0,
                'failed_count': len(file_paths),
                'total_files': len(file_paths),
                'total_bytes': 0,
                'failures': [{'path': p, 'error': str(e)} for p in file_paths],
                'file_results': []
            }

    async def _pull_changed_files_hypervisor(self, file_paths: list, dest_dir: Path) -> Dict[str, Any]:
        """Pull changed files via VBoxManage (hypervisor mode)."""
        if not self.vm:
            return {
                'success_count': 0,
                'failed_count': len(file_paths),
                'total_files': len(file_paths),
                'total_bytes': 0,
                'failures': [{'path': p, 'error': 'VM instance not available'} for p in file_paths],
                'file_results': []
            }

        success_count = 0
        failed_count = 0
        total_bytes = 0
        failures = []
        file_results = []

        for file_idx, guest_path in enumerate(file_paths, start=1):
            try:
                log.info(f"Pulling file {file_idx}/{len(file_paths)}: {guest_path}")

                # Preserve directory structure
                if ':' in guest_path:  # Windows path
                    guest_path_cleaned = guest_path.split(':', 1)[1].lstrip('\\').lstrip('/')
                    relative_path = guest_path_cleaned.replace('\\', '/')
                else:  # Unix path
                    relative_path = guest_path.lstrip('/')

                host_path = dest_dir / relative_path
                host_path.parent.mkdir(parents=True, exist_ok=True)

                # Use VBoxManage to copy file
                success = await self.vm.copy_from_guest(
                    guest_path=guest_path,
                    host_path=str(host_path),
                    recursive=False
                )

                if success:
                    file_size = host_path.stat().st_size if host_path.is_file() else 0
                    success_count += 1
                    total_bytes += file_size

                    file_results.append({
                        'path': guest_path,
                        'success': True,
                        'destination': str(host_path),
                        'file_size': file_size
                    })

                    log.info(f"Successfully pulled {guest_path} ({file_size} bytes)")
                else:
                    failed_count += 1
                    error_msg = "VBoxManage copy_from_guest returned False"
                    failures.append({'path': guest_path, 'error': error_msg})
                    file_results.append({'path': guest_path, 'success': False, 'error': error_msg})

            except Exception as e:
                failed_count += 1
                error_msg = str(e)
                log.error(f"Hypervisor pull failed for {guest_path}: {error_msg}")
                failures.append({'path': guest_path, 'error': error_msg})
                file_results.append({'path': guest_path, 'success': False, 'error': error_msg})

        return {
            'success_count': success_count,
            'failed_count': failed_count,
            'total_files': len(file_paths),
            'total_bytes': total_bytes,
            'failures': failures,
            'file_results': file_results
        }
