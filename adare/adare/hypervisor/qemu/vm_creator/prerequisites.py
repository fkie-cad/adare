"""Prerequisite checks for VM creation."""

import shutil
import platform
from pathlib import Path

from adare.hypervisor.qemu.vm_creator.os_catalog import OsDefinition
from adare.hypervisor.exceptions import HypervisorException

import logging
log = logging.getLogger(__name__)


class PrerequisiteError(HypervisorException):
    """Raised when a required prerequisite is missing."""

    def __init__(self, missing: list[str]):
        lines = '\n'.join(f'  - {m}' for m in missing)
        message = f"Missing prerequisites for VM creation:\n{lines}"
        super().__init__(message)


def check_prerequisites(os_def: OsDefinition, iso_path: Path | None = None) -> None:
    """Check that all required tools and resources are available.

    Args:
        os_def: OS definition for the VM to create
        iso_path: User-supplied ISO path (for Windows or manual installs)

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
    _check_disk_space(os_def, missing)

    if missing:
        raise PrerequisiteError(missing)


def _check_disk_space(os_def: OsDefinition, missing: list[str]) -> None:
    """Check approximate free disk space for VM creation."""
    from adare.config.configdirectory import APPDATA_DIR
    import shutil as _shutil

    try:
        usage = _shutil.disk_usage(APPDATA_DIR)
        free_gb = usage.free / (1024 ** 3)

        # Need space for: ISO cache (~3-6GB) + disk image (default size) + temp files (~2GB)
        disk_size_gb = int(os_def.default_disk_size.rstrip('G'))
        required_gb = disk_size_gb + 8  # disk + ISO + overhead

        if free_gb < required_gb:
            missing.append(
                f'Insufficient disk space: {free_gb:.1f}GB free, ~{required_gb}GB required '
                f'(disk image: {os_def.default_disk_size}, plus ISO and temp files)'
            )
    except OSError:
        pass  # Skip check if we can't determine disk usage
