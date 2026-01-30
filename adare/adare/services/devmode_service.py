"""
DevMode Service - Business logic for development mode operations.

This service handles dev mode session operations and returns Result[T] objects
that can be consumed by any frontend (CLI, Web UI, REST API).
"""

import asyncio
import logging
import sys
import time
import yaml
from pathlib import Path
from typing import List, Optional

from adare.backend.devmode.manager import DevModeSessionManager
from adare.backend.devmode.session import DevModeSnapshot
from adare.backend.experiment import database as experiment_database
from adare.backend.environment import database as environment_database
from adare.backend.environment.exceptions import EnvironmentDoesNotExistInDatabase
from adare.database.api.devmode import DevModeApi
from adare.types.playbook import parse_playbook, _structure_action
from adare.core.result import Result
from adare.core.dto.devmode import (
    DevSessionStartRequest,
    DevSessionStopRequest,
    DevActionExecuteRequest,
    DevPlaybookExecuteRequest,
    DevResetRequest,
    DevCheckpointCreateRequest,
    DevCheckpointDeleteRequest,
    DevCheckpointRestoreRequest,
    DevCheckpointListRequest,
    DevSessionListRequest,
    DevSessionStateRequest,
    DevSessionCleanupRequest,
    DevSessionInfo,
    DevActionResult,
    DevPlaybookResult,
    DevSessionListItem,
    DevCheckpointInfo,
    DevResetResult,
    DevCleanupResult,
    DevSessionRecordRequest,
    DevUpdateTestfunctionsRequest,
    DevUpdateTestfunctionsResult,
    DevCVRestartRequest,
    DevCVStopRequest,
)

log = logging.getLogger(__name__)


class DevModeService:
    """
    Service for development mode operations.

    Provides a synchronous API over the async DevModeSessionManager,
    with database persistence and multi-source input support.
    """

    def __init__(self):
        """Initialize the DevMode service."""
        self._manager = DevModeSessionManager()
        self._db_api = DevModeApi()

    # =========================================================================
    # Session Management
    # =========================================================================

    def start_session(self, request: DevSessionStartRequest) -> Result[DevSessionInfo]:
        """
        Create and start a new dev mode session.

        This method always creates a new session with a unique ID.
        To resume an existing stopped session, use resume_session() instead.

        Args:
            request: DevSessionStartRequest with project path and environment name

        Returns:
            Result[DevSessionInfo] with session details on success,
            or error information on failure
        """
        try:
            # Validate environment exists
            try:
                environment_ulid = environment_database.resolve_environment_identifier(
                    request.environment_name
                )
            except EnvironmentDoesNotExistInDatabase:
                return Result.fail(
                    "ENVIRONMENT_NOT_FOUND",
                    f"Environment '{request.environment_name}' not found",
                    [
                        "Check available environments with: adare environment list",
                        f"Load environment with: adare environment load <environment.yml>"
                    ]
                )

            # Check hypervisor type
            hypervisor = environment_database.get_environment_hypervisor(environment_ulid)
            if hypervisor == 'virtualbox':
                raise NotImplementedError(
                    "Dev mode start is not yet implemented for VirtualBox environments. "
                    "Please use QEMU/KVM for now."
                )

            # Create session via manager (async)
            session_id = asyncio.run(self._manager.create_session(
                request.project_path,
                request.environment_name,
                gui_mode=request.gui_mode,
                vm_memory=request.vm_memory,
                vm_cpus=request.vm_cpus,
                debug_screenshots=request.debug_screenshots,
                console_ulid=request.console_ulid,
                shared_directories=request.shared_directories
            ))

            # Get session to retrieve VM name
            session = self._manager.get_session(session_id)
            if not session or not session.experiment_ctx:
                return Result.fail(
                    "SESSION_START_FAILED",
                    "Session created but context not initialized",
                    ["Try starting the session again"]
                )

            vm_name = session.experiment_ctx.vm_name

            # Get experiment name (defaults to "_dev_session" for bare sessions)
            experiment_name = session.experiment_ctx.config.experiment_name or "_dev_session"

            # Persist to database
            self._db_api.save_session(
                session_id=session_id,
                project_path=request.project_path,
                experiment_name=experiment_name,
                environment_name=request.environment_name,
                vm_name=vm_name
            )

            # Store run directory path (prevents "None" directories on restoration)
            if session.run_directory_path:
                self._db_api.update_session_run_path(session_id, str(session.run_directory_path))
                log.info(f"CLAUDE: Stored run directory path for session {session_id}: {session.run_directory_path}")

            # Store overlay disk path (critical for preventing base disk deletion)
            if session.experiment_ctx.vm and hasattr(session.experiment_ctx.vm, 'config'):
                overlay_path = str(session.experiment_ctx.vm.config.disk_path)
                self._db_api.update_session_overlay_path(session_id, overlay_path)
                log.info(f"Stored overlay disk path for session {session_id}: {overlay_path}")

            # Get session state for response
            state = session.get_state()

            next_steps = [
                f"Execute single action: adare dev action {session_id} -y '<action_yaml>'",
                f"Execute playbook: adare dev playbook {session_id} -f <playbook.yml>",
                f"View session state: adare dev state {session_id}",
                f"Reset session: adare dev reset-soft {session_id}  (or reset-hard)",
                f"Stop session: adare dev stop {session_id}"
            ]

            tip = "Use 'adare dev checkpoint-create' to save snapshots before risky operations"

            return Result.ok(DevSessionInfo(
                session_id=state.session_id,
                project_path=request.project_path,
                environment_name=state.environment_name,
                vm_running=state.vm_running,
                actions_executed=state.actions_executed,
                created_at=self._db_api.get_session(session_id).created_at,
                current_variables=state.current_variables,
                available_snapshots=state.available_snapshots,
                experiment_name=None,
                next_steps=next_steps,
                tip=tip
            ))

        except RuntimeError as e:
            return Result.fail(
                "SESSION_START_FAILED",
                f"Failed to start dev mode session: {str(e)}",
                [
                    "Check VM exists: adare vm list",
                    "Check hypervisor (VirtualBox/QEMU) is running",
                    "Check experiment and environment configuration"
                ]
            )
        except Exception as e:
            log.error(f"Unexpected error starting dev session: {e}", exc_info=True)
            return Result.fail(
                "INTERNAL_ERROR",
                f"Unexpected error: {str(e)}",
                ["Check logs for details"]
            )

    def resume_session(self, session_id: str, console_ulid: Optional[str] = None) -> Result[DevSessionInfo]:
        """
        Resume a stopped dev mode session.

        This method:
        1. Validates the session exists and is stopped
        2. Validates VM resources (disk files, checkpoints) exist
        3. Calls restore_and_restart_session() to restart VM and reconnect
        4. Returns session info with preserved state

        Args:
            session_id: Session ID to resume
            console_ulid: Optional flow console ULID for event integration

        Returns:
            Result[DevSessionInfo] with resumed session details on success,
            or error information on failure
        """
        try:
            # Validate session exists and is stopped
            db_session = self._db_api.get_session(session_id)
            if not db_session:
                return Result.fail(
                    "SESSION_NOT_FOUND",
                    f"Session '{session_id}' not found in database",
                    ["Check available sessions with: adare dev list"]
                )

            # Check if already running
            if db_session.status == 'running':
                return Result.fail(
                    "SESSION_ALREADY_RUNNING",
                    f"Session '{session_id}' is already running",
                    [
                        f"Use existing session: adare dev action {session_id} -y '<action>'",
                        f"Or stop and restart: adare dev stop {session_id}"
                    ]
                )

            if db_session.status != 'stopped':
                return Result.fail(
                    "SESSION_NOT_STOPPED",
                    f"Session '{session_id}' has status '{db_session.status}', expected 'stopped'",
                    [
                        "Only stopped sessions can be resumed",
                        f"Current status: {db_session.status}"
                    ]
                )

            # Validate VM resources exist
            validation_result = self._validate_vm_resources(db_session)
            if not validation_result.is_success:
                return validation_result

            # Resume session via manager (async)
            log.info(f"Resuming stopped session {session_id}...")
            session = asyncio.run(
                self._manager.restore_and_restart_session(session_id, console_ulid)
            )

            if not session:
                return Result.fail(
                    "SESSION_RESUME_FAILED",
                    f"Failed to resume session '{session_id}'",
                    [
                        "Check VM exists and can be started",
                        "Check hypervisor (VirtualBox/QEMU) is running",
                        "Check logs for details"
                    ]
                )

            # Get session state for response
            state = session.get_state()

            # Count checkpoints
            checkpoints = self._db_api.list_checkpoints(session_id)

            next_steps = [
                f"Execute single action: adare dev action {session_id} -y '<action_yaml>'",
                f"Execute playbook: adare dev playbook {session_id} -f <playbook.yml>",
                f"View session state: adare dev state {session_id}",
                f"Reset session: adare dev reset-soft {session_id}  (or reset-hard)",
                f"Stop session: adare dev stop {session_id}"
            ]

            tip = f"Session resumed with {len(state.current_variables)} variables and {len(checkpoints)} checkpoints preserved"

            return Result.ok(DevSessionInfo(
                session_id=state.session_id,
                project_path=Path(db_session.project_path),
                experiment_name=state.experiment_name,
                environment_name=state.environment_name,
                vm_running=state.vm_running,
                actions_executed=state.actions_executed,
                created_at=db_session.created_at,
                current_variables=state.current_variables,
                available_snapshots=state.available_snapshots,
                next_steps=next_steps,
                tip=tip
            ))

        except Exception as e:
            log.error(f"Unexpected error resuming session: {e}", exc_info=True)
            return Result.fail(
                "INTERNAL_ERROR",
                f"Unexpected error: {str(e)}",
                ["Check logs for details"]
            )

    def resume_most_recent(self, project_path: Path, console_ulid: Optional[str] = None) -> Result[DevSessionInfo]:
        """
        Resume the most recently stopped session for the project.

        This is used when 'adare dev resume' is called without a session ID.
        It finds the most recent stopped session (any experiment, any environment)
        and resumes it.

        Args:
            project_path: Path to the project
            console_ulid: Optional flow console ULID for event integration

        Returns:
            Result[DevSessionInfo] with resumed session details on success,
            or error information on failure
        """
        try:
            # Get most recent stopped session (any experiment, any environment)
            stopped_sessions = self._db_api.list_sessions(project_path, status='stopped')

            if not stopped_sessions:
                return Result.fail(
                    "NO_STOPPED_SESSIONS",
                    "No stopped sessions found in project",
                    [
                        "Check available sessions: adare dev list",
                        "Create new session: adare dev start <experiment> -e <environment>"
                    ]
                )

            # Get most recent (list is already ordered by updated_at desc from list_sessions)
            most_recent = stopped_sessions[0]

            log.info(f"Resuming most recent stopped session: {most_recent.session_id}")

            # Resume the session
            return self.resume_session(most_recent.session_id, console_ulid)

        except Exception as e:
            log.error(f"Unexpected error resuming most recent session: {e}", exc_info=True)
            return Result.fail(
                "INTERNAL_ERROR",
                f"Unexpected error: {str(e)}",
                ["Check logs for details"]
            )

    async def _stop_session_async(self, request: DevSessionStopRequest):
        """Async helper for stopping session - keeps everything in same event loop."""

        # For removal: check if session is in memory first
        if request.remove_resources:
            session = self._manager._sessions.get(request.session_id)

            if session:
                # Session is running in memory - do graceful shutdown
                await self._manager.stop_and_remove_session(request.session_id)
                return 'removed'
            else:
                # Session not in memory - load minimal infrastructure for cleanup
                # This works regardless of whether the VM is running or stopped
                log.info(f"Loading session {request.session_id} infrastructure for cleanup")
                session = await self._manager.load_session_for_cleanup(request.session_id)
                
                if session:
                    # Loaded successfully - do full cleanup
                    # stop_and_remove() handles VM stop/destroy and file deletion
                    # regardless of the actual VM state (safe to call on stopped VM)
                    await session.stop_and_remove()
                    return 'removed'
                else:
                    # Could not load infrastructure - DB state might be corrupted
                    # or environment invalid. Fallback to DB-only cleanup.
                    log.warning(
                        f"Could not load infrastructure for session {request.session_id}. "
                        f"Performing database-only cleanup."
                    )
                    return 'removed_from_db_only'
        else:
            # For stop without removal: we need the session object for graceful shutdown
            session = await self._manager.get_or_restore_session(request.session_id)

            if not session:
                return None  # Already stopped

            await self._manager.shutdown_session(request.session_id)
            return 'stopped'

    def stop_session(self, request: DevSessionStopRequest) -> Result[bool]:
        """
        Stop a dev mode session.

        Args:
            request: DevSessionStopRequest with session ID and cleanup flag

        Returns:
            Result[bool] with True on success
        """
        try:
            # Check session exists in database
            if not self._db_api.session_exists(request.session_id):
                return Result.fail(
                    "SESSION_NOT_FOUND",
                    f"Dev session '{request.session_id}' not found",
                    ["Check active sessions with: adare dev list"]
                )

            # Single asyncio.run() for entire flow
            # Note: If VM is running but session not in memory, _stop_session_async
            # will automatically restore the session first before removal
            result = asyncio.run(self._stop_session_async(request))

            if result == 'removed':
                # Delete database entry (cascades to checkpoints)
                self._db_api.delete_session(request.session_id)
            elif result == 'removed_from_db_only':
                # Session wasn't running, just clean up database
                log.info(f"Cleaning up database records for stopped session {request.session_id}")
                self._db_api.delete_session(request.session_id)
            elif result == 'stopped':
                # Mark as stopped in database (keep entry)
                self._db_api.update_session_status(request.session_id, 'stopped')
            elif result is None:
                # Already stopped, just update status
                self._db_api.update_session_status(request.session_id, 'stopped')

            return Result.ok(True)

        except Exception as e:
            log.error(f"Error stopping dev session: {e}", exc_info=True)
            return Result.fail(
                "INTERNAL_ERROR",
                f"Unexpected error: {str(e)}",
                ["Check logs for details"]
            )

    def record_session(self, request: DevSessionRecordRequest) -> Result[bool]:
        """
        Start recording a dev session.
        
        Args:
            request: DevSessionRecordRequest
            
        Returns:
            Result[bool]
        """
        try:
            # Check session exists
            if not self._db_api.session_exists(request.session_id):
                return Result.fail("SESSION_NOT_FOUND", f"Session '{request.session_id}' not found")
                
            # Get or restore session
            session = asyncio.run(self._manager.get_or_restore_session(request.session_id))
            if not session:
                return Result.fail("SESSION_RESTORE_FAILED", "Failed to restore session")
                
            if not session.is_running:
                return Result.fail("SESSION_NOT_RUNNING", "Session must be running to record")
                
            # Start recording
            success = asyncio.run(session.start_recording(request.output_file))
            if not success:
               return Result.fail("RECORD_START_FAILED", "Failed to start recording (check logs)")
               
            return Result.ok(True)
            
        except Exception as e:
            log.error(f"Error starting recording: {e}", exc_info=True)
            return Result.fail("INTERNAL_ERROR", str(e))

    def stop_recording_session(self, session_id: str) -> Result[bool]:
        """
        Stop recording a dev session.
        
        Args:
            session_id: Session ID
            
        Returns:
            Result[bool]
        """
        try:
             # Get or restore session (should be in memory if we are same process)
            session = asyncio.run(self._manager.get_or_restore_session(session_id))
            if not session:
                return Result.fail("SESSION_NOT_FOUND", "Session not found")
                
            success = asyncio.run(session.stop_recording())
            if not success:
                return Result.fail("RECORD_STOP_FAILED", "Failed to stop recording")
                
            return Result.ok(True)
        except Exception as e:
            log.error(f"Error stopping recording: {e}", exc_info=True)
            return Result.fail("INTERNAL_ERROR", str(e))


    def list_sessions(self, request: DevSessionListRequest) -> Result[List[DevSessionListItem]]:
        """
        List all dev mode sessions (running, stopped, crashed).

        Args:
            request: DevSessionListRequest with optional project filter

        Returns:
            Result[List[DevSessionListItem]] with session list
        """
        try:
            # Get ALL sessions from database (not just running)
            db_sessions = self._db_api.list_sessions(request.project_path)

            # Build list items
            items = []
            for db_session in db_sessions:
                # Try to get live state from manager
                session = self._manager.get_session(db_session.session_id)

                if session:
                    state = session.get_state()
                    vm_running = state.vm_running
                    actions_executed = state.actions_executed
                else:
                    # Session not in manager
                    vm_running = False
                    actions_executed = 0

                items.append(DevSessionListItem(
                    session_id=db_session.session_id,
                    experiment_name=db_session.experiment_name,
                    environment_name=db_session.environment_name,
                    vm_running=vm_running,
                    actions_executed=actions_executed,
                    created_at=db_session.created_at,
                    project_path=Path(db_session.project_path),
                    status=db_session.status
                ))

            return Result.ok(items)

        except Exception as e:
            log.error(f"Error listing dev sessions: {e}", exc_info=True)
            return Result.fail(
                "INTERNAL_ERROR",
                f"Unexpected error: {str(e)}",
                ["Check logs for details"]
            )

    def get_state(self, request: DevSessionStateRequest) -> Result[DevSessionInfo]:
        """
        Get current session state.

        Args:
            request: DevSessionStateRequest with session ID

        Returns:
            Result[DevSessionInfo] with current state
        """
        try:
            # Check session exists in database
            db_session = self._db_api.get_session(request.session_id)
            if not db_session:
                return Result.fail(
                    "SESSION_NOT_FOUND",
                    f"Dev session '{request.session_id}' not found",
                    ["Check active sessions with: adare dev list"]
                )

            # Get or restore session from manager
            session = asyncio.run(self._manager.get_or_restore_session(request.session_id))
            if not session:
                return Result.fail(
                    "SESSION_RESTORATION_FAILED",
                    f"Session '{request.session_id}' exists in database but could not be restored",
                    [
                        "VM may not be running - check with virsh list (QEMU) or VBoxManage list runningvms (VirtualBox)",
                        "Session may have crashed - try cleaning up with: adare dev cleanup",
                        f"Or start a new session with: adare dev start {db_session.experiment_name} -e {db_session.environment_name}"
                    ]
                )

            # Get current state
            state = session.get_state()

            return Result.ok(DevSessionInfo(
                session_id=state.session_id,
                project_path=Path(db_session.project_path),
                experiment_name=state.experiment_name,
                environment_name=state.environment_name,
                vm_running=state.vm_running,
                actions_executed=state.actions_executed,
                created_at=db_session.created_at,
                current_variables=state.current_variables,
                available_snapshots=state.available_snapshots,
                next_steps=[],
                tip=None
            ))

        except Exception as e:
            log.error(f"Error getting session state: {e}", exc_info=True)
            return Result.fail(
                "INTERNAL_ERROR",
                f"Unexpected error: {str(e)}",
                ["Check logs for details"]
            )

    def update_testfunctions(self, request: DevUpdateTestfunctionsRequest) -> Result[DevUpdateTestfunctionsResult]:
        """
        Update testfunctions in the VM.
        
        Args:
            request: DevUpdateTestfunctionsRequest
            
        Returns:
            Result[DevUpdateTestfunctionsResult]
        """
        try:
            start_time = time.time()
            
            # Use manager to process update
            success = asyncio.run(self._manager.update_testfunctions(request.session_id))
            
            execution_time = time.time() - start_time
            
            if success:
                return Result.ok(DevUpdateTestfunctionsResult(
                    success=True,
                    message="Testfunctions updated successfully",
                    execution_time=execution_time
                ))
            else:
                return Result.fail(
                    "UPDATE_FAILED",
                    "Failed to update testfunctions",
                    ["Check if session is active and running", "Check logs for details"]
                )
                
        except Exception as e:
            log.error(f"Error updating testfunctions: {e}", exc_info=True)
            return Result.fail(
                "INTERNAL_ERROR",
                f"Unexpected error: {str(e)}",
                ["Check logs for details"]
            )

    def restart_cv_server(self, request: DevCVRestartRequest) -> Result[bool]:
        """
        Restart the CV server for an active session.

        Args:
            request: DevCVRestartRequest

        Returns:
            Result[bool]
        """
        try:
            start_time = time.time()
            
            # Use manager to process update
            success = asyncio.run(self._manager.restart_mcp_server(
                request.session_id,
                debug=request.debug,
                debug_output_dir=request.debug_output_dir
            ))
            
            if success:
                return Result.ok(True)
            else:
                return Result.fail(
                    "RESTART_FAILED",
                    "Failed to restart CV server",
                    ["Check if session is active and running", "Check logs for details"]
                )
                
        except Exception as e:
            log.error(f"Error restarting CV server: {e}", exc_info=True)
            return Result.fail(
                "INTERNAL_ERROR",
                f"Unexpected error: {str(e)}",
                ["Check logs for details"]
            )

    def stop_cv_server(self, request: DevCVStopRequest) -> Result[bool]:
        """
        Stop the CV server for an active session.

        Args:
            request: DevCVStopRequest

        Returns:
            Result[bool]
        """
        try:
            success = asyncio.run(self._manager.stop_mcp_server(
                request.session_id
            ))
            
            if success:
                return Result.ok(True)
            else:
                return Result.fail(
                    "STOP_FAILED",
                    "Failed to stop CV server",
                    ["Check if session is active and running", "Check logs for details"]
                )
                
        except Exception as e:
            log.error(f"Error stopping CV server: {e}", exc_info=True)
            return Result.fail(
                "INTERNAL_ERROR",
                f"Unexpected error: {str(e)}",
                ["Check logs for details"]
            )

    def cleanup_stale_sessions(self, request: DevSessionCleanupRequest) -> Result[DevCleanupResult]:
        """
        Cleanup orphaned dev mode sessions.

        Removes sessions marked as 'running' that are not actually active in memory.
        This handles cases where sessions crashed or were killed unexpectedly.

        Does NOT remove sessions with 'stopped' status - these are intentionally
        not in memory and can be resumed later.

        Args:
            request: DevSessionCleanupRequest with optional project filter

        Returns:
            Result[DevCleanupResult] with cleanup statistics
        """
        try:
            removed_ids = []

            # Get all sessions from database
            db_sessions = self._db_api.list_sessions(request.project_path)

            for db_session in db_sessions:
                # Skip stopped sessions - they're intentionally not in memory
                if db_session.status == 'stopped':
                    continue

                # Check if session exists in manager
                session = self._manager.get_session(db_session.session_id)
                if not session:
                    # Stale session - remove from database (marked as running but not actually running)
                    self._db_api.delete_session(db_session.session_id)
                    removed_ids.append(db_session.session_id)

            return Result.ok(DevCleanupResult(
                sessions_removed=len(removed_ids),
                removed_session_ids=removed_ids
            ))

        except Exception as e:
            log.error(f"Error cleaning up sessions: {e}", exc_info=True)
            return Result.fail(
                "INTERNAL_ERROR",
                f"Unexpected error: {str(e)}",
                ["Check logs for details"]
            )

    # =========================================================================
    # Action Execution
    # =========================================================================

    async def _execute_action_async(self, request: DevActionExecuteRequest):
        """
        Execute a single action in a single event loop.

        This async helper ensures the entire action execution (session retrieval,
        parsing, and execution) happens in one event loop, keeping the WebSocket
        message handler alive throughout.

        Args:
            request: DevActionExecuteRequest with session ID and action details

        Returns:
            Tuple of (action_result, execution_time)

        Raises:
            RuntimeError: If session not found or action execution fails
            ValueError: If invalid action source
        """
        # Get or restore session (stays in same event loop)
        session = await self._manager.get_or_restore_session(request.session_id)
        if not session:
            raise RuntimeError(
                f"Dev session '{request.session_id}' not found or could not be restored"
            )

        # Parse action based on source
        if request.action_source == 'file':
            action = self._parse_action_from_file(request.action_content)
        elif request.action_source == 'yaml':
            action = self._parse_action_from_yaml(request.action_content)
        elif request.action_source == 'stdin':
            action = self._parse_action_from_stdin()
        else:
            raise ValueError(f"Invalid action source '{request.action_source}'")

        # Execute action (in same event loop!)
        start_time = time.time()
        action_result = await session.execute_action(action)
        execution_time = time.time() - start_time

        return action_result, execution_time

    def execute_action(self, request: DevActionExecuteRequest) -> Result[DevActionResult]:
        """
        Execute a single action.

        Args:
            request: DevActionExecuteRequest with session ID, source, and content

        Returns:
            Result[DevActionResult] with execution result
        """
        try:
            # CRITICAL: Execute entire flow in ONE asyncio.run() call
            # This keeps the WebSocket message_handler_task alive throughout execution
            action_result, execution_time = asyncio.run(
                self._execute_action_async(request)
            )

            return Result.ok(DevActionResult(
                success=action_result.success,
                message=action_result.message,
                execution_time=execution_time,
                coordinates=action_result.coordinates,
                data=action_result.data
            ))

        except RuntimeError as e:
            # Raised by _execute_action_async when session not found
            return Result.fail(
                "SESSION_NOT_FOUND",
                str(e),
                [
                    "Check active sessions with: adare dev list",
                    "VM may not be running - check with hypervisor tools"
                ]
            )
        except ValueError as e:
            # Raised by _execute_action_async for invalid action source
            return Result.fail(
                "INVALID_ACTION_SOURCE",
                str(e),
                ["Valid sources: file, yaml, stdin"]
            )
        except yaml.YAMLError as e:
            return Result.fail(
                "YAML_PARSE_ERROR",
                f"Failed to parse action YAML: {str(e)}",
                ["Check YAML syntax", "Ensure action format is valid"]
            )
        except FileNotFoundError as e:
            return Result.fail(
                "FILE_NOT_FOUND",
                f"Action file not found: {str(e)}",
                ["Check file path is correct"]
            )
        except Exception as e:
            log.error(f"Error executing action: {e}", exc_info=True)
            return Result.fail(
                "ACTION_EXECUTION_ERROR",
                f"Action execution failed: {str(e)}",
                ["Check logs for details", "Verify action syntax"]
            )

    async def _execute_playbook_async(self, request: DevPlaybookExecuteRequest):
        """
        Execute playbook in a single event loop.

        This async helper ensures the entire playbook execution (session retrieval,
        parsing, and execution) happens in one event loop, keeping the WebSocket
        message handler alive throughout.

        Args:
            request: DevPlaybookExecuteRequest with session ID and playbook details

        Returns:
            Tuple of (playbook_result, execution_time)

        Raises:
            RuntimeError: If session not found or playbook execution fails
            ValueError: If invalid playbook source
        """
        # Get or restore session (stays in same event loop)
        session = await self._manager.get_or_restore_session(
            request.session_id,
            console_ulid=request.console_ulid
        )
        if not session:
            raise RuntimeError(
                f"Dev session '{request.session_id}' not found or could not be restored"
            )

        # Parse playbook based on source
        experiment_dir = None
        if request.playbook_source == 'file':
            # Identify experiment directory as parent of playbook file
            playbook_path = Path(request.playbook_content)
            experiment_dir = playbook_path.parent.resolve()
            log.info(f" inferred experiment directory from playbook file: {experiment_dir}")
            
            playbook = self._parse_playbook_from_file(request.playbook_content)
        elif request.playbook_source == 'url':
            playbook = self._fetch_playbook_from_url(request.playbook_content)
        elif request.playbook_source == 'stdin':
            playbook = self._parse_playbook_from_stdin()
        else:
            raise ValueError(f"Invalid playbook source '{request.playbook_source}'")

        # Parse indices if provided (now that we know action count)
        parsed_indices = None
        if request.indices:
            from adare.cli.dev import parse_indices_with_bounds
            try:
                parsed_indices = parse_indices_with_bounds(request.indices, len(playbook.actions))
            except ValueError as e:
                raise ValueError(f"Invalid indices specification: {e}")

        # Restore to initial checkpoint if requested
        if request.restore_initial:
            log.info("--restore flag set: restoring to initial checkpoint before playbook execution")
            restore_success = await session.restore_checkpoint('initial')

            if not restore_success:
                raise RuntimeError(
                    "Failed to restore initial checkpoint. "
                    "Checkpoint may not exist or restore operation failed. "
                    "Aborting playbook execution to avoid running with stale state."
                )

            log.info("Successfully restored to initial checkpoint")

        # Execute playbook (in same event loop!)
        start_time = time.time()
        playbook_result = await session.execute_playbook(
            playbook,
            experiment_dir=experiment_dir,
            indices=parsed_indices
        )
        execution_time = time.time() - start_time

        return playbook_result, execution_time

    def execute_playbook(self, request: DevPlaybookExecuteRequest) -> Result[DevPlaybookResult]:
        """
        Execute a playbook.

        Args:
            request: DevPlaybookExecuteRequest with session ID, source, and content

        Returns:
            Result[DevPlaybookResult] with execution statistics
        """
        try:
            # CRITICAL: Execute entire flow in ONE asyncio.run() call
            # This keeps the WebSocket message_handler_task alive throughout execution
            playbook_result, execution_time = asyncio.run(
                self._execute_playbook_async(request)
            )

            # Convert action results
            action_results = [
                DevActionResult(
                    success=ar.success,
                    message=ar.message,
                    execution_time=0.0,  # Individual timing not tracked
                    coordinates=ar.coordinates,
                    data=ar.data
                )
                for ar in playbook_result.action_results
            ]

            return Result.ok(DevPlaybookResult(
                success=playbook_result.success,
                total_actions=playbook_result.total_actions,
                successful_actions=playbook_result.successful_actions,
                failed_actions=playbook_result.failed_actions,
                execution_time=execution_time,
                action_results=action_results,
                error_message=playbook_result.error_message,
                test_stats={
                    'total_tests': playbook_result.total_tests,
                    'successful_tests': playbook_result.successful_tests,
                    'failed_tests': playbook_result.failed_tests,
                } if playbook_result.total_tests > 0 else None
            ))

        except RuntimeError as e:
            # Raised by _execute_playbook_async when session not found
            return Result.fail(
                "SESSION_NOT_FOUND",
                str(e),
                [
                    "Check active sessions with: adare dev list",
                    "VM may not be running - check with hypervisor tools"
                ]
            )
        except ValueError as e:
            # Raised by _execute_playbook_async for invalid playbook source
            return Result.fail(
                "INVALID_PLAYBOOK_SOURCE",
                str(e),
                ["Valid sources: file, url, stdin"]
            )
        except yaml.YAMLError as e:
            return Result.fail(
                "YAML_PARSE_ERROR",
                f"Failed to parse playbook YAML: {str(e)}",
                ["Check YAML syntax", "Ensure playbook format is valid"]
            )
        except FileNotFoundError as e:
            return Result.fail(
                "FILE_NOT_FOUND",
                f"Playbook file not found: {str(e)}",
                ["Check file path is correct"]
            )
        except Exception as e:
            log.error(f"Error executing playbook: {e}", exc_info=True)
            return Result.fail(
                "PLAYBOOK_EXECUTION_ERROR",
                f"Playbook execution failed: {str(e)}",
                ["Check logs for details", "Verify playbook syntax"]
            )

    # =========================================================================
    # Reset Operations
    # =========================================================================

    async def _reset_soft_async(self, request: DevResetRequest):
        """
        Execute soft reset in a single event loop.

        Args:
            request: DevResetRequest with session ID

        Returns:
            Tuple of (success, execution_time)

        Raises:
            RuntimeError: If session not found
        """
        # Get or restore session (stays in same event loop)
        session = await self._manager.get_or_restore_session(request.session_id)
        if not session:
            raise RuntimeError(
                f"Dev session '{request.session_id}' not found or could not be restored"
            )

        # Perform soft reset (in same event loop!)
        start_time = time.time()
        success = await session.reset_soft()
        execution_time = time.time() - start_time

        return success, execution_time

    def reset_soft(self, request: DevResetRequest) -> Result[DevResetResult]:
        """
        Soft reset (variables only).

        Args:
            request: DevResetRequest with session ID

        Returns:
            Result[DevResetResult] with reset details
        """
        try:
            # CRITICAL: Execute entire flow in ONE asyncio.run() call
            # This keeps the WebSocket message_handler_task alive throughout execution
            success, execution_time = asyncio.run(
                self._reset_soft_async(request)
            )

            if success:
                return Result.ok(DevResetResult(
                    success=True,
                    reset_type='soft',
                    execution_time=execution_time,
                    message="Variables reset to initial state"
                ))
            else:
                return Result.fail(
                    "RESET_FAILED",
                    "Soft reset failed - no snapshots available",
                    ["Try hard reset instead: adare dev reset-hard"]
                )

        except RuntimeError as e:
            # Raised by _reset_soft_async when session not found
            return Result.fail(
                "SESSION_NOT_FOUND",
                str(e),
                [
                    "Check active sessions with: adare dev list",
                    "VM may not be running - check with hypervisor tools"
                ]
            )
        except Exception as e:
            log.error(f"Error during soft reset: {e}", exc_info=True)
            return Result.fail(
                "RESET_ERROR",
                f"Soft reset failed: {str(e)}",
                ["Check logs for details"]
            )

    async def _reset_hard_async(self, request: DevResetRequest):
        """
        Execute hard reset in a single event loop.

        Args:
            request: DevResetRequest with session ID

        Returns:
            Tuple of (success, execution_time)

        Raises:
            RuntimeError: If session not found
        """
        # Get or restore session (stays in same event loop)
        session = await self._manager.get_or_restore_session(request.session_id)
        if not session:
            raise RuntimeError(
                f"Dev session '{request.session_id}' not found or could not be restored"
            )

        # Perform hard reset (in same event loop!)
        start_time = time.time()
        success = await session.reset_hard()
        execution_time = time.time() - start_time

        return success, execution_time

    def reset_hard(self, request: DevResetRequest) -> Result[DevResetResult]:
        """
        Hard reset (full VM restore).

        Args:
            request: DevResetRequest with session ID

        Returns:
            Result[DevResetResult] with reset details
        """
        try:
            # CRITICAL: Execute entire flow in ONE asyncio.run() call
            # This keeps the WebSocket message_handler_task alive throughout execution
            success, execution_time = asyncio.run(
                self._reset_hard_async(request)
            )

            if success:
                return Result.ok(DevResetResult(
                    success=True,
                    reset_type='hard',
                    execution_time=execution_time,
                    message="VM restored to initial snapshot"
                ))
            else:
                return Result.fail(
                    "RESET_FAILED",
                    "Hard reset failed - no snapshots available",
                    ["Check session state: adare dev state"]
                )

        except RuntimeError as e:
            # Raised by _reset_hard_async when session not found
            return Result.fail(
                "SESSION_NOT_FOUND",
                str(e),
                [
                    "Check active sessions with: adare dev list",
                    "VM may not be running - check with hypervisor tools"
                ]
            )
        except Exception as e:
            log.error(f"Error during hard reset: {e}", exc_info=True)
            return Result.fail(
                "RESET_ERROR",
                f"Hard reset failed: {str(e)}",
                ["Check logs for details"]
            )

    # =========================================================================
    # Checkpoint Operations
    # =========================================================================

    async def _create_checkpoint_async(self, request: DevCheckpointCreateRequest):
        """
        Create checkpoint in a single event loop.

        Args:
            request: DevCheckpointCreateRequest with session ID, name, description

        Returns:
            success: bool

        Raises:
            RuntimeError: If session not found
        """
        # Get or restore session (stays in same event loop)
        session = await self._manager.get_or_restore_session(
            request.session_id, 
            connect_websocket=False
        )
        if not session:
            raise RuntimeError(
                f"Dev session '{request.session_id}' not found or could not be restored"
            )

        # Create checkpoint (in same event loop!)
        success = await session.create_checkpoint(request.name, request.description)
        return success

    def create_checkpoint(self, request: DevCheckpointCreateRequest) -> Result[bool]:
        """
        Create a named checkpoint (live snapshot).

        Args:
            request: DevCheckpointCreateRequest with session ID, name, description

        Returns:
            Result[bool] with True on success
        """
        try:
            # CRITICAL: Execute entire flow in ONE asyncio.run() call
            # This keeps the WebSocket message_handler_task alive throughout execution
            success = asyncio.run(
                self._create_checkpoint_async(request)
            )

            if success:
                return Result.ok(True)
            else:
                return Result.fail(
                    "CHECKPOINT_CREATE_FAILED",
                    f"Failed to create checkpoint '{request.name}'",
                    ["Check hypervisor is running", "Check VM has sufficient disk space"]
                )

        except RuntimeError as e:
            # Raised by _create_checkpoint_async when session not found
            return Result.fail(
                "SESSION_NOT_FOUND",
                str(e),
                [
                    "Check active sessions with: adare dev list",
                    "VM may not be running - check with hypervisor tools"
                ]
            )
        except Exception as e:
            log.error(f"Error creating checkpoint: {e}", exc_info=True)
            return Result.fail(
                "CHECKPOINT_ERROR",
                f"Checkpoint creation failed: {str(e)}",
                ["Check logs for details"]
            )

    async def _restore_checkpoint_async(self, request: DevCheckpointRestoreRequest):
        """
        Restore checkpoint in a single event loop.

        Args:
            request: DevCheckpointRestoreRequest with session ID and checkpoint name

        Returns:
            success: bool

        Raises:
            RuntimeError: If session not found
        """
        # Get or restore session (stays in same event loop)
        session = await self._manager.get_or_restore_session(request.session_id)
        if not session:
            raise RuntimeError(
                f"Dev session '{request.session_id}' not found or could not be restored"
            )

        # Restore checkpoint (in same event loop!)
        success = await session.restore_checkpoint(request.name)
        return success

    def restore_checkpoint(self, request: DevCheckpointRestoreRequest) -> Result[bool]:
        """
        Restore to a checkpoint.

        Args:
            request: DevCheckpointRestoreRequest with session ID and checkpoint name

        Returns:
            Result[bool] with True on success
        """
        try:
            # CRITICAL: Execute entire flow in ONE asyncio.run() call
            # This keeps the WebSocket message_handler_task alive throughout execution
            success = asyncio.run(
                self._restore_checkpoint_async(request)
            )

            if success:
                return Result.ok(True)
            else:
                return Result.fail(
                    "CHECKPOINT_NOT_FOUND",
                    f"Checkpoint '{request.name}' not found",
                    [
                        f"List available checkpoints with: adare dev checkpoint-list {request.session_id}"
                    ]
                )

        except RuntimeError as e:
            # Raised by _restore_checkpoint_async when session not found
            return Result.fail(
                "SESSION_NOT_FOUND",
                str(e),
                [
                    "Check active sessions with: adare dev list",
                    "VM may not be running - check with hypervisor tools"
                ]
            )
        except Exception as e:
            log.error(f"Error restoring checkpoint: {e}", exc_info=True)
            return Result.fail(
                "CHECKPOINT_ERROR",
                f"Checkpoint restore failed: {str(e)}",
                ["Check logs for details"]
            )

    def list_checkpoints(self, request: DevCheckpointListRequest) -> Result[List[DevCheckpointInfo]]:
        """
        List available checkpoints (read-only operation).

        Args:
            request: DevCheckpointListRequest with session ID

        Returns:
            Result[List[DevCheckpointInfo]] with checkpoint list
        """
        try:
            # 1. Validate session exists in database
            db_session = self._db_api.get_session(request.session_id)
            if not db_session:
                return Result.fail(
                    "SESSION_NOT_FOUND",
                    f"Dev session '{request.session_id}' not found",
                    ["Check active sessions with: adare dev list"]
                )

            # 2. Query checkpoints directly from database (NO session restoration)
            db_checkpoints = self._db_api.list_checkpoints(request.session_id)

            # 3. Convert to DevCheckpointInfo with file size calculation
            import os
            checkpoints = []
            for checkpoint in db_checkpoints:
                # Calculate file size from checkpoint file paths
                file_size_mb = 0.0
                if checkpoint.memory_file_path and os.path.exists(checkpoint.memory_file_path):
                    file_size_mb += os.path.getsize(checkpoint.memory_file_path) / (1024 * 1024)
                if checkpoint.disk_file_path and os.path.exists(checkpoint.disk_file_path):
                    file_size_mb += os.path.getsize(checkpoint.disk_file_path) / (1024 * 1024)

                # Map database fields to DTO
                checkpoints.append(DevCheckpointInfo(
                    name=checkpoint.name,  # Use name directly from DB (no parsing needed)
                    description=checkpoint.description or "",
                    created_at=checkpoint.created_at,
                    variable_count=len(checkpoint.variable_state or {}),
                    checkpoint_id=checkpoint.checkpoint_id,
                    memory_file_path=checkpoint.memory_file_path or "",
                    disk_file_path=checkpoint.disk_file_path or "",
                    file_size_mb=file_size_mb
                ))

            return Result.ok(checkpoints)

        except Exception as e:
            log.error(f"Error listing checkpoints: {e}", exc_info=True)
            return Result.fail(
                "CHECKPOINT_ERROR",
                f"Failed to list checkpoints: {str(e)}",
                ["Check logs for details"]
            )

    def delete_checkpoint(self, request: DevCheckpointDeleteRequest) -> Result[bool]:
        """
        Delete a checkpoint.

        Args:
            request: DevCheckpointDeleteRequest with session ID and checkpoint name

        Returns:
            Result[bool] indicating success or failure
        """
        try:
            from adare.database.api.devmode import DevModeApi

            # First check if session exists in database
            with DevModeApi() as api:
                db_session = api.get_session(request.session_id)
                if not db_session:
                    return Result.fail(
                        "SESSION_NOT_FOUND",
                        f"Dev session '{request.session_id}' not found",
                        ["Check active sessions with: adare dev list"]
                    )

                # Get checkpoint from database
                checkpoint = api.get_checkpoint(request.session_id, request.name)
                if not checkpoint:
                    return Result.fail(
                        "CHECKPOINT_NOT_FOUND",
                        f"Checkpoint '{request.name}' not found",
                        [f"List available checkpoints with: adare dev checkpoint list --session-id {request.session_id}"]
                    )

            # Get infrastructure-only session context 
            # We use load_session_for_cleanup because we only need infrastructure access 
            # (hypervisor) to delete files, not full application context.
            session = asyncio.run(self._manager.load_session_for_cleanup(request.session_id))
            if session and session.experiment_ctx.hypervisor_type == 'qemu':
                # Delete external snapshot files
                vm = session.experiment_ctx.vm
                vm.delete_external_snapshot(
                    snapshot_name=checkpoint.snapshot_name,
                    memory_path=checkpoint.memory_file_path,
                    disk_path=checkpoint.disk_file_path
                )
                log.info(f"Deleted external snapshot files for checkpoint '{request.name}'")

            # Delete from database
            with DevModeApi() as api:
                success = api.delete_checkpoint(checkpoint.checkpoint_id)
                if not success:
                    return Result.fail(
                        "CHECKPOINT_DELETE_FAILED",
                        f"Failed to delete checkpoint '{request.name}' from database",
                        ["Check logs for details"]
                    )

            # Remove from session's in-memory snapshot list
            if session:
                session.snapshots = [
                    s for s in session.snapshots
                    if s.checkpoint_id != checkpoint.checkpoint_id
                ]

            log.info(f"Checkpoint '{request.name}' deleted successfully")
            return Result.ok(True)

        except Exception as e:
            log.error(f"Error deleting checkpoint: {e}", exc_info=True)
            return Result.fail(
                "CHECKPOINT_DELETE_ERROR",
                f"Failed to delete checkpoint: {str(e)}",
                ["Check logs for details"]
            )

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _validate_vm_resources(self, db_session) -> Result[bool]:
        """
        Validate that VM resources exist for session resumption.

        Args:
            db_session: DevSession database record

        Returns:
            Result[bool] with True on success, or error information if resources missing
        """
        try:
            # Get environment metadata
            environment_ulid = environment_database.resolve_environment_identifier(
                db_session.environment_name
            )

            # Check if VM disk file exists
            vm_file = environment_database.get_environment_vm_file(environment_ulid)
            if vm_file and not vm_file.exists():
                return Result.fail(
                    "VM_DISK_NOT_FOUND",
                    f"VM disk file not found: {vm_file}",
                    [
                        "The VM disk file for this session no longer exists",
                        "This session cannot be resumed",
                        f"Clean up orphaned session with: adare dev stop --rm {db_session.session_id}",
                        f"Create new session with: adare dev start {db_session.experiment_name} -e {db_session.environment_name}"
                    ]
                )

            # Check if checkpoint files exist (non-fatal warning)
            checkpoints = self._db_api.list_checkpoints(db_session.session_id)
            missing_checkpoints = []

            for checkpoint in checkpoints:
                if checkpoint.memory_file_path and not Path(checkpoint.memory_file_path).exists():
                    missing_checkpoints.append(checkpoint.name)
                elif checkpoint.disk_file_path and not Path(checkpoint.disk_file_path).exists():
                    missing_checkpoints.append(checkpoint.name)

            if missing_checkpoints:
                log.warning(
                    f"Some checkpoint files are missing for session {db_session.session_id}: "
                    f"{', '.join(missing_checkpoints)}. These checkpoints will be unavailable."
                )

            return Result.ok(True)

        except Exception as e:
            log.error(f"Error validating VM resources: {e}", exc_info=True)
            return Result.fail(
                "VALIDATION_ERROR",
                f"Failed to validate VM resources: {str(e)}",
                ["Check logs for details"]
            )

    def _parse_action_from_file(self, file_path: str):
        """Parse single action from YAML file."""
        with open(file_path, 'r') as f:
            yaml_content = f.read()
        return self._parse_action_from_yaml(yaml_content)

    def _parse_action_from_yaml(self, yaml_content: str):
        """Parse single action from YAML string."""
        action_dict = yaml.safe_load(yaml_content)
        return _structure_action(action_dict)

    def _parse_action_from_stdin(self):
        """Read and parse action from stdin."""
        yaml_content = sys.stdin.read()
        return self._parse_action_from_yaml(yaml_content)

    def _parse_playbook_from_file(self, file_path: str):
        """Parse playbook from file."""
        return parse_playbook(Path(file_path))

    def _fetch_playbook_from_url(self, url: str):
        """Fetch and parse playbook from URL."""
        try:
            import httpx
            response = httpx.get(url, timeout=30, follow_redirects=True)
            response.raise_for_status()

            # Write to temp file and parse
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
                f.write(response.text)
                temp_path = f.name

            playbook = parse_playbook(Path(temp_path))

            # Clean up temp file
            Path(temp_path).unlink()

            return playbook
        except ImportError:
            raise RuntimeError("httpx package required for URL fetching. Install with: pip install httpx")
        except Exception as e:
            raise RuntimeError(f"Failed to fetch playbook from URL: {str(e)}")

    def _parse_playbook_from_stdin(self):
        """Read and parse playbook from stdin."""
        import tempfile

        # Read stdin content
        yaml_content = sys.stdin.read()

        # Write to temp file and parse
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            f.write(yaml_content)
            temp_path = f.name

        playbook = parse_playbook(Path(temp_path))

        # Clean up temp file
        Path(temp_path).unlink()

        return playbook
