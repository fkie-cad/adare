"""
Mixin for data and command playbook actions.

Includes: command, save_timestamp, save_variable, pull, and related helpers.
"""

import logging
import time
from pathlib import Path
from typing import Any, Optional, Dict

from adare.types.playbook import (
    CommandAction, SaveTimestampAction, SaveVariableAction, PullAction,
)
from .base import ActionResult

log = logging.getLogger(__name__)


class DataActionsMixin:
    """Mixin providing data/command action execution methods for SimpleActionsExecutor."""

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
                timestamp_dt = datetime.datetime.fromtimestamp(current_timestamp, datetime.timezone.utc)
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

            effective_mode = self._resolve_pull_mode(action.mode)

            # Process each source file
            for file_idx, src_path in enumerate(src_paths, start=1):
                log.info(f"Pull {file_idx}/{total_files}: {src_path} (mode: {effective_mode})")

                # Determine destination path
                dest_path = self._determine_dest_path(
                    src_path, action.dst, artifacts_dir, total_files, file_idx
                )

                # Execute transfer based on mode
                if effective_mode == 'websocket':
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
                message = f"Successfully pulled {total_files} file(s) via {effective_mode}"
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
                    "mode": effective_mode,
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
