"""OVMF firmware detection for QEMU UEFI boot support."""

import logging
import os
import struct
from pathlib import Path

from adare.hypervisor.exceptions import HypervisorException

log = logging.getLogger(__name__)


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
            "  macOS (Homebrew): brew install qemu\n"
            "  macOS (MacPorts): sudo port install qemu"
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
    # macOS (MacPorts)
    ("/opt/local/share/qemu/edk2-x86_64-code.fd", "/opt/local/share/qemu/edk2-i386-vars.fd"),
    # macOS (Homebrew - Apple Silicon)
    ("/opt/homebrew/share/qemu/edk2-x86_64-code.fd", "/opt/homebrew/share/qemu/edk2-i386-vars.fd"),
    # macOS (Homebrew - Apple Silicon, opt/ symlink — stable across versions)
    ("/opt/homebrew/opt/qemu/share/qemu/edk2-x86_64-code.fd", "/opt/homebrew/opt/qemu/share/qemu/edk2-i386-vars.fd"),
    # macOS (Homebrew - Intel)
    ("/usr/local/share/qemu/edk2-x86_64-code.fd", "/usr/local/share/qemu/edk2-i386-vars.fd"),
]

# aarch64 OVMF firmware paths
AARCH64_OVMF_SEARCH_PATHS = [
    # macOS MacPorts
    ("/opt/local/share/qemu/edk2-aarch64-code.fd", "/opt/local/share/qemu/edk2-arm-vars.fd"),
    # macOS Homebrew (Apple Silicon)
    ("/opt/homebrew/share/qemu/edk2-aarch64-code.fd", "/opt/homebrew/share/qemu/edk2-arm-vars.fd"),
    # macOS Homebrew (Apple Silicon, opt/ symlink — stable across versions)
    ("/opt/homebrew/opt/qemu/share/qemu/edk2-aarch64-code.fd", "/opt/homebrew/opt/qemu/share/qemu/edk2-arm-vars.fd"),
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


def find_ovmf_firmware(architecture: str = 'x86_64') -> tuple[str, str]:
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

        # aarch64: pre-populate NVRAM with Shell as default boot option.
        # edk2-aarch64 ignores QEMU's fw_cfg bootorder for USB devices,
        # so bootindex= on usb-storage is silently ignored. Without boot
        # variables the firmware shows its UiApp menu requiring manual
        # Shell selection. Writing Shell as Boot0000 makes it auto-boot.
        if architecture == 'aarch64':
            _prepare_nvram_for_shell_boot(nvram_path)

    return nvram_path


# ---------------------------------------------------------------------------
# EFI NVRAM pre-population for aarch64 Shell boot
# ---------------------------------------------------------------------------

# EFI Global Variable GUID: {8BE4DF61-93CA-11D2-AA0D-00E098032B8C}
_EFI_GLOBAL_VARIABLE_GUID = bytes([
    0x61, 0xDF, 0xE4, 0x8B, 0xCA, 0x93, 0xD2, 0x11,
    0xAA, 0x0D, 0x00, 0xE0, 0x98, 0x03, 0x2B, 0x8C,
])

# UEFI Shell FFS file GUID: {7C04A583-9E3E-4F1C-AD65-E05268D0B4D1}
_SHELL_FFS_GUID = bytes([
    0x83, 0xA5, 0x04, 0x7C, 0x3E, 0x9E, 0x1C, 0x4F,
    0xAD, 0x65, 0xE0, 0x52, 0x68, 0xD0, 0xB4, 0xD1,
])

# Authenticated variable store GUID (edk2 default for aarch64)
_AUTH_VAR_STORE_GUID = bytes([
    0x78, 0x2C, 0xF3, 0xAA, 0x7B, 0x94, 0x9A, 0x43,
    0xA1, 0x80, 0x2E, 0x14, 0x4E, 0xC3, 0x77, 0x92,
])

# Standard (non-authenticated) variable store GUID
_STD_VAR_STORE_GUID = bytes([
    0x16, 0x36, 0xCF, 0xDD, 0x75, 0x32, 0x64, 0x41,
    0x98, 0xB6, 0xFE, 0x85, 0x70, 0x7F, 0xFE, 0x7D,
])

_VAR_ADDED = 0x3F  # Variable fully written and valid
_NV_BS_RT = 0x00000007  # NON_VOLATILE | BOOTSERVICE_ACCESS | RUNTIME_ACCESS
_VAR_STORE_HEADER_SIZE = 28  # GUID(16) + Size(4) + Format(1) + State(1) + Reserved(6)


def _prepare_nvram_for_shell_boot(nvram_path: str) -> None:
    """Pre-populate an empty aarch64 NVRAM with Shell as the default boot option.

    edk2-aarch64 doesn't translate QEMU's fw_cfg bootorder for USB-storage
    devices into EFI boot variables. With empty NVRAM the firmware falls
    through to the UiApp menu, requiring the user to manually select
    "EFI Internal Shell".

    This writes three variables so the firmware auto-boots Shell:
      Timeout   = 0        (no BDS delay)
      BootOrder = [0x0000] (try Boot0000 first)
      Boot0000  = Shell    (short-form FvFile device path)

    Shell then auto-executes startup.nsh which boots Windows Setup.
    """
    data = bytearray(Path(nvram_path).read_bytes())

    # Validate FV header signature '_FVH'
    if data[0x28:0x2C] != b'_FVH':
        log.warning('NVRAM: no valid FV header — skipping Shell boot prep')
        return

    # FV header length tells us where the variable store starts
    hdr_len = struct.unpack_from('<H', data, 0x30)[0]
    vs_guid = bytes(data[hdr_len:hdr_len + 16])

    if vs_guid == _AUTH_VAR_STORE_GUID:
        authenticated = True
    elif vs_guid == _STD_VAR_STORE_GUID:
        authenticated = False
    else:
        log.warning('NVRAM: unrecognised variable store GUID — skipping Shell boot prep')
        return

    var_start = hdr_len + _VAR_STORE_HEADER_SIZE

    # Only write into a genuinely empty store (template should be all-0xFF)
    if data[var_start] != 0xFF:
        log.info('NVRAM already has variables — skipping Shell boot prep')
        return

    offset = var_start
    offset = _write_efi_var(data, offset, 'Timeout', struct.pack('<H', 0), authenticated)
    offset = _write_efi_var(data, offset, 'BootOrder', struct.pack('<H', 0), authenticated)
    offset = _write_efi_var(data, offset, 'Boot0000', _build_shell_load_option(), authenticated)

    Path(nvram_path).write_bytes(bytes(data))
    log.info('NVRAM: pre-populated with Shell as Boot0000 (auto-boot)')


def _write_efi_var(
    data: bytearray, offset: int, name: str, value: bytes, authenticated: bool,
) -> int:
    """Write one EFI variable into *data* at *offset*. Return next aligned offset."""
    name_bytes = (name + '\0').encode('utf-16-le')

    # Build header (authenticated: 60 bytes, standard: 32 bytes)
    hdr = struct.pack('<HBxI', 0x55AA, _VAR_ADDED, _NV_BS_RT)
    if authenticated:
        hdr += struct.pack('<Q', 0)  # MonotonicCount
        hdr += b'\x00' * 16          # TimeStamp (EFI_TIME, all zeros)
        hdr += struct.pack('<I', 0)  # PubKeyIndex
    hdr += struct.pack('<II', len(name_bytes), len(value))
    hdr += _EFI_GLOBAL_VARIABLE_GUID

    entry = hdr + name_bytes + value
    data[offset:offset + len(entry)] = entry

    # Next variable must be 4-byte aligned
    return (offset + len(entry) + 3) & ~3


def _build_shell_load_option() -> bytes:
    """Build an EFI_LOAD_OPTION payload pointing to the built-in UEFI Shell.

    Uses a short-form MEDIA_PIWG_FW_FILE device path with Shell's FFS GUID.
    The BDS resolves this by scanning all firmware volumes for the matching
    file — no need to hard-code the containing FV GUID.
    """
    description = 'EFI Shell\0'.encode('utf-16-le')

    # Device path: FvFile(Shell GUID) + End-of-path
    fv_file = struct.pack('<BBH', 0x04, 0x06, 20) + _SHELL_FFS_GUID  # 20 bytes
    end = struct.pack('<BBH', 0x7F, 0xFF, 4)                          # 4 bytes
    file_path = fv_file + end  # 24 bytes total

    # EFI_LOAD_OPTION: Attributes(4) + FilePathListLength(2) + Description + FilePath
    return struct.pack('<IH', 0x00000001, len(file_path)) + description + file_path
