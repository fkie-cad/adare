import asyncio
import logging
import shutil
import threading
from datetime import UTC, datetime
from pathlib import Path

import adare.backend.environment.database as environment_database
import adare.backend.experiment.database as experiment_database
from adare.backend.experiment import agent_wheels
from adare.backend.experiment.directory import ExperimentRunDirectory
from adare.backend.experiment.runctx import ExperimentRunCtx
from adare.backend.experiment.stagectxmanager import StageCtxManager
from adare.database.exceptions import DatabaseError
from adare.database.models.global_models import VmInstance
from adare.exceptions import LoggedException
from adare.hypervisor.virtualbox import VirtualBoxVM
from adare.types.stages import (
    VMDestroyStage,
    VMExperimentSnapshotStage,
    VMFileTransferSetupStage,
    VMInstanceVerificationStage,
    VMNetworkingStage,
    VMRuntimePreparationStage,
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
        if context.project_directory is None or context.adarevm is None or context.adarelib is None:
            raise LoggedException(log, "Run context lacks the project or the agent sources (adarevm/adarelib)")
        agent_wheels.ensure_vm_runtime(
            context.project_directory.vm_runtime, {'adarevm': context.adarevm, 'adarelib': context.adarelib}
        )

    async def create_and_prepare_vm(self, context: ExperimentRunCtx):
        """Create and prepare VM for experiment with snapshots and shared folders."""
        # Get VM ID from environment (file operations already done during environment load)
        env_data = environment_database.get_environment_by_ulid(context.environment_ulid, fields=['vm_id'])
        vm_id = env_data['vm_id'] if env_data else None
        if not vm_id:
            raise LoggedException(log, "No VM associated with environment. Did you load the environment properly?")

        from adare.backend.vm.commands import ensure_vm_ready_for_experiment

        if not context.config.dev_mode:  # never from inside a dev session, which may be resuming
            from adare.backend.devmode.expiry import remove_expired_dev_sessions

            await asyncio.to_thread(remove_expired_dev_sessions)  # opt-in: ADARE_DEV_SESSION_MAX_AGE_DAYS

        async def allocate() -> VmInstance | None:
            vm_instance_id = await ensure_vm_ready_for_experiment(
                vm_id=vm_id,
                environment_ulid=context.environment_ulid,
                experiment_run_ulid=context.experiment_run_ulid,
                interrupt_event=context.user_interrupt_event,
                test_mode=context.test_mode,
                machine_key=context.machine_key,
            )
            if vm_instance_id is None:
                log.info("VM instance preparation was interrupted")
                return None
            return self._use_instance(context, vm_instance_id)

        vm_instance = await asyncio.wait_for(allocate(), timeout=300)  # VirtualBox imports can be slow
        if vm_instance is None:
            return

        with StageCtxManager(
            VMRuntimePreparationStage(), context.experiment_run_ulid, event=context.user_interrupt_event
        ):
            await self._ensure_vm_runtime_ready(context)

        await self.strategy.prepare_vm_for_experiment(context)

        # VirtualBox: a pooled instance can have vanished from VirtualBox since it
        # was last used. verify_and_cleanup removes such a row; allocate again,
        # which imports a fresh instance and takes its base snapshot.
        if self.hypervisor_type == 'virtualbox':
            from adare.backend.vm.commands import verify_and_cleanup_vm_instance_for_experiment

            with StageCtxManager(
                VMInstanceVerificationStage(), context.experiment_run_ulid, event=context.user_interrupt_event
            ):
                if not verify_and_cleanup_vm_instance_for_experiment(vm_instance.id, context.experiment_run_ulid):
                    log.info("VM instance was missing from VirtualBox and removed; allocating a new one")
                    vm_instance = await allocate()
                    if vm_instance is None:
                        return
                if not vm_instance.vbox_uuid or not VirtualBoxVM.verify_vm_exists_by_uuid(vm_instance.vbox_uuid):
                    raise LoggedException(
                        log, f"VM instance '{context.vm_name}' was not properly prepared - missing from VirtualBox"
                    )
            log.info(f"Using prepared VM instance '{context.vm_name}' with snapshots (UUID: {vm_instance.vbox_uuid})")

        # Update experiment run with VM-specific data (skip in diff mode where no database persistence)
        if (
            not context.stop_event.is_set()
            and context.experiment_run_directory is not None
            and isinstance(context.experiment_run_directory, ExperimentRunDirectory)
        ):
            context.experiment_run_ulid = experiment_database.update_experiment_run(
                context.experiment_run_ulid, context.experiment_run_directory
            )

        context.timestamp_before_vm_start = datetime.now(UTC)

    @staticmethod
    def _use_instance(context: ExperimentRunCtx, vm_instance_id: str) -> VmInstance:
        """Point this machine's context at the allocated instance and record it on the run."""
        from adare.database.api.vm import VmApi

        with VmApi() as api:
            vm_instance = api.get_vm_instance_by_id(vm_instance_id)
        if vm_instance is None:
            raise LoggedException(log, f"VM instance with ID {vm_instance_id} not found after preparation")
        if vm_instance.websocket_port is None:
            raise LoggedException(log, f"VM instance {vm_instance.instance_name} has no websocket port allocated")

        context.vm_instance_id = vm_instance.id
        context.vm_name = vm_instance.instance_name
        context.config.websocket_port = vm_instance.websocket_port
        # The run records the primary machine's instance; every machine releases
        # its own via context.vm_instance_id.
        if context.machine_key == context.primary_machine:
            experiment_database.update_experiment_run_vm_instance(
                context.config.project_path, context.experiment_run_ulid, vm_instance.id
            )
        log.info(f"Using VM instance: {vm_instance.instance_name} on port {vm_instance.websocket_port}")
        return vm_instance

    async def setup_networking(self, context: ExperimentRunCtx):
        """
        Setup network configuration with proper stage visibility.

        Delegates to hypervisor-specific strategy:
        - VirtualBox: Configure port forwarding via VBoxManage
        - QEMU: Save port forwarding rules to config (applied on VM start)
        """
        with StageCtxManager(VMNetworkingStage(), context.experiment_run_ulid, event=context.user_interrupt_event):
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
            VMFileTransferSetupStage(), context.experiment_run_ulid, event=context.user_interrupt_event
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
        log.debug(
            "mount_shared_directories() called - directories should already be mounted from start_and_initialize_vm()"
        )

    async def stop_vm(self, context: ExperimentRunCtx, post_interrupt: bool = False, force: bool = False):
        """Stop the virtual machine."""
        event = None if post_interrupt else context.user_interrupt_event
        with StageCtxManager(VMStopStage(), context.experiment_run_ulid, event=event):
            log.info('stopping virtual machine')
            if context.vm:
                await context.vm.stop(force=force)

    async def retrieve_artifacts(
        self, context: ExperimentRunCtx, post_interrupt: bool = False, force_stop: bool = False
    ):
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

        with StageCtxManager(VMFileTransferRetrievalStage(), context.experiment_run_ulid, event=event) as stage_ctx:
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
        with StageCtxManager(VMHostDiffStage(), context.experiment_run_ulid, event=event) as stage_ctx:
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
                    base_disk_path=base_disk_path, overlay_disk_path=overlay_disk_path, extract_dir=extract_content_dir
                )

                # Export results to artifacts directory
                if diff_results and diff_dir:
                    # Prepare metadata for JSON export
                    metadata = {
                        'diff_mode': 'host',
                        'tool': 'virt-ls-manual',
                        'base_disk_path': base_disk_path,
                        'overlay_disk_path': overlay_disk_path,
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
                    log.info(
                        f"Filesystem changes - "
                        f"Added: {len(diff_results.get('added', []))}, "
                        f"Removed: {len(diff_results.get('removed', []))}, "
                        f"Modified: {len(diff_results.get('modified', []))}"
                    )

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
            except (OSError, RuntimeError, ValueError, KeyError) as e:
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

    async def perform_disk_export(self, context: ExperimentRunCtx, post_interrupt: bool = False):
        """
        Export the VM's overlay disk as a self-contained raw image for forensic
        ingestion (e.g. Autopsy), independent of the metadata-level filesystem
        diff performed by :meth:`perform_host_diff`.

        Runs AFTER VM shutdown and BEFORE overlay cleanup, same as
        perform_host_diff, since both need the still-live overlay file.
        """
        if self.hypervisor_type != 'qemu':
            log.debug("Disk export skipped - requires QEMU hypervisor")
            return

        if not self._is_disk_export_enabled(context):
            log.debug("Disk export skipped - export_disk_image disabled")
            return

        from adare.types.stages import VMDiskExportStage

        event = None if post_interrupt else context.user_interrupt_event

        with StageCtxManager(VMDiskExportStage(), context.experiment_run_ulid, event=event) as stage_ctx:
            try:
                from adare.hypervisor.exceptions import DiskConversionException
                from adare.hypervisor.qemu.disk_export import export_disk_image
                from adare.hypervisor.qemu.vm import QEMUVM

                if not isinstance(context.vm, QEMUVM):
                    log.warning("VM is not a QEMU instance - cannot export disk image")
                    return

                if not context.experiment_run_directory:
                    log.warning("No experiment run directory - cannot export disk image")
                    return

                overlay_disk_path = Path(context.vm.config.disk_path)
                if not overlay_disk_path.exists():
                    log.error(f"Overlay disk not found: {overlay_disk_path}")
                    return

                fmt = 'raw'
                dest_path = context.experiment_run_directory.path / 'artifacts' / 'disk' / f'{context.vm_name}.{fmt}'

                log.info(f"Exporting disk image ({fmt}) to {dest_path}")
                export_disk_image(
                    overlay_disk_path,
                    dest_path,
                    fmt=fmt,
                    qemu_img_exe=context.vm.executables.qemu_img,
                )

                from sqlalchemy.exc import SQLAlchemyError

                from adare.database.api.experiment import ExperimentApi
                from adare.database.exceptions import DatabaseError

                with ExperimentApi(context.config.project_path) as api:
                    api.add_run_artifact(
                        run_ulid=context.experiment_run_ulid,
                        kind='disk_image',
                        path=str(dest_path),
                        format=fmt,
                    )

                stage_ctx.stage.sub_msg = f"Exported to {dest_path.name}"
                log.info(f"Disk image exported to {dest_path}")

            except DiskConversionException as e:
                log.warning(f"Disk export failed (continuing cleanup): {e}")
            except (OSError, RuntimeError, ValueError, KeyError) as e:
                log.warning(f"Disk export failed (continuing cleanup): {e}", exc_info=True)
            except (DatabaseError, SQLAlchemyError) as e:
                # DatabaseError from ExperimentApi(...) construction (wrapped),
                # SQLAlchemyError from add_run_artifact's raw session.commit() --
                # a failed artifact-row write must not block VM cleanup below.
                log.warning(f"Disk export artifact recording failed (continuing cleanup): {e}", exc_info=True)

    def _is_disk_export_enabled(self, context: ExperimentRunCtx) -> bool:
        """Check if raw/vmdk disk image export is enabled (CLI override, then playbook settings)."""
        if hasattr(context.config, 'export_disk_image') and context.config.export_disk_image is not None:
            return context.config.export_disk_image

        if context.playbook and hasattr(context.playbook, 'settings') and context.playbook.settings:
            return bool(getattr(context.playbook.settings, 'export_disk_image', False))
        return False

    async def perform_memory_dump(self, context: ExperimentRunCtx, post_interrupt: bool = False):
        """
        Dump the VM's live guest RAM via QMP ``dump-guest-memory`` for memory-forensics
        ingestion (e.g. Volatility3).

        Unlike perform_host_diff/perform_disk_export (which run AFTER shutdown, needing
        the still-live overlay), this must run BEFORE retrieve_artifacts/stop_vm --
        memory only exists while QEMU is running, and dump-guest-memory is designed to
        run live (no pause/quiesce first, which would itself be a forensically-visible
        side effect).
        """
        if self.hypervisor_type != 'qemu':
            log.debug("Memory dump skipped - requires QEMU hypervisor")
            return

        if not self._is_memory_dump_enabled(context):
            log.debug("Memory dump skipped - export_memory_dump disabled")
            return

        from adare.types.stages import VMMemoryDumpStage

        event = None if post_interrupt else context.user_interrupt_event

        with StageCtxManager(VMMemoryDumpStage(), context.experiment_run_ulid, event=event) as stage_ctx:
            try:
                from adare.hypervisor.exceptions import MemoryDumpException
                from adare.hypervisor.qemu.memory_dump import dump_guest_memory
                from adare.hypervisor.qemu.vm import QEMUVM

                if not isinstance(context.vm, QEMUVM):
                    log.warning("VM is not a QEMU instance - cannot dump guest memory")
                    return

                if not context.experiment_run_directory:
                    log.warning("No experiment run directory - cannot dump guest memory")
                    return

                fmt = 'elf'
                dest_path = context.experiment_run_directory.path / 'artifacts' / 'memory' / f'{context.vm_name}.{fmt}'
                dest_path.parent.mkdir(parents=True, exist_ok=True)

                configured_memory_mb = context.config.vm_memory
                if configured_memory_mb:
                    free_bytes = shutil.disk_usage(dest_path.parent).free
                    if free_bytes < configured_memory_mb * 1024 * 1024 * 1.5:
                        log.warning(
                            f"Free disk space ({free_bytes / (1024**3):.1f}GiB) is less than 1.5x "
                            f"configured VM RAM ({configured_memory_mb}MB) - memory dump may fail to complete"
                        )

                log.info(f"Dumping guest memory ({fmt}) to {dest_path}")
                await dump_guest_memory(context.vm, dest_path, fmt=fmt)

                from sqlalchemy.exc import SQLAlchemyError

                from adare.database.api.experiment import ExperimentApi
                from adare.database.exceptions import DatabaseError

                with ExperimentApi(context.config.project_path) as api:
                    api.add_run_artifact(
                        run_ulid=context.experiment_run_ulid,
                        kind='memory_dump',
                        path=str(dest_path),
                        format=fmt,
                    )

                stage_ctx.stage.sub_msg = f"Dumped to {dest_path.name}"
                log.info(f"Guest memory dumped to {dest_path}")

            except MemoryDumpException as e:
                log.warning(f"Memory dump failed (continuing cleanup): {e}")
            except (OSError, RuntimeError, ValueError, KeyError) as e:
                log.warning(f"Memory dump failed (continuing cleanup): {e}", exc_info=True)
            except (DatabaseError, SQLAlchemyError) as e:
                # DatabaseError from ExperimentApi(...) construction (wrapped),
                # SQLAlchemyError from add_run_artifact's raw session.commit() --
                # a failed artifact-row write must not block VM cleanup below.
                log.warning(f"Memory dump artifact recording failed (continuing cleanup): {e}", exc_info=True)

    def _is_memory_dump_enabled(self, context: ExperimentRunCtx) -> bool:
        """Check if RAM dump export is enabled (CLI override, then playbook settings)."""
        if hasattr(context.config, 'export_memory_dump') and context.config.export_memory_dump is not None:
            return context.config.export_memory_dump

        if context.playbook and hasattr(context.playbook, 'settings') and context.playbook.settings:
            return bool(getattr(context.playbook.settings, 'export_memory_dump', False))
        return False

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

            if self.hypervisor_type == 'qemu':
                # The run's domain, overlay, UEFI vars, vTPM copy, config and
                # instance row all go; the environment disk is never touched.
                await self._remove_qemu_run(context)
            else:
                log.info('Releasing VM instance for reuse by future experiments')
                await self._release_vm_instance(context)

    async def _remove_qemu_run(self, context: ExperimentRunCtx) -> None:
        from adare.backend.vm.run_instances import remove_qemu_run_instance

        if context.vm is not None:
            context.vm._libvirt_domain = None  # stale after the domain is undefined below
        instance_name = context.vm_name
        if not instance_name:
            log.warning('No run instance recorded - nothing to remove')
            return
        try:
            remove_qemu_run_instance(instance_name)
        except (OSError, DatabaseError) as e:
            # reconcile_instances() reaps whatever is left once this process is gone.
            log.error(f"Failed to remove run instance {instance_name}: {e}")

    async def _release_vm_instance(self, context: ExperimentRunCtx):
        """Return this machine's pooled (VirtualBox) instance to the pool."""
        from adare.backend.vm.commands import release_vm_instance_for_experiment

        instance_id = context.vm_instance_id
        if not instance_id:
            log.warning("No VM instance recorded for this machine - cannot release")
            return
        try:
            await release_vm_instance_for_experiment(instance_id)
            log.info(f"Released VM instance {instance_id} for reuse")
        except (OSError, ValueError, RuntimeError, DatabaseError) as e:
            log.error(f"Failed to release VM instance: {e}")

    async def _create_experiment_snapshot(self, context: ExperimentRunCtx, event: threading.Event):
        """Snapshot the final state of this machine's (VirtualBox) instance."""
        if self.hypervisor_type == 'qemu':
            log.warning(
                '--preserve-snapshot is VirtualBox-only: a QEMU run\'s overlay is discarded with the run. '
                'Use --export-disk-image to keep the final disk in the run directory.'
            )
            return
        if not context.vm or not context.experiment_run_ulid or not context.vm_instance_id:
            log.warning('No VM instance recorded for this machine - cannot create experiment snapshot')
            return
        from adare.backend.vm.snapshot_manager import SnapshotManager
        from adare.database.api.vm import VmApi

        try:
            with VmApi() as api:
                vm_instance = api.get_vm_instance_by_id(context.vm_instance_id)
            if not vm_instance or not vm_instance.vbox_uuid:
                log.warning('VM instance not found or missing UUID - cannot create experiment snapshot')
                return
            with StageCtxManager(VMExperimentSnapshotStage(), context.experiment_run_ulid, event=event):
                created_snapshot = SnapshotManager().create_experiment_snapshot_for_instance(
                    vm_instance,
                    context.experiment_run_ulid,
                    description=f"Final state snapshot for experiment {context.experiment_run_ulid}",
                    silent=False,
                )
            if created_snapshot:
                log.info(f'Created experiment snapshot: {created_snapshot}')
            else:
                log.warning('Failed to create experiment snapshot')
        except (OSError, ValueError, RuntimeError, DatabaseError) as e:
            log.warning(f'Error creating experiment snapshot: {e}')
