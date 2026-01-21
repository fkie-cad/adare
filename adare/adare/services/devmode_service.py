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

        Args:
            request: DevSessionStartRequest with project path, experiment name, environment name

        Returns:
            Result[DevSessionInfo] with session details on success,
            or error information on failure
        """
        try:
            # Validate experiment exists
            experiment_ulid = experiment_database.get_experiment_by_project_and_name(
                request.project_path,
                request.experiment_name,
                trigger_error=False
            )
            if not experiment_ulid:
                return Result.fail(
                    "EXPERIMENT_NOT_FOUND",
                    f"Experiment '{request.experiment_name}' not found in project",
                    [
                        f"Check available experiments with: adare experiment list",
                        f"Load experiment with: adare experiment load {request.experiment_name}"
                    ]
                )

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

            # Create session via manager (async)
            session_id = asyncio.run(self._manager.create_session(
                request.project_path,
                request.experiment_name,
                request.environment_name,
                gui_mode=request.gui_mode,
                vm_memory=request.vm_memory,
                vm_cpus=request.vm_cpus,
                debug_screenshots=request.debug_screenshots,
                console_ulid=request.console_ulid
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

            # Persist to database
            self._db_api.save_session(
                session_id=session_id,
                project_path=request.project_path,
                experiment_name=request.experiment_name,
                environment_name=request.environment_name,
                vm_name=vm_name
            )

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
                experiment_name=state.experiment_name,
                environment_name=state.environment_name,
                vm_running=state.vm_running,
                actions_executed=state.actions_executed,
                created_at=self._db_api.get_session(session_id).created_at,
                current_variables=state.current_variables,
                available_snapshots=state.available_snapshots,
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

            # Try to get or restore session for proper VM shutdown
            session = self._manager.get_or_restore_session(request.session_id)

            if session:
                # Session available (from memory or restored)
                if request.remove_resources:
                    # Full cleanup: stop and remove everything
                    asyncio.run(
                        self._manager.stop_and_remove_session(request.session_id)
                    )
                    # Delete database entry (cascades to checkpoints)
                    self._db_api.delete_session(request.session_id)
                else:
                    # Shutdown only: keep resources for restart
                    asyncio.run(
                        self._manager.shutdown_session(request.session_id)
                    )
                    # Mark as stopped in database (keep entry)
                    self._db_api.update_session_status(request.session_id, 'stopped')

                return Result.ok(True)
            else:
                # Session not in memory - handle based on mode
                if request.remove_resources:
                    # Clean up database entries only (VM already gone)
                    log.info(f"Session {request.session_id} not running, cleaning up database")
                    self._db_api.delete_session(request.session_id)
                else:
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

    def list_sessions(self, request: DevSessionListRequest) -> Result[List[DevSessionListItem]]:
        """
        List active dev mode sessions.

        Args:
            request: DevSessionListRequest with optional project filter

        Returns:
            Result[List[DevSessionListItem]] with session list
        """
        try:
            # Get sessions from database
            db_sessions = self._db_api.list_running_sessions(request.project_path)

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
                    # Session not in manager (stale)
                    vm_running = False
                    actions_executed = 0

                items.append(DevSessionListItem(
                    session_id=db_session.session_id,
                    experiment_name=db_session.experiment_name,
                    environment_name=db_session.environment_name,
                    vm_running=vm_running,
                    actions_executed=actions_executed,
                    created_at=db_session.created_at,
                    project_path=Path(db_session.project_path)
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
            session = self._manager.get_or_restore_session(request.session_id)
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

    def cleanup_stale_sessions(self, request: DevSessionCleanupRequest) -> Result[DevCleanupResult]:
        """
        Cleanup stale sessions.

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
                # Check if session exists in manager
                session = self._manager.get_session(db_session.session_id)
                if not session:
                    # Stale session - remove from database
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

    def execute_action(self, request: DevActionExecuteRequest) -> Result[DevActionResult]:
        """
        Execute a single action.

        Args:
            request: DevActionExecuteRequest with session ID, source, and content

        Returns:
            Result[DevActionResult] with execution result
        """
        try:
            # Get or restore session from manager
            session = self._manager.get_or_restore_session(request.session_id)
            if not session:
                return Result.fail(
                    "SESSION_NOT_FOUND",
                    f"Dev session '{request.session_id}' not found or could not be restored",
                    [
                        "Check active sessions with: adare dev list",
                        "VM may not be running - check with hypervisor tools"
                    ]
                )

            # Parse action based on source
            if request.action_source == 'file':
                action = self._parse_action_from_file(request.action_content)
            elif request.action_source == 'yaml':
                action = self._parse_action_from_yaml(request.action_content)
            elif request.action_source == 'stdin':
                action = self._parse_action_from_stdin()
            else:
                return Result.fail(
                    "INVALID_ACTION_SOURCE",
                    f"Invalid action source '{request.action_source}'",
                    ["Valid sources: file, yaml, stdin"]
                )

            # Execute action (async)
            start_time = time.time()
            action_result = asyncio.run(session.execute_action(action))
            execution_time = time.time() - start_time

            return Result.ok(DevActionResult(
                success=action_result.success,
                message=action_result.message,
                execution_time=execution_time,
                coordinates=action_result.coordinates,
                data=action_result.data
            ))

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

    def execute_playbook(self, request: DevPlaybookExecuteRequest) -> Result[DevPlaybookResult]:
        """
        Execute a playbook.

        Args:
            request: DevPlaybookExecuteRequest with session ID, source, and content

        Returns:
            Result[DevPlaybookResult] with execution statistics
        """
        try:
            # Get or restore session from manager
            session = self._manager.get_or_restore_session(request.session_id)
            if not session:
                return Result.fail(
                    "SESSION_NOT_FOUND",
                    f"Dev session '{request.session_id}' not found or could not be restored",
                    [
                        "Check active sessions with: adare dev list",
                        "VM may not be running - check with hypervisor tools"
                    ]
                )

            # Parse playbook based on source
            if request.playbook_source == 'file':
                playbook = self._parse_playbook_from_file(request.playbook_content)
            elif request.playbook_source == 'url':
                playbook = self._fetch_playbook_from_url(request.playbook_content)
            elif request.playbook_source == 'stdin':
                playbook = self._parse_playbook_from_stdin()
            else:
                return Result.fail(
                    "INVALID_PLAYBOOK_SOURCE",
                    f"Invalid playbook source '{request.playbook_source}'",
                    ["Valid sources: file, url, stdin"]
                )

            # Execute playbook (async)
            start_time = time.time()
            playbook_result = asyncio.run(session.execute_playbook(playbook))
            execution_time = time.time() - start_time

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
                test_stats=playbook_result.test_stats
            ))

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

    def reset_soft(self, request: DevResetRequest) -> Result[DevResetResult]:
        """
        Soft reset (variables only).

        Args:
            request: DevResetRequest with session ID

        Returns:
            Result[DevResetResult] with reset details
        """
        try:
            # Get or restore session from manager
            session = self._manager.get_or_restore_session(request.session_id)
            if not session:
                return Result.fail(
                    "SESSION_NOT_FOUND",
                    f"Dev session '{request.session_id}' not found or could not be restored",
                    [
                        "Check active sessions with: adare dev list",
                        "VM may not be running - check with hypervisor tools"
                    ]
                )

            # Perform soft reset (async)
            start_time = time.time()
            success = asyncio.run(session.reset_soft())
            execution_time = time.time() - start_time

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

        except Exception as e:
            log.error(f"Error during soft reset: {e}", exc_info=True)
            return Result.fail(
                "RESET_ERROR",
                f"Soft reset failed: {str(e)}",
                ["Check logs for details"]
            )

    def reset_hard(self, request: DevResetRequest) -> Result[DevResetResult]:
        """
        Hard reset (full VM restore).

        Args:
            request: DevResetRequest with session ID

        Returns:
            Result[DevResetResult] with reset details
        """
        try:
            # Get or restore session from manager
            session = self._manager.get_or_restore_session(request.session_id)
            if not session:
                return Result.fail(
                    "SESSION_NOT_FOUND",
                    f"Dev session '{request.session_id}' not found or could not be restored",
                    [
                        "Check active sessions with: adare dev list",
                        "VM may not be running - check with hypervisor tools"
                    ]
                )

            # Perform hard reset (async)
            start_time = time.time()
            success = asyncio.run(session.reset_hard())
            execution_time = time.time() - start_time

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

    def create_checkpoint(self, request: DevCheckpointCreateRequest) -> Result[bool]:
        """
        Create a named checkpoint (live snapshot).

        Args:
            request: DevCheckpointCreateRequest with session ID, name, description

        Returns:
            Result[bool] with True on success
        """
        try:
            # Get or restore session from manager
            session = self._manager.get_or_restore_session(request.session_id)
            if not session:
                return Result.fail(
                    "SESSION_NOT_FOUND",
                    f"Dev session '{request.session_id}' not found or could not be restored",
                    [
                        "Check active sessions with: adare dev list",
                        "VM may not be running - check with hypervisor tools"
                    ]
                )

            # Create checkpoint (async)
            success = asyncio.run(session.create_checkpoint(request.name, request.description))

            if success:
                return Result.ok(True)
            else:
                return Result.fail(
                    "CHECKPOINT_CREATE_FAILED",
                    f"Failed to create checkpoint '{request.name}'",
                    ["Check hypervisor is running", "Check VM has sufficient disk space"]
                )

        except Exception as e:
            log.error(f"Error creating checkpoint: {e}", exc_info=True)
            return Result.fail(
                "CHECKPOINT_ERROR",
                f"Checkpoint creation failed: {str(e)}",
                ["Check logs for details"]
            )

    def restore_checkpoint(self, request: DevCheckpointRestoreRequest) -> Result[bool]:
        """
        Restore to a checkpoint.

        Args:
            request: DevCheckpointRestoreRequest with session ID and checkpoint name

        Returns:
            Result[bool] with True on success
        """
        try:
            # Get or restore session from manager
            session = self._manager.get_or_restore_session(request.session_id)
            if not session:
                return Result.fail(
                    "SESSION_NOT_FOUND",
                    f"Dev session '{request.session_id}' not found or could not be restored",
                    [
                        "Check active sessions with: adare dev list",
                        "VM may not be running - check with hypervisor tools"
                    ]
                )

            # Restore checkpoint (async)
            success = asyncio.run(session.restore_checkpoint(request.name))

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

            # Get or restore session from manager
            session = self._manager.get_or_restore_session(request.session_id)
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
