"""
Disk Utilities - Standalone functions for disk operations.
"""


def get_boot_mode_for_os(guest_os: str) -> str:
    """
    Determine appropriate boot mode based on guest OS.

    Windows VMs work better with UEFI boot when converted from VirtualBox
    or other hypervisors. Linux VMs typically work fine with either BIOS
    or UEFI, so we default to BIOS for broader compatibility.

    Args:
        guest_os: Guest OS string (e.g., 'windows', 'linux', 'Windows_10')

    Returns:
        'uefi' for Windows, 'bios' for others

    Example:
        >>> get_boot_mode_for_os('Windows_10')
        'uefi'
        >>> get_boot_mode_for_os('Ubuntu_22')
        'bios'
    """
    if 'windows' in guest_os.lower():
        return 'uefi'
    return 'bios'
