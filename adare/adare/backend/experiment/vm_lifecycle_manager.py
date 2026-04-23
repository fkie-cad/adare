import logging
import os
import shutil
import threading
from datetime import UTC, datetime
from pathlib import Path

import adare.backend.environment.database as environment_database
import adare.backend.experiment.database as experiment_database
import adare.backend.vm.database as vm_database
from adare.backend.experiment.directory import ExperimentRunDirectory
from adare.backend.experiment.runctx import ExperimentRunCtx
from adare.backend.experiment.stagectxmanager import StageCtxManager
from adare.exceptions import LoggedException
from adare.hypervisor.virtualbox import VirtualBoxVM
from adare.types.stages import (
    VMDestroyStage,
    VMExperimentSnapshotStage,
    VMFileTransferSetupStage,
    VMImportStage,
    VMInstanceVerificationStage,
    VMNetworkingStage,
    VMRuntimePreparationStage,
    VMSnapshotCreateStage,
    VMStopStage,
)

log = logging.getLogger(__name__)


class VMLifecycleManager:
    """Manages the complete lifecycle of VMs for experiments using hypervisor-specific strategies."""

    def __init__(self, hypervisor_type: str = 'virtualbox'):
        """
        Initialize VM lifecycle manager with appropriate hypervisor strategy.

        Args:
            hypervisor_type: Type of hypervisor ('virtualbox' or 'qemu')
        """
        self.hypervisor_type = hypervisor_type

        # Instantiate appropriate lifecycle strategy based on hypervisor type
        if hypervisor_type == 'virtualbox':
            from adare.hypervisor.virtualbox.lifecycle import VirtualBoxLifecycleStrategy
            self.strategy = VirtualBoxLifecycleStrategy()
        elif hypervisor_type == 'qemu':
            from adare.hypervisor.qemu.lifecycle import QEMULifecycleStrategy
            self.strategy = QEMULifecycleStrategy()
        else:
            raise ValueError(f"Unsupported hypervisor: {hypervisor_type}. Supported: 'virtualbox', 'qemu'")

    async def _ensure_vm_runtime_ready(self, context: ExperimentRunCtx):
        """Ensure project VM runtime directory is ready with up-to-date adarevm and adarelib."""
        # Use project-level vm_runtime directory instead of creating per-experiment copies
        vm_runtime_dir = context.project_directory.vm_runtime
        adarevm_target = vm_runtime_dir / 'adarevm'
        adarelib_target = vm_runtime_dir / 'adarelib'

        # Use global sources
        adarevm_source = context.adarevm
        adarelib_source = context.adarelib

        # Check if we need to copy/update files
        needs_update = False

        if not vm_runtime_dir.exists():
            log.info("Creating project VM runtime directory for first time")
            needs_update = True
        elif not adarevm_target.exists() or not adarelib_target.exists():
            log.info("Project VM runtime directory incomplete, updating")
            needs_update = True
        else:
            # Check if source files are newer than target
            adarevm_source_time = self._get_latest_mtime(adarevm_source)
            adarelib_source_time = self._get_latest_mtime(adarelib_source)
            adarevm_target_time = self._get_latest_mtime(adarevm_target)
            adarelib_target_time = self._get_latest_mtime(adarelib_target)

            if (adarevm_source_time > adarevm_target_time or
                adarelib_source_time > adarelib_target_time):
                log.info("Source files newer than cached runtime, updating")
                needs_update = True

        if needs_update:
            # Create/recreate VM runtime directory
            if vm_runtime_dir.exists():
                shutil.rmtree(vm_runtime_dir)
            vm_runtime_dir.mkdir(parents=True)

            # Copy adarevm
            log.info(f"Copying adarevm from {adarevm_source} to {adarevm_target}")
            shutil.copytree(adarevm_source, adarevm_target, dirs_exist_ok=True)

            # Copy adarelib
            log.info(f"Copying adarelib from {adarelib_source} to {adarelib_target}")
            shutil.copytree(adarelib_source, adarelib_target, dirs_exist_ok=True)

            log.info("Project VM runtime directory ready")

        # Build wheels (separate from copy logic since we check mtime separately)
        wheels_dir = vm_runtime_dir / 'wheels'
        wheels_dir.mkdir(exist_ok=True)

        adarelib_wheel = list(wheels_dir.glob('adarelib-*.whl'))
        adarevm_wheel = list(wheels_dir.glob('adarevm-*.whl'))

        # Check if wheels need rebuilding
        rebuild_wheels = False
        if not adarelib_wheel or not adarevm_wheel:
            log.info("Wheels not found - building...")
            rebuild_wheels = True
        else:
            # Check if source is newer than wheels
            adarelib_wheel_time = adarelib_wheel[0].stat().st_mtime
            adarevm_wheel_time = adarevm_wheel[0].stat().st_mtime

            adarelib_source_time = self._get_latest_mtime(adarevm_source)
            adarevm_source_time = self._get_latest_mtime(adarevm_source)

            if (adarelib_source_time > adarelib_wheel_time or
                adarevm_source_time > adarevm_wheel_time):
                log.info("Source code newer than wheels - rebuilding...")
                rebuild_wheels = True
            else:
                log.info("Wheels are up-to-date - skipping build")

        if rebuild_wheels:
            try:
                # Clean old wheels
                for old_wheel in wheels_dir.glob('*.whl'):
                    old_wheel.unlink()

                # Build adarelib wheel first (it has no path dependencies)
                log.info("Building adarelib wheel...")
                import subprocess
                subprocess.run(
                    ["uv", "build", "--wheel", "--out-dir", str(wheels_dir)],
                    cwd=adarelib_target,
                    check=True,
                    capture_output=True
                )

                # Build adarevm wheel without path dependency
                log.info("Building adarevm wheel...")

                # Temporarily modify pyproject.toml to remove workspace source
                # This is necessary because uv workspace sources don't exist in the VM filesystem
                adarevm_pyproject = adarevm_target / 'pyproject.toml'
                original_content = adarevm_pyproject.read_text()

                # Remove workspace source for adarelib
                import re
                modified_content = re.sub(
                    r'adarelib\s*=\s*\{\s*workspace\s*=\s*true\s*\}',
                    '',
                    original_content
                )
                adarevm_pyproject.write_text(modified_content)

                try:
                    subprocess.run(
                        ["uv", "build", "--wheel", "--out-dir", str(wheels_dir)],
                        cwd=adarevm_target,
                        check=True,
                        capture_output=True
                    )
                finally:
                    # Restore original pyproject.toml
                    adarevm_pyproject.write_text(original_content)

                log.info(f"Wheels built in {wheels_dir}")
            except subprocess.CalledProcessError as e:
                log.warning(f"Wheel build failed: {e.stderr.decode() if e.stderr else str(e)}")
                log.warning("Falling back to editable install mode (wheels will not be available)")
                # Don't raise - let it fall back to editable install
        else:
            log.info("Project VM runtime directory up-to-date")

    def _get_latest_mtime(self, directory: Path) -> float:
        """Get the latest modification time in a directory tree."""
        if not directory.exists():
            return 0.0

        latest = 0.0
        for root, dirs, files in os.walk(directory):
            # Skip __pycache__ directories
            dirs[:] = [d for d in dirs if d != '__pycache__']

            for file in files:
                if file.endswith('.pyc'):
                    continue
                file_path = Path(root) / file
                try:
                    mtime = file_path.stat().st_mtime
                    latest = max(latest, mtime)
                except (OSError, PermissionError):
                    continue
        return latest


    async def create_and_prepare_vm(self, context: ExperimentRunCtx):
        """Create and prepare VM for experiment with snapshots and shared folders."""
        # Get VM ID from environment (file operations already done during environment load)
        env_data = environment_database.get_environment_by_ulid(context.environment_ulid, fields=['vm_id'])
        vm_id = env_data['vm_id'] if env_data else None
        if not vm_id:
            raise LoggedException(log, "No VM associated with environment. Did you load the environment properly?")

        # Prepare VM instance for experiment (includes port allocation and VM reuse)
        from adare.backend.vm.commands import ensure_vm_ready_for_experiment
        from adare.database.api.vm import VmApi

        log.info("Starting VM instance preparation for experiment (with dynamic port allocation)")

        # Use shorter experiment ID for VM instance naming (first 8 chars of ULID)
        short_experiment_id = context.experiment_run_ulid[:8]

        # Allocate VM instance (allocation and sync stages managed internally)
        import asyncio
        vm_instance_id = await asyncio.wait_for(
            ensure_vm_ready_for_experiment(
                vm_id=vm_id,
                experiment_id=short_experiment_id,  # Use shorter ID for naming
                environment_ulid=context.environment_ulid,
                experiment_run_ulid=context.experiment_run_ulid,
                preserve_experiment_snapshot=context.config.preserve_snapshot,
                interrupt_event=context.user_interrupt_event,
                test_mode=context.test_mode  # NEW: Pass test mode from context
            ),
            timeout=300  # 5 minute timeout for VM import operations
        )

        log.info(f"VM instance allocation completed successfully, instance_id={vm_instance_id}")

        # Check if VM preparation was interrupted - return early if so
        if vm_instance_id is None:
            log.info("VM instance preparation was interrupted - returning early")
            return

        # Get the prepared VM instance from database
        log.debug(f"Attempting to fetch VM instance with ID: {vm_instance_id}")
        try:
            with VmApi() as api:
                vm_instance = api.get_vm_instance_by_id(vm_instance_id)
                if not vm_instance:
                    # Try to debug what instances exist
                    log.error(f"VM instance {vm_instance_id} not found! Checking database...")
                    all_instances = api.get_all_vm_instances()
                    log.error(f"Found {len(all_instances)} total instances in database:")
                    for inst in all_instances:
                        log.error(f"  - {inst.id}: {inst.instance_name} (status: {inst.status})")

                    # Check if ID format is correct
                    log.error(f"Problematic ID: '{vm_instance_id}' (length: {len(vm_instance_id)}, type: {type(vm_instance_id)})")

                    raise LoggedException(log, f"VM instance with ID {vm_instance_id} not found after preparation")

                log.debug(f"Successfully found VM instance: {vm_instance.instance_name}")
        except Exception as e:
            log.error(f"Error fetching VM instance: {e}")
            import traceback
            log.debug(f"Fetch VM instance traceback: {traceback.format_exc()}")
            raise

        # Update experiment run with VM instance ID
        experiment_database.update_experiment_run_vm_instance(
            context.config.project_path,
            context.experiment_run_ulid,
            vm_instance_id
        )

        # Use the instance name and port from the allocated instance
        context.vm_name = vm_instance.instance_name
        context.config.websocket_port = vm_instance.websocket_port

        # Validate that the port was properly allocated
        if context.config.websocket_port is None:
            raise LoggedException(log, f"VM instance {vm_instance.instance_name} has no websocket port allocated")

        log.info(f"Using VM instance: {context.vm_name} on port {context.config.websocket_port}")

        # Setup VM runtime directory with smart copying
        with StageCtxManager(
            VMRuntimePreparationStage(),
            context.experiment_run_ulid,
            event=context.user_interrupt_event
        ):
            await self._ensure_vm_runtime_ready(context)

        # Delegate VM instance creation to hypervisor-specific strategy
        await self.strategy.prepare_vm_for_experiment(context)

        # NOTE: setup_file_transfer() removed from here - now called explicitly in run.py
        # This makes file transfer operations visible as a dedicated stage in the UI

        # VirtualBox-specific: VM instance is already prepared with snapshots - verify it exists and cleanup if missing
        # For QEMU, the prepare_vm_for_experiment already handles all VM creation
        # NOTE: VMCreateStage wrapper removed - will be added in run.py to wrap entire create_and_prepare_vm()
        if self.hypervisor_type == 'virtualbox':
            # Import the VM instance verification function
            from adare.backend.vm.commands import verify_and_cleanup_vm_instance_for_experiment
            from adare.database.api.vm import VmApi

            # Wrap verification and recovery logic with stage for visibility
            with StageCtxManager(
                VMInstanceVerificationStage(),
                context.experiment_run_ulid,
                event=context.user_interrupt_event
            ):
                # First verify and cleanup VM instance if missing from VirtualBox
                try:
                    vm_instance_is_available = verify_and_cleanup_vm_instance_for_experiment(
                        vm_instance.id,
                        context.experiment_run_ulid
                    )
                    if not vm_instance_is_available:
                        # VM instance was missing and cleaned up - need to allocate a new one
                        log.info("VM instance was cleaned up, allocating a new instance for the experiment")

                        # Re-allocate a new VM instance for this experiment
                        from adare.backend.vm.instance_manager import allocate_vm_instance_for_experiment

                        # Get VM ID from environment (same as original allocation)
                        env_data = environment_database.get_environment_by_ulid(context.environment_ulid, fields=['vm_id'])
                        vm_id = env_data['vm_id'] if env_data else None
                        if not vm_id:
                            raise LoggedException(log, "No VM associated with environment after cleanup")

                        # Allocate new instance
                        new_vm_instance = await allocate_vm_instance_for_experiment(vm_id, context.experiment_run_ulid)
                        if not new_vm_instance:
                            raise LoggedException(log, "Failed to allocate new VM instance after cleanup")

                        # Update the experiment run with new VM instance ID
                        experiment_database.update_experiment_run_vm_instance(
                            context.config.project_path,
                            context.experiment_run_ulid,
                            new_vm_instance.id
                        )

                        # Update context with new instance information
                        vm_instance = new_vm_instance
                        context.vm_name = vm_instance.instance_name
                        context.config.websocket_port = vm_instance.websocket_port

                        # Validate that the port was properly allocated
                        if context.config.websocket_port is None:
                            raise LoggedException(log, f"New VM instance {vm_instance.instance_name} has no websocket port allocated")

                        log.info(f"Successfully allocated new VM instance after cleanup: {context.vm_name} on port {context.config.websocket_port}")

                        # New instance needs to be imported to VirtualBox if it doesn't have a UUID
                        if not vm_instance.vbox_uuid:
                            log.info(f"New VM instance '{vm_instance.instance_name}' needs to be imported to VirtualBox")

                            # Get source VM for import
                            source_vm = vm_database.get_vm_by_id(vm_id)
                            if not source_vm:
                                raise LoggedException(log, f"Source VM with ID {vm_id} not found for import")

                            # Verify source VM integrity
                            from adare.backend.vm.commands import verify_vm_integrity
                            await verify_vm_integrity(vm_id, context.experiment_run_ulid, context.user_interrupt_event, test_mode=context.test_mode)

                            # Import VM instance to VirtualBox with proper stage management
                            from adare.types.stages import VMDiskPreparationStage
                            with StageCtxManager(VMDiskPreparationStage(), context.experiment_run_ulid, context.user_interrupt_event):
                                with StageCtxManager(VMImportStage(), context.experiment_run_ulid, context.user_interrupt_event):
                                    log.info(f"Importing new VM instance '{vm_instance.instance_name}' to VirtualBox...")

                                    # Import using VirtualBox manager directly (inline implementation)
                                    from adare.hypervisor.virtualbox.manager import VirtualBoxManager

                                    manager = VirtualBoxManager()
                                    vm_file_path = Path(source_vm.file)

                                    # Import VM with unique instance name
                                    vbox_vm = await manager.import_vm_async(
                                        vm_file_path,
                                        vm_instance.instance_name,
                                        environment_ulid=context.environment_ulid
                                    )

                                    # Update instance with VirtualBox UUID
                                    vbox_uuid = vbox_vm.get_vm_uuid()
                                    with VmApi() as api:
                                        api.update_vm_instance(
                                            vm_instance.id,
                                            vbox_uuid=vbox_uuid,
                                            base_snapshot_name=f"{vm_instance.instance_name}_base"
                                        )

                                    log.info(f"Successfully imported VM instance '{vm_instance.instance_name}' with UUID: {vbox_uuid}")

                                    # Return updated instance
                                    with VmApi() as api:
                                        vm_instance = api.get_vm_instance_by_id(vm_instance.id)

                            # Create base snapshot for the new instance
                            with StageCtxManager(VMSnapshotCreateStage(), context.experiment_run_ulid, context.user_interrupt_event):
                                from adare.backend.vm.snapshot_manager import create_base_snapshot_for_instance
                                snapshot_success = create_base_snapshot_for_instance(vm_instance, silent=False)
                                if not snapshot_success:
                                    log.warning(f"Failed to create base snapshot for new instance {vm_instance.instance_name}")
                                else:
                                    log.info(f"Successfully created base snapshot for new instance {vm_instance.instance_name}")

                            log.info(f"Successfully imported and prepared new VM instance: {vm_instance.instance_name}")
                except Exception as e:
                    log.error(f"VM instance verification failed: {e}")
                    raise LoggedException(log, f"VM instance verification failed: {e}") from e

                # Final verification that VM instance exists in VirtualBox
                if not vm_instance.vbox_uuid or not VirtualBoxVM.verify_vm_exists_by_uuid(vm_instance.vbox_uuid):
                    raise LoggedException(log, f"VM instance '{context.vm_name}' was not properly prepared - missing from VirtualBox")
                log.info(f"Using prepared VM instance '{context.vm_name}' with snapshots (UUID: {vm_instance.vbox_uuid})")

        # Update experiment run with VM-specific data (skip in diff mode where no database persistence)
        if (not context.stop_event.is_set() and
            context.experiment_run_directory is not None and
            isinstance(context.experiment_run_directory, ExperimentRunDirectory)):
            context.experiment_run_ulid = experiment_database.update_experiment_run(
                context.experiment_run_ulid,
                context.experiment_run_directory
            )

        context.timestamp_before_vm_start = datetime.now(UTC)

    async def setup_networking(self, context: ExperimentRunCtx):
        """
        Setup network configuration with proper stage visibility.

        Delegates to hypervisor-specific strategy:
        - VirtualBox: Configure port forwarding via VBoxManage
        - QEMU: Save port forwarding rules to config (applied on VM start)
        """
        with StageCtxManager(
            VMNetworkingStage(),
            context.experiment_run_ulid,
            event=context.user_interrupt_event
        ):
            await self.strategy.setup_networking(context)

    async def setup_file_transfer(self, context: ExperimentRunCtx):
        """
        Setup file transfer mechanism with proper stage visibility.

        Delegates to hypervisor-specific strategy:
        - VirtualBox: Configure shared folders and port forwarding
        - QEMU: Stop VM if needed, copy files via libguestfs
        """
        log.info("Starting file transfer setup")
        with StageCtxManager(
            VMFileTransferSetupStage(),
            context.experiment_run_ulid,
            event=context.user_interrupt_event
        ) as stage_ctx:
            if self.hypervisor_type == 'qemu' and hasattr(self.strategy, 'file_transfer'):
                stage_ctx.stage.sub_msg = self.strategy.file_transfer.setup_description
            await self.strategy.setup_file_transfer(context)
        log.info("File transfer setup completed")

    async def start_vm(self, context: ExperimentRunCtx):
        """
        Start the virtual machine and perform initialization.

        Delegates to hypervisor-specific strategy which handles:
        - VirtualBox: start -> set video mode -> wait for boot -> mount shared folders
        - QEMU: start -> wait for guest agent ready

        Note: Stages are now created inside strategy.start_and_initialize_vm()
        for better granularity (VMStartStage, VMGuestAgentWaitStage, etc.)
        """
        await self.strategy.start_and_initialize_vm(context)

    async def wait_until_ready(self, context: ExperimentRunCtx):
        """
        Wait until VM is fully booted and ready.

        NOTE: This is now handled by strategy.start_and_initialize_vm()
        but kept for backward compatibility with existing code that may call it separately.
        """
        # For backward compatibility - this is now a no-op as the strategy handles waiting
        log.debug("wait_until_ready() called - VM should already be ready from start_and_initialize_vm()")

    async def mount_shared_directories(self, context: ExperimentRunCtx):
        """
        Mount all configured shared directories in the VM.

        NOTE: This is now handled by strategy.start_and_initialize_vm()
        but kept for backward compatibility with existing code that may call it separately.
        """
        # For backward compatibility - this is now a no-op as the strategy handles mounting
        log.debug("mount_shared_directories() called - directories should already be mounted from start_and_initialize_vm()")

    async def stop_vm(self, context: ExperimentRunCtx, post_interrupt: bool = False, force: bool = False):
        """Stop the virtual machine."""
        event = None if post_interrupt else context.user_interrupt_event
        with StageCtxManager(VMStopStage(), context.experiment_run_ulid, event=event):
            log.info('stopping virtual machine')
            if context.vm:
                await context.vm.stop(force=force)

    async def retrieve_artifacts(self, context: ExperimentRunCtx, post_interrupt: bool = False, force_stop: bool = False):
        """
        Retrieve artifacts from VM with proper stage visibility.

        Delegates to hypervisor-specific strategy:
        - VirtualBox: No-op (artifacts already on host via shared folders)
        - QEMU: Strategy-dependent (QGA retrieves while running, libguestfs after stop)

        Args:
            context: ExperimentRunCtx
            post_interrupt: If True, don't check interrupt event (for cleanup after interrupt)
            force_stop: If True, force-stop VM (e.g. Windows on QEMU to prevent updates)
        """
        from adare.types.stages import VMFileTransferRetrievalStage

        # Don't check interrupt event when retrieving artifacts during post-interrupt cleanup
        event = None if post_interrupt else context.user_interrupt_event

        with StageCtxManager(
            VMFileTransferRetrievalStage(),
            context.experiment_run_ulid,
            event=event
        ) as stage_ctx:
            if self.hypervisor_type == 'qemu' and hasattr(self.strategy, 'file_transfer'):
                stage_ctx.stage.sub_msg = self.strategy.file_transfer.retrieval_description
            await self.strategy.retrieve_artifacts(context, post_interrupt=post_interrupt, force_stop=force_stop)

    async def perform_host_diff(self, context: ExperimentRunCtx, post_interrupt: bool = False):
        """
        Perform host-side disk diffing using virt-diff on base vs overlay disks.

        This method runs AFTER VM shutdown and BEFORE overlay cleanup to analyze
        filesystem changes using libguestfs virt-diff tool.

        Args:
            context: ExperimentRunCtx
            post_interrupt: If True, don't check interrupt event (for cleanup after interrupt)
        """
        # Early return for non-QEMU hypervisors
        if self.hypervisor_type != 'qemu':
            log.debug("Host-side diff skipped - requires QEMU hypervisor")
            return

        # Check if diff is enabled
        if not self._is_diff_enabled(context):
            log.debug("Host-side diff skipped - filesystem diff disabled")
            return

        # Check diff mode (only run for 'host' or 'auto' mode)
        diff_mode = self._get_diff_mode(context)
        if diff_mode not in ('host', 'auto'):
            log.debug(f"Host-side diff skipped - diff mode is '{diff_mode}'")
            return

        # Import VMHostDiffStage for stage visibility
        from adare.types.stages import VMHostDiffStage

        # Don't check interrupt event when performing diff during post-interrupt cleanup
        event = None if post_interrupt else context.user_interrupt_event

        # Wrap execution in StageCtxManager for flow console visibility
        with StageCtxManager(
            VMHostDiffStage(),
            context.experiment_run_ulid,
            event=event
        ) as stage_ctx:
            try:
                # Get disk paths from QEMU VM
                from adare.hypervisor.qemu.vm import QEMUVM
                if not isinstance(context.vm, QEMUVM):
                    log.warning("VM is not a QEMU instance - cannot perform host diff")
                    return

                base_disk_path = str(context.vm.get_base_disk_path())
                overlay_disk_path = str(context.vm.config.disk_path)

                log.debug(f"Base disk: {base_disk_path}")
                log.debug(f"Overlay disk: {overlay_disk_path}")

                # Validate disk paths exist
                from pathlib import Path
                if not Path(base_disk_path).exists():
                    log.error(f"Base disk not found: {base_disk_path}")
                    return
                if not Path(overlay_disk_path).exists():
                    log.error(f"Overlay disk not found: {overlay_disk_path}")
                    return

                # Call virt-diff through QEMU lifecycle strategy
                log.info("Performing host-side filesystem diff (virt-diff)")

                # Prepare diff artifacts directory
                diff_dir = None
                extract_content_dir = None

                if context.experiment_run_directory:
                    artifacts_dir = context.experiment_run_directory.path / 'artifacts'
                    diff_dir = artifacts_dir / 'diff'
                    diff_dir.mkdir(parents=True, exist_ok=True)
                    extract_content_dir = diff_dir / 'content'

                diff_results = self.strategy.compare_disk_images_with_virt_diff(
                    base_disk_path=base_disk_path,
                    overlay_disk_path=overlay_disk_path,
                    extract_dir=extract_content_dir
                )

                # Export results to artifacts directory
                if diff_results and diff_dir:
                    # Prepare metadata for JSON export
                    metadata = {
                        'diff_mode': 'host',
                        'tool': 'virt-ls-manual',
                        'base_disk_path': base_disk_path,
                        'overlay_disk_path': overlay_disk_path
                    }

                    # Export to JSON and CSV formats
                    from adare.backend.experiment.filesystem_snapshot import (
                        export_diff_bodyfile,
                        export_diff_csv,
                        export_diff_json,
                    )
                    json_path = diff_dir / 'filesystem_diffs.json'
                    csv_path = diff_dir / 'filesystem_diffs.csv'
                    bodyfile_path = diff_dir / 'filesystem_diffs.bodyfile'

                    export_diff_json(diff_results, json_path, metadata)
                    export_diff_csv(diff_results, csv_path)
                    export_diff_bodyfile(diff_results, bodyfile_path)

                    log.info(f"Host-side diff exported to {diff_dir}")
                    log.info(f"Filesystem changes - "
                            f"Added: {len(diff_results.get('added', []))}, "
                            f"Removed: {len(diff_results.get('removed', []))}, "
                            f"Modified: {len(diff_results.get('modified', []))}")

                    # Update stage sub_msg with diff summary for flow console display
                    stage_ctx.stage.sub_msg = (
                        f"Added: {len(diff_results.get('added', []))}, "
                        f"Removed: {len(diff_results.get('removed', []))}, "
                        f"Modified: {len(diff_results.get('modified', []))}"
                    )
                elif not diff_results:
                    log.warning("No diff results returned from virt-diff")

            except FileNotFoundError as e:
                log.warning(f"virt-diff tool not found - install libguestfs-tools: {e}")
            except Exception as e:
                log.warning(f"Host-side diff failed (continuing cleanup): {e}", exc_info=True)

    def _is_diff_enabled(self, context: ExperimentRunCtx) -> bool:
        """Check if filesystem diff is enabled from config or playbook settings."""
        # CLI override takes precedence
        if hasattr(context.config, 'enable_diff') and context.config.enable_diff is not None:
            return context.config.enable_diff

        # Fall back to playbook settings
        if context.playbook and hasattr(context.playbook, 'settings') and context.playbook.settings:
            return context.playbook.settings.enable_filesystem_diff

        return False

    def _get_diff_mode(self, context: ExperimentRunCtx) -> str:
        """Get diff mode from config or playbook settings."""
        # CLI override takes precedence
        if hasattr(context.config, 'diff_mode') and context.config.diff_mode:
            return context.config.diff_mode

        # Fall back to playbook settings
        if context.playbook and hasattr(context.playbook, 'settings') and context.playbook.settings:
            return getattr(context.playbook.settings, 'diff_mode', 'auto')

        return 'auto'

    async def cleanup_vm(self, context: ExperimentRunCtx, post_interrupt: bool = False):
        """
        Cleanup VM resources and handle experiment snapshots.

        NOTE: Artifact retrieval is now handled separately in run.py before this method
        to ensure proper stage hierarchy (VMFileTransferRetrievalStage is a sibling of
        VMDestroyStage, not a child).

        Delegates to hypervisor-specific strategy for:
        - Hypervisor-specific cleanup (port forwarding, etc.)
        """
        event = None if post_interrupt else context.user_interrupt_event
        with StageCtxManager(VMDestroyStage(), context.experiment_run_ulid, event=event):
            # Create experiment snapshot if requested
            if context.config.preserve_snapshot:
                log.info('Creating experiment snapshot (--preserve-snapshot enabled)')
                await self._create_experiment_snapshot(context, event)

            # Hypervisor-specific cleanup (port forwarding, etc.)
            await self.strategy.cleanup_vm(context, post_interrupt)

            # QEMU-specific: Cleanup experiment overlay disk
            # This deletes the overlay, leaving the immutable base disk intact
            if context.vm and hasattr(context.vm, 'cleanup_overlay_disk'):
                experiment_id = context.experiment_run_ulid or 'default'
                try:
                    await context.vm.cleanup_overlay_disk(experiment_id)
                    log.info(f"Cleaned up QEMU overlay for experiment {experiment_id}")
                except Exception as e:
                    log.warning(f"Failed to cleanup overlay disk: {e}")

            # QEMU-specific: Undefine libvirt domain to prevent stale disk path references
            # This ensures the domain doesn't persist with references to deleted overlay
            if context.vm and hasattr(context.vm, '_libvirt_domain'):
                try:
                    import libvirt

                    if context.vm._libvirt_domain:
                        try:
                            # Only undefine if domain is not running
                            state, _ = context.vm._libvirt_domain.state()
                            if state == libvirt.VIR_DOMAIN_SHUTOFF:
                                context.vm._libvirt_domain.undefine()
                                log.info(f"Undefined libvirt domain '{context.vm.vm_name}'")
                            else:
                                log.warning(
                                    f"Cannot undefine domain '{context.vm.vm_name}' - "
                                    f"still running (state: {state}). Domain will be undefined on next start."
                                )
                        except libvirt.libvirtError as e:
                            # Domain might already be undefined or in invalid state
                            log.debug(f"Could not undefine domain: {e}")
                        finally:
                            # Always clear cached domain object to force redefinition
                            context.vm._libvirt_domain = None
                            log.debug(f"Cleared libvirt domain cache for '{context.vm.vm_name}'")
                except Exception as e:
                    log.warning(f"Failed to cleanup libvirt domain: {e}")

            # Release VM instance for reuse by other experiments
            log.info('Releasing VM instance for reuse by future experiments')
            await self._release_vm_instance(context)

    async def _release_vm_instance(self, context: ExperimentRunCtx):
        """Release the VM instance used by this experiment."""
        try:
            # Get the VM instance ID from the experiment run
            from adare.database.api.experiment import ExperimentApi
            from adare.database.models.project_models import ExperimentRun

            with ExperimentApi(context.config.project_path) as api:
                experiment_run = api._session.query(ExperimentRun).filter(
                    ExperimentRun.id == context.experiment_run_ulid
                ).first()

            if experiment_run and experiment_run.vm_instance_id:
                from adare.backend.vm.commands import release_vm_instance_for_experiment
                await release_vm_instance_for_experiment(experiment_run.vm_instance_id)
                log.info(f"Released VM instance {experiment_run.vm_instance_id} for reuse")
            else:
                log.warning("No VM instance ID found in experiment run - cannot release")
        except Exception as e:
            log.error(f"Failed to release VM instance: {e}")


    async def _create_experiment_snapshot(self, context: ExperimentRunCtx, event: threading.Event):
        """Create a snapshot of the final experiment state."""
        if context.vm and context.experiment_run_ulid:
            # Import snapshot manager for creating snapshot
            from adare.backend.vm.snapshot_manager import SnapshotManager

            # Get VM instance from database to create snapshot
            try:
                from adare.database.api.experiment import ExperimentApi
                from adare.database.api.vm import VmApi
                from adare.database.models.project_models import ExperimentRun

                # Get the VM instance ID from the experiment run
                with ExperimentApi(context.config.project_path) as api:
                    experiment_run = api._session.query(ExperimentRun).filter(
                        ExperimentRun.id == context.experiment_run_ulid
                    ).first()

                if not experiment_run or not experiment_run.vm_instance_id:
                    log.warning('No VM instance ID found in experiment run - cannot create experiment snapshot')
                    return

                # Get the VM instance
                with VmApi() as api:
                    vm_instance = api.get_vm_instance_by_id(experiment_run.vm_instance_id)

                if vm_instance and vm_instance.vbox_uuid:
                    snapshot_manager = SnapshotManager()

                    # Create new experiment snapshot with current state
                    with StageCtxManager(VMExperimentSnapshotStage(), context.experiment_run_ulid, event=event):
                        created_snapshot = snapshot_manager.create_experiment_snapshot_for_instance(
                            vm_instance,
                            context.experiment_run_ulid,
                            description=f"Final state snapshot for experiment {context.experiment_run_ulid}",
                            silent=False
                        )

                    if created_snapshot:
                        log.info(f'Created experiment snapshot: {created_snapshot}')
                    else:
                        log.warning('Failed to create experiment snapshot')
                else:
                    log.warning('VM instance not found or missing UUID - cannot create experiment snapshot')

            except Exception as e:
                log.warning(f'Error creating experiment snapshot: {e}')

    async def _cleanup_experiment_snapshot(self, context: ExperimentRunCtx):
        """Clean up experiment-specific snapshots."""
        if context.vm and context.experiment_run_ulid:
            # Import snapshot manager for cleanup
            from adare.backend.vm.snapshot_manager import SnapshotManager

            # Get VM instance from database to delete snapshot
            try:
                from adare.database.api.experiment import ExperimentApi
                from adare.database.api.vm import VmApi
                from adare.database.models.project_models import ExperimentRun

                # Get the VM instance ID from the experiment run
                with ExperimentApi(context.config.project_path) as api:
                    experiment_run = api._session.query(ExperimentRun).filter(
                        ExperimentRun.id == context.experiment_run_ulid
                    ).first()

                if not experiment_run or not experiment_run.vm_instance_id:
                    log.warning('No VM instance ID found in experiment run - cannot cleanup experiment snapshot')
                    return

                # Get the VM instance
                with VmApi() as api:
                    vm_instance = api.get_vm_instance_by_id(experiment_run.vm_instance_id)

                if vm_instance and vm_instance.vbox_uuid:
                    snapshot_manager = SnapshotManager()

                    # Generate the experiment snapshot name (same logic as in create_experiment_snapshot_for_instance)
                    exp_snapshot_name = f"adare_exp_{context.experiment_run_ulid[:8]}"

                    # Delete only the experiment-specific snapshot
                    success = snapshot_manager.delete_instance_snapshot(vm_instance, exp_snapshot_name, silent=True)
                    if success:
                        log.info(f'Successfully cleaned up experiment snapshot: {exp_snapshot_name}')
                    else:
                        log.warning(f'Failed to cleanup experiment snapshot: {exp_snapshot_name} (may not exist)')
                else:
                    log.warning('VM instance not found or missing UUID - cannot cleanup experiment snapshot')

            except Exception as e:
                log.warning(f'Error during snapshot cleanup: {e}')
