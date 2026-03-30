"""Manual VM creation -- boots QEMU with native display for interactive OS installation."""

import platform
import subprocess
import time
from pathlib import Path

from adare.console import console, print_section, print_step
from adare.hypervisor.qemu.firmware import find_ovmf_firmware
from adare.hypervisor.qemu.vm_creator.base_creator import BaseVMCreator, VMCreationError
from adare.hypervisor.qemu.vm_creator.os_catalog import OsDefinition
from adare.hypervisor.qemu.vm_creator.qmp_utils import (
    qemu_params_for_arch,
    wait_for_input_or_exit,
)

import logging
log = logging.getLogger(__name__)


class ManualVMCreationError(VMCreationError):
    """Raised when manual VM creation fails."""

    def __init__(self, detail: str):
        super().__init__(f"Manual: {detail}")


class ManualVMCreator(BaseVMCreator):
    """Create a VM via interactive installation.

    Boots QEMU with the provided ISO and a native display window, allowing
    the user to perform a manual OS installation.
    """

    def _ensure_iso(self) -> None:
        """Validate the user-supplied ISO path."""
        if self.iso_path is None:
            raise ManualVMCreationError(
                f'ISO required for manual install. '
                f'Use --iso /path/to/{self.os_def.display_name}.iso'
            )
        if not self.iso_path.is_file():
            raise ManualVMCreationError(f'ISO file not found: {self.iso_path}')

    def _run_installation(self, disk_path: Path, nvram_path: Path | None) -> None:
        """Boot QEMU with native display for interactive installation."""
        _run_manual_installation(
            iso_path=self.iso_path,
            disk_path=disk_path,
            os_def=self.os_def,
            ram_mb=self.ram_mb,
            cpus=self.cpus,
            nvram_path=nvram_path,
        )


def create_manual_vm(
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
    """Create a VM via interactive installation.

    Convenience wrapper around ``ManualVMCreator`` for backward compatibility.
    """
    creator = ManualVMCreator(
        os_def=os_def,
        vm_name=vm_name,
        disk_size=disk_size,
        ram_mb=ram_mb,
        cpus=cpus,
        force=force,
        vm_dir=vm_dir,
        iso_path=iso_path,
    )
    return creator.create()


def _run_manual_installation(
    iso_path: Path,
    disk_path: Path,
    os_def: OsDefinition,
    ram_mb: int,
    cpus: int,
    nvram_path: Path | None = None,
) -> None:
    """Boot QEMU with native display for interactive OS installation."""
    arch_params = qemu_params_for_arch(os_def)
    machine = arch_params['machine']
    needs_uefi = os_def.requires_uefi or os_def.architecture == 'aarch64'

    # aarch64 + HVF needs highmem=off for UEFI firmware to enumerate USB boot
    # devices. highmem=off limits addressing to 32 bits — cap RAM at 3 GB to
    # leave room for device MMIO regions (sufficient for installation).
    if os_def.architecture == 'aarch64':
        machine = machine.replace('virt,', 'virt,highmem=off,')
        ram_mb = min(ram_mb, 3072)

    # QMP socket for ACPI shutdown
    qmp_sock_path = disk_path.parent / f'.{disk_path.stem}-qmp.sock'

    cmd = [
        arch_params['exe'],
        '-machine', machine,
        '-cpu', arch_params['cpu'],
        '-m', str(ram_mb),
        '-smp', str(cpus),
        # Disk
        '-drive', f'file={disk_path},format=qcow2,if=virtio,cache=writeback',
        # ISO as CD-ROM
        '-cdrom', str(iso_path),
        # QMP for ACPI shutdown
        '-qmp', f'unix:{qmp_sock_path},server=on,wait=off',
        # Network
        '-netdev', 'user,id=net0',
        '-device', 'virtio-net-pci,netdev=net0',
        # Virtio RNG
        '-device', 'virtio-rng-pci',
        # USB tablet for absolute mouse positioning in native display
        '-device', 'qemu-xhci',
        '-device', 'usb-tablet',
        '-device', 'usb-kbd',
    ]

    # VGA / display — ramfb only during install (virtio-gpu-pci conflicts with
    # firmware console init on aarch64)
    if os_def.architecture == 'aarch64':
        cmd.extend(['-device', 'ramfb'])
    else:
        cmd.extend(arch_params['vga_args'])

    # Native display (platform-specific)
    if platform.system() == 'Darwin':
        cmd.extend(['-display', 'cocoa'])
    else:
        cmd.extend(['-display', 'gtk'])

    # Boot from CD-ROM first (BIOS-style boot order — not used with UEFI/aarch64)
    if os_def.architecture != 'aarch64':
        cmd.extend(['-boot', 'd'])

    # Add UEFI firmware if required
    if needs_uefi and nvram_path is not None:
        ovmf_code, _ = find_ovmf_firmware(os_def.architecture)
        # aarch64 uses -bios mode for reliable USB boot discovery during install;
        # pflash mode with empty NVRAM doesn't scan USB devices on edk2-aarch64
        if os_def.architecture == 'aarch64':
            bios_args = ['-bios', ovmf_code]
        else:
            bios_args = [
                '-drive', f'if=pflash,format=raw,readonly=on,file={ovmf_code}',
                '-drive', f'if=pflash,format=raw,file={nvram_path}',
            ]
        # Insert after '-machine' and its value
        machine_idx = cmd.index('-machine') + 2
        cmd[machine_idx:machine_idx] = bios_args

    log.info(f'Starting QEMU manual installation: {" ".join(cmd)}')

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Check for early QEMU failure (bad args, port conflict, etc.)
    time.sleep(3)
    if process.poll() is not None:
        stderr = process.stderr.read().decode() if process.stderr else ''
        raise ManualVMCreationError(f'QEMU exited immediately (code {process.returncode}): {stderr.strip()}')

    display_backend = 'Cocoa' if platform.system() == 'Darwin' else 'GTK'
    print_section('Interactive Installation')
    console.print(f'  A QEMU [bold]{display_backend}[/bold] window has opened.')
    console.print('  Install the OS manually in the QEMU window.')

    try:
        wait_for_input_or_exit(process, qmp_sock_path)
    finally:
        # Clean up QMP socket
        if qmp_sock_path.exists():
            qmp_sock_path.unlink()

    if process.returncode and process.returncode != 0:
        stderr = process.stderr.read().decode() if process.stderr else ''
        raise ManualVMCreationError(
            f'QEMU exited with code {process.returncode}: {stderr.strip()}'
        )


