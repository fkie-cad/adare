"""
QEMU-specific VM lifecycle strategy.

This module implements the QEMU lifecycle strategy. File transfer between
host and guest is delegated to a FileTransferStrategy (Strategy pattern)
selected at init time by the factory in adare.hypervisor.qemu.file_transfer.

Supported transfer modes (chosen automatically):
- VirtioFS: shared directories (default, fastest)
- Libguestfs: offline guestfish disk access (fallback on Linux)
- QGA: QEMU Guest Agent file operations (macOS fallback)
"""
from pathlib import Path
import logging
import platform
import shutil
import subprocess
import time

from typing import List, Dict, Optional

from adare.hypervisor.base.lifecycle import AbstractVMLifecycleStrategy
from adare.hypervisor.qemu.manager import QEMUManager
from adare.hypervisor.qemu.libvirt_stderr_redirect import get_experiment_log_file
from adare.hypervisor.qemu.guestfish_client import GuestfishClient
from adare.hypervisor.qemu.disk_diff import DiskDiffComparator
from adare.hypervisor.qemu.file_transfer import get_file_transfer_strategy
from adare.hypervisor.exceptions import HypervisorException
from adare.exceptions import LoggedException
from adare.config import get_vm_credentials

log = logging.getLogger(__name__)


class QEMULifecycleStrategy(AbstractVMLifecycleStrategy):
    """
    QEMU-specific lifecycle strategy with virtio-fs and libguestfs support.

    Default mode (virtio-fs):
    1. Create shared directory on host with all required files
    2. VM boots with virtio-fs filesystem device
    3. Guest mounts the shared directory
    4. Artifacts written directly to shared directory

    Fallback mode (libguestfs, when QEMU_LIBGUESTFS=true):
    1. VM must be stopped to mount disk with guestfish
    2. Files are copied to disk before boot
    3. Artifacts are retrieved after shutdown
    """

    def __init__(self):
        self.qemu_manager = QEMUManager()
        self.guestfish = GuestfishClient()
        self.disk_diff = DiskDiffComparator(self.guestfish)
        self.file_transfer = get_file_transfer_strategy(self.guestfish)

    def _validate_external_disk_writable(self, disk_path: Path) -> None:
        """
        Validate that external disk path is writable (required for snapshots).

        Args:
            disk_path: Path to external disk image

        Raises:
            HypervisorException: If disk is not writable
        """
        import os

        # Check if file exists (for existing qcow2)
        if disk_path.exists():
            # Test write permission
            if not os.access(disk_path, os.W_OK):
                raise HypervisorException(
                    f"External disk is not writable: {disk_path}\n"
                    f"QEMU requires write access to disk for snapshot operations.\n"
                    f"Please ensure the file has write permissions."
                )
            log.debug(f"Validated write access to external disk: {disk_path}")
        else:
            # File doesn't exist yet (will be created by conversion)
            # Check parent directory is writable
            parent_dir = disk_path.parent
            if not parent_dir.exists():
                raise HypervisorException(
                    f"Parent directory does not exist: {parent_dir}\n"
                    f"Cannot create converted qcow2 file."
                )
            if not os.access(parent_dir, os.W_OK):
                raise HypervisorException(
                    f"Parent directory is not writable: {parent_dir}\n"
                    f"Cannot create converted qcow2 file for external VM.\n"
                    f"Please ensure directory has write permissions."
                )
            log.debug(f"Validated write access to parent directory: {parent_dir}")

    async def prepare_vm_for_experiment(self, context):
        """
        Create QEMU VM instance and allocate resources.

        Supports both managed and external (--no-copy) disk images.
        For external disks: detects format and uses in-place if qcow2, or determines conversion path.

        Args:
            context: ExperimentRunCtx with vm_name and guest_platform already set
        """
        from adare.database.api.vm import VmApi
        from adare.backend.environment import database as environment_database
        from adare.backend.vm.commands import _is_vm_managed
        from adare.hypervisor.qemu.vm import QEMUVM

        # Query database for source VM to get disk path and architecture
        env_data = environment_database.get_environment_by_ulid(
            context.environment_ulid,
            fields=['vm_id', 'vm_architecture']
        )

        if not env_data or not env_data.get('vm_id'):
            raise HypervisorException(
                "No VM associated with environment. Run 'adare environment load' first."
            )

        # Get source VM file path from database
        with VmApi() as api:
            source_vm = api.get_vm_by_id(env_data['vm_id'])

        if not source_vm:
            raise HypervisorException(f"Source VM not found in database")

        source_vm_path = Path(source_vm.file)

        # Determine if this is an external VM (--no-copy mode)
        is_external = not _is_vm_managed(source_vm_path)

        # Determine disk path for QEMU VM
        disk_path = None  # None = use managed storage (default behavior)

        if is_external:
            log.debug(f"External VM detected (--no-copy mode): {source_vm_path}")

            # Detect file format
            try:
                detected_format = QEMUVM._detect_disk_format_static(
                    source_vm_path,
                    self.qemu_manager.executables.qemu_img
                )
                log.debug(f"Detected format: {detected_format}")
            except HypervisorException as e:
                log.warning(f"Could not detect format: {e}")
                detected_format = 'unknown'

            if detected_format == 'qcow2':
                # Already qcow2 - use directly
                log.debug("Source is qcow2 format, will use directly without conversion")
                disk_path = str(source_vm_path.resolve())
            elif detected_format in ['ova', 'vmdk', 'vdi', 'raw', 'unknown']:
                # Non-qcow2 format - need to convert in-place
                log.debug(f"Source is {detected_format} format, will convert to qcow2 in-place")
                converted_path = source_vm_path.parent / f"{source_vm_path.stem}_adare_converted.qcow2"
                disk_path = str(converted_path.resolve())
            else:
                log.warning(f"Unknown format {detected_format}, treating as non-qcow2")
                converted_path = source_vm_path.parent / f"{source_vm_path.stem}_adare_converted.qcow2"
                disk_path = str(converted_path.resolve())

            # Validate write permissions for external disk path
            self._validate_external_disk_writable(Path(disk_path))
        else:
            log.debug(f"Managed VM detected, using managed storage")

        # Determine guest architecture
        vm_architecture = (env_data.get('vm_architecture') if env_data else None) or \
                          getattr(context, 'guest_architecture', None)
        if not vm_architecture:
            vm_architecture = 'x86_64'
            log.warning("Guest architecture not set in environment — defaulting to x86_64")

        # Block x86_64 guests on Apple Silicon (no hardware acceleration)
        if platform.system() == 'Darwin' and platform.machine() == 'arm64' and vm_architecture != 'aarch64':
            raise HypervisorException(
                f"QEMU cannot hardware-accelerate {vm_architecture} guests on Apple Silicon (ARM). "
                "Only aarch64 guests are supported on Apple Silicon with HVF. "
                "Use VirtualBox instead (supports x86 via Rosetta)."
            )

        # Compute architecture-appropriate machine type and accelerator
        if vm_architecture == 'aarch64':
            vm_machine = 'virt'
            vm_accel = 'hvf' if platform.system() == 'Darwin' else 'kvm'
        else:
            vm_machine = 'pc'
            vm_accel = 'hvf' if platform.system() == 'Darwin' else 'kvm'

        # Create QEMU VM instance with optional external disk path
        username, password = get_vm_credentials(context.guest_platform)
        context.vm = QEMUVM(
            vm_name=context.vm_name,
            guest_os=context.guest_platform,
            manager=self.qemu_manager,
            username=username,
            password=password,
            executables=self.qemu_manager.executables,
            cpus=context.config.vm_cpus,
            ram=context.config.vm_memory,
            machine=vm_machine,
            accel=vm_accel,
            disk_path=disk_path,
            architecture=vm_architecture
        )
        log.debug(f"Created QEMU VM instance: {context.vm_name}")

        # Configure VM logging paths for experiment run
        log_file = get_experiment_log_file()
        if log_file:
            run_dir = Path(log_file).parent
            context.vm.config.serial_console_log_path = str(run_dir / "serial_console.log")
            context.vm.config.qemu_debug_log_path = str(run_dir / "qemu_debug.log")
            context.vm._save_vm_config()  # Persist for domain XML generation
            log.debug(f"Configured VM logging to {run_dir}")

        # Create experiment overlay backed by immutable base disk
        # This ensures libguestfs operations don't modify the base disk,
        # preserving hash integrity for forensic validation
        from adare.types.stages import (
            VMDiskPreparationStage,
            VMDiskFormatDetectionStage,
            VMDiskConversionStage,
            VMDiskOverlayCreationStage
        )
        from adare.backend.experiment.stagectxmanager import StageCtxManager

        experiment_id = context.experiment_run_ulid or 'default'

        # Wrap entire disk preparation with parent stage
        with StageCtxManager(
            VMDiskPreparationStage(),
            context.experiment_run_ulid,
            context.user_interrupt_event
        ):

            # Step 1: Format detection (for external VMs only)
            if is_external:
                with StageCtxManager(
                    VMDiskFormatDetectionStage(),
                    context.experiment_run_ulid,
                    context.user_interrupt_event
                ) as detect_stage:
                    # Detection already happened at lines 518-526, just update stage message
                    detect_stage.stage.sub_msg = f"Detected: {detected_format}"
                    detect_stage.set_status(detect_stage.stage.status)
                    log.debug(f"Format detection stage: {detected_format}")

            # Step 2: Conversion (only if needed)
            if is_external and detected_format == 'qcow2':
                # External qcow2 - use directly without conversion
                log.debug(f"Skipping conversion - external qcow2 will be used as base")
                if not source_vm_path.exists():
                    raise HypervisorException(f"External qcow2 file not found: {source_vm_path}")
                # _get_true_base_disk() will return external path directly
            elif is_external and detected_format != 'qcow2':
                # External non-qcow2 - convert to qcow2
                base_disk_path = context.vm.get_base_disk_path()
                if not Path(base_disk_path).exists():
                    with StageCtxManager(
                        VMDiskConversionStage(),
                        context.experiment_run_ulid,
                        context.user_interrupt_event
                    ) as conv_stage:
                        conv_stage.stage.sub_msg = f"Converting {detected_format} → qcow2"
                        conv_stage.set_status(conv_stage.stage.status)

                        log.debug(f"Converting {detected_format} to qcow2 base disk...")
                        return_code, message = await context.vm.create_from_ovf_or_ova(
                            source_vm_path,
                            silent=False,
                            try_extract=True
                        )

                        if return_code != 0:
                            raise HypervisorException(f"Failed to convert VM disk: {message}")

                        log.debug(f"Conversion to base disk completed successfully")

            # Step 3: Create overlay disk (always happens)
            with StageCtxManager(
                VMDiskOverlayCreationStage(),
                context.experiment_run_ulid,
                context.user_interrupt_event
            ):
                try:
                    overlay_path = await context.vm.create_overlay_disk(experiment_id)

                    # Update VM config to use overlay (not base)
                    # This ensures all disk operations (especially libguestfs) write to overlay
                    context.vm.config.disk_path = overlay_path
                    log.debug(f"Using overlay disk for experiment: {overlay_path}")

                    # Validate overlay was created successfully
                    if not Path(overlay_path).exists():
                        raise HypervisorException(
                            f"Overlay disk creation reported success but file not found: {overlay_path}\n"
                            f"This indicates a race condition or filesystem issue."
                        )
                    log.debug(f"Verified overlay exists: {overlay_path}")

                    # Log base disk location for reference
                    if Path(context.vm.config.disk_path).exists():
                        base_info = "external qcow2"
                    else:
                        base_info = context.vm.get_base_disk_path()
                    log.debug(f"Base disk preserved for integrity checks: {base_info}")

                    # Cleanup orphaned overlays from old naming scheme
                    # Old overlays have chained names like: VM-name-overlay-{ULID1}-overlay-{ULID2}.qcow2
                    try:
                        disk_dir = Path(overlay_path).parent
                        base_disk_path = Path(context.vm.get_base_disk_path())

                        for orphan in disk_dir.glob('*-overlay-*-overlay-*.qcow2'):
                            # Only delete if it's not the current overlay or base disk
                            if orphan != Path(overlay_path) and orphan != base_disk_path:
                                log.debug(f"Cleaning up orphaned overlay: {orphan.name}")
                                orphan.unlink()
                    except OSError as e:
                        log.warning(f"Failed to cleanup orphaned overlays: {e}")

                except (subprocess.CalledProcessError, OSError, HypervisorException) as e:
                    raise HypervisorException(
                        f"Failed to create overlay disk: {e}\n"
                        f"Overlay creation failed. Ensure base disk exists and is accessible.\n"
                        f"VM: {context.vm_name}, External: {is_external}"
                    )


    async def setup_file_transfer(self, context):
        """
        Setup file transfer mechanism for the experiment.

        Delegates to the FileTransferStrategy selected at init time.

        Args:
            context: ExperimentRunCtx containing directories and VM
        """
        strategy_name = type(self.file_transfer).__name__
        log.info(f"Setting up file transfer via {strategy_name}")
        await self.file_transfer.setup(context)
        log.info(f"File transfer setup via {strategy_name} completed")

    async def setup_networking(self, context):
        """
        Setup port forwarding for WebSocket communication via QEMU config.

        Port forwarding rules are saved to VM config and applied when VM starts.
        The guest always uses port 18765, while the host uses a dynamically allocated port.

        Args:
            context: ExperimentRunCtx containing configuration
        """
        log.info("Setting up port forwarding for WebSocket communication")

        # Clean up any existing 'adarevm' port forwarding rule first
        await context.vm.remove_port_forwarding(
            name='adarevm',
            stop_event=context.user_interrupt_event,
            silent=True
        )

        # Add port forwarding: host uses allocated unique port, guest always uses 18765
        if context.config.websocket_port is None:
            raise LoggedException(log, "Cannot set up port forwarding: no websocket port allocated")

        await context.vm.add_port_forwarding(
            name='adarevm',
            protocol='tcp',
            host_port=context.config.websocket_port,
            guest_port=18765,
            stop_event=context.user_interrupt_event,
            silent=False
        )
        log.info(f'Added port forwarding for websocket server: host:{context.config.websocket_port} -> guest:18765')


    async def start_and_initialize_vm(self, context):
        """
        Start QEMU VM via libvirt and perform post-boot file transfer.

        After VM boot and guest agent readiness, delegates to the
        FileTransferStrategy for any post-boot actions (mounting
        virtiofs shares, uploading files via QGA, etc.).

        Args:
            context: ExperimentRunCtx containing VM
        """
        from adare.types.stages import VMStartStage, VMGuestAgentWaitStage
        from adare.backend.experiment.stagectxmanager import StageCtxManager

        # Stage 1: Start VM
        with StageCtxManager(
            VMStartStage(),
            context.experiment_run_ulid,
            context.user_interrupt_event
        ) as start_stage:
            log.info(f"Starting VM '{context.vm.vm_name}' via libvirt")
            await context.vm.start(stop_event=context.user_interrupt_event, stage_ctx=start_stage)
            log.debug(f"VM visible in virt-manager (use 'Open' button to access display)")

        # Stage 2: Wait for guest agent
        with StageCtxManager(
            VMGuestAgentWaitStage(),
            context.experiment_run_ulid,
            context.user_interrupt_event
        ):
            from adare.backend.experiment.execution.gui_executor_factory import resolve_gui_execution_mode
            from adare.backend.experiment.execution.base import GUIExecutionMode
            playbook_settings = context.playbook.settings if context.playbook and hasattr(context.playbook, 'settings') else None
            gui_mode = resolve_gui_execution_mode(context.vm, playbook_settings)
            skip_x11 = (gui_mode == GUIExecutionMode.HOST)

            log.info('Waiting until VM is ready (QEMU Guest Agent)')
            start_wait = time.time()
            if not await context.vm.wait_until_fully_booted(timeout=360, stop_event=context.user_interrupt_event, skip_x11_discovery=skip_x11):
                raise LoggedException(log, 'VM did not become ready in time')
            elapsed = time.time() - start_wait
            log.info(f'VM is ready (waited {elapsed:.1f}s)')

        # Stage 3: Post-boot file transfer (only if strategy needs it)
        if self.file_transfer.has_post_boot_transfer:
            from adare.types.stages import VMPostBootTransferStage

            stage = VMPostBootTransferStage()
            with StageCtxManager(stage, context.experiment_run_ulid, context.user_interrupt_event):
                stage.sub_msg = self.file_transfer.post_boot_description
                await self.file_transfer.post_boot_transfer(context)

    async def retrieve_artifacts(self, context, post_interrupt: bool = False, force_stop: bool = False):
        """
        Retrieve artifacts and logs from the VM.

        Delegates to the FileTransferStrategy. The strategy determines
        whether the VM must be stopped before retrieval (libguestfs)
        or can retrieve while running (virtiofs, QGA).

        Args:
            context: ExperimentRunCtx
            post_interrupt: If True, we're in post-interrupt cleanup
            force_stop: If True, force-stop the VM (e.g. Windows to prevent updates)
        """
        if not context.vm or not hasattr(context.vm, 'config'):
            log.info(
                "VM not initialized - skipping artifact retrieval. "
                "This is normal if experiment failed before VM was created."
            )
            return

        if self.file_transfer.requires_vm_stop_for_retrieval():
            # libguestfs mode: stop VM first
            log.info("Stopping VM to retrieve artifacts and logs via libguestfs")
            await context.vm.stop(force=force_stop)
            await self.file_transfer.retrieve_artifacts(context)
        else:
            # virtiofs / QGA: retrieve while running, then stop
            await self.file_transfer.retrieve_artifacts(context)
            log.info("Stopping VM after artifact retrieval")
            await context.vm.stop(force=force_stop)

        # Collect host-side QEMU logs (common to all strategies)
        self._collect_host_qemu_logs(context)

    def _collect_host_qemu_logs(self, context):
        """Copy QEMU host-side logs from /tmp to experiment run log directory."""
        if not context.vm or not context.experiment_run_directory:
            return

        vm_name = context.vm.vm_name
        log_dir = context.experiment_run_directory.log_directory

        log_pairs = [
            (f"/tmp/adare_serial_{vm_name}.log", log_dir / "serial_console.log"),
            (f"/tmp/adare_qemu_debug_{vm_name}.log", log_dir / "qemu_debug.log"),
        ]

        for src, dst in log_pairs:
            src_path = Path(src)
            if src_path.exists():
                try:
                    shutil.copy2(src_path, dst)
                    src_path.unlink()
                    log.debug(f"Collected QEMU log: {src} -> {dst}")
                except OSError as e:
                    log.warning(f"Failed to collect QEMU log {src}: {e}")

    async def cleanup_vm(self, context, post_interrupt: bool = False):
        """
        Cleanup QEMU VM resources.

        Args:
            context: ExperimentRunCtx
            post_interrupt: True if cleaning up after interrupt
        """
        # Clean up port forwarding before releasing VM instance
        if context.vm:
            event = None if post_interrupt else context.user_interrupt_event
            log.info('Cleaning up port forwarding rules before VM instance release')
            await context.vm.remove_port_forwarding(
                name='adarevm',
                stop_event=event,
                silent=True
            )

        # Cleanup file transfer resources (e.g. SMB temp directory)
        if hasattr(self.file_transfer, 'cleanup'):
            self.file_transfer.cleanup()

        log.debug("QEMU VM cleanup completed")

    def compare_disk_images_with_virt_diff(
        self,
        base_disk_path: str,
        overlay_disk_path: str,
        all: bool = False,
        extract_dir: Optional[Path] = None
    ) -> Optional[Dict[str, List[Dict]]]:
        """Compare base and overlay disks using manual virt-ls diff.

        Delegates to DiskDiffComparator for the actual comparison.

        Args:
            base_disk_path: Path to immutable base disk (pristine state)
            overlay_disk_path: Path to overlay disk (modified state)
            all: Unused (kept for compatibility)
            extract_dir: Optional path to directory where changed files
                content should be extracted

        Returns:
            Diff dict: {added: [...], removed: [...], modified: [...]}
            None on failure
        """
        return self.disk_diff.compare(
            base_disk_path, overlay_disk_path, extract_dir
        )
