"""
Action and playbook execution methods for DevModeSession.

This module contains the DevModeActionExecutionMixin with methods for
executing individual actions, full playbooks, test function reloading,
MCP server management, and recording.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from adare.backend.experiment.exceptions import ExperimentException
from adare.backend.experiment.mcp_server_manager import MCPServerManager
from adare.backend.experiment.websocket_client import WebSocketTimeoutError
from adare.core.result import Result
from adare.exceptions import LoggedErrorException
from adare.hypervisor.exceptions import HypervisorException
from adare.types.playbook import ActionType, Playbook

if TYPE_CHECKING:
    from adare.backend.experiment.execution.base import ActionResult
    from adare.backend.experiment.playbook_controller import PlaybookExecutionResult

log = logging.getLogger(__name__)


class DevModeActionExecutionMixin:
    """
    Mixin providing action/playbook execution and related operations.

    Depends on attributes from DevModeSessionCore:
        is_running, experiment_ctx, playbook_controller, actions_executed, recorder

    Depends on methods from DevModeSessionCore:
        _ensure_playbook_controller, _command_logger
    """

    async def execute_action(self, action: ActionType) -> ActionResult:
        """
        Execute a single action interactively.

        This directly uses PlaybookController's action executor - no modification needed!
        Variables are resolved via the existing VariableResolver.

        Args:
            action: The action to execute

        Returns:
            ActionResult with success status and details
        """
        if not self.is_running:
            from adare.backend.experiment.execution.base import ActionResult
            return ActionResult(success=False, message="Session not running")

        # Ensure controller is initialized
        controller_result = await self._ensure_playbook_controller()
        if not controller_result.success:
            from adare.backend.experiment.execution.base import ActionResult
            return ActionResult(success=False, message=controller_result.error.message)

        try:
            log.debug(f"Executing action: {action.__class__.__name__}")

            # Execute action via PlaybookController's action_executor
            # This automatically handles:
            # - Variable resolution via VariableResolver
            # - Target resolution via MCPTargetResolver
            # - Action-specific execution logic

            # Wrap in command logger
            action_name = action.__class__.__name__
            with self._command_logger(action_name):
                result = await self.playbook_controller.action_executor.execute_action(
                    action,
                    parent_event_id=None,  # No event tracking in dev mode
                    event_emitter=None,  # No event emission in dev mode
                    variable_resolver=self.playbook_controller.variable_resolver
                )

                if result.success:
                    self.actions_executed += 1
                    log.info(f"Action executed successfully: {action.__class__.__name__}")
                else:
                    log.warning(f"Action failed: {result.message}")

            return result

        except (HypervisorException, ExperimentException) as e:
            log.error(f"Action execution failed: {e}", exc_info=True)
            from adare.backend.experiment.execution.base import ActionResult
            return ActionResult(success=False, message=str(e))
        except (WebSocketTimeoutError, ConnectionError, OSError) as e:
            log.error(f"Action execution failed: {e}", exc_info=True)
            from adare.backend.experiment.execution.base import ActionResult
            return ActionResult(success=False, message=str(e))
        except LoggedErrorException as e:
            log.error(f"Action execution failed: {e}", exc_info=True)
            from adare.backend.experiment.execution.base import ActionResult
            return ActionResult(success=False, message=str(e))

    async def execute_playbook(self, playbook: Playbook, experiment_dir: Path | None = None, indices: list[int] | None = None) -> PlaybookExecutionResult:
        """
        Execute a full playbook (for testing sequences).

        Reuses PlaybookController.execute_playbook() unchanged!

        Args:
            playbook: The playbook to execute
            experiment_dir: Optional path to experiment directory (playbook parent)
            indices: Optional list of 1-based indices to execute

        Returns:
            PlaybookExecutionResult with execution statistics
        """
        if not self.is_running:
            raise RuntimeError("Session not running")

        # Ensure controller is initialized
        controller_result = await self._ensure_playbook_controller()
        if not controller_result.success:
            raise RuntimeError(f"Failed to initialize playbook controller: {controller_result.error.message}")

        # Update experiment directory if provided (crucial for bare sessions)
        if experiment_dir and self.playbook_controller:
            self.playbook_controller.update_experiment_directory(experiment_dir)

        log.info(f"Executing playbook with {len(playbook.actions)} actions")

        # Update playbook reference in controller
        self.playbook_controller.playbook = playbook

        # Update variables if playbook has them
        if playbook.variables:
            var_dict = playbook.variables.to_execution_context(for_tests=False)
            self.playbook_controller.execution_context.update(var_dict)

        # Execute using existing PlaybookController logic
        with self._command_logger("playbook_execution"):
            result = await self.playbook_controller.execute_playbook(indices=indices)

        # Update statistics
        self.actions_executed += result.total_actions

        log.info(
            f"Playbook execution complete: {result.successful_actions}/"
            f"{result.total_actions} actions succeeded"
        )

        return result

    async def reload_testfunctions(self) -> Result[None]:
        """
        Reload test functions from host to VM to enable dynamic updates.

        This packages the current test files from the host and uploads them to the VM again.
        The adarevm agent will extract them to a new temporary directory and use them for subsequent tests.
        """
        if not self.is_running:
            log.warning("Cannot reload test functions: Session not running")
            return Result.fail("SESSION_NOT_RUNNING", "Cannot reload test functions: Session not running")

        with self._command_logger("reload_testfunctions"):
            controller_result = await self._ensure_playbook_controller()
            if not controller_result.success:
                log.warning("Cannot reload test functions: Failed to ensure playbook controller")
                return Result.fail("CONTROLLER_INIT_FAILED", controller_result.error.message)

            if not self.experiment_ctx.client:
                log.warning("Cannot reload test functions: WebSocket client not connected")
                return Result.fail("CONNECTION_FAILED", "Cannot reload test functions: WebSocket client not connected")

            log.info("Reloading test functions from host...")
            try:
                await self.playbook_controller.test_loader.load_tests(self.experiment_ctx.client)

                log.info("Test functions reloaded successfully")
                return Result.ok(None)
            except (WebSocketTimeoutError, ConnectionError, OSError) as e:
                log.error(f"Failed to reload test functions: {e}", exc_info=True)
                return Result.fail("CONNECTION_FAILED", f"Failed to reload test functions: {e}")
            except LoggedErrorException as e:
                log.error(f"Failed to reload test functions: {e}", exc_info=True)
                return Result.fail("RELOAD_FAILED", f"Failed to reload test functions: {e}")

    async def restart_mcp_server(self, debug: bool | None = None, debug_output_dir: Path | None = None) -> Result[None]:
        """
        Restart the MCP GUI server with updated logging options.

        Args:
            debug: Enable debug logging (True/False). If None, keeps current setting.
            debug_output_dir: Directory for debug output. If None and debug=True,
                              tries to allow existing or creates new.

        Returns:
            Result[None] with success or error information
        """
        if not self.experiment_ctx:
            log.error("Cannot restart MCP server: context not initialized")
            return Result.fail("CONTEXT_NOT_INITIALIZED", "Cannot restart MCP server: context not initialized")

        with self._command_logger("restart_mcp_server"):
            log.info("Restarting MCP GUI server...")

            # 1. Stop existing server
            if self.experiment_ctx.mcp_server:
                log.info("Stopping existing MCP server...")
                await self.experiment_ctx.mcp_server.stop(force_external=True)

                # Wait for port to be released
                await asyncio.sleep(1.0)

            # 2. Determine configuration
            # Use provided values or fall back to existing config
            current_server = self.experiment_ctx.mcp_server

            # Debug flag
            new_debug = debug if debug is not None else (current_server.debug if current_server else False)

            # Debug output dir
            new_debug_output_dir = debug_output_dir
            if new_debug_output_dir is None:
                 if current_server and current_server.debug_output_dir:
                     new_debug_output_dir = current_server.debug_output_dir
                 elif new_debug and self.experiment_ctx.experiment_run_directory:
                     # Auto-configure if enabling debug for first time
                     new_debug_output_dir = self.experiment_ctx.experiment_run_directory.screenshots_directory / 'cv_debug'
                     new_debug_output_dir.mkdir(parents=True, exist_ok=True)

            # Log file (keep existing)
            log_file = current_server.log_file if current_server else None
            if not log_file and self.experiment_ctx.experiment_run_directory:
                log_file = self.experiment_ctx.experiment_run_directory.mcp_gui_log_file

            # 3. Create new manager
            log.info(f"Creating new MCP server manager (debug={new_debug}, output={new_debug_output_dir})")
            new_manager = MCPServerManager(
                log_file=log_file,
                debug=new_debug,
                debug_output_dir=new_debug_output_dir
            )

            # 4. Start new server
            try:
                success = await new_manager.start(allow_existing=False)
                if success:
                    self.experiment_ctx.mcp_server = new_manager
                    log.info("MCP GUI server restarted successfully")
                    return Result.ok(None)
                log.error("Failed to start new MCP server")
                return Result.fail("MCP_START_FAILED", "Failed to start new MCP server")
            except (OSError, RuntimeError) as e:
                log.error(f"Error restarting MCP server: {e}", exc_info=True)
                return Result.fail("MCP_RESTART_FAILED", f"Error restarting MCP server: {e}")

    async def stop_mcp_server(self) -> Result[None]:
        """
        Stop the MCP GUI server.

        Returns:
            Result[None] with success or error information
        """
        if not self.experiment_ctx:
            log.error("Cannot stop MCP server: context not initialized")
            return Result.fail("CONTEXT_NOT_INITIALIZED", "Cannot stop MCP server: context not initialized")

        with self._command_logger("stop_mcp_server"):
            if not self.experiment_ctx.mcp_server:
                log.info("MCP server not running")
                return Result.ok(None)

            log.info("Stopping MCP GUI server...")
            try:
                await self.experiment_ctx.mcp_server.stop(force_external=True)
                log.info("MCP GUI server stopped")
                return Result.ok(None)
            except (OSError, RuntimeError) as e:
                log.error(f"Error stopping MCP server: {e}", exc_info=True)
                return Result.fail("MCP_STOP_FAILED", f"Error stopping MCP server: {e}")

    async def start_recording(self, output_file: Path) -> Result[None]:
        """
        Start recording user interactions to a playbook file.

        Args:
            output_file: Path to save the recording (playbook YAML)

        Returns:
            Result[None] with success or error information
        """
        if self.recorder and self.recorder.is_recording:
            log.warning("Recording already in progress")
            return Result.fail("ALREADY_RECORDING", "Recording already in progress")

        if self.experiment_ctx.hypervisor_type != 'qemu':
            log.error("Recording is currently only supported for QEMU")
            return Result.fail("UNSUPPORTED", "Recording is currently only supported for QEMU")

        try:
            from adare.backend.devmode.recorder import SessionRecorder

            self.recorder = SessionRecorder(self.experiment_ctx.vm, output_file)
            await self.recorder.start()
            return Result.ok(None)

        except (OSError, RuntimeError) as e:
            log.error(f"Failed to start recording: {e}", exc_info=True)
            return Result.fail("RECORDING_START_FAILED", f"Failed to start recording: {e}")

    async def stop_recording(self) -> Result[None]:
        """
        Stop current recording session.

        Returns:
            Result[None] with success or error information
        """
        if not self.recorder or not self.recorder.is_recording:
            log.warning("No active recording to stop")
            return Result.fail("NO_RECORDING", "No active recording to stop")

        try:
            await self.recorder.stop()
            self.recorder = None
            return Result.ok(None)
        except (OSError, RuntimeError) as e:
            log.error(f"Failed to stop recording: {e}", exc_info=True)
            return Result.fail("RECORDING_STOP_FAILED", f"Failed to stop recording: {e}")
