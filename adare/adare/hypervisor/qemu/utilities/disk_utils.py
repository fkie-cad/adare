"""
Disk Utilities - Standalone functions for disk operations.
"""


def get_boot_mode_for_os(guest_os: str, architecture: str = 'x86_64') -> str:
    """
    Determine appropriate boot mode based on guest OS and architecture.

    Windows VMs work better with UEFI boot when converted from VirtualBox
    or other hypervisors. Linux VMs typically work fine with either BIOS
    or UEFI, so we default to BIOS for broader compatibility.
    aarch64 (ARM) always requires UEFI — there is no BIOS on ARM.

    Args:
        guest_os: Guest OS string (e.g., 'windows', 'linux', 'Windows_10')
        architecture: Guest architecture ('x86_64' or 'aarch64')

    Returns:
        'uefi' for Windows or aarch64, 'bios' for x86_64 Linux

    Example:
        >>> get_boot_mode_for_os('Windows_10')
        'uefi'
        >>> get_boot_mode_for_os('Ubuntu_22')
        'bios'
        >>> get_boot_mode_for_os('Ubuntu_22', 'aarch64')
        'uefi'
    """
    if architecture == 'aarch64':
        return 'uefi'
    if 'windows' in guest_os.lower():
        return 'uefi'
    return 'bios'
