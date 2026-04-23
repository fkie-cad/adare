"""
Session management mixin for DevMode service.

Handles session lifecycle: start, resume, stop, record, list, get_state, cleanup.
"""

import asyncio
import logging
import time
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from adare.backend.environment import database as environment_database
from adare.backend.environment.exceptions import EnvironmentDoesNotExistInDatabase
from adare.core.dto.devmode import (
    DevCleanupResult,
    DevCVRestartRequest,
    DevCVStopRequest,
    DevSessionCleanupRequest,
    DevSessionInfo,
    DevSessionListItem,
    DevSessionListRequest,
    DevSessionRecordRequest,
    DevSessionStartRequest,
    DevSessionStateRequest,
    DevSessionStopRequest,
    DevUpdateTestfunctionsRequest,
    DevUpdateTestfunctionsResult,
)
from adare.core.result import Result

log = logging.getLogger(__name__)


class SessionManagementMixin:
    """Mixin providing session lifecycle methods for DevModeService."""

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
                        "Load environment with: adare environment load <environment.yml>"
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
                log.info(f"Stored run directory path for session {session_id}: {session.run_directory_path}")

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
        except (SQLAlchemyError, OSError, NotImplementedError, asyncio.CancelledError) as e:
            log.error(f"Unexpected error starting dev session: {e}", exc_info=True)
            return Result.fail(
                "INTERNAL_ERROR",
                f"Unexpected error: {str(e)}",
                ["Check logs for details"]
            )

    def resume_session(self, session_id: str, console_ulid: str | None = None) -> Result[DevSessionInfo]:
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

        except (RuntimeError, SQLAlchemyError, OSError, asyncio.CancelledError) as e:
            log.error(f"Unexpected error resuming session: {e}", exc_info=True)
            return Result.fail(
                "INTERNAL_ERROR",
                f"Unexpected error: {str(e)}",
                ["Check logs for details"]
            )

    def resume_most_recent(self, project_path: Path, console_ulid: str | None = None) -> Result[DevSessionInfo]:
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

        except (RuntimeError, SQLAlchemyError, OSError) as e:
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
            # Could not load infrastructure - DB state might be corrupted
            # or environment invalid. Fallback to DB-only cleanup.
            log.warning(
                f"Could not load infrastructure for session {request.session_id}. "
                f"Performing database-only cleanup."
            )
            return 'removed_from_db_only'
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

        except (RuntimeError, SQLAlchemyError, OSError, asyncio.CancelledError) as e:
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
            result = asyncio.run(session.start_recording(request.output_file))
            if not result.success:
               return Result.fail(
                   result.error.code if result.error else "RECORD_START_FAILED",
                   result.error.message if result.error else "Failed to start recording (check logs)"
               )

            return Result.ok(True)

        except (RuntimeError, SQLAlchemyError, OSError) as e:
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

            result = asyncio.run(session.stop_recording())
            if not result.success:
                return Result.fail(
                    result.error.code if result.error else "RECORD_STOP_FAILED",
                    result.error.message if result.error else "Failed to stop recording"
                )

            return Result.ok(True)
        except (RuntimeError, SQLAlchemyError, OSError) as e:
            log.error(f"Error stopping recording: {e}", exc_info=True)
            return Result.fail("INTERNAL_ERROR", str(e))

    def list_sessions(self, request: DevSessionListRequest) -> Result[list[DevSessionListItem]]:
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

        except (SQLAlchemyError, OSError) as e:
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

        except (RuntimeError, SQLAlchemyError, OSError) as e:
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
            return Result.fail(
                "UPDATE_FAILED",
                "Failed to update testfunctions",
                ["Check if session is active and running", "Check logs for details"]
            )

        except (RuntimeError, SQLAlchemyError, OSError) as e:
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
            # Use manager to process update
            success = asyncio.run(self._manager.restart_mcp_server(
                request.session_id,
                debug=request.debug,
                debug_output_dir=request.debug_output_dir
            ))

            if success:
                return Result.ok(True)
            return Result.fail(
                "RESTART_FAILED",
                "Failed to restart CV server",
                ["Check if session is active and running", "Check logs for details"]
            )

        except (RuntimeError, OSError, asyncio.CancelledError) as e:
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
            return Result.fail(
                "STOP_FAILED",
                "Failed to stop CV server",
                ["Check if session is active and running", "Check logs for details"]
            )

        except (RuntimeError, OSError, asyncio.CancelledError) as e:
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

        except (SQLAlchemyError, OSError) as e:
            log.error(f"Error cleaning up sessions: {e}", exc_info=True)
            return Result.fail(
                "INTERNAL_ERROR",
                f"Unexpected error: {str(e)}",
                ["Check logs for details"]
            )
