"""
Checkpoint management mixin for DevMode service.

Handles: reset (soft/hard), create/restore/list/delete checkpoint, VM resource validation.
"""

import asyncio
import logging
import os
import time
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from adare.backend.environment import database as environment_database
from adare.core.dto.devmode import (
    DevCheckpointCreateRequest,
    DevCheckpointDeleteRequest,
    DevCheckpointInfo,
    DevCheckpointListRequest,
    DevCheckpointRestoreRequest,
    DevResetRequest,
    DevResetResult,
)
from adare.core.result import Result

log = logging.getLogger(__name__)


class CheckpointManagementMixin:
    """Mixin providing checkpoint and reset methods for DevModeService."""

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
        result = await session.reset_soft()
        execution_time = time.time() - start_time

        return result, execution_time

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
            result, execution_time = asyncio.run(
                self._reset_soft_async(request)
            )

            if result.success:
                return Result.ok(DevResetResult(
                    success=True,
                    reset_type='soft',
                    execution_time=execution_time,
                    message="Variables reset to initial state"
                ))
            return Result.fail(
                result.error.code if result.error else "RESET_FAILED",
                result.error.message if result.error else "Soft reset failed",
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
        except (OSError, SQLAlchemyError, asyncio.CancelledError) as e:
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
        result = await session.reset_hard()
        execution_time = time.time() - start_time

        return result, execution_time

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
            result, execution_time = asyncio.run(
                self._reset_hard_async(request)
            )

            if result.success:
                return Result.ok(DevResetResult(
                    success=True,
                    reset_type='hard',
                    execution_time=execution_time,
                    message="VM restored to initial snapshot"
                ))
            return Result.fail(
                result.error.code if result.error else "RESET_FAILED",
                result.error.message if result.error else "Hard reset failed",
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
        result = await session.create_checkpoint(request.name, request.description)
        return result

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
            result = asyncio.run(
                self._create_checkpoint_async(request)
            )

            if result.success:
                return Result.ok(True)
            return Result.fail(
                result.error.code if result.error else "CHECKPOINT_CREATE_FAILED",
                result.error.message if result.error else f"Failed to create checkpoint '{request.name}'",
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
        result = await session.restore_checkpoint(request.name)
        return result

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
            result = asyncio.run(
                self._restore_checkpoint_async(request)
            )

            if result.success:
                return Result.ok(True)
            return Result.fail(
                result.error.code if result.error else "CHECKPOINT_NOT_FOUND",
                result.error.message if result.error else f"Checkpoint '{request.name}' not found",
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

    def list_checkpoints(self, request: DevCheckpointListRequest) -> Result[list[DevCheckpointInfo]]:
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
                if checkpoint.memory_file_path and not Path(checkpoint.memory_file_path).exists() or checkpoint.disk_file_path and not Path(checkpoint.disk_file_path).exists():
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
