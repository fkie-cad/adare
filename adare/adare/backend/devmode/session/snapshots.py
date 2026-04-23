"""
Snapshot, checkpoint, and reset methods for DevModeSession.

This module contains the DevModeSnapshotsMixin with methods for
creating/restoring snapshots, soft/hard resets, and checkpoint management.
"""

import asyncio
import logging
import time
from datetime import datetime
from pathlib import Path

import ulid

from adare.backend.experiment.runctx import ExperimentRunCtx
from adare.backend.experiment.stagectxmanager import StageCtxManager
from adare.backend.experiment.websocket_client import WebSocketTimeoutError
from adare.core.result import Result
from adare.database.exceptions import DatabaseError
from adare.exceptions import LoggedErrorException
from adare.hypervisor.exceptions import HypervisorException, SnapshotOperationException
from adare.types.stages import (
    CleanupShutdownStage,
    SoftwareInstallationStage,
)

from .core import DevModeSnapshot

log = logging.getLogger(__name__)


class DevModeSnapshotsMixin:
    """
    Mixin providing snapshot, checkpoint, and reset operations.

    Depends on attributes from DevModeSessionCore:
        session_id, console_ulid, experiment_ctx, playbook_controller,
        vm_manager, snapshots, actions_executed

    Depends on methods from DevModeSessionCore:
        _command_logger, _create_stage_context, _ensure_playbook_controller,
        _make_json_serializable
    """

    async def reset_soft(self) -> Result[None]:
        """
        Soft reset: Restore VM to initial external snapshot (no full OS reboot).

        For QEMU: Restores external snapshot (memory + disk, ~2-5 seconds, no OS boot)
        For VirtualBox: Only resets variables (fast, <1 second)

        Returns:
            Result[None] with success or error information
        """
        with self._command_logger("reset_soft"):
            try:
                # Ensure controller is initialized (needed for variable reset)
                controller_result = await self._ensure_playbook_controller()

                if not controller_result.success:
                    return controller_result

                # Get initial snapshot (first in list)
                if not self.snapshots:
                    log.warning("No snapshots available for soft reset")
                    return Result.fail("NO_SNAPSHOTS", "No snapshots available for soft reset")

                initial_snapshot = self.snapshots[0]
                vm = self.experiment_ctx.vm

                # QEMU: Restore external snapshot (memory + disk, no OS boot)
                if self.experiment_ctx.hypervisor_type == 'qemu':
                    log.info(f"Soft reset: restoring external snapshot '{initial_snapshot.snapshot_name}'")

                    try:
                        # Disconnect WebSocket before VM state change
                        if self.experiment_ctx.client:
                            await self.experiment_ctx.client.disconnect()
                            log.debug("WebSocket disconnected")

                        # Restore external snapshot
                        success = vm.restore_external_snapshot(
                            memory_path=initial_snapshot.memory_file_path,
                            disk_path=initial_snapshot.disk_file_path
                        )

                        if not success:
                            log.error("External snapshot restore failed")
                            # Fall back to variable-only reset
                            log.info("Falling back to variable-only reset")
                        else:
                            log.info("External snapshot restored (no OS reboot)")

                            # Reconnect WebSocket
                            from adare.backend.experiment.run import (
                                step_connect_websocket,
                            )
                            stage_ulid = self.console_ulid or self.experiment_ctx.experiment_run_ulid
                            with StageCtxManager(
                                SoftwareInstallationStage(),
                                stage_ulid,
                                event=self.experiment_ctx.user_interrupt_event
                            ):
                                await step_connect_websocket(self.experiment_ctx)
                                log.debug("WebSocket reconnected")

                    except (HypervisorException, SnapshotOperationException) as e:
                        log.error(f"External snapshot restore failed: {e}", exc_info=True)
                        log.info("Falling back to variable-only reset")
                    except (WebSocketTimeoutError, ConnectionError, OSError) as e:
                        log.error(f"External snapshot restore failed: {e}", exc_info=True)
                        log.info("Falling back to variable-only reset")

                # Reset playbook variables (always done, for both QEMU and VirtualBox)
                if self.playbook_controller:
                    self.playbook_controller.execution_context.clear()
                    self.playbook_controller.execution_context.update(
                        initial_snapshot.variable_state.copy()
                    )

                # Reset counters
                self.actions_executed = 0

                log.info("Soft reset completed successfully")
                return Result.ok(None)

            except HypervisorException as e:
                log.error(f"Soft reset failed: {e}", exc_info=True)
                return Result.fail("VM_OPERATION_FAILED", f"Soft reset failed: {e}")
            except (WebSocketTimeoutError, ConnectionError, OSError) as e:
                log.error(f"Soft reset failed: {e}", exc_info=True)
                return Result.fail("CONNECTION_FAILED", f"Soft reset failed: {e}")
            except LoggedErrorException as e:
                log.error(f"Soft reset failed: {e}", exc_info=True)
                return Result.fail("RESET_FAILED", f"Soft reset failed: {e}")

    async def reset_hard(self) -> Result[None]:
        """
        Hard reset: Restore VM to initial snapshot, reset all state.

        This uses VMLifecycleManager snapshot restoration (~10-30 seconds).
        All VM state (files, registry, memory) is restored to initial snapshot.

        Returns:
            Result[None] with success or error information
        """
        with self._command_logger("reset_hard"):
            try:
                if not self.snapshots:
                    log.error("No snapshots available for hard reset")
                    return Result.fail("NO_SNAPSHOTS", "No snapshots available for hard reset")

                initial_snapshot = self.snapshots[0]
                log.info(f"Starting hard reset to snapshot: {initial_snapshot.snapshot_name}")

                # 1. Disconnect WebSocket
                if self.experiment_ctx.client:
                    await self.experiment_ctx.client.disconnect()
                    log.debug("WebSocket disconnected")

                # 2. Stop VM (don't destroy)
                with self._create_stage_context(CleanupShutdownStage()):
                    await self.vm_manager.stop_vm(self.experiment_ctx, post_interrupt=True)
                log.debug("VM stopped")

                # 3. Restore snapshot using hypervisor-specific strategy
                await self._restore_snapshot(initial_snapshot.snapshot_name)
                log.debug("Snapshot restored")

                # 4. Start VM again
                await self.vm_manager.start_vm(self.experiment_ctx)
                log.debug("VM restarted")

                # 5. Install and reconnect to WebSocket
                from adare.backend.experiment.run import (
                    step_connect_websocket,
                    step_install_and_run_websocket_server,
                )
                with StageCtxManager(
                    SoftwareInstallationStage(),
                    self.experiment_ctx.experiment_run_ulid,
                    event=self.experiment_ctx.user_interrupt_event
                ):
                    await step_install_and_run_websocket_server(self.experiment_ctx)
                    await step_connect_websocket(self.experiment_ctx)
                    log.debug("WebSocket reconnected")

                # 6. Reset playbook controller state
                if self.playbook_controller:
                    self.playbook_controller.execution_context.clear()
                    self.playbook_controller.execution_context.update(
                        initial_snapshot.variable_state.copy()
                    )

                # 7. Reset counters
                self.actions_executed = 0

                log.info("Hard reset completed successfully")
                return Result.ok(None)

            except HypervisorException as e:
                log.error(f"Hard reset failed: {e}", exc_info=True)
                return Result.fail("VM_OPERATION_FAILED", f"Hard reset failed: {e}")
            except (WebSocketTimeoutError, ConnectionError, OSError) as e:
                log.error(f"Hard reset failed: {e}", exc_info=True)
                return Result.fail("CONNECTION_FAILED", f"Hard reset connection failed: {e}")
            except LoggedErrorException as e:
                log.error(f"Hard reset failed: {e}", exc_info=True)
                return Result.fail("RESET_FAILED", f"Hard reset failed: {e}")

    async def create_checkpoint(self, name: str, description: str = "") -> Result[None]:
        """
        Create a named snapshot for later restoration.

        Args:
            name: Name for the checkpoint
            description: Optional description

        Returns:
            Result[None] with success or error information
        """
        with self._command_logger(f"checkpoint_create_{name}"):
            try:
                await self._create_dev_snapshot(name, description)
                return Result.ok(None)
            except (HypervisorException, SnapshotOperationException) as e:
                log.error(f"Failed to create checkpoint: {e}", exc_info=True)
                return Result.fail("SNAPSHOT_FAILED", f"Failed to create checkpoint: {e}")
            except (WebSocketTimeoutError, ConnectionError, OSError) as e:
                log.error(f"Failed to create checkpoint: {e}", exc_info=True)
                return Result.fail("CONNECTION_FAILED", f"Failed to create checkpoint: {e}")
            except (DatabaseError, LoggedErrorException) as e:
                log.error(f"Failed to create checkpoint: {e}", exc_info=True)
                return Result.fail("CHECKPOINT_FAILED", f"Failed to create checkpoint: {e}")

    async def _wait_for_vm_ready_after_restore(self, context: ExperimentRunCtx, timeout: int = 60):
        """
        Wait for VM to be ready after external snapshot restore.

        After virsh restore, the VM is running with restored memory state,
        but the guest OS needs time to initialize network and services.

        Args:
            context: Experiment run context
            timeout: Maximum seconds to wait for readiness

        Raises:
            LoggedException: If VM doesn't become ready within timeout
        """
        log.info("Waiting for VM to be ready after snapshot restore...")
        start_time = time.time()

        # For QEMU, wait for guest agent to be ready
        if hasattr(context.vm, '_check_guest_agent'):
            try:
                # Try to wait for guest agent with timeout
                elapsed = 0
                while elapsed < timeout:
                    try:
                        # Check if guest agent is responsive
                        is_ready = context.vm._check_guest_agent()
                        if is_ready:
                            log.info(f"VM ready after {elapsed:.1f}s")
                            return
                    except Exception:
                        pass

                    await asyncio.sleep(2)
                    elapsed = time.time() - start_time

                # Timeout - but don't fail, just warn
                log.warning(f"Guest agent not ready after {timeout}s, continuing anyway")

            except Exception as e:
                log.warning(f"Could not check guest agent readiness: {e}")
        else:
            # Fallback: simple sleep to give VM time to stabilize
            await asyncio.sleep(5)
            log.info("VM stabilization wait completed")

    async def restore_checkpoint(self, name: str) -> Result[None]:
        """
        Restore to a named checkpoint using external snapshot.

        Loads checkpoint from database and restores VM to external snapshot state.

        Args:
            name: Name of the checkpoint to restore

        Returns:
            Result[None] with success or error information
        """
        with self._command_logger(f"checkpoint_restore_{name}"):
            try:
                from adare.database.api.devmode import DevModeApi

                # Load checkpoint from database
                with DevModeApi() as api:
                    checkpoint = api.get_checkpoint(self.session_id, name)

                if not checkpoint:
                    log.error(f"Checkpoint '{name}' not found in database")
                    return Result.fail("CHECKPOINT_NOT_FOUND", f"Checkpoint '{name}' not found in database")

                log.info(f"Restoring checkpoint: {checkpoint.name}")

                # Find corresponding snapshot in memory (for variable state)
                snapshot = next(
                    (s for s in self.snapshots if s.checkpoint_id == checkpoint.checkpoint_id),
                    None
                )

                # If not in memory, construct from database checkpoint
                if not snapshot:
                    snapshot = DevModeSnapshot(
                        snapshot_name=checkpoint.snapshot_name,
                        created_at=checkpoint.created_at,
                        variable_state=checkpoint.variable_state or {},
                        description=checkpoint.description or "",
                        memory_file_path=checkpoint.memory_file_path,
                        disk_file_path=checkpoint.disk_file_path,
                        checkpoint_id=checkpoint.checkpoint_id
                    )

                vm = self.experiment_ctx.vm

                # QEMU: Restore external snapshot
                if self.experiment_ctx.hypervisor_type == 'qemu':
                    # Disconnect WebSocket before VM state change
                    if self.experiment_ctx.client:
                        await self.experiment_ctx.client.disconnect()

                    # Restore external snapshot (destroys VM, updates disk, restores memory)
                    success = vm.restore_external_snapshot(
                        memory_path=snapshot.memory_file_path,
                        disk_path=snapshot.disk_file_path
                    )

                    if not success:
                        log.error(f"Failed to restore external snapshot for checkpoint '{name}'")
                        return Result.fail("SNAPSHOT_RESTORE_FAILED", f"Failed to restore external snapshot for checkpoint '{name}'")

                    # Wait for VM to be ready after memory restore
                    # The VM is running after virsh restore, but guest OS needs time to initialize
                    log.info("Waiting for VM to be ready after snapshot restore...")
                    await self._wait_for_vm_ready_after_restore(self.experiment_ctx)

                    # Verify websocket port is set (should be from session restore)
                    if not self.experiment_ctx.config.websocket_port:
                        log.error("WebSocket port not set in context - cannot reconnect")
                        return Result.fail("CONNECTION_FAILED", "WebSocket port not set in context - cannot reconnect")

                    # Restart agent and reconnect to WebSocket server
                    # (Required because shared directory issues may kill the agent during restore)
                    from adare.backend.experiment.run import (
                        step_connect_websocket,
                        step_install_and_run_websocket_server,
                    )
                    with StageCtxManager(
                        SoftwareInstallationStage(),
                        self.experiment_ctx.experiment_run_ulid,
                        event=self.experiment_ctx.user_interrupt_event
                    ):
                        await step_install_and_run_websocket_server(self.experiment_ctx)
                        await step_connect_websocket(self.experiment_ctx)

                # VirtualBox path (unchanged)
                elif self.experiment_ctx.hypervisor_type == 'virtualbox':
                    # Disconnect WebSocket
                    if self.experiment_ctx.client:
                        await self.experiment_ctx.client.disconnect()

                    # Stop VM
                    with self._create_stage_context(CleanupShutdownStage()):
                        await self.vm_manager.stop_vm(self.experiment_ctx, post_interrupt=True)

                    # Restore snapshot
                    await self._restore_snapshot(snapshot.snapshot_name)

                    # Start VM
                    await self.vm_manager.start_vm(self.experiment_ctx)

                    # Reconnect WebSocket
                    from adare.backend.experiment.run import (
                        step_connect_websocket,
                        step_install_and_run_websocket_server,
                    )
                    with StageCtxManager(
                        SoftwareInstallationStage(),
                        self.experiment_ctx.experiment_run_ulid,
                        event=self.experiment_ctx.user_interrupt_event
                    ):
                        await step_install_and_run_websocket_server(self.experiment_ctx)
                        await step_connect_websocket(self.experiment_ctx)

                # Reset playbook controller state
                self.playbook_controller.execution_context.clear()
                self.playbook_controller.execution_context.update(
                    snapshot.variable_state.copy()
                )

                # Reset counters
                self.actions_executed = 0

                log.info(f"Checkpoint '{name}' restored successfully")
                return Result.ok(None)

            except (HypervisorException, SnapshotOperationException) as e:
                log.error(f"Failed to restore checkpoint: {e}", exc_info=True)
                return Result.fail("SNAPSHOT_RESTORE_FAILED", f"Failed to restore checkpoint: {e}")
            except (WebSocketTimeoutError, ConnectionError, OSError) as e:
                log.error(f"Failed to restore checkpoint: {e}", exc_info=True)
                return Result.fail("CONNECTION_FAILED", f"Failed to restore checkpoint: {e}")
            except (DatabaseError, LoggedErrorException) as e:
                log.error(f"Failed to restore checkpoint: {e}", exc_info=True)
                return Result.fail("CHECKPOINT_RESTORE_FAILED", f"Failed to restore checkpoint: {e}")

    async def _create_dev_snapshot(self, name: str, description: str):
        """
        Create VM external snapshot for dev mode.

        For QEMU, creates external libvirt snapshot with memory and disk files.
        Saves checkpoint metadata to database.

        Args:
            name: Name for the snapshot
            description: Description of the snapshot
        """
        from adare.database.api.devmode import DevModeApi
        from adare.database.models.devcheckpoint import DevCheckpoint

        snapshot_name = f"devmode_{self.session_id}_{name}"
        checkpoint_id = str(ulid.ULID())

        log.info(f"Creating external snapshot: {snapshot_name}")

        # Delegate to hypervisor-specific strategy
        if self.experiment_ctx.hypervisor_type == 'virtualbox':
            # VirtualBox: Can create snapshots on running VMs
            vm = self.experiment_ctx.vm
            returncode = vm.create_snapshot(snapshot_name, description)
            if returncode != 0:
                raise HypervisorException(f"Failed to create VirtualBox snapshot '{snapshot_name}'")
            log.debug(f"VirtualBox snapshot created: {snapshot_name}")

            # For VirtualBox, we don't have external files
            memory_file_path = ""
            disk_file_path = ""

        elif self.experiment_ctx.hypervisor_type == 'qemu':
            # QEMU: Create external libvirt snapshot
            vm = self.experiment_ctx.vm

            # Verify VM is running
            if vm.get_state() != 'running':
                raise HypervisorException("VM must be running to create live snapshot")

            # STOP AGENT BEFORE SNAPSHOT
            # This ensures that when the snapshot is restored, the agent is NOT running,
            # allowing for a clean fresh start using the cached command.
            log.info("Stopping AdareVM agent before snapshot to ensure clean state")

            # 1. Disconnect WebSocket client
            if self.experiment_ctx.client:
                try:
                    await self.experiment_ctx.client.disconnect()
                except (WebSocketTimeoutError, ConnectionError, OSError) as e:
                    log.warning(f"Error disconnecting client before snapshot: {e}")

            # 2. Kill adarevm process in VM
            try:
                if self.experiment_ctx.guest_platform == 'windows':
                    stop_cmd = "taskkill /F /IM adarevm.exe"
                else:
                    # Linux: pkill
                    stop_cmd = "pkill -f adarevm"

                # Run stop command (ignore errors if not running)
                # We use a short timeout
                await vm.run_command(stop_cmd, timeout=10)
            except (HypervisorException, OSError, TimeoutError) as e:
                log.warning(f"Failed to stop adarevm agent in VM (might not be running): {e}")

            # Wait a moment for process to die and file handles to close
            await asyncio.sleep(2)

            # Compute snapshot storage directory
            snapshot_dir = vm._get_snapshot_storage_dir()

            # Generate file paths
            memory_file_path = str(snapshot_dir / f"{snapshot_name}_RAM.save")
            disk_file_path = str(snapshot_dir / f"{snapshot_name}_DISK.qcow2")

            # Create external snapshot
            success = vm.create_external_snapshot(
                snapshot_name=snapshot_name,
                memory_path=memory_file_path,
                disk_path=disk_file_path,
                use_quiesce=True
            )

            if not success:
                raise HypervisorException(f"Failed to create external snapshot '{snapshot_name}'")

            log.info(f"External snapshot created: {snapshot_name}")
            log.debug(f"Memory file: {memory_file_path}")
            log.debug(f"Disk file: {disk_file_path}")

            # Restart agent and reconnect
            # (Required because shared directory issues may kill the agent during snapshot creation)
            log.info("Restarting AdareVM agent after snapshot creation")

            from adare.backend.experiment.run import step_connect_websocket, step_install_and_run_websocket_server

            with StageCtxManager(
                SoftwareInstallationStage(),
                self.experiment_ctx.experiment_run_ulid,
                event=self.experiment_ctx.user_interrupt_event
            ):
                await step_install_and_run_websocket_server(self.experiment_ctx)
                await step_connect_websocket(self.experiment_ctx)

        else:
            log.warning(f"Unknown hypervisor type: {self.experiment_ctx.hypervisor_type}")
            memory_file_path = ""
            disk_file_path = ""

        # Save checkpoint to database
        variable_state = (
            self._make_json_serializable(self.playbook_controller.execution_context)
            if self.playbook_controller else {}
        )

        checkpoint = DevCheckpoint(
            checkpoint_id=checkpoint_id,
            session_id=self.session_id,
            name=name,
            description=description,
            memory_file_path=memory_file_path,
            disk_file_path=disk_file_path,
            snapshot_name=snapshot_name,
            variable_state=variable_state,
            created_at=datetime.now()
        )

        with DevModeApi() as api:
            api.save_checkpoint(checkpoint)

        log.info(f"Checkpoint saved to database: {checkpoint_id}")

        # Removed redundant YAML log creation (_write_checkpoint_log)
        # We only want the standard adare command log created by _command_logger wrapper

        # Store snapshot metadata in memory
        snapshot = DevModeSnapshot(
            snapshot_name=snapshot_name,
            created_at=datetime.now(),
            variable_state=variable_state,
            description=description,
            memory_file_path=memory_file_path,
            disk_file_path=disk_file_path,
            checkpoint_id=checkpoint_id
        )
        self.snapshots.append(snapshot)

        log.info(f"Snapshot metadata stored: {snapshot_name}")

    async def _restore_snapshot(self, snapshot_name: str):
        """
        Restore VM to specific snapshot.

        Args:
            snapshot_name: Name of the snapshot to restore
        """
        log.info(f"Restoring snapshot: {snapshot_name}")

        # Delegate to hypervisor-specific strategy
        if self.experiment_ctx.hypervisor_type == 'virtualbox':
            # VirtualBox: Use VM's snapshot mixin directly
            vm = self.experiment_ctx.vm
            success = vm.restore_snapshot(snapshot_name)
            if not success:
                raise HypervisorException(f"Failed to restore VirtualBox snapshot '{snapshot_name}'")
            log.debug(f"VirtualBox snapshot restored: {snapshot_name}")

        elif self.experiment_ctx.hypervisor_type == 'qemu':
            # QEMU Hard Reset: Restore disk snapshot + full OS reboot
            vm = self.experiment_ctx.vm

            log.info(f"Hard reset: restoring disk snapshot '{snapshot_name}_disk' with full reboot")

            try:
                # Check if disk snapshot exists
                disk_snapshot_name = f"{snapshot_name}_disk"
                if vm.snapshot_exists(disk_snapshot_name):
                    # Restore disk snapshot (qemu-img)
                    success = vm.restore_snapshot(disk_snapshot_name, silent=False)
                    if not success:
                        raise HypervisorException("Disk snapshot restore failed")
                    log.info("Disk snapshot restored")
                else:
                    # Fall back to overlay recreation if snapshot doesn't exist
                    log.warning(f"Disk snapshot '{disk_snapshot_name}' not found, falling back to overlay recreation")

                    experiment_id = self.experiment_ctx.experiment_run_ulid

                    # Delete old overlay disk
                    old_overlay = vm.get_overlay_disk_path(experiment_id)
                    if Path(old_overlay).exists():
                        log.debug(f"Deleting old overlay: {old_overlay}")
                        Path(old_overlay).unlink()

                    # Create fresh overlay from base disk
                    new_overlay = await vm.create_overlay_disk(experiment_id)
                    log.debug(f"Created fresh overlay: {new_overlay}")

                    # Update VM config to use new overlay
                    vm.config.disk_path = new_overlay
                    log.info("QEMU overlay reset complete")

            except (HypervisorException, OSError) as e:
                log.error(f"Hard reset disk restoration failed: {e}", exc_info=True)
                raise

        else:
            log.warning(f"Unknown hypervisor type: {self.experiment_ctx.hypervisor_type}")

        log.info(f"Snapshot restored successfully: {snapshot_name}")

    async def _cleanup_snapshots(self):
        """
        Cleanup all checkpoints and snapshot files for this session.

        Deletes external snapshot files and database checkpoint records.
        """
        from adare.database.api.devmode import DevModeApi

        log.info(f"Cleaning up checkpoints for session {self.session_id}")

        # Load all checkpoints from database
        with DevModeApi() as api:
            checkpoints = api.list_checkpoints(self.session_id)

        if not checkpoints:
            log.debug("No checkpoints to clean up")
            return

        # Delete snapshots based on hypervisor type
        if self.experiment_ctx.hypervisor_type == 'qemu':
            vm = self.experiment_ctx.vm

            for checkpoint in checkpoints:
                try:
                    # Delete external snapshot
                    success = vm.delete_external_snapshot(
                        snapshot_name=checkpoint.snapshot_name,
                        memory_path=checkpoint.memory_file_path,
                        disk_path=checkpoint.disk_file_path
                    )
                    if success:
                        log.debug(f"Deleted external snapshot: {checkpoint.snapshot_name}")
                    else:
                        log.warning(f"Failed to delete external snapshot: {checkpoint.snapshot_name}")

                except Exception as e:
                    log.warning(f"Error deleting external snapshot {checkpoint.snapshot_name}: {e}")

        elif self.experiment_ctx.hypervisor_type == 'virtualbox':
            vm = self.experiment_ctx.vm

            for checkpoint in checkpoints:
                try:
                    success = vm.delete_snapshot(checkpoint.snapshot_name, silent=True)
                    if success:
                        log.debug(f"Deleted VirtualBox snapshot: {checkpoint.snapshot_name}")
                except Exception as e:
                    log.warning(f"Failed to delete VirtualBox snapshot {checkpoint.snapshot_name}: {e}")

        # Delete all checkpoints from database
        with DevModeApi() as api:
            deleted_count = api.delete_session_checkpoints(self.session_id)

        log.info(f"Cleaned up {deleted_count} checkpoints for session {self.session_id}")

        # Clean up empty snapshot directory for QEMU
        if self.experiment_ctx.hypervisor_type == 'qemu':
            try:
                vm = self.experiment_ctx.vm
                snapshot_dir = vm._get_snapshot_storage_dir()
                if snapshot_dir.exists():
                    # Check if directory is empty
                    if not any(snapshot_dir.iterdir()):
                        snapshot_dir.rmdir()
                        log.info(f"Removed empty snapshot directory: {snapshot_dir}")
                    else:
                        log.warning(f"Snapshot directory not empty after cleanup: {snapshot_dir}")
            except Exception as e:
                log.warning(f"Failed to remove snapshot directory: {e}")
