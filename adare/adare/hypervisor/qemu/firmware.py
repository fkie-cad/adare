"""OVMF firmware detection for QEMU UEFI boot support."""

import os
from pathlib import Path
from typing import Tuple

from adare.hypervisor.exceptions import HypervisorException


class OVMFFirmwareNotFoundError(HypervisorException):
    """Raised when OVMF firmware files cannot be found on the system."""

    def __init__(self, searched_paths: list[str]):
        paths_str = "\n  - ".join(searched_paths)
        message = (
            f"OVMF firmware not found. Searched locations:\n  - {paths_str}\n\n"
            "To use UEFI boot mode, install OVMF firmware:\n"
            "  Ubuntu/Debian: sudo apt install ovmf\n"
            "  Fedora/RHEL: sudo dnf install edk2-ovmf\n"
            "  Arch: sudo pacman -S edk2-ovmf\n"
            "  macOS (Homebrew): brew install qemu"
        )
        super().__init__(message)


# Common OVMF firmware paths across different Linux distributions
OVMF_SEARCH_PATHS = [
    # Ubuntu/Debian
    ("/usr/share/OVMF/OVMF_CODE.fd", "/usr/share/OVMF/OVMF_VARS.fd"),
    # Fedora/RHEL/CentOS
    ("/usr/share/edk2/ovmf/OVMF_CODE.fd", "/usr/share/edk2/ovmf/OVMF_VARS.fd"),
    # Arch Linux
    ("/usr/share/ovmf/x64/OVMF_CODE.fd", "/usr/share/ovmf/x64/OVMF_VARS.fd"),
    # Alternative Arch paths
    ("/usr/share/edk2-ovmf/x64/OVMF_CODE.fd", "/usr/share/edk2-ovmf/x64/OVMF_VARS.fd"),
    # OpenSUSE
    ("/usr/share/qemu/ovmf-x86_64-code.bin", "/usr/share/qemu/ovmf-x86_64-vars.bin"),
    # Gentoo
    ("/usr/share/edk2-ovmf/OVMF_CODE.fd", "/usr/share/edk2-ovmf/OVMF_VARS.fd"),
    # macOS (Homebrew - Apple Silicon)
    ("/opt/homebrew/share/qemu/edk2-x86_64-code.fd", "/opt/homebrew/share/qemu/edk2-i386-vars.fd"),
    # macOS (Homebrew - Intel)
    ("/usr/local/share/qemu/edk2-x86_64-code.fd", "/usr/local/share/qemu/edk2-i386-vars.fd"),
]

# aarch64 OVMF firmware paths
AARCH64_OVMF_SEARCH_PATHS = [
    # macOS Homebrew (Apple Silicon)
    ("/opt/homebrew/share/qemu/edk2-aarch64-code.fd", "/opt/homebrew/share/qemu/edk2-arm-vars.fd"),
    # macOS Homebrew (Intel — cross-arch)
    ("/usr/local/share/qemu/edk2-aarch64-code.fd", "/usr/local/share/qemu/edk2-arm-vars.fd"),
    # Ubuntu/Debian
    ("/usr/share/AAVMF/AAVMF_CODE.fd", "/usr/share/AAVMF/AAVMF_VARS.fd"),
    ("/usr/share/qemu-efi-aarch64/QEMU_EFI.fd", "/usr/share/qemu-efi-aarch64/vars-template-pflash.raw"),
    # Fedora/RHEL
    ("/usr/share/edk2/aarch64/QEMU_EFI.fd", "/usr/share/edk2/aarch64/vars-template-pflash.raw"),
    # Arch Linux
    ("/usr/share/edk2-armvirt/aarch64/QEMU_EFI.fd", "/usr/share/edk2-armvirt/aarch64/vars-template-pflash.raw"),
]


def find_ovmf_firmware(architecture: str = 'x86_64') -> Tuple[str, str]:
    """Find OVMF CODE and VARS files on the system.

    Searches common installation paths for OVMF firmware across different
    Linux distributions (Ubuntu, Fedora, Arch, etc.).

    Args:
        architecture: Target architecture ('x86_64' or 'aarch64')

    Returns:
        Tuple of (code_path, vars_template_path) - paths to OVMF CODE
        and VARS firmware files.

    Raises:
        OVMFFirmwareNotFoundError: If OVMF firmware files are not found
            in any of the standard locations.
    """
    search_paths = AARCH64_OVMF_SEARCH_PATHS if architecture == 'aarch64' else OVMF_SEARCH_PATHS
    searched_paths = []

    for code_path, vars_path in search_paths:
        searched_paths.append(code_path)

        if os.path.exists(code_path) and os.path.exists(vars_path):
            return (code_path, vars_path)

    # No valid OVMF firmware found
    raise OVMFFirmwareNotFoundError(searched_paths)


def get_nvram_path_for_vm(vm_name: str, vm_config_dir: Path) -> str:
    """Get the NVRAM file path for a specific VM.

    NVRAM stores UEFI variables (boot settings, etc.) and must be unique
    per VM. This function returns the path where the VM's NVRAM should be
    stored.

    Args:
        vm_name: Name of the VM
        vm_config_dir: Directory where VM configuration is stored
            (typically ~/.adare/qemu/vms/)

    Returns:
        Absolute path to the VM's NVRAM file

    Example:
        >>> nvram = get_nvram_path_for_vm("windows-10", Path("/home/user/.adare/qemu/vms"))
        >>> print(nvram)
        '/home/user/.adare/qemu/vms/windows-10-nvram.fd'
    """
    nvram_filename = f"{vm_name}-nvram.fd"
    return str(vm_config_dir / nvram_filename)


def create_nvram_for_vm(vm_name: str, vm_config_dir: Path, architecture: str = 'x86_64') -> str:
    """Create NVRAM file for a VM by copying the OVMF VARS template.

    This creates a per-VM NVRAM file that stores UEFI variables. Each VM
    needs its own NVRAM to maintain independent boot settings.

    Args:
        vm_name: Name of the VM
        vm_config_dir: Directory where VM configuration is stored
        architecture: Target architecture ('x86_64' or 'aarch64')

    Returns:
        Path to the created NVRAM file

    Raises:
        OVMFFirmwareNotFoundError: If OVMF VARS template is not found
        IOError: If NVRAM file cannot be created
    """
    _, vars_template = find_ovmf_firmware(architecture)
    nvram_path = get_nvram_path_for_vm(vm_name, vm_config_dir)

    # Only create if it doesn't exist (preserve existing UEFI settings)
    if not os.path.exists(nvram_path):
        # Ensure parent directory exists
        os.makedirs(vm_config_dir, exist_ok=True)

        # Copy VARS template to create VM-specific NVRAM
        import shutil
        shutil.copy2(vars_template, nvram_path)

    return nvram_path
