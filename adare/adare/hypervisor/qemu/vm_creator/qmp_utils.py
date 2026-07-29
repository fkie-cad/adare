"""Shared QEMU utilities -- architecture params, QMP shutdown, and input/exit waiting."""

import hashlib
import json
import logging
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from adare.console import console, print_step
from adare.hypervisor.qemu.accel import resolve_accel
from adare.hypervisor.qemu.vm_creator.os_catalog import OsDefinition

log = logging.getLogger(__name__)

# A Unix-domain socket path lives in `sockaddr_un.sun_path`, which is 104 bytes on
# macOS (108 on Linux) *including* the NUL terminator. Bind with a longer path and
# Python raises `OSError: AF_UNIX path too long` before QEMU even starts.
AF_UNIX_PATH_MAX = 103


def install_qmp_socket_path(disk_stem: str) -> Path:
    """Return a QMP socket path for an install-phase VM that fits AF_UNIX limits.

    The obvious construction — ``gettempdir() / f'adare-qemu-install-{stem}.qmp'``
    — overflows on macOS, where ``TMPDIR`` is a 48-character per-user folder
    (``/var/folders/xx/…/T/``). A recipe base disk is named
    ``<profile>-recipebase-<hash>.partial``, so the full path reached 116 characters
    and every Stage 1 Windows build died with ``AF_UNIX path too long`` before QEMU
    was launched.

    Readability is preferred but not at the cost of working: the full name is used
    when it fits, then a truncated stem plus a digest, then the digest alone, and
    ``/tmp`` is tried as a shorter base directory before giving up. The digest keeps
    concurrent builds of different disks on separate sockets.
    """
    digest = hashlib.sha256(disk_stem.encode()).hexdigest()[:10]
    names = (
        f'adare-qemu-install-{disk_stem}.qmp',
        f'adare-qmp-{disk_stem[:16]}-{digest}.qmp',
        f'adare-qmp-{digest}.qmp',
    )
    bases = [Path(tempfile.gettempdir())]
    if Path('/tmp') not in bases:
        bases.append(Path('/tmp'))

    for base in bases:
        if not (base.is_dir() and os.access(base, os.W_OK)):
            continue
        for name in names:
            candidate = base / name
            if len(str(candidate)) <= AF_UNIX_PATH_MAX:
                return candidate

    raise OSError(
        f'no writable directory yields a QMP socket path within '
        f'{AF_UNIX_PATH_MAX} characters (tried {[str(b) for b in bases]}). '
        f'Set TMPDIR to a short path, e.g. TMPDIR=/tmp.'
    )


def qemu_params_for_arch(os_def: OsDefinition, allow_emulation: bool = False) -> dict:
    """Return architecture-specific QEMU parameters for the GUEST architecture.

    The binary and accelerator are derived from `os_def.architecture`, never
    from the host: on a non-matching host this resolves to the guest's own
    `qemu-system-<arch>` binary under TCG (requires `allow_emulation=True`).

    Returns a dict with keys: exe, machine, cpu, vga_args.
    """
    accel = resolve_accel(os_def.architecture, allow_emulation)
    exe = f'qemu-system-{os_def.architecture}'

    if os_def.architecture == 'aarch64':
        return {
            'exe': exe,
            'machine': f'virt,accel={accel}',
            'cpu': 'host' if accel == 'hvf' else 'max',
            # ramfb for UEFI boot + virtio-gpu-device for viogpudo (UTM guest tools driver).
            # Note: virtio-gpu-PCI causes BSOD — must use virtio-gpu-device (MMIO variant).
            'vga_args': ['-device', 'ramfb', '-device', 'virtio-gpu-device'],
        }
    # x86_64
    return {
        'exe': exe,
        'machine': f'type=q35,accel={accel}',
        'cpu': 'max',
        'vga_args': ['-vga', 'std'],
    }


def wait_for_input_or_exit(process: subprocess.Popen, qmp_sock: Path) -> None:
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
        if send_acpi_shutdown(qmp_sock):
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


def send_keypress_via_qmp(socket_path: Path, key: str = 'ret') -> bool:
    """Send a single keypress to the VM via QMP.

    Args:
        socket_path: Path to the QMP Unix socket.
        key: QEMU key name (e.g. 'ret', 'spc', 'a').

    Returns:
        True if the key was sent successfully, False otherwise.
    """
    max_retries = 10
    for attempt in range(max_retries):
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect(str(socket_path))
            break
        except (ConnectionRefusedError, FileNotFoundError):
            if attempt < max_retries - 1:
                time.sleep(0.5)
            else:
                log.debug('Could not connect to QMP socket for keypress after %d attempts', max_retries)
                return False

    try:
        sock.recv(4096)  # QMP greeting
        sock.sendall(json.dumps({'execute': 'qmp_capabilities'}).encode() + b'\n')
        sock.recv(4096)

        cmd = {'execute': 'send-key', 'arguments': {'keys': [{'type': 'qcode', 'data': key}]}}
        sock.sendall(json.dumps(cmd).encode() + b'\n')
        sock.recv(4096)
        return True
    except (OSError, json.JSONDecodeError) as e:
        log.debug('QMP send-key failed: %s', e)
        return False
    finally:
        sock.close()


def repeatedly_send_keypress(socket_path: Path, interval: float = 1.0,
                             duration: float = 15.0, key: str = 'ret') -> None:
    """Send repeated keypresses to the VM over a period of time.

    Used to catch the "Press any key to boot from CD or DVD..." prompt
    during Windows installation. Runs in the calling thread.

    Args:
        socket_path: Path to the QMP Unix socket.
        interval: Seconds between keypresses.
        duration: Total seconds to keep sending.
        key: QEMU key name to send.
    """
    deadline = time.monotonic() + duration
    while time.monotonic() < deadline:
        send_keypress_via_qmp(socket_path, key)
        time.sleep(interval)


def send_acpi_shutdown(socket_path: Path) -> bool:
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
