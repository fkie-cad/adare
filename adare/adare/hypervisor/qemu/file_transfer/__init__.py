"""
File transfer strategy package for QEMU guests.

Provides a factory function that selects the appropriate file transfer
strategy based on available tools and platform:

- VirtioFS (default): high-performance shared directories
- Libguestfs (fallback): offline disk manipulation via guestfish
- QGA (macOS fallback): QEMU Guest Agent file operations
"""
import logging
import os
import platform
import shutil
import subprocess
from typing import Optional

from adare.hypervisor.qemu.file_transfer.base import FileTransferStrategy
from adare.hypervisor.qemu.file_transfer.libguestfs_strategy import LibguestfsStrategy
from adare.hypervisor.qemu.file_transfer.qga_strategy import QGAStrategy
from adare.hypervisor.qemu.file_transfer.smb_strategy import SMBStrategy
from adare.hypervisor.qemu.file_transfer.virtiofs_strategy import VirtioFSStrategy

log = logging.getLogger(__name__)

__all__ = [
    'FileTransferStrategy',
    'VirtioFSStrategy',
    'LibguestfsStrategy',
    'QGAStrategy',
    'SMBStrategy',
    'get_file_transfer_strategy',
    'detect_file_transfer_mode',
]


def _guestfish_appliance_available() -> bool:
    """Check that guestfish binary exists AND its appliance is functional.

    On macOS, guestfish may be installed but the libguestfs supermin
    appliance is often missing, causing runtime failures.
    """
    if not shutil.which('guestfish'):
        return False

    try:
        result = subprocess.run(
            ['guestfish', '--version'],
            capture_output=True, timeout=10,
        )
        if result.returncode != 0:
            log.warning(
                f"guestfish found but --version failed (rc={result.returncode}): "
                f"{result.stderr.decode(errors='replace').strip()}"
            )
            return False
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        log.warning(f"guestfish found but not usable: {e}")
        return False

    # Check that LIBGUESTFS_PATH or default appliance location exists
    appliance_path = os.environ.get('LIBGUESTFS_PATH', '')
    if appliance_path and os.path.isdir(appliance_path):
        return True

    # Check common appliance locations
    for candidate in [
        '/opt/local/lib/guestfs',
        '/usr/local/lib/guestfs',
        '/opt/homebrew/lib/guestfs',
        '/usr/lib/guestfs',
    ]:
        if os.path.isdir(candidate) and os.listdir(candidate):
            return True

    log.warning(
        "guestfish binary found but no libguestfs appliance detected. "
        "Set LIBGUESTFS_PATH or install the appliance. "
        "Falling back to QGA file transfer."
    )
    return False


def _get_qemu_expected_smbd_path() -> str | None:
    """Extract the smbd path that QEMU was compiled to use.

    QEMU hardcodes the smbd path at compile time (e.g. /opt/local/sbin/smbd
    for MacPorts builds). There is no runtime option to override it.

    Returns:
        The hardcoded smbd path, or None if it cannot be determined.
    """
    for arch in ('aarch64', 'x86_64'):
        qemu_bin = shutil.which(f'qemu-system-{arch}')
        if qemu_bin:
            break
    else:
        return None

    try:
        result = subprocess.run(
            ['strings', qemu_bin],
            capture_output=True, timeout=30,
        )
        if result.returncode != 0:
            return None
        for line in result.stdout.decode(errors='replace').splitlines():
            stripped = line.strip()
            if stripped.endswith('/smbd') and '/' in stripped:
                return stripped
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def _find_real_samba_smbd() -> str | None:
    """Locate the real Samba smbd binary (not Apple's built-in)."""
    candidates = [
        '/opt/homebrew/opt/samba/sbin/samba-dot-org-smbd',
        '/opt/homebrew/sbin/smbd',
        '/opt/local/sbin/smbd',
        '/usr/local/sbin/smbd',
    ]
    for path in candidates:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path

    # Try Homebrew's samba-dot-org-smbd via which
    found = shutil.which('samba-dot-org-smbd')
    if found:
        return found

    return None


def _smbd_available() -> bool:
    """Check if smbd is usable by QEMU for SLIRP SMB sharing.

    QEMU has the smbd path hardcoded at compile time. On macOS with Homebrew,
    this is typically /opt/local/sbin/smbd (a MacPorts path), but Homebrew
    installs samba elsewhere. A symlink is needed to bridge the gap.
    """
    if platform.system() != 'Darwin':
        return shutil.which('smbd') is not None

    expected_path = _get_qemu_expected_smbd_path()
    if expected_path and os.path.isfile(expected_path) and os.access(expected_path, os.X_OK):
        return True

    # QEMU's expected smbd path doesn't exist — find the real one and guide the user
    real_smbd = _find_real_samba_smbd()
    if expected_path and real_smbd:
        log.warning(
            f"QEMU expects smbd at '{expected_path}' (compiled-in path), "
            f"but it was found at '{real_smbd}'. "
            f"Create a symlink to fix this:\n"
            f"  sudo mkdir -p {os.path.dirname(expected_path)}\n"
            f"  sudo ln -s {real_smbd} {expected_path}\n"
            f"Falling back to QGA file transfer."
        )
    elif expected_path:
        log.warning(
            f"QEMU expects smbd at '{expected_path}', but no Samba smbd was found. "
            f"Install samba (brew install samba) and create a symlink:\n"
            f"  sudo mkdir -p {os.path.dirname(expected_path)}\n"
            f"  sudo ln -s /opt/homebrew/opt/samba/sbin/samba-dot-org-smbd {expected_path}\n"
            f"Falling back to QGA file transfer."
        )
    elif real_smbd:
        log.warning(
            f"Samba smbd found at '{real_smbd}' but could not determine QEMU's "
            f"expected smbd path. Try:\n"
            f"  sudo mkdir -p /opt/local/sbin\n"
            f"  sudo ln -s {real_smbd} /opt/local/sbin/smbd\n"
            f"Falling back to QGA file transfer."
        )
    else:
        log.info(
            "No Samba smbd found. Install samba for faster file transfer: "
            "brew install samba"
        )
    return False


def detect_file_transfer_mode() -> str:
    """Determine file transfer mode: 'virtiofs', 'smb', 'libguestfs', or 'qga'.

    Decision logic:
    1. QEMU_LIBGUESTFS env var forces 'libguestfs' mode
    2. virtiofsd available -> 'virtiofs'
    3. macOS without virtiofsd:
       - smbd available -> 'smb' (QEMU SLIRP SMB, mount-based)
       - guestfish available AND appliance works -> 'libguestfs'
       - otherwise -> 'qga'
    4. Linux without virtiofsd -> 'libguestfs'

    Returns:
        One of 'virtiofs', 'smb', 'libguestfs', 'qga'
    """
    # Explicit libguestfs override via environment variable
    if os.environ.get('QEMU_LIBGUESTFS', '').lower() in ('true', '1', 'yes'):
        return 'libguestfs'

    if shutil.which('virtiofsd'):
        return 'virtiofs'

    # No virtiofsd -- check fallbacks
    if platform.system() == 'Darwin':
        if _smbd_available():
            log.info(
                "Using SMB file transfer mode on macOS (QEMU SLIRP SMB). "
                "Host directories will be mounted in the guest via SMB."
            )
            return 'smb'
        if _guestfish_appliance_available():
            log.warning(
                "virtiofsd not found on macOS -- falling back to "
                "libguestfs mode. To use virtio-fs, install virtiofsd "
                "(e.g. from source or a third-party tap)."
            )
            return 'libguestfs'
        log.info(
            "Using QGA file transfer mode on macOS. "
            "Files will be transferred via QEMU Guest Agent after VM boot. "
            "For better performance, install samba: brew install samba"
        )
        return 'qga'

    # Linux without virtiofsd
    return 'libguestfs'


def get_file_transfer_strategy(
    guestfish_client=None,
) -> FileTransferStrategy:
    """Factory: select strategy based on available tools and platform.

    Args:
        guestfish_client: Optional GuestfishClient instance for libguestfs mode.
                          If None and libguestfs mode is selected, a new one is created.

    Returns:
        Appropriate FileTransferStrategy instance
    """
    mode = detect_file_transfer_mode()

    if mode == 'virtiofs':
        return VirtioFSStrategy()
    if mode == 'smb':
        return SMBStrategy()
    if mode == 'qga':
        return QGAStrategy()
    return LibguestfsStrategy(guestfish_client)
