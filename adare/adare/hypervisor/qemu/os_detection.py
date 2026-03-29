"""
OS detection utilities for QEMU VMs using guestfish inspection.

This module provides automatic OS platform detection from disk images,
enabling proper boot mode selection (UEFI for Windows, BIOS for Linux).
"""
import shutil
import subprocess
from pathlib import Path
import logging
from typing import Tuple, Dict, Optional

log = logging.getLogger(__name__)


def detect_os_from_disk(disk_path: Path) -> Tuple[str, Dict[str, Optional[str]]]:
    """
    Detect OS platform and details from disk image using guestfish.

    Uses libguestfs inspection API to determine the OS type and version
    information from a VM disk image. This is critical for Windows VMs
    which require UEFI boot mode.

    Args:
        disk_path: Path to the VM disk image (qcow2, vmdk, vdi, etc.)

    Returns:
        Tuple of (platform, details_dict) where:
        - platform: 'windows' or 'linux'
        - details_dict: {'distribution': ..., 'version': ..., 'architecture': ...}

    Raises:
        None - Returns safe defaults on failure

    Example:
        >>> platform, details = detect_os_from_disk(Path('/path/to/win11.qcow2'))
        >>> platform
        'windows'
        >>> details
        {'distribution': 'windows', 'version': '11', 'architecture': 'x86_64'}
    """
    try:
        log.info(f"Detecting OS from disk: {disk_path}")

        # Fallback to filename-based detection when guestfish is unavailable (e.g. macOS)
        if not shutil.which('guestfish'):
            log.warning("guestfish not available — using filename-based OS detection")
            filename_result = detect_os_from_filename(disk_path.name)
            if filename_result:
                return (filename_result, {'distribution': filename_result, 'version': None, 'architecture': 'x86_64'})
            return ('linux', {'distribution': None, 'version': None, 'architecture': 'x86_64'})

        # Run inspect-os to find OS root partition
        cmd = ['guestfish', '--ro', '-a', str(disk_path), 'run', ':', 'inspect-os']
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            check=False
        )

        if result.returncode != 0:
            log.warning(f"OS detection failed (guestfish returned {result.returncode})")
            log.debug(f"guestfish stderr: {result.stderr}")
            return 'linux', {}  # Safe default

        if not result.stdout.strip():
            log.warning(f"OS detection found no OS in {disk_path}")
            return 'linux', {}  # Safe default

        os_root = result.stdout.strip().split('\n')[0]
        log.debug(f"Found OS root partition: {os_root}")

        # Get OS type (windows, linux, etc.)
        cmd = ['guestfish', '--ro', '-a', str(disk_path), 'run', ':', 'inspect-get-type', os_root]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10, check=False)

        if result.returncode != 0:
            log.warning(f"Failed to get OS type")
            return 'linux', {}

        os_type = result.stdout.strip().lower()
        log.debug(f"Detected OS type: {os_type}")

        # Get distribution name
        distro = None
        try:
            cmd = ['guestfish', '--ro', '-a', str(disk_path), 'run', ':', 'inspect-get-distro', os_root]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10, check=False)
            if result.returncode == 0:
                distro = result.stdout.strip()
                log.debug(f"Detected distribution: {distro}")
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            log.debug(f"Could not get distribution: {e}")

        # Get version (major version number)
        version = None
        try:
            cmd = ['guestfish', '--ro', '-a', str(disk_path), 'run', ':', 'inspect-get-major-version', os_root]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10, check=False)
            if result.returncode == 0:
                version = result.stdout.strip()
                log.debug(f"Detected version: {version}")
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            log.debug(f"Could not get version: {e}")

        # Determine platform
        platform = 'windows' if 'windows' in os_type else 'linux'

        log.info(f"OS detection complete - platform={platform}, distro={distro}, version={version}")

        return platform, {
            'distribution': distro if distro else os_type,
            'version': version,
            'architecture': 'x86_64'  # Default, can be enhanced with inspect-get-arch
        }

    except subprocess.TimeoutExpired:
        log.warning(f"OS detection timed out for {disk_path}")
        return 'linux', {}
    except FileNotFoundError:
        log.warning("guestfish command not found. Install libguestfs-tools.")
        return 'linux', {}
    except (subprocess.SubprocessError, OSError, ValueError) as e:
        log.warning(f"OS detection error for {disk_path}: {e}")
        log.debug(f"OS detection exception details:", exc_info=True)
        return 'linux', {}


def detect_os_from_filename(filename: str) -> Optional[str]:
    """
    Attempt to infer OS platform from VM filename (fallback method).

    This is a heuristic-based approach and should only be used when
    disk inspection is unavailable or fails.

    Args:
        filename: VM filename (e.g., 'Win11-Pro.qcow2', 'ubuntu-22.04.vmdk')

    Returns:
        'windows', 'linux', or None if cannot determine

    Example:
        >>> detect_os_from_filename('Win11-Enterprise.qcow2')
        'windows'
        >>> detect_os_from_filename('debian-12-server.vmdk')
        'linux'
        >>> detect_os_from_filename('myvm.qcow2')
        None
    """
    filename_lower = filename.lower()

    # Windows indicators
    windows_keywords = ['windows', 'win11', 'win10', 'win7', 'win8', 'winxp', 'vista']
    if any(keyword in filename_lower for keyword in windows_keywords):
        log.debug(f"Inferred Windows from filename: {filename}")
        return 'windows'

    # Linux distribution indicators
    linux_distros = ['ubuntu', 'debian', 'fedora', 'centos', 'rhel', 'arch', 'suse', 'mint', 'kali']
    if any(distro in filename_lower for distro in linux_distros):
        log.debug(f"Inferred Linux from filename: {filename}")
        return 'linux'

    log.debug(f"Could not infer OS from filename: {filename}")
    return None
