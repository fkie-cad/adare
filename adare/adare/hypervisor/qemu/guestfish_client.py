"""
Abstraction over the guestfish CLI for offline disk operations.

This module encapsulates all guestfish subprocess interactions, providing
a clean interface for:
- Running guestfish commands on disk images
- Detecting root filesystems
- Checking and removing NTFS hibernation
- Running guestfish scripts from temp files

Extracted from QEMULifecycleStrategy to separate concerns and enable testing.
"""

import contextlib
import logging
import os
import subprocess
import tempfile
from pathlib import Path

from adare.hypervisor.exceptions import HypervisorException
from adare.hypervisor.qemu.libvirt_stderr_redirect import (
    LibvirtStderrRedirect,
    get_experiment_log_file,
)

log = logging.getLogger(__name__)


class GuestfishClient:
    """Abstraction over the guestfish CLI for offline disk operations.

    All methods operate on stopped VM disk images using the guestfish
    command-line tool. The VM must not be running when these operations
    are performed.
    """

    def run_command(
        self,
        disk_path: str,
        commands: list[str],
        readonly: bool = False,
        auto_mount: bool = True,
    ) -> tuple[int, str, str]:
        """Execute guestfish commands on a disk image with manual mounting.

        Args:
            disk_path: Path to disk image
            commands: List of guestfish command parts (will be joined with ':')
            readonly: If True, mount disk read-only
            auto_mount: If True, automatically detect and mount root filesystem

        Returns:
            Tuple of (returncode, stdout, stderr)

        Raises:
            HypervisorException: If auto_mount is True and filesystem detection fails
        """
        mode_flag = '--ro' if readonly else '--rw'
        # Build base command without -i flag (no longer using auto-inspect)
        cmd = ['guestfish', mode_flag, '--format=qcow2', '-a', disk_path]

        # Add manual mount logic if requested
        if auto_mount:
            # Detect root filesystem
            root_device, fs_type = self.detect_root_filesystem(disk_path)
            log.debug(f"Mounting root filesystem: {root_device} ({fs_type})")

            # Check for NTFS hibernation if mounting read-write
            if not readonly:
                # Always run ntfsfix for NTFS filesystems in RW mode
                # This safely clears dirty bits and hibernation flags
                # that prevent RW mounting
                if fs_type == 'ntfs':
                    log.info(
                        f"Ensuring NTFS filesystem {root_device} is clean "
                        f"(running ntfsfix)..."
                    )
                    self.remove_ntfs_hibernation(disk_path, root_device)

            # Add run as first command (no leading colon), then mount
            cmd.extend(['run', ':', 'mount', root_device, '/'])

        # Add user commands
        if commands:
            cmd.extend([':'] + commands)

        # Enhanced logging for diagnostics
        log.debug(f"Running guestfish on disk: {disk_path}")
        log.debug(f"Guestfish command: {' '.join(cmd)}")

        # Redirect guestfish stderr to experiment log instead of console
        log_file = get_experiment_log_file()
        with LibvirtStderrRedirect(log_file=log_file, suppress_console=True):
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
            )

        # Always log results for diagnostics
        log.debug(f"Guestfish returncode: {result.returncode}")
        if result.stdout:
            log.debug(f"Guestfish stdout: '{result.stdout.strip()}'")
        if result.stderr:
            log.debug(f"Guestfish stderr: '{result.stderr.strip()}'")

        if result.returncode != 0:
            log.debug(f"Guestfish stderr: {result.stderr}")

        return result.returncode, result.stdout, result.stderr

    def detect_root_filesystem(self, disk_path: str) -> tuple[str, str]:
        """Detect root filesystem by finding largest OS partition.

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
        # NO leading colon before first command! Colon only separates commands.
        cmd = [
            'guestfish', '--ro', '--format=qcow2', '-a', disk_path,
            'run', ':', 'list-filesystems',
        ]

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
            # NO leading colon before first command
            size_cmd = [
                'guestfish', '--ro', '--format=qcow2', '-a', disk_path,
                'run', ':', 'blockdev-getsize64', device,
            ]

            size_result = subprocess.run(
                size_cmd, capture_output=True, text=True, check=False
            )
            if size_result.returncode == 0:
                try:
                    size = int(size_result.stdout.strip())
                    partition_sizes.append((device, fs_type, size))
                    if size > largest_size:
                        largest_size = size
                        largest_device = device
                        largest_fs_type = fs_type
                except ValueError:
                    log.warning(
                        f"Could not parse size for {device}: "
                        f"{size_result.stdout}"
                    )
            else:
                log.warning(
                    f"Size query failed for {device}: "
                    f"{size_result.stderr}"
                )

        # Log all detected partitions for debugging
        if partition_sizes:
            log.debug("Detected partitions with sizes:")
            for dev, fs, sz in sorted(
                partition_sizes, key=lambda x: x[2], reverse=True
            ):
                size_gb = sz / (1024 * 1024 * 1024)
                log.debug(f"  {dev}: {fs}, {size_gb:.2f} GB")

        if not largest_device:
            # Fallback to first filesystem if size detection fails
            log.warning(
                "Could not determine partition sizes, "
                "using first detected filesystem"
            )
            return os_filesystems[0]

        # Warn if selected partition is suspiciously small for an OS partition
        # Windows root should be at least 10 GB, Linux at least 5 GB
        min_size_gb = 10 if largest_fs_type == 'ntfs' else 5
        min_size_bytes = min_size_gb * 1024 * 1024 * 1024
        if largest_size < min_size_bytes:
            log.warning(
                f"Selected partition {largest_device} is only "
                f"{largest_size / (1024*1024*1024):.2f} GB. "
                f"This may be a recovery partition, not the main OS partition. "
                f"Expected at least {min_size_gb} GB for {largest_fs_type}."
            )

        log.debug(
            f"Selected root filesystem: {largest_device} "
            f"({largest_fs_type}, size: {largest_size} bytes)"
        )
        return largest_device, largest_fs_type

    def _parse_filesystems_output(self, stdout: str) -> list[tuple[str, str]]:
        """Parse guestfish list-filesystems output.

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

    def is_ntfs_hibernated(
        self, disk_path: str, device: str
    ) -> tuple[bool, str]:
        """Check if NTFS filesystem is in hibernation state.

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
        cmd = [
            'guestfish', '--ro', '--format=qcow2', '-a', disk_path,
            'run', ':', 'list-filesystems',
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)

        if result.returncode != 0:
            log.warning(
                f"Failed to detect filesystem type for {device}: "
                f"{result.stderr}"
            )
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
            log.debug(
                f"Device {device} is {fs_type}, "
                f"skipping hibernation check"
            )
            return False, fs_type

        # Try to mount NTFS filesystem read-only to check for hibernation
        log.debug(
            f"Checking NTFS hibernation state for {device}"
        )

        # Use guestfish to check if filesystem can be mounted
        test_cmd = [
            'guestfish', '--ro', '--format=qcow2', '-a', disk_path,
            'run', ':', 'mount-ro', device, '/',
            ':', 'is-file', '/hiberfil.sys',
        ]

        test_result = subprocess.run(
            test_cmd, capture_output=True, text=True, check=False
        )

        # Check stderr for hibernation-related messages and
        # hiberfil.sys existence
        is_hibernated = self._check_ntfs_hibernation_output(
            test_result.stdout, test_result.stderr
        )

        if is_hibernated:
            log.debug(f"NTFS hibernation detected on {device}")
            return True, fs_type

        return False, fs_type

    def _check_ntfs_hibernation_output(
        self, stdout: str, stderr: str
    ) -> bool:
        """Analyze guestfish output to detect NTFS hibernation.

        Args:
            stdout: Output from guestfish command
            stderr: Error output from guestfish command

        Returns:
            True if hibernation detected
        """
        stderr_lower = stderr.lower()
        if (
            'hibernat' in stderr_lower
            or 'hiberfile' in stderr_lower
            or 'unsafe' in stderr_lower
        ):
            return True

        return 'true' in stdout.lower()

    def remove_ntfs_hibernation(
        self, disk_path: str, device: str
    ) -> None:
        """Remove NTFS hibernation metadata to enable read-write mounting.

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
            f"This is safe for overlay disks and required for "
            f"read-write access."
        )

        # Run ntfsfix to clear hibernation metadata
        # The -d flag removes the dirty bit and hibernation file
        # Use 'debug sh' to invoke ntfsfix binary directly
        cmd = [
            'guestfish', '--rw', '--format=qcow2', '-a', disk_path, '--',
            'run', ':', 'debug', 'sh', f'ntfsfix -d {device}',
        ]

        log.debug(f"Running ntfsfix command: {' '.join(cmd)}")

        result = subprocess.run(
            cmd, capture_output=True, text=True, check=False
        )

        if result.returncode != 0:
            # Check if ntfsfix command is not available
            if (
                'unknown command' in result.stderr.lower()
                or 'ntfsfix' in result.stderr.lower()
            ):
                raise HypervisorException(
                    f"Failed to remove NTFS hibernation: ntfsfix utility "
                    f"not available.\n"
                    f"Error: {result.stderr}\n\n"
                    f"To fix this issue:\n"
                    f"  1. Install ntfs-3g package: "
                    f"sudo apt-get install ntfs-3g (Debian/Ubuntu)\n"
                    f"  2. Ensure libguestfs has ntfs support: "
                    f"sudo apt-get install libguestfs-tools\n"
                    f"  3. Alternatively, disable Windows Fast Startup:\n"
                    f"     - Boot Windows VM\n"
                    f"     - Run: powercfg /h off\n"
                    f"     - Shutdown cleanly\n"
                    f"     - Re-run experiment"
                )
            raise HypervisorException(
                f"Failed to remove NTFS hibernation metadata.\n"
                f"Error: {result.stderr}\n"
                f"Device: {device}\n"
                f"Disk: {disk_path}\n\n"
                f"Troubleshooting:\n"
                f"  1. Ensure VM was shut down cleanly "
                f"(not forced off)\n"
                f"  2. Disable Windows Fast Startup in the VM\n"
                f"  3. Check disk integrity: "
                f"qemu-img check {disk_path}\n"
                f"  4. Try manual ntfsfix: guestfish --rw "
                f"-a {disk_path} : run : ntfsfix {device}"
            )

        log.info(
            f"Successfully removed NTFS hibernation metadata from {device}"
        )
        log.debug(f"ntfsfix output: {result.stdout}")

    def run_script(
        self, disk_path: str, commands: list[str]
    ) -> bool:
        """Run a guestfish script from a temp file.

        Creates a temporary file with the given commands, executes
        guestfish with the -f flag, and cleans up.

        Args:
            disk_path: Path to disk image
            commands: List of guestfish commands (one per line)

        Returns:
            True on success, False on failure
        """
        script_content = '\n'.join(commands)

        script_fd = None
        script_path = None
        try:
            script_fd, script_path = tempfile.mkstemp(
                suffix='.guestfish', text=True
            )
            with os.fdopen(script_fd, 'w') as f:
                f.write(script_content)
                script_fd = None

            cmd = [
                'guestfish', '--ro', '--format=qcow2',
                '-a', disk_path, '-f', script_path,
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode != 0:
                log.warning(
                    f"Guestfish extraction script had errors "
                    f"(partial success possible): {result.stderr}"
                )
                return False

            return True

        except OSError as e:
            log.error(f"Failed to run guestfish script: {e}")
            return False

        finally:
            if script_fd is not None:
                with contextlib.suppress(OSError):
                    os.close(script_fd)
            if script_path and Path(script_path).exists():
                with contextlib.suppress(OSError):
                    Path(script_path).unlink()
