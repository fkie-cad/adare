"""
QEMU-specific VM lifecycle strategy.

This module implements the QEMU lifecycle strategy with two modes for file transfer:

1. virtio-fs mode (default):
   - Uses multiple virtio-fs shared directories for high-performance file sharing
   - Shares: run, vm, experiment, project_shared, shared
   - Linux: mounted via `mount -t virtiofs {tag} /adare/{name}`
   - Windows: mounted via `virtiofs.exe -t {tag} -m C:\\adare\\{name}`

2. libguestfs mode (fallback, set QEMU_LIBGUESTFS=true):
   - Uses guestfish CLI for file transfer to stopped VM disk
   - Files copied before boot, artifacts retrieved after shutdown
   - Original implementation for backwards compatibility

The mode is determined by the QEMU_LIBGUESTFS environment variable.
"""
from pathlib import Path
import logging
import asyncio
import subprocess
import shutil
import os
import tempfile
import time
import json

from typing import List, Dict, Any, Optional, Tuple

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


def _use_shared_folder_mode() -> bool:
    """Check if shared folder mode (virtio-fs) should be used.

    Returns:
        True for virtio-fs mode (default for ALL modes, including session)
        False for libguestfs mode (only when QEMU_LIBGUESTFS=true/1/yes)
    """
    libguestfs_env = os.environ.get('QEMU_LIBGUESTFS', '').lower()
    if libguestfs_env in ('true', '1', 'yes'):
        return False
        
    # Always use shared folders (virtio-fs) by default
    # This applies to both system and session mode for Windows and Linux
    return True


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

    def _run_guestfish_command(
        self,
        disk_path: str,
        commands: List[str],
        readonly: bool = False,
        auto_mount: bool = True
    ) -> tuple[int, str, str]:
        """
        Execute guestfish commands on a disk image with manual mounting.

        Args:
            disk_path: Path to disk image
            commands: List of guestfish command parts (will be joined with ':')
            readonly: If True, mount disk read-only
            auto_mount: If True, automatically detect and mount root filesystem (default)

        Returns:
            Tuple of (returncode, stdout, stderr)
        """
        mode_flag = '--ro' if readonly else '--rw'
        # Build base command without -i flag (no longer using auto-inspect)
        cmd = ['guestfish', mode_flag, '--format=qcow2', '-a', disk_path]

        # Add manual mount logic if requested
        if auto_mount:
            # Detect root filesystem
            try:
                root_device, fs_type = self._detect_root_filesystem(disk_path)
                log.debug(f"CLAUDE: Mounting root filesystem: {root_device} ({fs_type})")

                # Check for NTFS hibernation if mounting read-write
                if not readonly:
                    # Always run ntfsfix for NTFS filesystems in RW mode
                    # This safely clears dirty bits and hibernation flags that prevent RW mounting
                    if fs_type == 'ntfs':
                        log.info(f"Ensuring NTFS filesystem {root_device} is clean (running ntfsfix)...")
                        self._remove_ntfs_hibernation(disk_path, root_device)

                # FIXED: Add run as first command (no leading colon), then mount with colon separator
                cmd.extend(['run', ':', 'mount', root_device, '/'])
            except HypervisorException:
                # If detection fails, raise immediately (user-approved error handling)
                raise

        # Add user commands
        if commands:
            cmd.extend([':'] + commands)

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

    def _detect_root_filesystem(self, disk_path: str) -> tuple[str, str]:
        """
        Detect root filesystem by finding largest OS partition.

        Args:
            disk_path: Path to VM disk image

        Returns:
            Tuple of (device_path, filesystem_type)
            e.g., ('/dev/sda4', 'ntfs') or ('/dev/sda1', 'ext4')

        Raises:
            HypervisorException: If no suitable filesystem found

        Algorithm:
            1. Run guestfish with: run : list-filesystems
            2. Parse output format: "/dev/sda1: ext4" or "unknown"
            3. Filter for OS filesystems: ntfs, ext4, xfs, ext3
            4. Get size for each device using: blockdev-getsize64
            5. Select largest partition
        """
        # FIXED: NO leading colon before first command! Colon only separates commands.
        cmd = ['guestfish', '--ro', '--format=qcow2', '-a', disk_path, 'run', ':', 'list-filesystems']

        result = subprocess.run(cmd, capture_output=True, text=True, check=False)

        if result.returncode != 0:
            raise HypervisorException(
                f"Failed to detect filesystems on {disk_path}\n"
                f"Error: {result.stderr}\n\n"
                f"Manual troubleshooting:\n"
                f"  guestfish --ro -a {disk_path}\n"
                f"  ><fs> run\n"
                f"  ><fs> list-filesystems"
            )

        # Parse output: "/dev/sda1: ext4\n/dev/sda2: unknown\n"
        os_filesystems = self._parse_filesystems_output(result.stdout)

        if not os_filesystems:
            raise HypervisorException(
                f"No suitable OS filesystem found on {disk_path}\n"
                f"Detected filesystems:\n{result.stdout}\n\n"
                f"Manual mount required:\n"
                f"  guestfish --ro -a {disk_path}\n"
                f"  ><fs> run\n"
                f"  ><fs> list-filesystems\n"
                f"  ><fs> mount /dev/sdaX /"
            )

        # Get sizes and select largest
        if len(os_filesystems) == 1:
            return os_filesystems[0]

        # Multiple partitions - find largest by size
        largest_device = None
        largest_fs_type = None
        largest_size = 0
        partition_sizes = []  # For debugging

        for device, fs_type in os_filesystems:
            # FIXED: NO leading colon before first command
            size_cmd = ['guestfish', '--ro', '--format=qcow2', '-a', disk_path, 'run', ':', 'blockdev-getsize64', device]

            size_result = subprocess.run(size_cmd, capture_output=True, text=True, check=False)
            if size_result.returncode == 0:
                try:
                    size = int(size_result.stdout.strip())
                    partition_sizes.append((device, fs_type, size))
                    if size > largest_size:
                        largest_size = size
                        largest_device = device
                        largest_fs_type = fs_type
                except ValueError:
                    log.warning(f"Could not parse size for {device}: {size_result.stdout}")
            else:
                log.warning(f"CLAUDE: Size query failed for {device}: {size_result.stderr}")

        # Log all detected partitions for debugging
        if partition_sizes:
            log.debug(f"CLAUDE: Detected partitions with sizes:")
            for dev, fs, sz in sorted(partition_sizes, key=lambda x: x[2], reverse=True):
                size_gb = sz / (1024 * 1024 * 1024)
                log.debug(f"CLAUDE:   {dev}: {fs}, {size_gb:.2f} GB")

        if not largest_device:
            # Fallback to first filesystem if size detection fails
            log.warning("Could not determine partition sizes, using first detected filesystem")
            return os_filesystems[0]

        # Warn if selected partition is suspiciously small for an OS partition
        # Windows root should be at least 10 GB, Linux at least 5 GB
        min_size_gb = 10 if largest_fs_type == 'ntfs' else 5
        min_size_bytes = min_size_gb * 1024 * 1024 * 1024
        if largest_size < min_size_bytes:
            log.warning(
                f"CLAUDE: Selected partition {largest_device} is only {largest_size / (1024*1024*1024):.2f} GB. "
                f"This may be a recovery partition, not the main OS partition. "
                f"Expected at least {min_size_gb} GB for {largest_fs_type}."
            )

        log.debug(f"CLAUDE: Selected root filesystem: {largest_device} ({largest_fs_type}, size: {largest_size} bytes)")
        return largest_device, largest_fs_type

    def _parse_filesystems_output(self, stdout: str) -> List[Tuple[str, str]]:
        """
        Parse guestfish list-filesystems output.
        
        Args:
            stdout: Output from 'list-filesystems' command
            
        Returns:
            List of (device, fs_type) tuples for supported OS filesystems
        """
        os_filesystems = []
        for line in stdout.strip().split('\n'):
            if ':' not in line:
                continue
            device, fs_type = line.split(':', 1)
            device = device.strip()
            fs_type = fs_type.strip()

            if fs_type in ['ntfs', 'ext4', 'xfs', 'ext3']:
                os_filesystems.append((device, fs_type))
        return os_filesystems

    def _is_ntfs_hibernated(self, disk_path: str, device: str) -> tuple[bool, str]:
        """
        Check if NTFS filesystem is in hibernation state.

        Windows Fast Startup and hibernation leave NTFS filesystems in a
        "dirty" state that forces libguestfs to mount them read-only.

        Args:
            disk_path: Path to disk image
            device: Device path (e.g., '/dev/sda4')

        Returns:
            Tuple of (is_hibernated: bool, fs_type: str)
            - is_hibernated: True if NTFS filesystem has hibernation metadata
            - fs_type: Filesystem type ('ntfs', 'ext4', etc.)
        """
        # First, detect filesystem type
        cmd = ['guestfish', '--ro', '--format=qcow2', '-a', disk_path, 'run', ':', 'list-filesystems']
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)

        if result.returncode != 0:
            log.warning(f"Failed to detect filesystem type for {device}: {result.stderr}")
            return False, 'unknown'

        # Parse output to find filesystem type for this device
        fs_type = 'unknown'
        for line in result.stdout.strip().split('\n'):
            if ':' not in line:
                continue
            dev, fs = line.split(':', 1)
            if dev.strip() == device:
                fs_type = fs.strip()
                break

        # Only check hibernation for NTFS filesystems
        if fs_type != 'ntfs':
            log.debug(f"CLAUDE: Device {device} is {fs_type}, skipping hibernation check")
            return False, fs_type

        # Try to mount NTFS filesystem read-only to check for hibernation
        # If it has hibernation metadata, even read-only mount may show warnings
        log.debug(f"CLAUDE: Checking NTFS hibernation state for {device}")

        # Use guestfish to check if filesystem can be mounted
        # The presence of hibernation is indicated by mount errors or warnings
        test_cmd = ['guestfish', '--ro', '--format=qcow2', '-a', disk_path,
                   'run', ':', 'mount-ro', device, '/', ':', 'is-file', '/hiberfil.sys']

        test_result = subprocess.run(test_cmd, capture_output=True, text=True, check=False)

        # Check stderr for hibernation-related messages and hiberfil.sys existence
        is_hibernated = self._check_ntfs_hibernation_output(test_result.stdout, test_result.stderr)
        
        if is_hibernated:
            log.debug(f"CLAUDE: NTFS hibernation detected on {device}")
            return True, fs_type

        return False, fs_type

    def _check_ntfs_hibernation_output(self, stdout: str, stderr: str) -> bool:
        """
        Analyze guestfish output to detect NTFS hibernation.
        
        Args:
            stdout: Output from guestfish command
            stderr: Error output from guestfish command
            
        Returns:
            True if hibernation detected
        """
        stderr_lower = stderr.lower()
        if 'hibernat' in stderr_lower or 'hiberfile' in stderr_lower or 'unsafe' in stderr_lower:
            return True

        if 'true' in stdout.lower():
            return True
            
        return False

    def _remove_ntfs_hibernation(self, disk_path: str, device: str) -> None:
        """
        Remove NTFS hibernation metadata to enable read-write mounting.

        Uses ntfsfix utility which safely removes Windows hibernation data.
        This is safe for QEMU overlay disks as changes only affect the overlay.

        Args:
            disk_path: Path to disk image (qcow2 overlay)
            device: Device path (e.g., '/dev/sda4')

        Raises:
            HypervisorException: If ntfsfix operation fails
        """
        log.warning(
            f"Removing NTFS hibernation metadata from {device}. "
            f"This is safe for overlay disks and required for read-write access."
        )

        # Run ntfsfix to clear hibernation metadata
        # The -d flag removes the dirty bit and hibernation file
        # Use 'debug sh' to invoke ntfsfix binary directly, bypassing 'sh' mount check
        cmd = ['guestfish', '--rw', '--format=qcow2', '-a', disk_path, '--',
               'run', ':', 'debug', 'sh', f'ntfsfix -d {device}']

        log.debug(f"CLAUDE: Running ntfsfix command: {' '.join(cmd)}")

        result = subprocess.run(cmd, capture_output=True, text=True, check=False)

        if result.returncode != 0:
            # Check if ntfsfix command is not available
            if 'unknown command' in result.stderr.lower() or 'ntfsfix' in result.stderr.lower():
                raise HypervisorException(
                    f"Failed to remove NTFS hibernation: ntfsfix utility not available.\n"
                    f"Error: {result.stderr}\n\n"
                    f"To fix this issue:\n"
                    f"  1. Install ntfs-3g package: sudo apt-get install ntfs-3g (Debian/Ubuntu)\n"
                    f"  2. Ensure libguestfs has ntfs support: sudo apt-get install libguestfs-tools\n"
                    f"  3. Alternatively, disable Windows Fast Startup:\n"
                    f"     - Boot Windows VM\n"
                    f"     - Run: powercfg /h off\n"
                    f"     - Shutdown cleanly\n"
                    f"     - Re-run experiment"
                )
            else:
                raise HypervisorException(
                    f"Failed to remove NTFS hibernation metadata.\n"
                    f"Error: {result.stderr}\n"
                    f"Device: {device}\n"
                    f"Disk: {disk_path}\n\n"
                    f"Troubleshooting:\n"
                    f"  1. Ensure VM was shut down cleanly (not forced off)\n"
                    f"  2. Disable Windows Fast Startup in the VM\n"
                    f"  3. Check disk integrity: qemu-img check {disk_path}\n"
                    f"  4. Try manual ntfsfix: guestfish --rw -a {disk_path} : run : ntfsfix {device}"
                )

        log.info(f"Successfully removed NTFS hibernation metadata from {device}")
        log.debug(f"CLAUDE: ntfsfix output: {result.stdout}")

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
        commands.extend(['mkdir-p', f'{target_base_dir}/vm', ':'])

        # Collect and create all parent directories
        parent_dirs = set()
        import re
        
        # Helper to resolve destination path in guest
        def resolve_guest_dest(dest):
            # Check for Windows drive letter (e.g. C:\ or C:/)
            # We assume the drive is mounted at root /
            if re.match(r'^[a-zA-Z]:[\\/]', dest):
                # Strip drive letter (C:) and normalize to forward slashes 
                # C:\Path -> /Path
                return dest[2:].replace('\\', '/')
            # Check for Linux absolute path
            elif dest.startswith('/'):
                return dest
            else:
                return f"{target_base_dir}/{dest}"

        for file_spec in files_to_copy:
            dest_full = resolve_guest_dest(file_spec['dest'])
            parent = str(Path(dest_full).parent)
            parent_dirs.add(parent)

        # Sort by depth to create parents before children
        for parent_dir in sorted(parent_dirs, key=lambda p: len(p.split('/'))):
            if parent_dir != target_base_dir:
                commands.extend(['mkdir-p', parent_dir, ':'])

        # Copy each file/directory
        for file_spec in files_to_copy:
            source_path = file_spec['source']
            dest_full = resolve_guest_dest(file_spec['dest'])
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
                f"  1. For Windows VMs: Disable Fast Startup in Control Panel > Power Options\n"
                f"  2. Ensure VM was shut down cleanly (not hibernated or forced off)\n"
                f"  3. Run with verbose logging: export LIBGUESTFS_DEBUG=1 LIBGUESTFS_TRACE=1\n"
                f"  4. Test filesystem detection: guestfish --ro --format=qcow2 -a {disk_path} : run : list-filesystems\n"
                f"  5. Mount manually: guestfish --rw --format=qcow2 -a {disk_path} : run : mount /dev/sdaX /\n"
                f"  6. Check backing file: qemu-img info {disk_path}\n"
                f"  7. Verify libguestfs: libguestfs-test-tool"
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

        # Detect root filesystem once for entire script
        try:
            root_device, _ = self._detect_root_filesystem(disk_path)
            log.debug(f"CLAUDE: Using root filesystem for batch retrieval: {root_device}")
        except HypervisorException as e:
            log.error(f"Failed to detect root filesystem: {e}")
            raise

        # Build guestfish script commands with manual mount
        script_content = self._generate_guestfish_retrieval_script(root_device, retrieval_specs)

        if not script_content:
            log.warning("No retrieval specs provided or script generation failed")
            return {'retrieved': [], 'missing': []}




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

            # Execute guestfish with script file (no -i flag, using manual mount)
            cmd = [
                'guestfish',
                '--ro',
                '--format=qcow2',
                '-a', disk_path,
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

    def _generate_guestfish_retrieval_script(self, root_device: str, retrieval_specs: List[Dict[str, Any]]) -> str:
        """
        Generate guestfish script for batched file retrieval.
        
        Args:
            root_device: Root filesystem device
            retrieval_specs: List of retrieval specifications
            
        Returns:
            String containing the guestfish script
        """
        script_lines = [
            'run',  # Launch guestfish backend
            f'mount {root_device} /',  # Mount root filesystem
        ]

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
                
        if len(script_lines) <= 2:  # Only run and mount
            return ""

        return '\n'.join(script_lines)

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
                    log.debug(f"CLAUDE: Format detection stage: {detected_format}")

            # Step 2: Conversion (only if needed)
            if is_external and detected_format == 'qcow2':
                # External qcow2 - use directly without conversion
                log.debug(f"CLAUDE: Skipping conversion - external qcow2 will be used as base")
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

                        log.debug(f"CLAUDE: Converting {detected_format} to qcow2 base disk...")
                        return_code, message = await context.vm.create_from_ovf_or_ova(
                            source_vm_path,
                            silent=False,
                            try_extract=True
                        )

                        if return_code != 0:
                            raise HypervisorException(f"Failed to convert VM disk: {message}")

                        log.debug(f"CLAUDE: Conversion to base disk completed successfully")

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
        Setup file transfer mechanism for the experiment.

        This method chooses between virtio-fs and libguestfs modes:
        - virtio-fs (default): Creates shared directory on host, no disk modification needed
        - libguestfs (fallback): Copies files to stopped VM disk

        Args:
            context: ExperimentRunCtx containing directories and VM
        """
        if _use_shared_folder_mode():
            log.info("Using virtio-fs mode for file transfer (multiple shares)")
            await self._setup_virtiofs_shared_directories(context)
        else:
            log.info("Using libguestfs mode for file transfer (QEMU_LIBGUESTFS=true)")
            await self._setup_file_transfer_via_libguestfs(context)

    async def _setup_file_transfer_via_libguestfs(self, context):
        """
        Use libguestfs to place files on stopped VM disk (fallback mode).

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

        # CRITICAL: Explicitly disable virtiofs in config when using libguestfs mode
        # This ensures that any previous run's virtiofs config is removed,
        # preventing "migration with virtiofs device is not supported" errors during snapshots.
        context.vm.config.virtiofs_enabled = False
        context.vm.config.virtiofs_shares = []
        context.vm._save_vm_config()
        log.info("CLAUDE: Disabled virtiofs in VM config (required for snapshots)")

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

        # Check if wheels are available (wheel mode) or use editable mode
        wheels_dir = context.project_directory.vm_runtime / 'wheels'
        adarelib_wheels = list(wheels_dir.glob('adarelib-*.whl'))
        adarevm_wheels = list(wheels_dir.glob('adarevm-*.whl'))

        wheels_available = bool(adarelib_wheels and adarevm_wheels)

        # NEW: Check if wheels already installed in guest VM
        wheels_already_installed = False
        if wheels_available:
            # Quick check: Are wheels already in the VM at /adare/vm/wheels/?
            # User may have pre-installed them manually
            try:
                check_cmd = [
                    'guestfish', '--ro', '-a', str(disk_path), '-i',
                    'sh', 'ls /adare/vm/wheels/ 2>/dev/null | grep -E "adarevm-|adarelib-" || echo MISSING'
                ]
                result = subprocess.run(check_cmd, capture_output=True, text=True, timeout=10)

                if 'adarevm-' in result.stdout and 'adarelib-' in result.stdout and 'MISSING' not in result.stdout:
                    wheels_already_installed = True
                    log.info("✓ Detected wheels already installed in VM - skipping wheel copy")
                    log.info("  PERFORMANCE: Saved ~20-40s by skipping wheel copy")
            except Exception as e:
                log.debug(f"Could not check for pre-installed wheels: {e}")
                # Fall back to copying wheels

        # Build file manifest
        files_to_copy = []
        if context.experiment_directory:
            files_to_copy.append({'source': str(context.experiment_directory.playbookfile), 'dest': 'playbook.yml'})

        if wheels_available and not wheels_already_installed:
            # Wheel mode: copy wheels (not yet installed in VM)
            log.info("Using wheel installation mode for QEMU - copying wheels")
            adarelib_wheel = adarelib_wheels[0]
            adarevm_wheel = adarevm_wheels[0]
            files_to_copy.extend([
                {'source': str(adarevm_wheel), 'dest': f'vm/wheels/{adarevm_wheel.name}'},
                {'source': str(adarelib_wheel), 'dest': f'vm/wheels/{adarelib_wheel.name}'}
            ])
        elif wheels_available and wheels_already_installed:
            # Wheels already in VM - skip copy
            log.info("Using wheel installation mode for QEMU - wheels already present in VM")
        else:
            # Editable mode: copy source directories to /adare/vm/
            log.info("Using editable installation mode for QEMU (no wheels found)")
            adarelib_src = context.project_directory.vm_runtime / 'adarelib'
            adarevm_src = context.project_directory.vm_runtime / 'adarevm'

            if not adarelib_src.exists():
                raise HypervisorException(
                    f"adarelib source not found at {adarelib_src}. "
                    f"Run 'adare experiment load' first."
                )
            if not adarevm_src.exists():
                raise HypervisorException(
                    f"adarevm source not found at {adarevm_src}. "
                    f"Run 'adare experiment load' first."
                )

            files_to_copy.extend([
                {'source': str(adarevm_src), 'dest': 'vm/adarevm'},
                {'source': str(adarelib_src), 'dest': 'vm/adarelib'}
            ])

        # Add shared project and experiment directories if they exist
        # These correspond to what VirtualBox mounts as 'project_shared' and 'shared'
        if context.project_directory.shared.exists():
            log.info(f"Adding shared project directory to transfer: {context.project_directory.shared}")
            files_to_copy.append({
                'source': str(context.project_directory.shared),
                'dest': 'project_shared'
            })

        if context.experiment_directory and context.experiment_directory.shared.exists():
            log.info(f"Adding shared experiment directory to transfer: {context.experiment_directory.shared}")
            files_to_copy.append({
                'source': str(context.experiment_directory.shared),
                'dest': 'shared'
            })
    
        # User defined shared directories (fallback copy)
        if hasattr(context.config, 'shared_directories') and context.config.shared_directories:
             for name, details in context.config.shared_directories.items():
                host_path = details.get('host')
                vm_path = details.get('vm')
                if host_path and vm_path:
                    files_to_copy.append({
                        'source': str(host_path),
                        'dest': str(vm_path)
                    })


        log.info(f"Transferring {len(files_to_copy)} files to VM disk via libguestfs")

        # Copy files using libguestfs
        self._copy_files_to_disk_via_libguestfs(
            disk_path=disk_path,
            files_to_copy=files_to_copy,
            target_base_dir="/adare"
        )

        log.info("File transfer to VM completed successfully")

    async def _setup_virtiofs_shared_directories(self, context):
        """
        Set up multiple virtio-fs shared directories matching VirtualBox pattern.

        Creates separate host directories for each share (no file copying):
        - run: experiment run directory (logs, artifacts)
        - vm: adarevm/adarelib runtime
        - experiment: experiment configuration
        - project_shared: project-level shared files (optional)
        - shared: experiment-level shared files (optional)

        Each directory is shared with the guest via a separate virtio-fs filesystem,
        mounted at /adare/{name} (Linux) or C:\\adare\\{name} (Windows).

        Args:
            context: ExperimentRunCtx containing directories and VM
        """
        is_windows = 'windows' in context.guest_platform.lower()

        # Define mount base based on platform
        if is_windows:
            base_mount = 'C:\\adare'
        else:
            base_mount = '/adare'

        log.info("Setting up multiple virtio-fs shared directories")

        # Build list of virtiofs shares
        virtiofs_shares = []

        # 1. Run directory - experiment run artifacts and logs
        run_dir = context.experiment_run_directory.path
        (run_dir / 'logs').mkdir(parents=True, exist_ok=True)
        (run_dir / 'artifacts').mkdir(parents=True, exist_ok=True)

        # Copy playbook.yml to run directory for easy guest access
        if context.experiment_directory:
            shutil.copy2(context.experiment_directory.playbookfile, run_dir / 'playbook.yml')
            log.debug(f"Copied playbook to {run_dir / 'playbook.yml'}")

        virtiofs_shares.append({
            'tag': 'run',
            'host_path': str(run_dir),
            'guest_mount': f'{base_mount}\\run' if is_windows else f'{base_mount}/run',
            'readonly': False
        })

        # 2. VM runtime - adarevm/adarelib wheels or source
        vm_runtime_dir = context.project_directory.vm_runtime
        if not vm_runtime_dir.exists():
            raise HypervisorException(
                f"VM runtime directory not found at {vm_runtime_dir}. "
                f"Run 'adare experiment load' first."
            )
        virtiofs_shares.append({
            'tag': 'vm',
            'host_path': str(vm_runtime_dir),
            'guest_mount': f'{base_mount}\\vm' if is_windows else f'{base_mount}/vm',
            'readonly': True  # VM runtime shouldn't be modified by guest
        })

        # 3. Experiment directory (optional)
        if context.experiment_directory:
            experiment_dir = context.experiment_directory.path
            virtiofs_shares.append({
                'tag': 'experiment',
                'host_path': str(experiment_dir),
                'guest_mount': f'{base_mount}\\experiment' if is_windows else f'{base_mount}/experiment',
                'readonly': True
            })

        # 4. Project shared directory (optional)
        if context.project_directory.shared.exists():
            virtiofs_shares.append({
                'tag': 'project_shared',
                'host_path': str(context.project_directory.shared),
                'guest_mount': f'{base_mount}\\project_shared' if is_windows else f'{base_mount}/project_shared',
                'readonly': True
            })

        # 5. Experiment shared directory (optional)
        if context.experiment_directory and context.experiment_directory.shared.exists():
            virtiofs_shares.append({
                'tag': 'shared',
                'host_path': str(context.experiment_directory.shared),
                'guest_mount': f'{base_mount}\\shared' if is_windows else f'{base_mount}/shared',
                'readonly': True
            })
    
        # 6. User-defined shared directories
        if hasattr(context.config, 'shared_directories') and context.config.shared_directories:
            log.info(f"Configuring {len(context.config.shared_directories)} user-defined shared directories")
            for name, details in context.config.shared_directories.items():
                host_path = details.get('host')
                vm_path = details.get('vm')
                
                if host_path and vm_path:
                    # Treat vm_path as the absolute mount point in the guest
                    share = {
                        'tag': name,
                        'host_path': str(host_path),
                        'guest_mount': str(vm_path),
                        'readonly': False
                    }
                    virtiofs_shares.append(share)

        # Write config.json to run directory with new paths
        config_data = self._build_config_json(
            is_windows=is_windows,
            installation_mode=context.config.installation_mode
        )
        with open(run_dir / 'config.json', 'w') as f:
            json.dump(config_data, f, indent=2)
        log.debug(f"Wrote config.json to {run_dir / 'config.json'}")

        # Store shares in VM config for libvirt XML generation
        context.vm.config.virtiofs_enabled = True
        context.vm.config.virtiofs_shares = virtiofs_shares
        context.vm._save_vm_config()

        # Store in context for later use (mounting, artifact retrieval)
        context.virtiofs_shares = virtiofs_shares

        log.info(f"Configured {len(virtiofs_shares)} virtio-fs shares:")
        for share in virtiofs_shares:
            log.debug(f"  {share['tag']}: {share['host_path']} -> {share['guest_mount']}")

    def _build_config_json(self, is_windows: bool, installation_mode: str = "wheel") -> Dict[str, Any]:
        """Build config.json content for adarevm with new mount paths.

        Args:
            is_windows: True if guest is Windows
            installation_mode: "wheel" (pip) or "editable" (Poetry)

        Returns:
            Dictionary with config.json contents
        """
        if is_windows:
            return {
                "tools_paths": ["C:\\adare\\project_shared\\tools", "C:\\adare\\shared\\tools"],
                "data_paths": ["C:\\adare\\project_shared\\data", "C:\\adare\\shared\\data"],
                "logfile": "C:\\adare\\run\\logs\\adarevm.log",
                "installation_mode": installation_mode
            }
        else:
            return {
                "tools_paths": ["/adare/project_shared/tools", "/adare/shared/tools"],
                "data_paths": ["/adare/project_shared/data", "/adare/shared/data"],
                "logfile": "/adare/run/logs/adarevm.log",
                "installation_mode": installation_mode
            }

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
        from adare.types.stages import VMStartStage, VMGuestAgentWaitStage
        from adare.backend.experiment.stagectxmanager import StageCtxManager

        # Stage 1: Start VM
        with StageCtxManager(
            VMStartStage(),
            context.experiment_run_ulid,
            context.user_interrupt_event
        ) as start_stage:
            # Start the VM (via libvirt) with stage context for progress updates
            log.debug(f"CLAUDE: Starting VM '{context.vm.vm_name}' via libvirt")
            await context.vm.start(stop_event=context.user_interrupt_event, stage_ctx=start_stage)
            log.debug(f"CLAUDE: VM visible in virt-manager (use 'Open' button to access display)")

        # Stage 2: Wait for guest agent
        with StageCtxManager(
            VMGuestAgentWaitStage(),
            context.experiment_run_ulid,
            context.user_interrupt_event
        ):
            # Wait until VM is fully booted and guest agent is ready
            # Determine if we should skip X11 discovery based on GUI execution mode
            from adare.backend.experiment.execution.gui_executor_factory import resolve_gui_execution_mode
            from adare.backend.experiment.execution.base import GUIExecutionMode
            playbook_settings = context.playbook.settings if context.playbook and hasattr(context.playbook, 'settings') else None
            gui_mode = resolve_gui_execution_mode(context.vm, playbook_settings)
            skip_x11 = (gui_mode == GUIExecutionMode.HOST)

            # Guest agent check is ALWAYS required (even in test mode)
            # because we need the agent to install adarevm and execute commands
            log.info('Waiting until VM is ready (QEMU Guest Agent)')
            start_wait = time.time()
            if not await context.vm.wait_until_fully_booted(timeout=360, stop_event=context.user_interrupt_event, skip_x11_discovery=skip_x11):
                raise LoggedException(log, 'VM did not become ready in time')
            elapsed = time.time() - start_wait
            log.info(f'VM is ready (waited {elapsed:.1f}s)')

        # Stage 3: Mount virtio-fs shared directories (if using virtio-fs mode)
        if _use_shared_folder_mode():
            from adare.types.stages import VMMountVirtioFSStage

            is_windows = 'windows' in context.guest_platform.lower()

            with StageCtxManager(
                VMMountVirtioFSStage(),
                context.experiment_run_ulid,
                context.user_interrupt_event
            ):
                if is_windows:
                    # Windows: Use virtiofs.exe to mount each share to C:\adare\{name}
                    log.info("Mounting virtio-fs shares on Windows guest using virtiofs.exe")
                    await self._mount_virtiofs_windows(context)
                else:
                    # Linux: Mount each virtiofs share to /adare/{name}
                    await self._mount_virtiofs_linux(context)

    async def _mount_virtiofs_linux(self, context):
        """
        Mount multiple virtio-fs filesystems on Linux guest.

        Mounts each configured virtiofs share to its designated mount point.

        Args:
            context: ExperimentRunCtx containing VM
        """
        shares = getattr(context, 'virtiofs_shares', None) or context.vm.config.virtiofs_shares

        if not shares:
            log.warning("No virtiofs shares configured, skipping mount")
            return

        log.info(f"Mounting {len(shares)} virtio-fs filesystems on Linux guest")

        # Create parent directory
        await context.vm.run_command(
            'sudo mkdir -p /adare && sudo chmod 755 /adare',
            stop_event=context.user_interrupt_event
        )

        # Mount each share
        for share in shares:
            tag = share['tag']
            mount_point = share['guest_mount']

            mount_cmd = (
                f'sudo mkdir -p {mount_point} && '
                f'sudo mount -t virtiofs {tag} {mount_point} && '
                f'sudo chmod 777 {mount_point}'
            )

            result = await context.vm.run_command(
                mount_cmd,
                stop_event=context.user_interrupt_event
            )

            if result.returncode != 0:
                log.warning(f"Failed to mount virtiofs '{tag}': {result.stderr}")
            else:
                log.debug(f"Mounted virtiofs '{tag}' to {mount_point}")

        # Verify mounts
        verify_result = await context.vm.run_command(
            'mount | grep virtiofs',
            stop_event=context.user_interrupt_event
        )

        mounted_count = verify_result.stdout.count('virtiofs')
        if mounted_count >= len(shares):
            log.info(f"All {len(shares)} virtio-fs shares mounted successfully")
        else:
            log.warning(f"Only {mounted_count} of {len(shares)} virtio-fs shares mounted")

    async def _mount_virtiofs_windows(self, context):
        """
        Mount multiple virtio-fs shares on Windows guest using virtiofs.exe.

        Unlike Linux which uses the kernel's virtiofs driver, Windows requires
        running virtiofs.exe from WinFsp for each share. The viofs service
        auto-mounts to a single drive (Z:), but we need specific directories.

        Uses Windows Scheduled Tasks to escape Session 0 isolation. The QEMU Guest
        Agent runs as SYSTEM in Session 0, so processes launched directly cannot
        access the user's interactive session. We use schtasks with explicit user
        credentials to run virtiofs.exe in the user's session.

        Approach:
        1. Stop viofs service (if running) to prevent Z: auto-mount
        2. For each share, create a scheduled task that runs virtiofs.exe as the user
        3. Run and cleanup the scheduled task immediately

        Args:
            context: ExperimentRunCtx containing VM
        """
        shares = getattr(context, 'virtiofs_shares', None) or context.vm.config.virtiofs_shares

        if not shares:
            log.warning("No virtiofs shares configured, skipping Windows mount")
            return
            
        # Create base directory
        await context.vm.run_command(
            'New-Item -ItemType Directory -Path "C:\\adare" -Force | Out-Null',
            stop_event=context.user_interrupt_event
        )

        for share in shares:
            tag = share['tag']
            mount_point = str(share['guest_mount']).replace('/', '\\')
            task_name = f"mount_{tag}"

            # NOTE: Do NOT pre-create the mount point directory - virtiofs.exe creates it automatically
            # Pre-creating causes the mount to fail
            virtiofs_exe = r"C:\Program Files\VirtIO-Win\VioFS\virtiofs.exe"
            mount_cmd = f'"{virtiofs_exe}" -t {tag} -m {mount_point}'

            log.debug(f"Mounting virtio-fs share '{tag}' using run_as_user strategy")

            result = await context.vm.run_command(
                mount_cmd,
                background=True,
                stop_event=context.user_interrupt_event,
                binary_is_filepath=True
            )

            if result.returncode != 0:
                raise HypervisorException(f"Failed to mount virtio-fs share '{tag}': {result.stderr}")
            log.debug(f"Mounted virtio-fs share '{tag}' -> {mount_point}")


    async def retrieve_artifacts(self, context, post_interrupt: bool = False):
        """
        Retrieve artifacts and logs from the VM.

        For virtio-fs mode (default):
            Artifacts are already on the host in the shared directory.
            Just copy them to the final destination.

        For libguestfs mode (fallback):
            Stop VM and use libguestfs to retrieve artifacts from disk.

        Args:
            context: ExperimentRunCtx
            post_interrupt: If True, we're in post-interrupt cleanup
        """
        # Early return if VM not initialized (experiment failed before VM creation)
        if not context.vm or not hasattr(context.vm, 'config'):
            log.info(
                "VM not initialized - skipping artifact retrieval. "
                "This is normal if experiment failed before VM was created."
            )
            return

        if _use_shared_folder_mode():
            log.info("Retrieving artifacts from virtio-fs shared directory")
            await self._retrieve_artifacts_from_virtiofs(context)
            # Still need to stop VM after retrieval
            log.info("Stopping VM after artifact retrieval")
            await context.vm.stop()
            return

        # libguestfs mode: Stop VM first (required for libguestfs)
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
            },
            {
                'guest_path': '/adare/run/logs/scheduled_task_error.log',
                'host_path': context.experiment_run_directory.log_directory / 'scheduled_task_error.log',
                'type': 'file',
                'optional': True,  # Only exists if scheduled task failed
                'name': 'scheduled_task_error.log'
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

    async def _retrieve_artifacts_from_virtiofs(self, context):
        """
        Verify artifacts are accessible from virtio-fs shared directories.

        With multi-share virtio-fs, the 'run' share points directly to
        context.experiment_run_directory.path, so artifacts are already
        in the correct location. This method just verifies and logs what was found.

        Args:
            context: ExperimentRunCtx
        """
        # With multi-share setup, 'run' share = experiment_run_directory
        # Artifacts are already in the right place, no copying needed
        run_dir = context.experiment_run_directory.path

        retrieved = []
        missing = []

        # Check artifacts directory
        artifacts_dir = run_dir / 'artifacts'
        if artifacts_dir.exists() and any(artifacts_dir.iterdir()):
            artifact_count = len(list(artifacts_dir.iterdir()))
            retrieved.append(f'artifacts ({artifact_count} items)')
            log.debug(f"Found artifacts at {artifacts_dir}")
        else:
            missing.append('artifacts')

        # Check log files
        logs_dir = run_dir / 'logs'
        log_files = ['adarevm.log', 'adarevmstartup.log', 'scheduled_task_error.log']

        for log_file in log_files:
            log_path = logs_dir / log_file
            if log_path.exists():
                # Copy to log_directory if different from logs subdirectory
                log_dest = context.experiment_run_directory.log_directory
                if log_dest != logs_dir:
                    shutil.copy2(log_path, log_dest / log_file)
                    log.debug(f"Copied {log_file} to {log_dest}")
                retrieved.append(log_file)
            else:
                missing.append(log_file)

        # Log results summary
        if retrieved:
            log.info(f"Found in virtio-fs run share: {', '.join(retrieved)}")
        if missing:
            log.debug(f"Not found in virtio-fs run share (skipped): {', '.join(missing)}")

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

    def compare_disk_images_with_virt_diff(
        self,
        base_disk_path: str,
        overlay_disk_path: str,
        all: bool = False,
        extract_dir: Optional[Path] = None
    ) -> Optional[Dict[str, List[Dict]]]:
        """Compare base and overlay disks using manual virt-ls diff.
        
        Args:
            base_disk_path: Path to immutable base disk (pristine state)
            overlay_disk_path: Path to overlay disk (modified state)
            all: Unused (kept for compatibility)
            extract_dir: Optional path to directory where changed files content should be extracted
            
        Returns:
            Diff dict: {added: [...], removed: [...], modified: [...]}
            None on failure
        """
        try:
            log.info(f"CLAUDE: Comparing base disk vs overlay using manual virt-ls diff")
            log.debug(f"CLAUDE: Base: {base_disk_path}")
            log.debug(f"CLAUDE: Overlay: {overlay_disk_path}")

            # Direct fallback to manual diff to avoid 'no operating system found' errors
            # virt-diff's auto-detection is unreliable for some disk images
            return self._compare_disks_manual(base_disk_path, overlay_disk_path, extract_dir)

        except Exception as e:
            log.error(f"CLAUDE: Error running diff: {e}", exc_info=True)
            return None

    def _compare_disks_manual(
        self,
        base_disk_path: str,
        overlay_disk_path: str,
        extract_dir: Optional[Path] = None
    ) -> Optional[Dict[str, List[Dict]]]:
        """
        Manually compare disks using optimized guestfish single-boot scan.
        """
        try:
            log.info("CLAUDE: Starting manual disk comparison using optimized guestfish scan")
            
            # Detect root partition on the overlay
            # We assume the layout is identical on base.
            # root_device will be something like '/dev/sda4' (as seen by inspection of that single disk)
            root_device, _ = self._detect_root_filesystem(overlay_disk_path)
            log.debug(f"CLAUDE: Detected root partition: {root_device}")
            
            # Parse partition number to map to sda/sdb in the combined session
            # We assume simple partitioning (sdaX). If LVM, this optimization might fail
            # effectively but valid for the Windows usecase seen.
            import re
            part_match = re.search(r'(\d+)$', root_device)
            if not part_match:
                log.warning(f"CLAUDE: Could not extract partition number from {root_device}. Assuming LVM or complex layout - optimization logic might require adjustment.")
                # Fallback or risk it? We'll try to map exact string if no number, 
                # but valid /dev/sda4 -> 4.
                part_suffix = ""
            else:
                part_suffix = part_match.group(1)
            
            # Scan both disks in one go
            base_files, overlay_files = self._scan_disks_via_guestfish(
                base_disk_path, 
                overlay_disk_path, 
                part_suffix
            )
            
            if base_files is None or overlay_files is None:
                log.error("CLAUDE: Failed to scan disks")
                return None
                
            # Compute diff
            diff = {
                'added': [],
                'removed': [],
                'modified': []
            }
            
            # Check for additions and modifications
            for path, meta in overlay_files.items():
                if path not in base_files:
                    # Added
                    diff['added'].append({
                        'path': path,
                        'size': meta['size'],
                        'mtime': meta['mtime'],
                        'mtime_readable': meta['mtime_readable']
                    })
                else:
                    # Check if modified
                    base_meta = base_files[path]
                    if meta['size'] != base_meta['size'] or meta['mtime'] != base_meta['mtime']:
                        diff['modified'].append({
                            'path': path,
                            'size_before': base_meta['size'],
                            'size_after': meta['size'],
                            'mtime_before': base_meta['mtime'],
                            'mtime_after': meta['mtime'],
                            'mtime_before_readable': base_meta['mtime_readable'],
                            'mtime_after_readable': meta['mtime_readable']
                        })
            
            # Check for removals
            for path, meta in base_files.items():
                if path not in overlay_files:
                    diff['removed'].append({
                        'path': path,
                        'size': meta['size'],
                        'mtime': meta['mtime'],
                        'mtime_readable': meta['mtime_readable']
                    })
            
            log.info(
                f"CLAUDE: Manual Diff complete: {len(diff['added'])} added, "
                f"{len(diff['removed'])} removed, "
                f"{len(diff['modified'])} modified"
            )

            # Extract file content if requested
            # Note: This will start a NEW guestfish session (2nd boot), which is acceptable for stability.
            if extract_dir:
                # We need the full device path for extraction mounts.
                # _extract_diff_files uses single-disk sessions so /dev/sdaX is always correct 
                # relative to THAT session.
                # root_device comes from _detect_root_filesystem which inspected a single disk.
                # So passing root_device (e.g. /dev/sda4) is correct for _extract_diff_files 
                # because it processes one disk at a time (or mounts one at a time).
                self._extract_diff_files(base_disk_path, overlay_disk_path, root_device, diff, extract_dir)
            
            return diff
            
        except Exception as e:
            log.error(f"CLAUDE: Error during manual disk comparison: {e}", exc_info=True)
            return None

    
    def _extract_diff_files(
        self,
        base_disk_path: str,
        overlay_disk_path: str,
        partition: str,
        diff_results: Dict[str, List[Dict]],
        extract_dir: Path
    ) -> None:
        """
        Extract content of changed files from disks using batched guestfish commands.
        """
        log.info(f"CLAUDE: Extracting diff content to {extract_dir}")
        extract_dir.mkdir(parents=True, exist_ok=True)
        
        # Create structure
        added_dir = extract_dir / 'added'
        removed_dir = extract_dir / 'removed'
        mod_base_dir = extract_dir / 'modified' / 'base'
        mod_overlay_dir = extract_dir / 'modified' / 'overlay'
        
        for d in [added_dir, removed_dir, mod_base_dir, mod_overlay_dir]:
            d.mkdir(parents=True, exist_ok=True)
            
        # Prepare batch specs: (disk_path, guest_path, host_path)
        specs = []
        
        # 1. Added files -> from Overlay
        for item in diff_results['added']:
            guest_path = item['path']
            # Remove leading slash for safe join, but keep structure
            rel_path = guest_path.lstrip('/')
            host_path = added_dir / rel_path
            specs.append(('overlay', guest_path, host_path))
            
        # 2. Removed files -> from Base
        for item in diff_results['removed']:
            guest_path = item['path']
            rel_path = guest_path.lstrip('/')
            host_path = removed_dir / rel_path
            specs.append(('base', guest_path, host_path))
            
        # 3. Modified files -> from Both
        for item in diff_results['modified']:
            guest_path = item['path']
            rel_path = guest_path.lstrip('/')
            specs.append(('base', guest_path, mod_base_dir / rel_path))
            specs.append(('overlay', guest_path, mod_overlay_dir / rel_path))

        if not specs:
            log.info("No files to extract.")
            return

        # Group by disk source to minimize guestfish invocations
        base_specs = [s for s in specs if s[0] == 'base']
        overlay_specs = [s for s in specs if s[0] == 'overlay']
        
        for name, disk_path, current_specs in [('Base', base_disk_path, base_specs), ('Overlay', overlay_disk_path, overlay_specs)]:
            if not current_specs:
                continue
                
            log.info(f"CLAUDE: Extracting {len(current_specs)} files from {name} disk")
            
            # Create parent directories for all targets
            for _, _, target_path in current_specs:
                target_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Build guestfish script
            script_lines = [
                'run',
                f'mount {partition} /'
            ]
            
            for _, guest_path, host_path in current_specs:
                # Use download command
                script_lines.append(f"download {guest_path} {host_path}")
                
            # Execute batch
            self._run_guestfish_script(disk_path, script_lines)

    def _run_guestfish_script(self, disk_path: str, commands: List[str]) -> bool:
        """Helper to run a raw guestfish script string."""
        script_content = '\n'.join(commands)
        
        script_fd = None
        script_path = None
        try:
            script_fd, script_path = tempfile.mkstemp(suffix='.guestfish', text=True)
            with os.fdopen(script_fd, 'w') as f:
                f.write(script_content)
                script_fd = None
            
            cmd = ['guestfish', '--ro', '--format=qcow2', '-a', disk_path, '-f', script_path]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False
            )
            
            if result.returncode != 0:
                log.warning(f"CLAUDE: Guestfish extraction script had errors (partial success possible): {result.stderr}")
                return False
                
            return True
            
        except Exception as e:
            log.error(f"CLAUDE: Failed to run guestfish script: {e}")
            return False
            
        finally:
            if script_fd is not None:
                try:
                    os.close(script_fd)
                except: pass
            if script_path and Path(script_path).exists():
                try:
                    Path(script_path).unlink()
                except: pass

    def _scan_disks_via_guestfish(
        self, 
        base_disk: str, 
        overlay_disk: str, 
        part_suffix: str
    ) -> Tuple[Optional[Dict], Optional[Dict]]:
        """
        Scan both disks using separate virt-ls calls.
        Returns (base_files, overlay_files).
        """
        
        def scan_single_disk(disk_path: str) -> Optional[Dict]:
            # virt-ls -a disk.img -m /dev/sda{suffix} --csv --time-t -l -R /
            # Note: We always use /dev/sda because we are mounting a single disk image
            mount_dev = f"/dev/sda{part_suffix}"
            
            cmd = [
                'virt-ls',
                '-a', disk_path,
                '-m', mount_dev,
                '--csv',
                '--time-t',
                '-l',
                '-R',
                '/'
            ]
            
            try:
                log.debug(f"CLAUDE: Running virt-ls on {disk_path} (mount: {mount_dev})")
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    check=False
                )
                
                if result.returncode != 0:
                    log.error(f"CLAUDE: virt-ls failed for {disk_path}: {result.stderr}")
                    return None
                    
                files = {}
                import csv
                from io import StringIO
                
                # virt-ls output has no header
                # Columns: type, perms, size, atime, mtime, ctime, path
                
                reader = csv.reader(StringIO(result.stdout))
                for row in reader:
                    if not row or len(row) < 7:
                        continue
                        
                    ftype = row[0]
                    # perms = row[1]
                    size = int(row[2])
                    # atime = float(row[3])
                    mtime = int(row[4])
                    # ctime = float(row[5])
                    path = row[6]
                    
                    # virt-ls quote handling? csv module should handle it
                    
                    from datetime import datetime
                    files[path] = {
                        'size': size,
                        'mtime': mtime,
                        'mtime_readable': datetime.fromtimestamp(mtime).isoformat()
                    }
                    
                return files
                
            except Exception as e:
                log.error(f"CLAUDE: Error during virt-ls scan of {disk_path}: {e}")
                return None

        # Scan Base
        log.info("CLAUDE: Scanning base disk with virt-ls...")
        base_files = scan_single_disk(base_disk)
        
        # Scan Overlay
        log.info("CLAUDE: Scanning overlay disk with virt-ls...")
        overlay_files = scan_single_disk(overlay_disk)
        
        if base_files is None or overlay_files is None:
            return None, None
            
        log.info(f"CLAUDE: Scanned {len(base_files)} base files, {len(overlay_files)} overlay files")
        return base_files, overlay_files

    def _add_scanned_file(self, file_map: Dict, file_data: Dict):
        """Helper to process and add a file record from filesystem_walk."""
        # Handle both standard and TSK-style output
        path = file_data.get('path') or file_data.get('tsk_name')
        if not path:
            return
            
        # Clean path formatting
        path = path.strip().replace('"', '')
            
        # Skip directories if desired, similar to virt-ls -lR behavior which lists everything
        # virt-diff often ignores directories for content diff, but keeps them for structure.
        # We'll include them.
        
        # Parse fields
        try:
            # Handle size
            if 'size' in file_data:
                size = int(file_data['size'])
            elif 'tsk_size' in file_data:
                size = int(file_data['tsk_size'])
            else:
                size = 0

            # Handle mtime (seconds since epoch)
            if 'mtime' in file_data:
                mtime = int(file_data['mtime'])
            elif 'tsk_mtime_sec' in file_data:
                mtime = int(file_data['tsk_mtime_sec'])
            else:
                mtime = 0
            
            from datetime import datetime
            file_map[path] = {
                'size': size,
                'mtime': mtime,
                'mtime_readable': datetime.fromtimestamp(mtime).isoformat()
            }
        except ValueError:
            pass  # Skip malformed records

    def _parse_virt_diff_output(self, csv_output: str) -> Dict[str, List[Dict]]:
        """Parse virt-diff CSV output into standard diff format.

        virt-diff CSV columns: Change,Path,Old Size,New Size,Old Time,New Time
        Change types: added, removed, changed

        Args:
            csv_output: CSV output from virt-diff

        Returns:
            Dict with keys: added, removed, modified (each containing list of file dicts)
        """
        import csv
        from io import StringIO

        diff = {
            'added': [],
            'removed': [],
            'modified': []
        }

        try:
            reader = csv.DictReader(StringIO(csv_output))

            for row in reader:
                change_type = row.get('Change', '').strip()
                path = row.get('Path', '').strip()

                if change_type == 'added':
                    diff['added'].append({
                        'path': path,
                        'size': int(row.get('New Size', 0) or 0),
                        'mtime': self._parse_virt_diff_time(row.get('New Time', '')),
                        'mtime_readable': row.get('New Time', '')
                    })

                elif change_type == 'removed':
                    diff['removed'].append({
                        'path': path,
                        'size': int(row.get('Old Size', 0) or 0),
                        'mtime': self._parse_virt_diff_time(row.get('Old Time', '')),
                        'mtime_readable': row.get('Old Time', '')
                    })

                elif change_type == 'changed':
                    diff['modified'].append({
                        'path': path,
                        'size_before': int(row.get('Old Size', 0) or 0),
                        'size_after': int(row.get('New Size', 0) or 0),
                        'mtime_before': self._parse_virt_diff_time(row.get('Old Time', '')),
                        'mtime_after': self._parse_virt_diff_time(row.get('New Time', '')),
                        'mtime_before_readable': row.get('Old Time', ''),
                        'mtime_after_readable': row.get('New Time', '')
                    })

            return diff

        except Exception as e:
            log.error(f"CLAUDE: Error parsing virt-diff output: {e}", exc_info=True)
            return diff  # Return partial results

    def _parse_virt_diff_time(self, time_str: str) -> float:
        """Parse virt-diff timestamp to Unix epoch.

        virt-diff may output various formats - handle common ones.
        """
        if not time_str:
            return 0.0

        try:
            # Try parsing ISO format or common timestamp formats
            # virt-diff typically outputs: "2024-01-15 10:30:45"
            from datetime import datetime
            dt = datetime.strptime(time_str.split('.')[0], '%Y-%m-%d %H:%M:%S')
            return dt.timestamp()
        except (ValueError, AttributeError):
            try:
                # Try Unix timestamp
                return float(time_str)
            except (ValueError, TypeError):
                log.debug(f"CLAUDE: Could not parse timestamp: {time_str}")
                return 0.0
