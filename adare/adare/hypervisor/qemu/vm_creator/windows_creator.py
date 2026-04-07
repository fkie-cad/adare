"""Windows VM creation orchestrator - Autounattend via floppy/ISO + UEFI boot."""

import platform
import shutil
import struct
import subprocess
import tempfile
import threading
from pathlib import Path

from adare.config.configdirectory import QEMU_CACHE_DIR
from adare.console import console, print_section, print_step
from adare.helperfunctions.web.download import download
from adare.hypervisor.qemu.firmware import find_ovmf_firmware
from adare.hypervisor.qemu.vm_creator.base_creator import BaseVMCreator, VMCreationError
from adare.hypervisor.qemu.vm_creator.os_catalog import (
    UTM_GUEST_TOOLS_ISO_FILENAME,
    UTM_GUEST_TOOLS_ISO_URL,
    VIRTIO_WIN_ISO_FILENAME,
    VIRTIO_WIN_ISO_URL,
    OsDefinition,
    SetupLevel,
)
from adare.hypervisor.qemu.vm_creator.progress import wait_for_qemu_exit
from adare.hypervisor.qemu.vm_creator.qmp_utils import (
    qemu_params_for_arch,
    repeatedly_send_keypress,
)

from jinja2 import Environment, FileSystemLoader

from adare.config.configdirectory import VM_TEMPLATES_DIR

import logging
log = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / 'templates'

# Autounattend template mapping
_AUTOUNATTEND_MAP = {
    'windows11': 'autounattend_win11.xml',
    'windows10': 'autounattend_win10.xml',
}


def _render_autounattend(template_name: str, architecture: str = 'x86_64', setup_level: int = SetupLevel.FULL) -> str:
    """Render an Autounattend XML template with Jinja2.

    Args:
        template_name: Filename of the template in TEMPLATES_DIR
        architecture: CPU architecture ('x86_64' or 'aarch64')
        setup_level: VM setup level (0=bare, 1=base, 2=full)

    Returns:
        Rendered XML content as a string
    """
    is_arm = architecture == 'aarch64'
    template_vars = {
        'setup_level': setup_level,
        'proc_arch': 'arm64' if is_arm else 'amd64',
        'driver_arch': 'ARM64' if is_arm else 'amd64',
        'miniforge_arch': 'aarch64' if is_arm else 'x86_64',
    }

    # Search user templates first, then built-in templates
    search_paths = [str(VM_TEMPLATES_DIR), str(TEMPLATES_DIR)]
    env = Environment(loader=FileSystemLoader(search_paths), keep_trailing_newline=True)
    template = env.get_template(template_name)
    return template.render(**template_vars)


class WindowsVMCreationError(VMCreationError):
    """Raised when Windows VM creation fails."""

    def __init__(self, detail: str):
        super().__init__(f"Windows: {detail}")


class WindowsVMCreator(BaseVMCreator):
    """Create a fully configured Windows VM from a user-supplied ISO.

    Orchestrates the full creation flow:
    1. Check prerequisites
    2. Download virtio-win drivers ISO (cached)
    3. Create Autounattend floppy image
    4. Create UEFI disk image + NVRAM
    5. Boot QEMU with UEFI + Windows ISO + virtio-win + floppy
    6. Wait for installation to complete (VM self-shutdown)
    7. Return path to the finished qcow2 disk image
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._virtio_iso_path: Path | None = None
        self._utm_iso_path: Path | None = None

    def _ensure_iso(self) -> None:
        """Validate user-supplied ISO and download virtio-win drivers."""
        print_section('Drivers & Prerequisites')
        self._virtio_iso_path = _ensure_virtio_win_iso()
        if self.os_def.architecture == 'aarch64':
            self._utm_iso_path = _ensure_utm_guest_tools_iso()

    def _run_installation(self, disk_path: Path, nvram_path: Path | None) -> None:
        """Create floppy, boot QEMU with UEFI + ISOs, and wait for install."""
        with tempfile.TemporaryDirectory(prefix='adare-winvm-') as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create Autounattend media (floppy for x86_64, ISO for aarch64)
            media_path = _create_autounattend_media(self.os_def, tmpdir_path, setup_level=self.setup_level, virtio_iso_path=self._virtio_iso_path)

            # Boot QEMU and wait for install
            try:
                _run_windows_installation(
                    os_def=self.os_def,
                    windows_iso_path=self.iso_path,
                    virtio_iso_path=self._virtio_iso_path,
                    utm_iso_path=self._utm_iso_path,
                    media_path=media_path,
                    disk_path=disk_path,
                    nvram_path=nvram_path,
                    ram_mb=self.ram_mb,
                    cpus=self.cpus,
                    has_tpm=shutil.which('swtpm') is not None,
                )
            except (TimeoutError, subprocess.CalledProcessError) as e:
                raise WindowsVMCreationError(str(e)) from e


def create_windows_vm(
    os_def: OsDefinition,
    iso_path: Path,
    vm_name: str | None = None,
    disk_size: str | None = None,
    ram_mb: int | None = None,
    cpus: int | None = None,
    force: bool = False,
    vm_dir: Path | None = None,
    setup_level: SetupLevel = SetupLevel.FULL,
) -> Path:
    """Create a fully configured Windows VM from a user-supplied ISO.

    Convenience wrapper around ``WindowsVMCreator`` for backward compatibility.
    """
    creator = WindowsVMCreator(
        os_def=os_def,
        vm_name=vm_name,
        disk_size=disk_size,
        ram_mb=ram_mb,
        cpus=cpus,
        force=force,
        vm_dir=vm_dir,
        iso_path=iso_path,
        setup_level=setup_level,
    )
    return creator.create()


def _ensure_virtio_win_iso() -> Path:
    """Download virtio-win ISO if not already cached."""
    QEMU_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    virtio_path = QEMU_CACHE_DIR / VIRTIO_WIN_ISO_FILENAME

    if virtio_path.exists():
        print_step(f'Using cached virtio-win ISO: [dim]{virtio_path}[/dim]')
        return virtio_path

    print_step('Downloading virtio-win drivers ISO...')
    download(VIRTIO_WIN_ISO_URL, virtio_path)
    return virtio_path


def _ensure_utm_guest_tools_iso() -> Path:
    """Download UTM guest tools ISO for ARM64 Windows if not already cached.

    UTM guest tools include ARM64 virtio drivers, SPICE vdagent, and QEMU guest agent.
    See: https://github.com/utmapp/spice-nsis
    """
    QEMU_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    utm_path = QEMU_CACHE_DIR / UTM_GUEST_TOOLS_ISO_FILENAME

    if utm_path.exists():
        print_step(f'Using cached UTM guest tools ISO: [dim]{utm_path}[/dim]')
        return utm_path

    print_step('Downloading UTM guest tools ISO (ARM64 virtio drivers + SPICE)...')
    download(UTM_GUEST_TOOLS_ISO_URL, utm_path)
    return utm_path


def _create_autounattend_media(os_def: OsDefinition, tmpdir: Path, setup_level: int = SetupLevel.FULL, virtio_iso_path: Path | None = None) -> Path:
    """Create media containing Autounattend.xml, appropriate for the architecture.

    - x86_64: 1.44MB FAT12 floppy image (attached via if=floppy as drive A:)
    - aarch64: Combined ISO with Autounattend.xml + guest tools exe (UTM approach)

    Args:
        os_def: OS definition to select the right template
        tmpdir: Temporary directory for the media image
        setup_level: VM setup level (0=bare, 1=base, 2=full)
        virtio_iso_path: Path to virtio-win ISO (required for aarch64 tools ISO)

    Returns:
        Path to the media image (floppy .img or .iso)
    """
    # Resolve template: os_def.template > _AUTOUNATTEND_MAP
    if os_def.template:
        template_name = os_def.template
    else:
        template_name = _AUTOUNATTEND_MAP.get(os_def.name)
        if template_name is None:
            raise WindowsVMCreationError(f"No Autounattend template for OS '{os_def.name}'")

    xml_content = _render_autounattend(template_name, architecture=os_def.architecture, setup_level=setup_level).encode('utf-8')

    if os_def.architecture == 'aarch64':
        from adare.hypervisor.qemu.vm_creator.iso_utils import create_tools_iso
        iso_path = tmpdir / 'tools.iso'
        return create_tools_iso(xml_content, virtio_iso_path, iso_path)

    floppy_path = tmpdir / 'autounattend.img'
    _write_fat12_floppy(floppy_path, {'Autounattend.xml': xml_content})
    log.info(f'Created Autounattend floppy image: {floppy_path}')
    return floppy_path



def _write_fat12_floppy(path: Path, files: dict[str, bytes]) -> None:
    """Write a minimal FAT12 1.44MB floppy image with the given files.

    Creates a bootable-format floppy image that Windows Setup can read.
    This is a minimal FAT12 implementation - sufficient for a few small files.
    """
    FLOPPY_SIZE = 1474560  # 1.44 MB
    SECTOR_SIZE = 512
    SECTORS_PER_CLUSTER = 1
    RESERVED_SECTORS = 1
    NUM_FATS = 2
    ROOT_DIR_ENTRIES = 224
    TOTAL_SECTORS = FLOPPY_SIZE // SECTOR_SIZE
    SECTORS_PER_FAT = 9
    SECTORS_PER_TRACK = 18
    NUM_HEADS = 2

    img = bytearray(FLOPPY_SIZE)

    # Boot sector (BPB - BIOS Parameter Block)
    bpb = struct.pack(
        '<3s8sHBHBHHBHHHIIBBBI11s8s',
        b'\xEB\x3C\x90',       # Jump + NOP
        b'MSDOS5.0',           # OEM name
        SECTOR_SIZE,            # Bytes per sector
        SECTORS_PER_CLUSTER,    # Sectors per cluster
        RESERVED_SECTORS,       # Reserved sectors
        NUM_FATS,               # Number of FATs
        ROOT_DIR_ENTRIES,       # Root directory entries
        TOTAL_SECTORS,          # Total sectors (16-bit)
        0xF0,                   # Media descriptor (1.44MB floppy)
        SECTORS_PER_FAT,        # Sectors per FAT
        SECTORS_PER_TRACK,      # Sectors per track
        NUM_HEADS,              # Number of heads
        0,                      # Hidden sectors
        0,                      # Total sectors (32-bit, 0 = use 16-bit)
        0x00,                   # Drive number
        0,                      # Reserved
        0x29,                   # Extended boot signature
        0x12345678,             # Volume serial number
        b'ADARE      ',        # Volume label
        b'FAT12   ',           # File system type
    )
    img[:len(bpb)] = bpb
    img[510] = 0x55
    img[511] = 0xAA

    # FAT tables
    fat_start = RESERVED_SECTORS * SECTOR_SIZE
    root_dir_start = fat_start + (NUM_FATS * SECTORS_PER_FAT * SECTOR_SIZE)
    data_start = root_dir_start + (ROOT_DIR_ENTRIES * 32)

    # Initialize both FAT copies with media descriptor
    for fat_num in range(NUM_FATS):
        offset = fat_start + (fat_num * SECTORS_PER_FAT * SECTOR_SIZE)
        img[offset] = 0xF0
        img[offset + 1] = 0xFF
        img[offset + 2] = 0xFF

    next_cluster = 2  # First data cluster is cluster 2
    dir_entry_offset = root_dir_start
    short_name_index = 1  # Counter for ~N short name generation

    for filename, content in files.items():
        clusters_needed = (len(content) + SECTOR_SIZE - 1) // SECTOR_SIZE
        if clusters_needed == 0:
            clusters_needed = 1

        # Check if filename needs VFAT long filename entries
        needs_lfn = _needs_lfn(filename)
        if needs_lfn:
            name_83 = _make_short_name(filename, short_name_index)
            short_name_index += 1
            # Write LFN entries (reversed order) before the 8.3 entry
            lfn_entries = _make_lfn_entries(filename, name_83)
            for lfn_entry in lfn_entries:
                img[dir_entry_offset:dir_entry_offset + 32] = lfn_entry
                dir_entry_offset += 32
        else:
            name_83 = _to_83_name(filename)

        # Write 8.3 directory entry
        entry = struct.pack(
            '<11sBBBHHHHHHHI',
            name_83,             # Filename (8.3)
            0x20,                # Attribute (Archive)
            0,                   # Reserved
            0,                   # Create time (fine)
            0,                   # Create time
            0,                   # Create date
            0,                   # Access date
            0,                   # EA index (high cluster for FAT32)
            0,                   # Modify time
            0,                   # Modify date
            next_cluster,        # Starting cluster
            len(content),        # File size
        )
        img[dir_entry_offset:dir_entry_offset + 32] = entry
        dir_entry_offset += 32

        # Write file data
        data_offset = data_start + (next_cluster - 2) * SECTOR_SIZE * SECTORS_PER_CLUSTER
        img[data_offset:data_offset + len(content)] = content

        # Write FAT chain
        for i in range(clusters_needed - 1):
            _set_fat12_entry(img, fat_start, SECTORS_PER_FAT, SECTOR_SIZE, next_cluster + i, next_cluster + i + 1)
        _set_fat12_entry(img, fat_start, SECTORS_PER_FAT, SECTOR_SIZE, next_cluster + clusters_needed - 1, 0xFFF)

        next_cluster += clusters_needed

    with open(path, 'wb') as f:
        f.write(img)


def _needs_lfn(filename: str) -> bool:
    """Check if a filename requires VFAT long filename entries."""
    parts = filename.rsplit('.', 1)
    name = parts[0]
    ext = parts[1] if len(parts) > 1 else ''
    # LFN needed if name > 8 chars, ext > 3 chars, or has mixed case
    if len(name) > 8 or len(ext) > 3:
        return True
    if name != name.upper() or ext != ext.upper():
        return True
    return False


def _make_short_name(filename: str, index: int = 1) -> bytes:
    """Generate a valid 8.3 short name with ~N suffix for LFN files."""
    parts = filename.rsplit('.', 1)
    name = parts[0].upper()
    ext = (parts[1].upper() if len(parts) > 1 else '')[:3]
    # Keep only valid 8.3 characters
    name = ''.join(c for c in name if c.isalnum() or c in '!#$%&\'()-@^_`{}~')
    suffix = f'~{index}'
    name = name[:8 - len(suffix)] + suffix
    return name.ljust(8).encode('ascii') + ext.ljust(3).encode('ascii')


def _lfn_checksum(short_name: bytes) -> int:
    """Calculate checksum for LFN entries from 11-byte 8.3 short name."""
    s = 0
    for b in short_name:
        s = (((s & 1) << 7) | ((s & 0xFE) >> 1)) + b
        s &= 0xFF
    return s


def _make_lfn_entries(long_name: str, short_name: bytes) -> list[bytes]:
    """Create VFAT long filename directory entries for a file.

    Returns a list of 32-byte LFN entries in the order they should appear
    in the directory (highest sequence number first, then decreasing).
    """
    checksum = _lfn_checksum(short_name)

    # Encode as UTF-16LE with NUL terminator
    encoded = long_name.encode('utf-16-le') + b'\x00\x00'
    # Pad to multiple of 26 bytes (13 UTF-16 chars per LFN entry)
    while len(encoded) % 26 != 0:
        encoded += b'\xFF\xFF'

    num_entries = len(encoded) // 26
    entries = []

    for i in range(num_entries):
        entry = bytearray(32)
        seq = i + 1
        if i == num_entries - 1:
            seq |= 0x40  # mark as last LFN entry

        chunk = encoded[i * 26:(i + 1) * 26]
        entry[0] = seq
        entry[1:11] = chunk[0:10]     # chars 1-5 (5 UTF-16 chars = 10 bytes)
        entry[11] = 0x0F              # LFN attribute
        entry[12] = 0                 # type
        entry[13] = checksum
        entry[14:26] = chunk[10:22]   # chars 6-11 (6 UTF-16 chars = 12 bytes)
        entry[26:28] = b'\x00\x00'    # first cluster = 0
        entry[28:32] = chunk[22:26]   # chars 12-13 (2 UTF-16 chars = 4 bytes)

        entries.append(bytes(entry))

    # LFN entries stored in reverse order (highest sequence first)
    entries.reverse()
    return entries


def _to_83_name(filename: str) -> bytes:
    """Convert a filename to 8.3 format (11 bytes, space-padded)."""
    if '.' in filename:
        name, ext = filename.rsplit('.', 1)
    else:
        name, ext = filename, ''
    name = name.upper()[:8].ljust(8)
    ext = ext.upper()[:3].ljust(3)
    return (name + ext).encode('ascii')


def _set_fat12_entry(img: bytearray, fat_start: int, sectors_per_fat: int,
                     sector_size: int, cluster: int, value: int) -> None:
    """Set a FAT12 entry for the given cluster in both FAT copies."""
    for fat_num in range(2):
        offset = fat_start + (fat_num * sectors_per_fat * sector_size)
        byte_offset = offset + (cluster * 3 // 2)
        if cluster % 2 == 0:
            img[byte_offset] = value & 0xFF
            img[byte_offset + 1] = (img[byte_offset + 1] & 0xF0) | ((value >> 8) & 0x0F)
        else:
            img[byte_offset] = (img[byte_offset] & 0x0F) | ((value & 0x0F) << 4)
            img[byte_offset + 1] = (value >> 4) & 0xFF


def _run_windows_installation(
    os_def: OsDefinition,
    windows_iso_path: Path,
    virtio_iso_path: Path,
    media_path: Path,
    disk_path: Path,
    nvram_path: Path,
    ram_mb: int,
    cpus: int,
    has_tpm: bool = False,
    utm_iso_path: Path | None = None,
) -> None:
    """Boot QEMU with UEFI + Windows ISO + virtio-win + Autounattend media and wait for install.

    ARM64 uses a two-phase approach with -no-reboot:
      Phase 1: Boot from ISO (WinPE), QEMU exits on first guest reboot
      Phase 2: Boot from NVMe (OOBE + FirstLogonCommands), QEMU exits on shutdown

    This avoids the UEFI boot loop where AAVMF re-boots from ISO after the
    mid-install reboot instead of continuing from NVMe.
    """
    if os_def.architecture == 'aarch64':
        print_section('Installation (Phase 1/2)')
        print_step('Installing Windows (WinPE) [dim](this may take 15-30 minutes)[/dim]')
        _run_qemu_install_phase(
            os_def=os_def,
            windows_iso_path=windows_iso_path,
            virtio_iso_path=virtio_iso_path,
            media_path=media_path,
            disk_path=disk_path,
            nvram_path=nvram_path,
            ram_mb=ram_mb,
            cpus=cpus,
            has_tpm=has_tpm,
            utm_iso_path=utm_iso_path,
            boot_from_disk=False,
            no_reboot=True,
            phase_label='Phase 1/2: WinPE',
        )
        print_section('Installation (Phase 2/2)')
        print_step('Completing setup (OOBE + drivers) [dim](this may take 30-60 minutes)[/dim]')
        _run_qemu_install_phase(
            os_def=os_def,
            windows_iso_path=windows_iso_path,
            virtio_iso_path=virtio_iso_path,
            media_path=media_path,
            disk_path=disk_path,
            nvram_path=nvram_path,
            ram_mb=ram_mb,
            cpus=cpus,
            has_tpm=has_tpm,
            utm_iso_path=utm_iso_path,
            boot_from_disk=True,
            no_reboot=False,
            phase_label='Phase 2/2: OOBE',
        )
    else:
        print_section('Installation')
        print_step('Starting unattended Windows installation [dim](this may take 30-90 minutes)[/dim]')
        _run_qemu_install_phase(
            os_def=os_def,
            windows_iso_path=windows_iso_path,
            virtio_iso_path=virtio_iso_path,
            media_path=media_path,
            disk_path=disk_path,
            nvram_path=nvram_path,
            ram_mb=ram_mb,
            cpus=cpus,
            has_tpm=has_tpm,
            utm_iso_path=utm_iso_path,
            boot_from_disk=False,
            no_reboot=False,
            phase_label='Windows installation',
        )


def _run_qemu_install_phase(
    os_def: OsDefinition,
    windows_iso_path: Path,
    virtio_iso_path: Path,
    media_path: Path,
    disk_path: Path,
    nvram_path: Path,
    ram_mb: int,
    cpus: int,
    has_tpm: bool,
    utm_iso_path: Path | None,
    boot_from_disk: bool,
    no_reboot: bool,
    phase_label: str,
) -> None:
    """Run a single QEMU install phase.

    Args:
        boot_from_disk: If True, NVMe gets bootindex=0 and ISO has no bootindex.
                        If False, ISO gets bootindex=0 and NVMe gets bootindex=1.
        no_reboot: If True, add -no-reboot so QEMU exits on guest reboot.
        phase_label: Label for log messages and status display.
    """
    arch_params = qemu_params_for_arch(os_def)
    machine = arch_params['machine']

    # aarch64 + HVF: keep device MMIO/ECAM/GIC regions below 4 GB so edk2
    # firmware can enumerate PCI and USB devices. Using the fine-grained
    # highmem-* properties instead of blanket highmem=off, because highmem=off
    # also caps RAM at ~3 GB (incompatible with Windows 11's 4 GB minimum).
    if os_def.architecture == 'aarch64':
        machine = machine.replace(
            'virt,', 'virt,highmem-mmio=off,highmem-ecam=off,highmem-redists=off,')

    ovmf_code, _ = find_ovmf_firmware(os_def.architecture)

    cmd = [
        arch_params['exe'],
        '-machine', machine,
        '-cpu', arch_params['cpu'],
        '-m', str(ram_mb),
        '-smp', str(cpus),
    ]

    # UEFI firmware — pflash mode with separate NVRAM for persistent boot vars.
    # aarch64: NVRAM is pre-populated with Shell as Boot0000 (firmware.py).
    # Shell auto-executes startup.nsh which boots Windows Setup.
    # x86_64: NVRAM starts empty; fw_cfg bootorder handles boot device selection.
    cmd.extend([
        '-drive', f'if=pflash,format=raw,readonly=on,file={ovmf_code}',
        '-drive', f'if=pflash,format=raw,file={nvram_path}',
    ])

    # Disk — ARM64 uses NVMe (native Windows driver, no viostor needed in WinPE).
    # x86_64 uses virtio-blk-pci (viostor loaded via Autounattend DriverPaths).
    # ARM64: cache=writethrough for stability (writeback causes random corruption with HVF)
    disk_cache = 'writethrough' if os_def.architecture == 'aarch64' else 'writeback'
    cmd.extend([
        '-drive', f'file={disk_path},format=qcow2,if=none,id=hd0,cache={disk_cache}',
    ])
    if os_def.architecture == 'aarch64':
        # Phase 1 (boot_from_disk=False): bootindex=1 (fallback)
        # Phase 2 (boot_from_disk=True):  bootindex=0 (primary)
        nvme_bootindex = 0 if boot_from_disk else 1
        cmd.extend(['-device', f'nvme,drive=hd0,serial=boot,bootindex={nvme_bootindex}'])
    else:
        cmd.extend(['-device', 'virtio-blk-pci,drive=hd0'])
    cmd.extend([
        # Network
        '-nic', 'user,model=virtio-net-pci',
        # Display — show QEMU window so user can watch install progress
        '-display', 'cocoa' if platform.system() == 'Darwin' else 'gtk',
    ])
    # Display device — ramfb only during install (virtio-gpu-device conflicts
    # with firmware console init on aarch64, causes UEFI Shell).
    if os_def.architecture == 'aarch64':
        cmd.extend(['-device', 'ramfb'])
    else:
        cmd.extend(arch_params['vga_args'])
    cmd.extend([
        # USB controller (must come before USB devices)
        '-device', 'qemu-xhci',
        '-device', 'usb-kbd',
        '-device', 'usb-tablet',
    ])

    # -boot c is a legacy BIOS concept; UEFI uses bootindex on devices instead.
    # Only add for x86_64 (SeaBIOS fallback compatibility).
    if os_def.architecture != 'aarch64':
        cmd.extend(['-boot', 'c'])

    # CD-ROM / ISO drives — aarch64: all ISOs via USB storage (UTM approach).
    # x86_64 uses IDE CD-ROMs + floppy (classic approach).
    if os_def.architecture == 'aarch64':
        guest_tools_iso = utm_iso_path if utm_iso_path else virtio_iso_path
        # Phase 1 (boot_from_disk=False): bootindex=0 (primary — boot from ISO)
        # Phase 2 (boot_from_disk=True):  no bootindex (don't boot from ISO)
        iso_bootindex = '' if boot_from_disk else ',bootindex=0'
        cmd.extend([
            '-drive', f'file={windows_iso_path},media=cdrom,if=none,id=winiso',
            '-device', f'usb-storage,drive=winiso{iso_bootindex},removable=on',
            '-drive', f'file={media_path},media=cdrom,if=none,id=toolsiso',
            '-device', 'usb-storage,drive=toolsiso,removable=on',
            '-drive', f'file={guest_tools_iso},media=cdrom,if=none,id=guestiso',
            '-device', 'usb-storage,drive=guestiso,removable=on',
        ])
    else:
        cmd.extend([
            '-drive', f'file={windows_iso_path},media=cdrom,index=0',
            '-drive', f'file={virtio_iso_path},media=cdrom,index=1',
        ])
        # x86_64 uses a FAT12 floppy image on drive A: (classic Autounattend delivery)
        cmd.extend(['-drive', f'file={media_path},format=raw,if=floppy'])

    if no_reboot:
        cmd.append('-no-reboot')

    # QMP socket for sending keypresses (needed for "Press any key to boot from CD")
    qmp_sock = Path(tempfile.gettempdir()) / f'adare-qemu-install-{disk_path.stem}.qmp'
    if qmp_sock.exists():
        qmp_sock.unlink()
    cmd.extend(['-qmp', f'unix:{qmp_sock},server,nowait'])

    # Capture firmware serial output for boot debugging
    serial_log = Path(tempfile.gettempdir()) / 'adare-qemu-uefi-serial.log'
    cmd.extend(['-serial', f'file:{serial_log}'])

    log.info(f'Starting QEMU {phase_label}: {" ".join(cmd)}')
    log.info(f'UEFI serial log at {serial_log}')

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Send repeated keypresses during early boot:
    # x86_64: catches "Press any key to boot from CD or DVD..." prompt.
    # ARM64: dismisses any firmware prompt and accelerates Shell's startup.nsh
    #        execution (Shell waits 1-5s for ESC before running startup.nsh;
    #        any non-ESC key like Enter runs it immediately).
    keypress_duration = 15.0
    keypress_thread = threading.Thread(
        target=repeatedly_send_keypress,
        args=(qmp_sock,),
        kwargs={'interval': 1.0, 'duration': keypress_duration},
        daemon=True,
    )
    keypress_thread.start()

    try:
        with console.status(f'  [cyan]{disk_path.stem}[/cyan] {phase_label}...', spinner='dots') as status:
            wait_for_qemu_exit(
                process,
                timeout_minutes=90,
                label=f'{disk_path.stem} {phase_label}',
                status=status,
            )
    except (TimeoutError, subprocess.CalledProcessError):
        raise
    except KeyboardInterrupt:
        console.print('\n  [bold red]Installation interrupted by user[/bold red]')
        process.terminate()
        process.wait(timeout=30)
        raise WindowsVMCreationError('Installation interrupted by user')
