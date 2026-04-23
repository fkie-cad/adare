"""Post-install interactive session -- boots a finished VM disk for manual customization."""

import logging
import platform
import subprocess
import time
from pathlib import Path

from adare.console import console, print_section, print_step
from adare.hypervisor.qemu.firmware import find_ovmf_firmware
from adare.hypervisor.qemu.vm_creator.base_creator import VMCreationError
from adare.hypervisor.qemu.vm_creator.os_catalog import OsDefinition
from adare.hypervisor.qemu.vm_creator.qmp_utils import (
    qemu_params_for_arch,
    wait_for_input_or_exit,
)

log = logging.getLogger(__name__)


class InteractiveSessionError(VMCreationError):
    """Raised when the post-install interactive session fails."""

    def __init__(self, detail: str):
        super().__init__(f"Interactive: {detail}")


def run_post_install_session(
    disk_path: Path,
    nvram_path: Path | None,
    os_def: OsDefinition,
    ram_mb: int,
    cpus: int,
) -> None:
    """Boot a finished VM disk image for manual customization.

    Starts QEMU from the installed disk (no ISO, no kernel/initrd, no -no-reboot)
    so the user can install additional software on top of the automated setup.

    Args:
        disk_path: Path to the qcow2 disk image.
        nvram_path: Path to NVRAM file (None if UEFI is not required).
        os_def: OS definition for architecture-specific parameters.
        ram_mb: RAM allocation in MB.
        cpus: Number of CPU cores.
    """
    arch_params = qemu_params_for_arch(os_def)

    # QMP socket for ACPI shutdown
    qmp_sock_path = disk_path.parent / f'.{disk_path.stem}-interactive-qmp.sock'

    cmd = [
        arch_params['exe'],
        '-machine', arch_params['machine'],
        '-cpu', arch_params['cpu'],
        '-m', str(ram_mb),
        '-smp', str(cpus),
        # Boot from installed disk
        '-drive', f'file={disk_path},format=qcow2,if=virtio,cache=writeback',
        # QMP for ACPI shutdown
        '-qmp', f'unix:{qmp_sock_path},server=on,wait=off',
        # Network
        '-netdev', 'user,id=net0',
        '-device', 'virtio-net-pci,netdev=net0',
        # USB tablet/keyboard for native display
        '-device', 'qemu-xhci',
        '-device', 'usb-tablet',
        '-device', 'usb-kbd',
        # Virtio RNG
        '-device', 'virtio-rng-pci',
    ]

    # VGA / display device (architecture-specific)
    cmd.extend(arch_params['vga_args'])

    # Native display (platform-specific)
    if platform.system() == 'Darwin':
        cmd.extend(['-display', 'cocoa'])
    else:
        cmd.extend(['-display', 'gtk'])

    # Add UEFI firmware if required
    needs_uefi = os_def.requires_uefi or os_def.architecture == 'aarch64'
    if needs_uefi and nvram_path is not None:
        ovmf_code, _ = find_ovmf_firmware(os_def.architecture)
        pflash_args = [
            '-drive', f'if=pflash,format=raw,readonly=on,file={ovmf_code}',
            '-drive', f'if=pflash,format=raw,file={nvram_path}',
        ]
        machine_idx = cmd.index('-machine') + 2
        cmd[machine_idx:machine_idx] = pflash_args

    log.info(f'Starting interactive post-install session: {" ".join(cmd)}')

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Check for early QEMU failure
    time.sleep(3)
    if process.poll() is not None:
        stderr = process.stderr.read().decode() if process.stderr else ''
        raise InteractiveSessionError(f'QEMU exited immediately (code {process.returncode}): {stderr.strip()}')

    display_backend = 'Cocoa' if platform.system() == 'Darwin' else 'GTK'
    print_section('Interactive Post-Install Session')
    console.print(f'  A QEMU [bold]{display_backend}[/bold] window has opened.')
    console.print('  Install additional software or configure the VM as needed.')

    try:
        wait_for_input_or_exit(process, qmp_sock_path)
    finally:
        if qmp_sock_path.exists():
            qmp_sock_path.unlink()

    if process.returncode and process.returncode != 0:
        stderr = process.stderr.read().decode() if process.stderr else ''
        raise InteractiveSessionError(
            f'QEMU exited with code {process.returncode}: {stderr.strip()}'
        )

    print_step('[green]Interactive session completed.[/green]')
