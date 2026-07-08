"""Post-install interactive session -- boots a finished VM disk for manual customization."""

import logging
import platform
import subprocess
import time
import uuid
from pathlib import Path

from adare.console import console, print_section, print_step
from adare.hypervisor.qemu.firmware import find_ovmf_firmware
from adare.hypervisor.qemu.vm_creator.base_creator import VMCreationError
from adare.hypervisor.qemu.vm_creator.extend_console import run_extend_console
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


# macOS AF_UNIX sun_path limit is 104 bytes; Linux allows 108. Use the stricter
# bound so interactive-extend works on macOS long temp dirs ($TMPDIR ≈ 49 chars).
_QMP_SOCK_LIMIT = 104


def _interactive_socket(disk_path: Path, kind: str) -> Path:
    """Unix socket path for an interactive-session channel (`kind` = 'qmp'/'qga').

    Co-located with the disk when it fits the Unix socket limit; otherwise
    falls back to ADARE's managed run dir so long temp-disk paths (e.g.
    `env extend` under macOS's /var/folders/... TMPDIR) don't blow the limit.
    """
    preferred = disk_path.parent / f'.{disk_path.stem}-interactive-{kind}.sock'
    if len(str(preferred)) < _QMP_SOCK_LIMIT:
        return preferred
    run_dir = Path.home() / '.adare' / 'qemu' / 'run'
    run_dir.mkdir(parents=True, exist_ok=True)
    fallback = run_dir / f'.interactive-{uuid.uuid4().hex[:8]}.{kind}'
    if len(str(fallback)) >= _QMP_SOCK_LIMIT:
        raise InteractiveSessionError(
            f'{kind.upper()} socket path too long ({len(str(fallback))} >= '
            f'{_QMP_SOCK_LIMIT} chars): {fallback}'
        )
    return fallback


def run_post_install_session(
    disk_path: Path,
    nvram_path: Path | None,
    os_def: OsDefinition,
    ram_mb: int,
    cpus: int,
    console_mode: bool = False,
) -> list[dict]:
    """Boot a finished VM disk image for manual customization.

    Starts QEMU from the installed disk (no ISO, no kernel/initrd, no -no-reboot)
    so the user can install additional software on top of the automated setup.

    With ``console_mode`` (used by `env extend --interactive`) a QEMU guest-agent
    channel is added and an interactive console runs in the terminal alongside
    the GUI window, recording the commands the user runs. Without it (the default,
    used by `vm create --interactive`) the legacy press-Enter GUI wait is used and
    no recording is produced.

    Args:
        disk_path: Path to the qcow2 disk image.
        nvram_path: Path to NVRAM file (None if UEFI is not required).
        os_def: OS definition for architecture-specific parameters.
        ram_mb: RAM allocation in MB.
        cpus: Number of CPU cores.
        console_mode: If True, attach the guest-agent console and record commands.

    Returns:
        The commands the user ran in the console, as install dicts to record as
        the new environment's post-setup installations. Always empty when
        ``console_mode`` is False.
    """
    arch_params = qemu_params_for_arch(os_def)

    # QMP socket for ACPI shutdown; QGA socket only when the console is used.
    qmp_sock_path = _interactive_socket(disk_path, 'qmp')
    qga_sock_path = _interactive_socket(disk_path, 'qga') if console_mode else None

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
    ]

    # QEMU guest agent channel (virtio-serial) for the interactive console.
    if console_mode:
        cmd += [
            '-chardev', f'socket,path={qga_sock_path},server=on,wait=off,id=qga0',
            '-device', 'virtio-serial',
            '-device', 'virtserialport,chardev=qga0,name=org.qemu.guest_agent.0',
        ]

    cmd += [
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
    if console_mode:
        console.print('  Use the window for GUI-only steps; use the console below to run commands.')
    else:
        console.print('  Install additional software or configure the VM as needed.')

    recorded: list[dict] = []
    windows = 'windows' in (os_def.platform or '').lower()
    try:
        if console_mode:
            recorded = run_extend_console(
                qga_sock_path, qmp_sock_path, process, windows=windows
            )
        else:
            wait_for_input_or_exit(process, qmp_sock_path)
    finally:
        for sock in (qmp_sock_path, qga_sock_path):
            if sock is not None and sock.exists():
                sock.unlink()

    if process.returncode and process.returncode != 0:
        stderr = process.stderr.read().decode() if process.stderr else ''
        raise InteractiveSessionError(
            f'QEMU exited with code {process.returncode}: {stderr.strip()}'
        )

    print_step('[green]Interactive session completed.[/green]')
    return recorded
