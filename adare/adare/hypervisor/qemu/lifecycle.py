"""
QEMU-specific VM lifecycle strategy.

This module implements the QEMU lifecycle strategy using guestfish CLI for file
transfer. Files must be copied to the disk image before boot and retrieved
after shutdown, as QEMU doesn't support live shared folders like VirtualBox.
"""
from pathlib import Path
import logging
import asyncio
import subprocess
import shutil
from typing import List, Dict

from adare.hypervisor.base.lifecycle import AbstractVMLifecycleStrategy
from adare.hypervisor.qemu.manager import QEMUManager
from adare.hypervisor.exceptions import HypervisorException
from adare.exceptions import LoggedException
from adare.config import get_vm_credentials

log = logging.getLogger(__name__)


class QEMULifecycleStrategy(AbstractVMLifecycleStrategy):
    """
    QEMU-specific lifecycle strategy using guestfish CLI.

    QEMU uses guestfish to transfer files to/from the VM. This requires:
    1. VM must be stopped to mount disk with guestfish
    2. Files are copied to disk before boot
    3. Artifacts are retrieved after shutdown
    """

    def __init__(self):
        self.qemu_manager = QEMUManager()

    def _run_guestfish_command(
        self,
        disk_path: str,
        commands: List[str],
        readonly: bool = False
    ) -> tuple[int, str, str]:
        """
        Execute guestfish commands on a disk image.

        Args:
            disk_path: Path to disk image
            commands: List of guestfish command parts (will be joined with ':')
            readonly: If True, mount disk read-only

        Returns:
            Tuple of (returncode, stdout, stderr)
        """
        mode_flag = '--ro' if readonly else '--rw'
        cmd = ['guestfish', mode_flag, '-a', disk_path, '-i'] + commands

        log.debug(f"Running guestfish: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False
        )

        if result.returncode != 0:
            log.debug(f"Guestfish stderr: {result.stderr}")

        return result.returncode, result.stdout, result.stderr

    def _copy_files_to_disk_via_libguestfs(
        self,
        disk_path: str,
        files_to_copy: List[Dict[str, str]],
        target_base_dir: str = "/adare"
    ) -> None:
        """
        Copy files to guest disk using guestfish CLI.

        Args:
            disk_path: Absolute path to VM disk image (qcow2)
            files_to_copy: List of dicts with 'source' (host path) and 'dest' (guest relative path)
            target_base_dir: Base directory in guest where files will be placed

        Raises:
            HypervisorException: If any operation fails
        """
        # Validate disk exists
        if not Path(disk_path).exists():
            raise HypervisorException(
                f"VM disk not found at {disk_path}. "
                f"Ensure the VM has been created before transferring files."
            )

        # Validate all source files exist
        for file_spec in files_to_copy:
            source_path = Path(file_spec['source'])
            if not source_path.exists():
                raise HypervisorException(
                    f"Source file/directory not found: {source_path}"
                )

        log.info(f"Mounting guest disk {disk_path} via guestfish for file transfer")

        # Build command list
        commands = []

        # Create base directory
        commands.extend(['mkdir-p', target_base_dir, ':'])

        # Collect and create all parent directories
        parent_dirs = set()
        for file_spec in files_to_copy:
            dest_full = f"{target_base_dir}/{file_spec['dest']}"
            parent = str(Path(dest_full).parent)
            parent_dirs.add(parent)

        # Sort by depth to create parents before children
        for parent_dir in sorted(parent_dirs, key=lambda p: len(p.split('/'))):
            if parent_dir != target_base_dir:
                commands.extend(['mkdir-p', parent_dir, ':'])

        # Copy each file/directory
        for file_spec in files_to_copy:
            source_path = file_spec['source']
            dest_relative = file_spec['dest']
            dest_full = f"{target_base_dir}/{dest_relative}"
            dest_parent = str(Path(dest_full).parent)

            log.info(f"Copying {source_path} -> {dest_full}")
            commands.extend(['copy-in', source_path, dest_parent, ':'])

        # Remove trailing ':'
        if commands and commands[-1] == ':':
            commands = commands[:-1]

        # Execute all commands in single guestfish invocation
        returncode, stdout, stderr = self._run_guestfish_command(
            disk_path, commands, readonly=False
        )

        if returncode != 0:
            raise HypervisorException(
                f"Failed to copy files to guest disk.\n"
                f"Guestfish error: {stderr}\n"
                f"Disk: {disk_path}"
            )

        log.info(f"Successfully copied {len(files_to_copy)} items to guest disk")

    def _copy_artifacts_from_disk_via_libguestfs(
        self,
        disk_path: str,
        source_path: str,
        destination_path: Path
    ) -> None:
        """
        Copy artifacts from guest disk using guestfish CLI.

        Args:
            disk_path: Absolute path to VM disk image (qcow2)
            source_path: Path in guest filesystem (e.g., "/adare/run/artifacts")
            destination_path: Path on host where artifacts should be copied

        Raises:
            HypervisorException: If critical operations fail
        """
        # Validate disk exists
        if not Path(disk_path).exists():
            raise HypervisorException(
                f"VM disk not found at {disk_path}"
            )

        log.info(f"Mounting guest disk {disk_path} via guestfish to retrieve artifacts")

        # Create destination directory on host
        try:
            destination_path.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise HypervisorException(
                f"Failed to create destination directory {destination_path}: {e}"
            )

        # Check if source path exists in guest
        returncode, stdout, stderr = self._run_guestfish_command(
            disk_path, ['exists', source_path], readonly=True
        )

        if returncode != 0 or 'false' in stdout.lower():
            log.warning(
                f"Artifact path {source_path} does not exist in guest. "
                f"This may be normal if the experiment did not produce artifacts."
            )
            return

        # Check if directory or file
        returncode, stdout, stderr = self._run_guestfish_command(
            disk_path, ['is-dir', source_path], readonly=True
        )

        is_directory = returncode == 0 and 'true' in stdout.lower()

        if is_directory:
            log.info(f"Copying artifact directory {source_path} -> {destination_path}")

            # copy-out copies directory to parent with its original name
            temp_parent = destination_path.parent

            returncode, stdout, stderr = self._run_guestfish_command(
                disk_path, ['copy-out', source_path, str(temp_parent)], readonly=True
            )

            if returncode != 0:
                raise HypervisorException(
                    f"Failed to copy artifacts from {source_path}: {stderr}"
                )

            # Handle path adjustment if needed
            source_name = Path(source_path).name
            copied_dir = temp_parent / source_name
            if copied_dir != destination_path:
                if destination_path.exists():
                    shutil.rmtree(destination_path)
                shutil.move(str(copied_dir), str(destination_path))
        else:
            log.info(f"Copying artifact file {source_path} -> {destination_path}")

            returncode, stdout, stderr = self._run_guestfish_command(
                disk_path, ['download', source_path, str(destination_path)], readonly=True
            )

            if returncode != 0:
                raise HypervisorException(
                    f"Failed to download artifact file {source_path}: {stderr}"
                )

        log.info(f"Successfully retrieved artifacts from {source_path}")

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
            log.debug(f"CLAUDE: Validated write access to external disk: {disk_path}")
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
            log.debug(f"CLAUDE: Validated write access to parent directory: {parent_dir}")

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

        # Query database for source VM to get disk path
        env_data = environment_database.get_environment_by_ulid(
            context.environment_ulid,
            fields=['vm_id']
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
            log.info(f"CLAUDE: External VM detected (--no-copy mode): {source_vm_path}")

            # Detect file format
            try:
                detected_format = QEMUVM._detect_disk_format_static(
                    source_vm_path,
                    self.qemu_manager.executables.qemu_img
                )
                log.debug(f"CLAUDE: Detected format: {detected_format}")
            except HypervisorException as e:
                log.warning(f"CLAUDE: Could not detect format: {e}")
                detected_format = 'unknown'

            if detected_format == 'qcow2':
                # Already qcow2 - use directly
                log.info("CLAUDE: Source is qcow2 format, will use directly without conversion")
                disk_path = str(source_vm_path.resolve())
            elif detected_format in ['ova', 'vmdk', 'vdi', 'raw', 'unknown']:
                # Non-qcow2 format - need to convert in-place
                log.info(f"CLAUDE: Source is {detected_format} format, will convert to qcow2 in-place")
                converted_path = source_vm_path.parent / f"{source_vm_path.stem}_adare_converted.qcow2"
                disk_path = str(converted_path.resolve())
            else:
                log.warning(f"CLAUDE: Unknown format {detected_format}, treating as non-qcow2")
                converted_path = source_vm_path.parent / f"{source_vm_path.stem}_adare_converted.qcow2"
                disk_path = str(converted_path.resolve())

            # Validate write permissions for external disk path
            self._validate_external_disk_writable(Path(disk_path))
        else:
            log.debug(f"CLAUDE: Managed VM detected, using managed storage")

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
            disk_path=disk_path  # NEW: Pass external disk path for --no-copy mode
        )
        log.info(f"CLAUDE: Created QEMU VM instance: {context.vm_name}")

        # If external VM with non-qcow2 source, ensure conversion happens
        # This creates the base disk (with -base suffix) from the source
        if is_external and detected_format != 'qcow2':
            base_disk_path = context.vm.get_base_disk_path()
            if not Path(base_disk_path).exists():
                log.info(f"CLAUDE: Converting {detected_format} to qcow2 base disk...")
                return_code, message = await context.vm.create_from_ovf_or_ova(
                    source_vm_path,
                    silent=False,
                    try_extract=True
                )
                if return_code != 0:
                    raise HypervisorException(f"Failed to convert VM disk: {message}")
                log.info(f"CLAUDE: Conversion to base disk completed successfully")

        # Create experiment overlay backed by immutable base disk
        # This ensures libguestfs operations don't modify the base disk,
        # preserving hash integrity for forensic validation
        experiment_id = context.experiment_run_ulid or 'default'
        log.info(f"CLAUDE: Creating overlay disk for experiment {experiment_id}...")

        try:
            overlay_path = await context.vm.create_overlay_disk(experiment_id)

            # Update VM config to use overlay (not base)
            # This ensures all disk operations (especially libguestfs) write to overlay
            context.vm.config.disk_path = overlay_path
            log.info(f"CLAUDE: Using overlay disk for experiment: {overlay_path}")

            # Log base disk location for reference
            if Path(context.vm.config.disk_path).exists():
                base_info = "external qcow2"
            else:
                base_info = context.vm.get_base_disk_path()
            log.info(f"CLAUDE: Base disk preserved for integrity checks: {base_info}")

        except Exception as e:
            raise HypervisorException(
                f"Failed to create overlay disk: {e}\n"
                f"Overlay creation failed. Ensure base disk exists and is accessible.\n"
                f"VM: {context.vm_name}, External: {is_external}"
            )

    async def setup_file_transfer(self, context):
        """
        Use libguestfs to place files on stopped VM disk.

        This method:
        1. Ensures VM is stopped
        2. Uses libguestfs to mount the disk image
        3. Copies playbook, wheels, and other files to /adare/ directory
        4. Unmounts and closes libguestfs

        Args:
            context: ExperimentRunCtx containing directories and VM
        """
        # Ensure VM is stopped (required for libguestfs)
        vm_state = context.vm.get_state()
        if vm_state == "running":
            log.info("Stopping VM for libguestfs file transfer")
            await context.vm.stop()
        elif vm_state != "poweroff":
            raise HypervisorException(
                f"VM in unexpected state '{vm_state}'. Expected 'poweroff' or 'running'."
            )

        # Get disk path from VM configuration
        disk_path = context.vm.config.disk_path

        # Find wheel files
        wheels_dir = context.project_directory.vm_runtime / 'wheels'
        adarelib_wheels = list(wheels_dir.glob('adarelib-*.whl'))
        adarevm_wheels = list(wheels_dir.glob('adarevm-*.whl'))

        if not adarelib_wheels:
            raise HypervisorException(
                f"adarelib wheel not found in {wheels_dir}. Run 'adare experiment load' first."
            )
        if not adarevm_wheels:
            raise HypervisorException(
                f"adarevm wheel not found in {wheels_dir}. Run 'adare experiment load' first."
            )

        adarelib_wheel = adarelib_wheels[0]
        adarevm_wheel = adarevm_wheels[0]

        # Build file manifest
        files_to_copy = [
            {'source': str(context.experiment_directory.playbookfile), 'dest': 'playbook.yml'},
            {'source': str(adarevm_wheel), 'dest': f'wheels/{adarevm_wheel.name}'},
            {'source': str(adarelib_wheel), 'dest': f'wheels/{adarelib_wheel.name}'}
        ]

        log.info(f"Transferring {len(files_to_copy)} files to VM disk via libguestfs")

        # Copy files using libguestfs
        self._copy_files_to_disk_via_libguestfs(
            disk_path=disk_path,
            files_to_copy=files_to_copy,
            target_base_dir="/adare"
        )

        log.info("File transfer to VM completed successfully")

    async def start_and_initialize_vm(self, context):
        """
        Start QEMU VM via libvirt (files already on disk from setup_file_transfer).

        VM will be visible in virsh and virt-manager. Display can be accessed
        by opening the VM in virt-manager and clicking 'Open'.

        Args:
            context: ExperimentRunCtx containing VM
        """
        # Start the VM (via libvirt)
        log.info(f"CLAUDE: Starting VM '{context.vm.vm_name}' via libvirt")
        await context.vm.start(stop_event=context.user_interrupt_event)
        log.info(f"CLAUDE: VM visible in virt-manager (use 'Open' button to access display)")

        # Wait until VM is fully booted and guest agent is ready
        log.info('Waiting until VM is ready (QEMU Guest Agent)')
        if not await context.vm.wait_until_fully_booted(timeout=360, stop_event=context.user_interrupt_event):
            raise LoggedException(log, 'VM did not become ready in time')
        log.info('VM is ready')

    async def retrieve_artifacts(self, context):
        """
        Stop VM and use libguestfs to retrieve artifacts.

        For QEMU, artifacts must be explicitly copied from the disk after
        the experiment completes, as there are no shared folders.

        Args:
            context: ExperimentRunCtx
        """
        # Stop VM first (required for libguestfs)
        log.info("Stopping VM to retrieve artifacts via libguestfs")
        await context.vm.stop()

        # Get disk path from VM configuration
        disk_path = context.vm.config.disk_path

        # Define artifact paths
        # Guest: /adare/run/artifacts
        # Host: <run_directory>/artifacts
        guest_artifact_path = "/adare/run/artifacts"
        host_artifact_path = context.experiment_run_directory.path / 'artifacts'

        log.info(f"Retrieving artifacts from {guest_artifact_path} to {host_artifact_path}")

        # Copy artifacts using libguestfs
        self._copy_artifacts_from_disk_via_libguestfs(
            disk_path=disk_path,
            source_path=guest_artifact_path,
            destination_path=host_artifact_path
        )

        log.info("Artifact retrieval completed successfully")

    async def cleanup_vm(self, context, post_interrupt: bool = False):
        """
        Cleanup QEMU VM resources.

        Args:
            context: ExperimentRunCtx
            post_interrupt: True if cleaning up after interrupt
        """
        # QEMU cleanup is simpler than VirtualBox - no shared folders or port forwarding to clean up
        log.debug("QEMU VM cleanup completed")
