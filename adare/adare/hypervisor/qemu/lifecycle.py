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
import os
import tempfile
from typing import List, Dict, Any

from adare.hypervisor.base.lifecycle import AbstractVMLifecycleStrategy
from adare.hypervisor.qemu.manager import QEMUManager
from adare.hypervisor.qemu.libvirt_stderr_redirect import (
    LibvirtStderrRedirect,
    get_experiment_log_file
)
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
        # Explicitly specify qcow2 format for libguestfs compatibility with overlay disks
        cmd = ['guestfish', mode_flag, '--format=qcow2', '-a', disk_path, '-i'] + commands

        # Enhanced logging for diagnostics
        log.debug(f"CLAUDE: Running guestfish on disk: {disk_path}")
        log.debug(f"CLAUDE: Guestfish command: {' '.join(cmd)}")

        # Redirect guestfish stderr to experiment log instead of console
        log_file = get_experiment_log_file()
        with LibvirtStderrRedirect(log_file=log_file, suppress_console=True):
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False
            )

        # Always log results for diagnostics
        log.debug(f"CLAUDE: Guestfish returncode: {result.returncode}")
        if result.stdout:
            log.debug(f"CLAUDE: Guestfish stdout: '{result.stdout.strip()}'")
        if result.stderr:
            log.debug(f"CLAUDE: Guestfish stderr: '{result.stderr.strip()}'")

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

        # Create base directory and runtime subdirectories
        commands.extend(['mkdir-p', target_base_dir, ':'])
        commands.extend(['mkdir-p', f'{target_base_dir}/run/logs', ':'])
        commands.extend(['mkdir-p', f'{target_base_dir}/run/artifacts', ':'])

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
                f"Disk: {disk_path}\n\n"
                f"Troubleshooting:\n"
                f"  1. Run with verbose logging: export LIBGUESTFS_DEBUG=1 LIBGUESTFS_TRACE=1\n"
                f"  2. Test guestfish manually: guestfish --rw --format=qcow2 -a {disk_path} -i\n"
                f"  3. Check backing file: qemu-img info {disk_path}\n"
                f"  4. Verify libguestfs: libguestfs-test-tool"
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

    def _batch_retrieve_files_from_disk(
        self,
        disk_path: str,
        retrieval_specs: List[Dict[str, Any]],
    ) -> Dict[str, List[str]]:
        """
        Retrieve multiple files/directories from guest disk in single guestfish session.

        This method batches all file retrieval operations into a single guestfish invocation,
        eliminating redundant disk mounting overhead. Uses guestfish script mode with optional
        commands (- prefix) to handle missing files gracefully.

        Args:
            disk_path: Path to guest disk image (qcow2)
            retrieval_specs: List of retrieval specifications, each dict containing:
                - 'guest_path': Path in guest filesystem (e.g., "/adare/run/artifacts")
                - 'host_path': Destination path on host (Path object)
                - 'type': 'directory' or 'file'
                - 'optional': If True, missing files are logged as info; if False, logged as warning
                - 'name': Human-readable name for logging (e.g., "artifacts")

        Returns:
            Dict with results:
                - 'retrieved': List of successfully retrieved file names
                - 'missing': List of files that didn't exist in guest

        Raises:
            HypervisorException: If disk not found or guestfish mount fails
        """
        # Validate disk exists
        if not Path(disk_path).exists():
            raise HypervisorException(f"VM disk not found at {disk_path}")

        log.info(f"CLAUDE: Starting batched retrieval of {len(retrieval_specs)} paths via single guestfish session")

        # Create all host destination directories
        for spec in retrieval_specs:
            try:
                spec['host_path'].parent.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                log.warning(f"Failed to create directory {spec['host_path'].parent}: {e}")

        # Build guestfish script commands
        script_lines = []

        for spec in retrieval_specs:
            guest_path = spec['guest_path']
            host_path = spec['host_path']
            file_type = spec['type']

            # Add optional marker (- prefix) for all paths to continue on error
            # This allows best-effort retrieval even if some paths don't exist
            prefix = '-'

            if file_type == 'file':
                # Download individual file
                script_lines.append(f"{prefix}download {guest_path} {host_path}")
            elif file_type == 'directory':
                # Copy directory (guestfish copies to parent with original name)
                # e.g., copy-out /adare/run/artifacts /dest/parent creates /dest/parent/artifacts
                script_lines.append(f"{prefix}copy-out {guest_path} {host_path.parent}")

        if not script_lines:
            log.warning("No retrieval specs provided for batched retrieval")
            return {'retrieved': [], 'missing': []}

        script_content = '\n'.join(script_lines)
        log.debug(f"CLAUDE: Guestfish script:\n{script_content}")

        # Write script to temporary file
        script_fd = None
        script_path = None
        try:
            script_fd, script_path = tempfile.mkstemp(suffix='.guestfish', text=True)
            with os.fdopen(script_fd, 'w') as f:
                f.write(script_content)
                script_fd = None  # Transferred ownership to context manager

            log.debug(f"CLAUDE: Wrote guestfish script to {script_path}")

            # Execute guestfish with script file
            cmd = [
                'guestfish',
                '--ro',
                '--format=qcow2',
                '-a', disk_path,
                '-i',  # Automatically inspect and mount filesystems
                '-f', script_path
            ]

            log.debug(f"CLAUDE: Executing: {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False
            )

            if result.returncode != 0:
                # Check if this is a mount failure (critical) or just missing files (expected)
                if 'could not' in result.stderr.lower() or 'cannot' in result.stderr.lower():
                    log.error(
                        f"Guestfish failed to mount disk: {result.stderr}\n"
                        f"This may indicate a corrupted overlay backing chain."
                    )
                    raise HypervisorException(f"Failed to mount guest disk via guestfish: {result.stderr}")
                else:
                    # Likely just missing optional files, continue with result analysis
                    log.debug(f"CLAUDE: Guestfish completed with returncode {result.returncode}: {result.stderr}")

            # Parse results by checking which files were actually created on host
            results = {'retrieved': [], 'missing': []}

            for spec in retrieval_specs:
                host_path = spec['host_path']
                name = spec['name']
                optional = spec['optional']

                # For directories, guestfish copies to parent with original name
                # So we need to check both the expected path and the quirky path
                if spec['type'] == 'directory':
                    # Check if directory was created
                    quirky_path = host_path.parent / Path(spec['guest_path']).name

                    if quirky_path.exists():
                        # Handle path adjustment if needed (same logic as old implementation)
                        if quirky_path != host_path:
                            if host_path.exists():
                                shutil.rmtree(host_path)
                            shutil.move(str(quirky_path), str(host_path))
                        results['retrieved'].append(name)
                    elif host_path.exists():
                        # Already at correct location
                        results['retrieved'].append(name)
                    else:
                        results['missing'].append(name)
                        if optional:
                            log.info(f"Optional path {name} not found in guest (normal if experiment didn't produce it)")
                        else:
                            log.warning(f"Required path {name} not found in guest: {spec['guest_path']}")
                else:
                    # File type
                    if host_path.exists():
                        results['retrieved'].append(name)
                    else:
                        results['missing'].append(name)
                        if optional:
                            log.debug(f"Optional file {name} not found in guest")
                        else:
                            log.warning(f"Required file {name} not found in guest: {spec['guest_path']}")

            return results

        finally:
            # Clean up temporary script file
            if script_fd is not None:
                try:
                    os.close(script_fd)
                except Exception:
                    pass

            if script_path and Path(script_path).exists():
                try:
                    Path(script_path).unlink()
                except Exception as e:
                    log.warning(f"Failed to clean up temp script {script_path}: {e}")

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
            log.debug(f"CLAUDE: External VM detected (--no-copy mode): {source_vm_path}")

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
                log.debug("CLAUDE: Source is qcow2 format, will use directly without conversion")
                disk_path = str(source_vm_path.resolve())
            elif detected_format in ['ova', 'vmdk', 'vdi', 'raw', 'unknown']:
                # Non-qcow2 format - need to convert in-place
                log.debug(f"CLAUDE: Source is {detected_format} format, will convert to qcow2 in-place")
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
        log.debug(f"CLAUDE: Created QEMU VM instance: {context.vm_name}")

        # Configure VM logging paths for experiment run
        log_file = get_experiment_log_file()
        if log_file:
            run_dir = Path(log_file).parent
            context.vm.config.serial_console_log_path = str(run_dir / "serial_console.log")
            context.vm.config.qemu_debug_log_path = str(run_dir / "qemu_debug.log")
            context.vm._save_vm_config()  # Persist for domain XML generation
            log.debug(f"CLAUDE: Configured VM logging to {run_dir}")

        # If external VM with non-qcow2 source, ensure conversion happens
        # This creates the base disk (with -base suffix) from the source
        if is_external and detected_format != 'qcow2':
            base_disk_path = context.vm.get_base_disk_path()
            if not Path(base_disk_path).exists():
                log.debug(f"CLAUDE: Converting {detected_format} to qcow2 base disk...")
                return_code, message = await context.vm.create_from_ovf_or_ova(
                    source_vm_path,
                    silent=False,
                    try_extract=True
                )
                if return_code != 0:
                    raise HypervisorException(f"Failed to convert VM disk: {message}")
                log.debug(f"CLAUDE: Conversion to base disk completed successfully")

        # Create experiment overlay backed by immutable base disk
        # This ensures libguestfs operations don't modify the base disk,
        # preserving hash integrity for forensic validation
        experiment_id = context.experiment_run_ulid or 'default'
        log.debug(f"CLAUDE: Creating overlay disk for experiment {experiment_id}...")

        try:
            overlay_path = await context.vm.create_overlay_disk(experiment_id)

            # Update VM config to use overlay (not base)
            # This ensures all disk operations (especially libguestfs) write to overlay
            context.vm.config.disk_path = overlay_path
            log.debug(f"CLAUDE: Using overlay disk for experiment: {overlay_path}")

            # Validate overlay was created successfully
            if not Path(overlay_path).exists():
                raise HypervisorException(
                    f"Overlay disk creation reported success but file not found: {overlay_path}\n"
                    f"This indicates a race condition or filesystem issue."
                )
            log.debug(f"CLAUDE: Verified overlay exists: {overlay_path}")

            # Log base disk location for reference
            if Path(context.vm.config.disk_path).exists():
                base_info = "external qcow2"
            else:
                base_info = context.vm.get_base_disk_path()
            log.debug(f"CLAUDE: Base disk preserved for integrity checks: {base_info}")

            # Cleanup orphaned overlays from old naming scheme
            # Old overlays have chained names like: VM-name-overlay-{ULID1}-overlay-{ULID2}.qcow2
            try:
                disk_dir = Path(overlay_path).parent
                base_disk_path = Path(context.vm.get_base_disk_path())

                for orphan in disk_dir.glob('*-overlay-*-overlay-*.qcow2'):
                    # Only delete if it's not the current overlay or base disk
                    if orphan != Path(overlay_path) and orphan != base_disk_path:
                        log.debug(f"CLAUDE: Cleaning up orphaned overlay: {orphan.name}")
                        orphan.unlink()
            except Exception as e:
                log.warning(f"CLAUDE: Failed to cleanup orphaned overlays: {e}")

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

        # Validate disk exists and check backing file if it's an overlay
        if not Path(disk_path).exists():
            raise HypervisorException(
                f"Disk image not found: {disk_path}\n"
                "Ensure VM overlay was created successfully."
            )

        # Log disk info for debugging
        log.debug(f"CLAUDE: Preparing to copy files to disk: {disk_path}")

        # Check if this is an overlay with a backing file and VALIDATE the chain
        try:
            import json as json_module
            result = subprocess.run(
                ['qemu-img', 'info', '--output=json', disk_path],
                capture_output=True,
                text=True,
                check=False
            )

            if result.returncode == 0:
                disk_info = json_module.loads(result.stdout)

                if 'backing-filename' in disk_info:
                    backing_file = disk_info['backing-filename']
                    log.debug(f"CLAUDE: Overlay disk detected with backing file: {backing_file}")

                    # Check if backing file exists (resolve relative paths)
                    disk_dir = Path(disk_path).parent
                    backing_path = disk_dir / backing_file if not Path(backing_file).is_absolute() else Path(backing_file)

                    if not backing_path.exists():
                        log.warning(
                            f"CLAUDE: Backing file not found at expected location:\n"
                            f"  Backing file (from qcow2): {backing_file}\n"
                            f"  Resolved path: {backing_path}\n"
                            f"  This may cause libguestfs to fail."
                        )
                    else:
                        log.debug(f"CLAUDE: Backing file verified: {backing_path}")

                        # CRITICAL: Validate backing file is NOT itself an overlay
                        # Overlay chaining causes logs/data from previous runs to accumulate
                        if '-overlay-' in str(backing_file):
                            raise HypervisorException(
                                f"OVERLAY CHAIN DETECTED - refusing to proceed.\n"
                                f"The overlay disk's backing file is itself an overlay:\n"
                                f"  Current overlay: {disk_path}\n"
                                f"  Backing file (also overlay!): {backing_file}\n\n"
                                f"This indicates a bug where overlay paths were persisted to config.\n"
                                f"Logs and data from previous runs would accumulate in this chain.\n\n"
                                f"To fix: Delete the orphaned overlay files and re-run.\n"
                                f"Overlay files are located in: {disk_dir}\n"
                                f"Pattern: *-overlay-*.qcow2"
                            )

                        # Also check the backing file's backing file (one level deep)
                        backing_info_result = subprocess.run(
                            ['qemu-img', 'info', '--output=json', str(backing_path)],
                            capture_output=True,
                            text=True,
                            check=False
                        )
                        if backing_info_result.returncode == 0:
                            backing_info = json_module.loads(backing_info_result.stdout)
                            if 'backing-filename' in backing_info:
                                nested_backing = backing_info['backing-filename']
                                log.debug(f"CLAUDE: Base disk has backing file: {nested_backing}")
                                # This is expected for some VM formats, just log it
                else:
                    log.debug(f"CLAUDE: Standalone disk (no backing file)")

        except HypervisorException:
            raise  # Re-raise our validation error
        except json_module.JSONDecodeError as e:
            log.warning(f"CLAUDE: Failed to parse qemu-img output: {e}")
        except FileNotFoundError:
            log.warning("CLAUDE: qemu-img not found - skipping disk validation")
        except subprocess.SubprocessError as e:
            log.warning(f"CLAUDE: Failed to inspect disk image: {e}")

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

    async def setup_networking(self, context):
        """
        Setup port forwarding for WebSocket communication via QEMU config.

        Port forwarding rules are saved to VM config and applied when VM starts.
        The guest always uses port 18765, while the host uses a dynamically allocated port.

        Args:
            context: ExperimentRunCtx containing configuration
        """
        log.debug("Setting up port forwarding for WebSocket communication")

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
        Start QEMU VM via libvirt (files already on disk from setup_file_transfer).

        VM will be visible in virsh and virt-manager. Display can be accessed
        by opening the VM in virt-manager and clicking 'Open'.

        Args:
            context: ExperimentRunCtx containing VM
        """
        # Start the VM (via libvirt)
        log.debug(f"CLAUDE: Starting VM '{context.vm.vm_name}' via libvirt")
        await context.vm.start(stop_event=context.user_interrupt_event)
        log.debug(f"CLAUDE: VM visible in virt-manager (use 'Open' button to access display)")

        # Wait until VM is fully booted and guest agent is ready
        # Determine if we should skip X11 discovery based on GUI execution mode
        from adare.backend.experiment.execution.gui_executor_factory import resolve_gui_execution_mode
        from adare.backend.experiment.execution.base import GUIExecutionMode
        playbook_settings = context.playbook.settings if context.playbook and hasattr(context.playbook, 'settings') else None
        gui_mode = resolve_gui_execution_mode(context.vm, playbook_settings)
        skip_x11 = (gui_mode == GUIExecutionMode.HOST)

        # Skip validation in test mode for faster iteration
        if context.config.test_mode:
            log.warning('SKIPPING VM validation (test mode) - VM must be pre-configured correctly')
            log.info('VM assumed ready (test mode)')
        else:
            log.info('Waiting until VM is ready (QEMU Guest Agent)')
            if not await context.vm.wait_until_fully_booted(timeout=360, stop_event=context.user_interrupt_event, skip_x11_discovery=skip_x11):
                raise LoggedException(log, 'VM did not become ready in time')
            log.info('VM is ready')

    async def retrieve_artifacts(self, context, post_interrupt: bool = False):
        """
        Stop VM and use libguestfs to retrieve artifacts and logs.

        For QEMU, artifacts and logs must be explicitly copied from the disk after
        the experiment completes, as there are no shared folders.

        Handles case where VM was never fully initialized by returning early.

        Args:
            context: ExperimentRunCtx
            post_interrupt: If True, we're in post-interrupt cleanup (ignored for QEMU)
        """
        # Early return if VM not initialized (experiment failed before VM creation)
        if not context.vm or not hasattr(context.vm, 'config'):
            log.info(
                "VM not initialized - skipping artifact retrieval. "
                "This is normal if experiment failed before VM was created."
            )
            return

        # Stop VM first (required for libguestfs)
        log.info("Stopping VM to retrieve artifacts and logs via libguestfs")
        await context.vm.stop()

        # Get disk path from VM configuration
        disk_path = context.vm.config.disk_path

        # Enhanced disk path logging for diagnostics
        log.info(f"CLAUDE: Artifact retrieval - using disk path: {disk_path}")
        log.debug(f"CLAUDE: Disk exists: {Path(disk_path).exists()}")

        # Check if overlay and log backing file info
        try:
            import json
            result = subprocess.run(
                ['qemu-img', 'info', '--output=json', disk_path],
                capture_output=True, text=True, check=False
            )
            if result.returncode == 0:
                disk_info = json.loads(result.stdout)
                if 'backing-filename' in disk_info:
                    log.info(f"CLAUDE: Disk is overlay, backing file: {disk_info['backing-filename']}")
                else:
                    log.info(f"CLAUDE: Disk is standalone (no backing file)")
                log.debug(f"CLAUDE: Disk format: {disk_info.get('format', 'unknown')}")
        except Exception as e:
            log.warning(f"CLAUDE: Failed to inspect disk: {e}")

        # Validate disk exists before attempting retrieval
        if not Path(disk_path).exists():
            log.warning(
                f"Disk image not found at {disk_path}. "
                f"Skipping artifact retrieval - experiment may have failed very early."
            )
            return

        # Build retrieval specification for batched operation
        # This batches all file retrieval into a single guestfish session,
        # eliminating ~7 redundant disk mount operations
        retrieval_specs = [
            {
                'guest_path': '/adare/run/artifacts',
                'host_path': context.experiment_run_directory.path / 'artifacts',
                'type': 'directory',
                'optional': True,  # May not exist if experiment didn't produce artifacts
                'name': 'artifacts'
            },
            {
                'guest_path': '/adare/run/logs/adarevm.log',
                'host_path': context.experiment_run_directory.log_directory / 'adarevm.log',
                'type': 'file',
                'optional': True,  # May not exist if VM failed to start agent
                'name': 'adarevm.log'
            },
            {
                'guest_path': '/adare/run/logs/adarevmstartup.log',
                'host_path': context.experiment_run_directory.log_directory / 'adarevmstartup.log',
                'type': 'file',
                'optional': True,  # May not exist if startup script failed early
                'name': 'adarevmstartup.log'
            }
        ]

        log.info("Retrieving artifacts and logs in single guestfish session (batched operation)")

        # Execute batched retrieval
        results = self._batch_retrieve_files_from_disk(disk_path, retrieval_specs)

        # Log results summary
        if results['retrieved']:
            log.info(f"Successfully retrieved: {', '.join(results['retrieved'])}")
        if results['missing']:
            log.info(f"Not found in guest (skipped): {', '.join(results['missing'])}")

        log.info("Artifact and log retrieval completed")

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

        log.debug("QEMU VM cleanup completed")
