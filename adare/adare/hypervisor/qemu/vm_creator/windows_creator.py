"""Windows VM creation orchestrator - Autounattend via floppy image + UEFI boot."""

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
    VIRTIO_WIN_ISO_FILENAME,
    VIRTIO_WIN_ISO_URL,
    OsDefinition,
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


def _render_autounattend(template_name: str, architecture: str = 'x86_64', bare: bool = False) -> str:
    """Render an Autounattend XML template with Jinja2.

    Args:
        template_name: Filename of the template in TEMPLATES_DIR
        architecture: CPU architecture ('x86_64' or 'aarch64')
        bare: If True, skip ADARE agent software (Miniforge3, conda env)

    Returns:
        Rendered XML content as a string
    """
    is_arm = architecture == 'aarch64'
    template_vars = {
        'bare': bare,
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

    def __init__(self, *args, bare: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self.bare = bare
        self._virtio_iso_path: Path | None = None

    def _ensure_iso(self) -> None:
        """Validate user-supplied ISO and download virtio-win drivers."""
        print_section('Drivers & Prerequisites')
        self._virtio_iso_path = _ensure_virtio_win_iso()

    def _run_installation(self, disk_path: Path, nvram_path: Path | None) -> None:
        """Create floppy, boot QEMU with UEFI + ISOs, and wait for install."""
        with tempfile.TemporaryDirectory(prefix='adare-winvm-') as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create floppy image with Autounattend.xml
            floppy_path = _create_autounattend_floppy(self.os_def, tmpdir_path, bare=self.bare)

            # Boot QEMU and wait for install
            try:
                _run_windows_installation(
                    os_def=self.os_def,
                    windows_iso_path=self.iso_path,
                    virtio_iso_path=self._virtio_iso_path,
                    floppy_path=floppy_path,
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
    bare: bool = False,
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
        bare=bare,
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


def _create_autounattend_floppy(os_def: OsDefinition, tmpdir: Path, bare: bool = False) -> Path:
    """Create a 1.44MB FAT12 floppy image containing Autounattend.xml.

    Windows Setup auto-reads A:\\ for Autounattend.xml during installation.
    We create a raw FAT12 floppy image using pure Python (struct module).

    Args:
        os_def: OS definition to select the right template
        tmpdir: Temporary directory for the floppy image
        bare: If True, skip ADARE agent software (Miniforge3, conda env)

    Returns:
        Path to the floppy image
    """
    # Resolve template: os_def.template > _AUTOUNATTEND_MAP
    if os_def.template:
        template_name = os_def.template
    else:
        template_name = _AUTOUNATTEND_MAP.get(os_def.name)
        if template_name is None:
            raise WindowsVMCreationError(f"No Autounattend template for OS '{os_def.name}'")

    xml_content = _render_autounattend(template_name, architecture=os_def.architecture, bare=bare).encode('utf-8')

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

    for filename, content in files.items():
        # Root directory entry (8.3 format)
        name_83 = _to_83_name(filename)
        clusters_needed = (len(content) + SECTOR_SIZE - 1) // SECTOR_SIZE
        if clusters_needed == 0:
            clusters_needed = 1

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
    floppy_path: Path,
    disk_path: Path,
    nvram_path: Path,
    ram_mb: int,
    cpus: int,
    has_tpm: bool = False,
) -> None:
    """Boot QEMU with UEFI + Windows ISO + virtio-win + floppy and wait for install."""
    arch_params = qemu_params_for_arch(os_def)
    machine = arch_params['machine']

    # aarch64 on HVF: cap RAM at 4 GB for installation (sufficient for Windows
    # setup; full RAM is used when running the finished VM)
    if os_def.architecture == 'aarch64':
        ram_mb = min(ram_mb, 4096)

    ovmf_code, _ = find_ovmf_firmware(os_def.architecture)

    cmd = [
        arch_params['exe'],
        '-machine', machine,
        '-cpu', arch_params['cpu'],
        '-m', str(ram_mb),
        '-smp', str(cpus),
    ]

    # UEFI firmware — pflash mode with separate NVRAM for persistent boot vars
    cmd.extend([
        '-drive', f'if=pflash,format=raw,readonly=on,file={ovmf_code}',
        '-drive', f'if=pflash,format=raw,file={nvram_path}',
    ])

    cmd.extend([
        # Disk (virtio for performance, requires virtio-win drivers)
        '-drive', f'file={disk_path},format=qcow2,if=virtio,cache=writeback',
        # Network
        '-netdev', 'user,id=net0',
        '-device', 'virtio-net-pci,netdev=net0',
        # Display — show QEMU window so user can watch install progress
        '-display', 'cocoa' if platform.system() == 'Darwin' else 'gtk',
        # Display — aarch64 needs virtio-gpu-pci for proper GOP framebuffer
        # mapping (bare ramfb causes ConvertPages failures in Windows Boot Manager)
        *arch_params['vga_args'],
        # USB controller (must come before USB devices)
        '-device', 'qemu-xhci',
        '-device', 'usb-tablet',
        '-device', 'usb-kbd',
        # Virtio RNG
        '-device', 'virtio-rng-pci',
    ])

    # CD-ROM drives — aarch64 on HVF cannot boot from USB storage;
    # use virtio-scsi which has built-in edk2 firmware drivers
    if os_def.architecture == 'aarch64':
        cmd.extend([
            '-device', 'virtio-scsi-pci,id=scsi0',
            '-drive', f'file={windows_iso_path},if=none,id=winiso,media=cdrom,readonly=on',
            '-device', 'scsi-cd,drive=winiso,bootindex=0',
            '-drive', f'file={virtio_iso_path},if=none,id=virtioiso,media=cdrom,readonly=on',
            '-device', 'scsi-cd,drive=virtioiso',
        ])
    else:
        cmd.extend([
            '-drive', f'file={windows_iso_path},media=cdrom,index=0',
            '-drive', f'file={virtio_iso_path},media=cdrom,index=1',
        ])

    # Floppy with Autounattend.xml — aarch64 virt machine has no floppy controller
    if os_def.architecture == 'aarch64':
        cmd.extend(['-drive', f'file={floppy_path},format=raw,if=none,id=usbdrive'])
        cmd.extend(['-device', 'usb-storage,drive=usbdrive'])
    else:
        cmd.extend(['-drive', f'file={floppy_path},format=raw,if=floppy'])

    # QMP socket for sending keypresses (needed for "Press any key to boot from CD")
    qmp_sock = Path(tempfile.gettempdir()) / f'adare-qemu-install-{disk_path.stem}.qmp'
    if qmp_sock.exists():
        qmp_sock.unlink()
    cmd.extend(['-qmp', f'unix:{qmp_sock},server,nowait'])

    # CLAUDE: capture firmware serial output for boot debugging
    serial_log = Path(tempfile.gettempdir()) / 'adare-qemu-uefi-serial.log'
    cmd.extend(['-serial', f'file:{serial_log}'])

    log.info(f'Starting QEMU Windows installation: {" ".join(cmd)}')
    log.info(f'CLAUDE: UEFI serial log at {serial_log}')
    print_section('Installation')
    print_step('Starting unattended Windows installation [dim](this may take 30-90 minutes)[/dim]')

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Send repeated keypresses to catch "Press any key to boot from CD or DVD..."
    # Windows Boot Manager on CD media shows this prompt and times out without input.
    keypress_thread = threading.Thread(
        target=repeatedly_send_keypress,
        args=(qmp_sock,),
        kwargs={'interval': 1.0, 'duration': 15.0},
        daemon=True,
    )
    keypress_thread.start()

    try:
        with console.status(f'  [cyan]{disk_path.stem}[/cyan] installing...', spinner='dots') as status:
            wait_for_qemu_exit(
                process,
                timeout_minutes=90,
                label=f'{disk_path.stem} Windows installation',
                status=status,
            )
    except (TimeoutError, subprocess.CalledProcessError):
        raise
    except KeyboardInterrupt:
        console.print('\n  [bold red]Installation interrupted by user[/bold red]')
        process.terminate()
        process.wait(timeout=30)
        raise WindowsVMCreationError('Installation interrupted by user')
