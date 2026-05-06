"""Prerequisite checks for VM creation."""

import logging
import platform
import shutil
from pathlib import Path

from adare.hypervisor.exceptions import HypervisorException
from adare.hypervisor.qemu.vm_creator.os_catalog import OsDefinition

log = logging.getLogger(__name__)


class PrerequisiteError(HypervisorException):
    """Raised when a required prerequisite is missing."""

    def __init__(self, missing: list[str]):
        lines = '\n'.join(f'  - {m}' for m in missing)
        message = f"Missing prerequisites for VM creation:\n{lines}"
        super().__init__(message)


def check_prerequisites(
    os_def: OsDefinition,
    iso_path: Path | None = None,
    vm_dir: Path | None = None,
    disk_size: str | None = None,
) -> None:
    """Check that all required tools and resources are available.

    Args:
        os_def: OS definition for the VM to create
        iso_path: User-supplied ISO path (for Windows or manual installs)
        vm_dir: Target directory where the qcow2 will be written (overrides VMS_DIR)
        disk_size: User-requested disk size (overrides os_def.default_disk_size)

    Raises:
        PrerequisiteError: If any prerequisite is missing
    """
    missing: list[str] = []

    # Architecture vs host compatibility
    host_os = platform.system().lower()
    host_arch = platform.machine().lower()
    is_apple_silicon = host_os == 'darwin' and host_arch in ('arm64', 'aarch64')

    if is_apple_silicon and os_def.architecture == 'x86_64':
        missing.append(
            'Apple Silicon cannot hardware-accelerate x86_64 guests. '
            'Either use an aarch64 OS profile, or run on x86_64 hardware.'
        )
        raise PrerequisiteError(missing)

    # QEMU system executable for target architecture
    qemu_exe = f'qemu-system-{os_def.architecture}'
    if not shutil.which(qemu_exe):
        host = platform.system()
        if host == 'Darwin':
            hint = 'Install with: brew install qemu'
        elif host == 'Linux':
            hint = 'Install with: sudo apt install qemu-system-x86 (Debian/Ubuntu) or sudo dnf install qemu-system-x86-core (Fedora)'
        else:
            hint = 'Install QEMU for your platform'
        missing.append(f'{qemu_exe} not found. {hint}')

    # qemu-img
    if not shutil.which('qemu-img'):
        missing.append('qemu-img not found. It is usually included with QEMU.')

    # pycdlib (for Linux ISO kernel extraction — only needed for auto install)
    if os_def.platform == 'linux' and os_def.install_mode != 'manual':
        try:
            import pycdlib  # noqa: F401
        except ImportError:
            missing.append('pycdlib Python package not installed. Install with: uv pip install pycdlib')

    # Windows-specific checks
    if os_def.platform == 'windows':
        # User must supply ISO
        if iso_path is None:
            missing.append(
                f'Windows ISO required. Use --iso /path/to/{os_def.display_name}.iso'
            )
        elif not iso_path.is_file():
            missing.append(f'ISO file not found: {iso_path}')

        # OVMF firmware for UEFI boot
        if os_def.requires_uefi:
            try:
                from adare.hypervisor.qemu.firmware import find_ovmf_firmware
                find_ovmf_firmware(os_def.architecture)
            except HypervisorException:
                host = platform.system()
                if host == 'Darwin':
                    hint = 'Install with: brew install qemu (includes OVMF)'
                else:
                    hint = 'Install with: sudo apt install ovmf (Debian/Ubuntu) or sudo dnf install edk2-ovmf (Fedora)'
                missing.append(f'OVMF firmware required for UEFI boot. {hint}')

        # swtpm for TPM (optional - warn but don't block)
        if os_def.requires_tpm and not shutil.which('swtpm'):
            log.warning(
                'swtpm not found. Windows 11 TPM requirement will be bypassed '
                'via registry hack in Autounattend.xml. Install swtpm for proper TPM support.'
            )

    # Manual install mode checks
    if os_def.install_mode == 'manual':
        if iso_path is None:
            missing.append(
                f'ISO required for manual install. Use --iso /path/to/{os_def.display_name}.iso'
            )
        elif not iso_path.is_file():
            missing.append(f'ISO file not found: {iso_path}')

        if os_def.requires_uefi or os_def.architecture == 'aarch64':
            try:
                from adare.hypervisor.qemu.firmware import find_ovmf_firmware
                find_ovmf_firmware(os_def.architecture)
            except HypervisorException:
                host = platform.system()
                if host == 'Darwin':
                    hint = 'Install with: brew install qemu (includes OVMF)'
                else:
                    hint = 'Install with: sudo apt install ovmf (Debian/Ubuntu) or sudo dnf install edk2-ovmf (Fedora)'
                missing.append(f'OVMF firmware required for UEFI boot. {hint}')

    # Disk space check (rough estimate)
    _check_disk_space(os_def, missing, iso_path=iso_path, vm_dir=vm_dir, disk_size=disk_size)

    if missing:
        raise PrerequisiteError(missing)


def _existing_parent(path: Path) -> Path | None:
    """Walk up `path` until we find an existing directory (or None)."""
    current = path
    while True:
        if current.exists():
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent


def _parse_disk_size_gb(value: str) -> int:
    """Parse a disk size string like '60G' or '60g' into integer GB."""
    return int(value.rstrip('Gg'))


def _check_disk_space(
    os_def: OsDefinition,
    missing: list[str],
    iso_path: Path | None = None,
    vm_dir: Path | None = None,
    disk_size: str | None = None,
) -> None:
    """Check approximate free disk space for VM creation.

    Probes the actual filesystem the qcow2 will land on (vm_dir, falling back to
    VMS_DIR) using the user-requested disk size. Separately checks the ISO cache
    drive only when an ISO download is actually going to happen.
    """
    from adare.config.configdirectory import QEMU_CACHE_DIR, VMS_DIR

    # 1) Target VM directory: NVRAM + qcow2 metadata (image is sparse, grows on demand).
    target_dir = vm_dir or VMS_DIR
    probe_dir = _existing_parent(target_dir)
    if probe_dir is not None:
        try:
            usage = shutil.disk_usage(probe_dir)
            free_gb = usage.free / (1024 ** 3)
            disk_size_gb = _parse_disk_size_gb(disk_size or os_def.default_disk_size)
            required_gb = disk_size_gb + 1  # NVRAM + qcow2 metadata overhead
            if free_gb < required_gb:
                missing.append(
                    f'Insufficient disk space at {target_dir}: '
                    f'{free_gb:.1f}GB free, ~{required_gb}GB required '
                    f'(disk image: {disk_size or os_def.default_disk_size})'
                )
        except OSError:
            pass  # Skip check if we can't determine disk usage

    # 2) ISO cache directory: only checked when a download will actually happen.
    iso_download_expected = (
        os_def.platform == 'linux'
        and os_def.install_mode != 'manual'
        and iso_path is None
    )
    if iso_download_expected:
        cache_probe = _existing_parent(QEMU_CACHE_DIR)
        if cache_probe is not None:
            try:
                usage = shutil.disk_usage(cache_probe)
                free_gb = usage.free / (1024 ** 3)
                iso_size_gb = getattr(os_def, 'iso_size_gb', None) or 6
                if free_gb < iso_size_gb:
                    missing.append(
                        f'Insufficient disk space at {QEMU_CACHE_DIR}: '
                        f'{free_gb:.1f}GB free, ~{iso_size_gb}GB required for ISO download'
                    )
            except OSError:
                pass  # Skip check if we can't determine disk usage
