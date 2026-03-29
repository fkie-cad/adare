"""Manual VM creation -- boots QEMU with native display for interactive OS installation."""

import json
import platform
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

from adare.config import HYPERVISOR_CONFIGS
from adare.console import console, print_section, print_step
from adare.hypervisor.qemu.firmware import find_ovmf_firmware
from adare.hypervisor.qemu.vm_creator.base_creator import BaseVMCreator, VMCreationError
from adare.hypervisor.qemu.vm_creator.os_catalog import OsDefinition

import logging
log = logging.getLogger(__name__)


def _qemu_params_for_arch(os_def: OsDefinition) -> dict:
    """Return architecture-specific QEMU parameters."""
    host_os = platform.system().lower()

    if os_def.architecture == 'aarch64':
        accel = 'hvf' if host_os == 'darwin' else 'kvm'
        return {
            'exe': 'qemu-system-aarch64',
            'machine': f'virt,accel={accel}',
            'cpu': 'host' if accel == 'hvf' else 'max',
            'vga_args': ['-device', 'virtio-gpu-pci'],
        }
    else:  # x86_64
        accel = HYPERVISOR_CONFIGS['qemu']['default_accel']
        return {
            'exe': HYPERVISOR_CONFIGS['qemu']['qemu_system_exe'],
            'machine': f'type=q35,accel={accel}',
            'cpu': 'max',
            'vga_args': ['-vga', 'std'],
        }


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
    arch_params = _qemu_params_for_arch(os_def)
    needs_uefi = os_def.requires_uefi or os_def.architecture == 'aarch64'

    # QMP socket for ACPI shutdown
    qmp_sock_path = disk_path.parent / f'.{disk_path.stem}-qmp.sock'

    cmd = [
        arch_params['exe'],
        '-machine', arch_params['machine'],
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

    # VGA / display device (architecture-specific)
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
        pflash_args = [
            '-drive', f'if=pflash,format=raw,readonly=on,file={ovmf_code}',
            '-drive', f'if=pflash,format=raw,file={nvram_path}',
        ]
        # Insert after '-machine' and its value
        machine_idx = cmd.index('-machine') + 2
        cmd[machine_idx:machine_idx] = pflash_args

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
        _wait_for_input_or_exit(process, qmp_sock_path)
    finally:
        # Clean up QMP socket
        if qmp_sock_path.exists():
            qmp_sock_path.unlink()

    if process.returncode and process.returncode != 0:
        stderr = process.stderr.read().decode() if process.stderr else ''
        raise ManualVMCreationError(
            f'QEMU exited with code {process.returncode}: {stderr.strip()}'
        )


def _wait_for_input_or_exit(process: subprocess.Popen, qmp_sock: Path) -> None:
    """Wait for either the QEMU process to exit or the user to press Enter.

    Uses daemon threads for concurrent monitoring of process exit and stdin.
    If stdin is not a TTY (piped/non-interactive), only waits for process exit.
    """
    process_exited = threading.Event()
    user_pressed_enter = threading.Event()

    def _watch_process():
        process.wait()
        process_exited.set()

    def _watch_stdin():
        sys.stdin.readline()
        user_pressed_enter.set()

    # Start process watcher
    proc_thread = threading.Thread(target=_watch_process, daemon=True)
    proc_thread.start()

    # Start stdin watcher only if interactive
    if sys.stdin.isatty():
        console.print('  When done, shut down the VM or press [bold]Enter[/bold] to send ACPI shutdown.\n')
        stdin_thread = threading.Thread(target=_watch_stdin, daemon=True)
        stdin_thread.start()
    else:
        console.print('  [dim]Non-interactive mode: waiting for VM to shut down.[/dim]\n')

    try:
        while not process_exited.is_set() and not user_pressed_enter.is_set():
            time.sleep(0.5)
    except KeyboardInterrupt:
        console.print('\n  [yellow]Terminating QEMU...[/yellow]')
        process.terminate()
        process.wait(timeout=30)
        raise

    if user_pressed_enter.is_set() and process.poll() is None:
        print_step('Sending ACPI shutdown...')
        if _send_acpi_shutdown(qmp_sock):
            try:
                process.wait(timeout=120)
                console.print('  [green]VM shut down successfully.[/green]')
            except subprocess.TimeoutExpired:
                console.print('  [yellow]VM did not shut down within 120s, terminating...[/yellow]')
                process.terminate()
                process.wait(timeout=30)
        else:
            console.print('  [yellow]ACPI shutdown failed, terminating QEMU...[/yellow]')
            process.terminate()
            process.wait(timeout=30)
    elif process_exited.is_set():
        console.print('  [dim]VM process exited.[/dim]')


def _send_acpi_shutdown(socket_path: Path) -> bool:
    """Send ACPI powerdown via QMP protocol over a Unix socket.

    Returns:
        True if the command was sent successfully, False otherwise.
    """
    max_retries = 5
    for attempt in range(max_retries):
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(10)
            sock.connect(str(socket_path))
            break
        except (ConnectionRefusedError, FileNotFoundError):
            if attempt < max_retries - 1:
                time.sleep(0.5)
            else:
                log.warning('Could not connect to QMP socket after %d attempts', max_retries)
                return False

    try:
        # Read QMP greeting
        sock.recv(4096)

        # Send qmp_capabilities to enter command mode
        sock.sendall(json.dumps({'execute': 'qmp_capabilities'}).encode() + b'\n')
        sock.recv(4096)

        # Send system_powerdown (ACPI shutdown)
        sock.sendall(json.dumps({'execute': 'system_powerdown'}).encode() + b'\n')
        sock.recv(4096)

        return True
    except (OSError, json.JSONDecodeError) as e:
        log.warning('QMP ACPI shutdown failed: %s', e)
        return False
    finally:
        sock.close()
