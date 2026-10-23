"""Manual VM creation -- boots QEMU with native display for interactive OS installation."""

import logging
import platform
import subprocess
import time
from pathlib import Path

from rich.markup import escape

from adare.console import console, print_section
from adare.hypervisor.qemu.firmware import find_ovmf_firmware
from adare.hypervisor.qemu.vm_creator.base_creator import BaseVMCreator, VMCreationError
from adare.hypervisor.qemu.vm_creator.guest_readiness import GUEST_PASSWORD, GUEST_USER
from adare.hypervisor.qemu.vm_creator.os_catalog import OsDefinition, SetupLevel
from adare.hypervisor.qemu.vm_creator.qmp_utils import (
    qemu_params_for_arch,
    wait_for_input_or_exit,
)

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

    # The unattended pass needs a guest agent the hand install does not have;
    # this creator installs it itself after the install (see _make_manual_install_ready).
    readiness_pass = False

    def _ensure_iso(self) -> None:
        """Validate the user-supplied ISO path."""
        if self.iso_path is None:
            raise ManualVMCreationError(
                f'ISO required for manual install. Use --iso /path/to/{self.os_def.display_name}.iso'
            )
        if not self.iso_path.is_file():
            raise ManualVMCreationError(f'ISO file not found: {self.iso_path}')

    def _run_installation(self, disk_path: Path, nvram_path: Path | None) -> None:
        """Boot QEMU with native display for interactive installation."""
        setup = self.setup_level >= SetupLevel.BASE and self.os_def.platform == 'linux'
        _run_manual_installation(
            iso_path=self.iso_path,
            disk_path=disk_path,
            os_def=self.os_def,
            ram_mb=self.ram_mb,
            cpus=self.cpus,
            nvram_path=nvram_path,
            allow_emulation=self.allow_emulation,
            account_hint=setup,
        )
        if setup:
            self._make_manual_install_ready(disk_path, nvram_path)

    def _make_manual_install_ready(self, disk_path: Path, nvram_path: Path | None) -> None:
        """Install the guest agent into the hand-installed OS and set it up for ADARE.

        Same steps and checks as a playbook install (bootstrap from a text console,
        provisioning over the agent, reboot check), driven by the playbook engine on
        a headless boot of the installed disk. A failure only warns: the install
        itself is the user's work and stays usable; the warning says what to fix.
        """
        from adare.hypervisor.qemu.vm_creator.interactive import build_post_install_qemu_cmd
        from adare.hypervisor.qemu.vm_creator.playbook_creator import PlaybookVMCreator
        from adare.hypervisor.qemu.vm_creator.playbook_provision import DECLARATIVE_DISTRIBUTIONS

        print_section('Setting the guest up for ADARE')
        if self.os_def.distribution in DECLARATIVE_DISTRIBUTIONS:
            _warn_not_ready(DECLARATIVE_DISTRIBUTIONS[self.os_def.distribution])
            return

        run_dir = disk_path.parent / f'{self.vm_name}_setup'
        run_dir.mkdir(parents=True, exist_ok=True)
        qmp_sock, qga_sock = run_dir / 'qmp.sock', run_dir / 'qga.sock'
        for sock in (qmp_sock, qga_sock):
            if sock.exists():
                sock.unlink()
        cmd = build_post_install_qemu_cmd(
            disk_path,
            nvram_path,
            self.os_def,
            self.ram_mb,
            self.cpus,
            qmp_sock_path=qmp_sock,
            qga_sock_path=qga_sock,
            allow_emulation=self.allow_emulation,
            headless=True,
        )
        log.info('Booting the manual install for ADARE setup: %s', ' '.join(cmd))
        engine = PlaybookVMCreator(
            os_def=self.os_def,
            vm_name=self.vm_name,
            ram_mb=self.ram_mb,
            cpus=self.cpus,
            setup_level=self.setup_level,
            allow_emulation=self.allow_emulation,
        )
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            engine.make_ready_in_session(proc, qmp_sock, qga_sock, run_dir)
        except (VMCreationError, OSError) as e:
            _warn_not_ready(
                f'{e}\n'
                f'    Screenshots: {run_dir}\n'
                f'    Did you create the user {GUEST_USER} with password {GUEST_PASSWORD}? ADARE logs in with it.\n'
                f'    Or install qemu-guest-agent, autologin for {GUEST_USER} and no screen lock by hand '
                f'(adare environment extend <env> --interactive), then run `adare vm test`.'
            )
            return
        console.print(f'  [green]Guest is ADARE-ready[/green] — screenshots in {run_dir}')


def create_manual_vm(
    os_def: OsDefinition,
    iso_path: Path,
    vm_name: str | None = None,
    disk_size: str | None = None,
    ram_mb: int | None = None,
    cpus: int | None = None,
    force: bool = False,
    vm_dir: Path | None = None,
    setup_level: SetupLevel = SetupLevel.FULL,
    compress: bool = True,
    allow_emulation: bool = False,
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
        setup_level=setup_level,
        compress=compress,
        allow_emulation=allow_emulation,
    )
    return creator.create()


def _run_manual_installation(
    iso_path: Path,
    disk_path: Path,
    os_def: OsDefinition,
    ram_mb: int,
    cpus: int,
    nvram_path: Path | None = None,
    allow_emulation: bool = False,
    account_hint: bool = False,
) -> None:
    """Boot QEMU with native display for interactive OS installation.

    ``account_hint`` asks for the account ADARE's setup and runtime log in with.
    """
    arch_params = qemu_params_for_arch(os_def, allow_emulation)
    machine = arch_params['machine']
    needs_uefi = os_def.requires_uefi or os_def.architecture == 'aarch64'

    # aarch64 + HVF: keep device MMIO/ECAM/GIC regions below 4 GB so edk2
    # firmware can enumerate PCI and USB devices. Fine-grained highmem-*
    # properties avoid the ~3 GB RAM cap imposed by blanket highmem=off.
    if os_def.architecture == 'aarch64':
        machine = machine.replace('virt,', 'virt,highmem-mmio=off,highmem-ecam=off,highmem-redists=off,')

    # QMP socket for ACPI shutdown
    qmp_sock_path = disk_path.parent / f'.{disk_path.stem}-qmp.sock'

    cmd = [
        arch_params['exe'],
        '-machine',
        machine,
        '-cpu',
        arch_params['cpu'],
        '-m',
        str(ram_mb),
        '-smp',
        str(cpus),
        # Disk
        '-drive',
        f'file={disk_path},format=qcow2,if=virtio,cache=writeback',
        # ISO as CD-ROM
        '-cdrom',
        str(iso_path),
        # QMP for ACPI shutdown
        '-qmp',
        f'unix:{qmp_sock_path},server=on,wait=off',
        # Network
        '-netdev',
        'user,id=net0',
        '-device',
        'virtio-net-pci,netdev=net0',
        # Virtio RNG
        '-device',
        'virtio-rng-pci',
        # USB tablet for absolute mouse positioning in native display
        '-device',
        'qemu-xhci',
        '-device',
        'usb-tablet',
        '-device',
        'usb-kbd',
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
                '-drive',
                f'if=pflash,format=raw,readonly=on,file={ovmf_code}',
                '-drive',
                f'if=pflash,format=raw,file={nvram_path}',
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
    if account_hint:
        console.print(
            f'  Create the user [bold]{GUEST_USER}[/bold] with password [bold]{GUEST_PASSWORD}[/bold] '
            '(an administrator/sudo account): ADARE logs in with it to install its guest agent afterwards.'
        )

    try:
        wait_for_input_or_exit(process, qmp_sock_path)
    finally:
        # Clean up QMP socket
        if qmp_sock_path.exists():
            qmp_sock_path.unlink()

    if process.returncode and process.returncode != 0:
        stderr = process.stderr.read().decode() if process.stderr else ''
        raise ManualVMCreationError(f'QEMU exited with code {process.returncode}: {stderr.strip()}')


def _warn_not_ready(detail: str) -> None:
    console.print(f'  [yellow]The VM is installed but not ADARE-ready:[/yellow] {escape(detail)}')
