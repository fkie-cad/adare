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
from adare.hypervisor.qemu.file_transfer.virtiofs_strategy import VirtioFSStrategy
from adare.hypervisor.qemu.file_transfer.libguestfs_strategy import LibguestfsStrategy
from adare.hypervisor.qemu.file_transfer.qga_strategy import QGAStrategy

log = logging.getLogger(__name__)

__all__ = [
    'FileTransferStrategy',
    'VirtioFSStrategy',
    'LibguestfsStrategy',
    'QGAStrategy',
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


def detect_file_transfer_mode() -> str:
    """Determine file transfer mode: 'virtiofs', 'libguestfs', or 'qga'.

    Decision logic:
    1. QEMU_LIBGUESTFS env var forces 'libguestfs' mode
    2. virtiofsd available -> 'virtiofs'
    3. macOS without virtiofsd:
       - guestfish available AND appliance works -> 'libguestfs'
       - otherwise -> 'qga'
    4. Linux without virtiofsd -> 'libguestfs'

    Returns:
        One of 'virtiofs', 'libguestfs', 'qga'
    """
    # Explicit libguestfs override via environment variable
    if os.environ.get('QEMU_LIBGUESTFS', '').lower() in ('true', '1', 'yes'):
        return 'libguestfs'

    if shutil.which('virtiofsd'):
        return 'virtiofs'

    # No virtiofsd -- check fallbacks
    if platform.system() == 'Darwin':
        if _guestfish_appliance_available():
            log.warning(
                "virtiofsd not found on macOS -- falling back to "
                "libguestfs mode. To use virtio-fs, install virtiofsd "
                "(e.g. from source or a third-party tap)."
            )
            return 'libguestfs'
        log.info(
            "Using QGA file transfer mode on macOS. "
            "Files will be transferred via QEMU Guest Agent after VM boot."
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
    elif mode == 'qga':
        return QGAStrategy()
    else:
        return LibguestfsStrategy(guestfish_client)
