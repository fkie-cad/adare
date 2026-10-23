"""Deterministic, LLM-free GUI-installer VM creation (``install_mode: playbook``).

Installs a genuine desktop edition by replaying a fixed keyboard/mouse **playbook**
embedded directly in the OS profile (``install_steps`` / ``verify_steps``) — no
vision model. It boots the installer ISO under raw ``qemu-system`` with a QMP
socket (the same lightweight approach ``linux_creator`` uses, and the native-adare
port of ``scripts/gui-install/``), drives the graphical installer over QMP
(screendump + absolute-tablet click + send-key), then reboots from the installed
disk and verifies.

A single self-contained profile is the whole recipe:

    install_steps drive the installer (ISO booted from CD-ROM), then the VM
    reboots from the installed disk and verify_steps log in + confirm the desktop.

The guest renders at a fixed 1024x768 (``-vga qxl``), so the profiles' pixel
coordinates are stable across hosts. Input goes over QMP whatever the display,
so the QEMU window (shown when there is a desktop session, ``--no-display``
hides it) is only for watching; ``playbook_live`` draws the terminal status.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import socket
import subprocess
import time
from pathlib import Path

from rich.markup import escape

from adare.console import console, print_section, print_step
from adare.hypervisor.qemu.firmware import find_ovmf_firmware
from adare.hypervisor.qemu.vm_creator.base_creator import BaseVMCreator, VMCreationError
from adare.hypervisor.qemu.vm_creator.os_catalog import OsDefinition, SetupLevel
from adare.hypervisor.qemu.vm_creator.playbook_live import fmt_duration, live
from adare.hypervisor.qemu.vm_creator.playbook_provision import (
    AUTOLOGIN_CHECK_LINUX,
    bootstrap_steps,
    provision_steps,
)
from adare.hypervisor.qemu.vm_creator.qga_utils import QgaError, qga_exec, qga_shutdown, qga_wait_ready
from adare.hypervisor.qemu.vm_creator.qmp_utils import qemu_params_for_arch

log = logging.getLogger(__name__)

# char -> (qcode, needs_shift) for type()
_BASE = {
    '\n': ('ret', False),
    ' ': ('spc', False),
    '\t': ('tab', False),
    '-': ('minus', False),
    '=': ('equal', False),
    '.': ('dot', False),
    ',': ('comma', False),
    '/': ('slash', False),
    ';': ('semicolon', False),
    "'": ('apostrophe', False),
    '`': ('grave_accent', False),
    '[': ('bracket_left', False),
    ']': ('bracket_right', False),
    '\\': ('backslash', False),
}
_SHIFTED = {
    '_': 'minus',
    '+': 'equal',
    ':': 'semicolon',
    '"': 'apostrophe',
    '?': 'slash',
    '<': 'comma',
    '>': 'dot',
    '~': 'grave_accent',
    '{': 'bracket_left',
    '}': 'bracket_right',
    '|': 'backslash',
    '!': '1',
    '@': '2',
    '#': '3',
    '$': '4',
    '%': '5',
    '^': '6',
    '&': '7',
    '*': '8',
    '(': '9',
    ')': '0',
}


def _char_to_keys(ch: str) -> tuple[list[str], bool]:
    if ch.isalpha():
        return [ch.lower()], ch.isupper()
    if ch.isdigit():
        return [ch], False
    if ch in _BASE:
        q, sh = _BASE[ch]
        return [q], sh
    if ch in _SHIFTED:
        return [_SHIFTED[ch]], True
    raise ValueError(f'unmapped character {ch!r}')


# A long wait prints a progress line this often, so it never looks hung.
HEARTBEAT_S = 60.0
# A wait_text whose frame has not changed this long is flagged as possibly stuck.
STUCK_S = 600.0
# Guest-agent waits while making the installed desktop ADARE-ready: the console
# bootstrap runs apt update + install; a reboot is a plain desktop boot.
AGENT_BOOTSTRAP_TIMEOUT_S = 900.0
AGENT_REBOOT_TIMEOUT_S = 600.0
AUTOLOGIN_TIMEOUT_S = 180.0


class _Heartbeat:
    """Reports ``waiting for X: elapsed / timeout — detail``.

    On a terminal it updates the live status block on every beat; elsewhere it
    prints a line at most every HEARTBEAT_S.
    """

    def __init__(self, what: str, timeout: float):
        self.what = what
        self.timeout = timeout
        self.start = self._last = time.time()

    def elapsed(self) -> float:
        return time.time() - self.start

    def beat(self, detail: str = '') -> None:
        now = time.time()
        line = f'{self.what}: {fmt_duration(now - self.start)} / {fmt_duration(self.timeout)}'
        line += f' — {detail}' if detail else ''
        if live.active:
            live.detail(line)
            return
        if now - self._last < HEARTBEAT_S:
            return
        self._last = now
        print_step(f'    … {line}')


class PlaybookVMCreationError(VMCreationError):
    def __init__(self, detail: str):
        super().__init__(f'playbook: {detail}')


class _QMP:
    """Minimal synchronous QMP client: screendump, abs mouse, keyboard."""

    def __init__(self, sock_path: str, ppm_path: Path, connect_timeout: float = 60.0):
        self._ppm = str(ppm_path)
        self.s = socket.socket(socket.AF_UNIX)
        deadline = time.time() + connect_timeout
        while True:
            try:
                self.s.connect(sock_path)
                break
            except (FileNotFoundError, ConnectionRefusedError):
                if time.time() > deadline:
                    raise PlaybookVMCreationError(f'QMP socket not ready: {sock_path}')
                time.sleep(0.2)
        self.f = self.s.makefile('r')
        self.f.readline()  # greeting
        self.cmd('qmp_capabilities')

    def cmd(self, execute: str, **args):
        obj = {'execute': execute}
        if args:
            obj['arguments'] = args
        self.s.sendall((json.dumps(obj) + '\n').encode())
        while True:
            resp = json.loads(self.f.readline())
            if 'error' in resp:
                raise PlaybookVMCreationError(f'QMP {execute}: {resp["error"]}')
            if 'return' in resp:
                return resp['return']

    def close(self):
        try:
            self.s.close()
        except OSError:
            pass

    # -- input --
    def key(self, qcodes, shift=False):
        keys = (['shift'] if shift else []) + list(qcodes)
        self.cmd('send-key', keys=[{'type': 'qcode', 'data': k} for k in keys])

    def type_text(self, text: str):
        for ch in text:
            q, sh = _char_to_keys(ch)
            self.key(q, sh)
            time.sleep(0.03)

    def tap(self, x, y, w, h):
        ax = round(x / max(w - 1, 1) * 32767)
        ay = round(y / max(h - 1, 1) * 32767)
        self.cmd(
            'input-send-event',
            events=[
                {'type': 'abs', 'data': {'axis': 'x', 'value': ax}},
                {'type': 'abs', 'data': {'axis': 'y', 'value': ay}},
            ],
        )
        time.sleep(0.1)
        self.cmd('input-send-event', events=[{'type': 'btn', 'data': {'button': 'left', 'down': True}}])
        time.sleep(0.05)
        self.cmd('input-send-event', events=[{'type': 'btn', 'data': {'button': 'left', 'down': False}}])

    def powerdown(self):
        self.cmd('system_powerdown')

    # -- framebuffer --
    def dump(self) -> bytes:
        self.cmd('screendump', filename=self._ppm)
        with open(self._ppm, 'rb') as fh:
            return fh.read()

    def wait_stable(self, settle=20.0, timeout=600.0, poll=3.0, min_elapsed=0.0) -> bool:
        start = time.time()
        deadline = start + timeout
        heartbeat = _Heartbeat(f'waiting for the screen to settle {settle:.0f}s', timeout)
        prev = self.dump()
        stable_since = None
        while time.time() < deadline:
            time.sleep(poll)
            cur = self.dump()
            same = cur == prev
            prev = cur
            if same:
                if stable_since is None:
                    stable_since = time.time()
                elif time.time() - stable_since >= settle and time.time() - start >= min_elapsed:
                    return True
            else:
                stable_since = None
            heartbeat.beat(
                f'still for {fmt_duration(time.time() - stable_since)}' if stable_since else 'screen changing'
            )
        return False


def _as_list(value) -> list[str]:
    if value is None:
        return []
    return [value] if isinstance(value, str) else list(value)


def _want_window(display: bool | None) -> bool:
    """``--display``/``--no-display`` decide; by default show the VM whenever
    there is a desktop session to show it on."""
    if display is not None:
        return display
    if platform.system() == 'Darwin':
        return True
    return bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'))


def _describe(step: dict) -> str:
    """``click_text 'Next' x2  note`` — the step as one line of (escaped) markup."""
    action = step['action']
    text = f' {escape(repr(step["text"]))}' if action in ('click_text', 'wait_text') else ''
    gone = ' gone' if step.get('gone') else ''
    repeat = int(step.get('repeat', 1))
    note = step.get('note', '')
    return f'{action}{text}{gone}' + (f' x{repeat}' if repeat > 1 else '') + (f'  {escape(note)}' if note else '')


class PlaybookVMCreator(BaseVMCreator):
    """Create a VM by replaying a profile's embedded GUI-installer playbook."""

    # Readied inside its own install session (bootstrap + provision + check).
    readiness_pass = False

    def __init__(self, *args, display: bool | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.display = _want_window(display)

    def _ensure_iso(self) -> None:
        if self.iso_path is not None:
            if not self.iso_path.is_file():
                raise PlaybookVMCreationError(f'ISO file not found: {self.iso_path}')
            return
        if self.os_def.iso_url:
            from adare.hypervisor.qemu.vm_creator.linux_creator import _download_and_cache_iso

            self.iso_path = _download_and_cache_iso(self.os_def)
            return
        raise PlaybookVMCreationError(
            f'No ISO for {self.os_def.display_name}. Set iso_url in the profile or pass --iso /path/to/installer.iso'
        )

    def _run_installation(self, disk_path: Path, nvram_path: Path | None) -> None:
        if not self.os_def.install_steps:
            raise PlaybookVMCreationError(f'{self.os_def.name} has install_mode=playbook but no install_steps')
        run_dir = disk_path.parent / f'{self.vm_name}_playbook'
        run_dir.mkdir(parents=True, exist_ok=True)
        sock = run_dir / 'qmp.sock'
        ppm = run_dir / '_frame.ppm'

        # ── 1. boot the installer, replay install_steps ───────────────────
        # install_steps must end by confirming completion on screen (wait_text on
        # the installer's "done" dialog); a still screen alone proves nothing.
        print_section('GUI installer (deterministic playbook)')
        with live.session(f'{self.vm_name} · installer'):
            proc = self._launch(disk_path, self.iso_path, sock, run_dir, nvram_path)
            q = None
            try:
                q = _QMP(str(sock), ppm)
                self._run_steps(q, self.os_def.install_steps, run_dir, 'install')
                # Shut the live session down cleanly so every write to the new
                # disk is flushed, rather than cutting power under it.
                self._shutdown(proc, q, grace=120)
            finally:
                if q:
                    q.close()
                self._stop(proc, sock)

        # ── 2. reboot from the installed disk, verify, make ADARE-ready ───
        # The guest-agent port is there from this boot on, so the agent that
        # the bootstrap installs is started by udev and reachable at once.
        print_section('Booting installed system')
        provision = self.setup_level >= SetupLevel.BASE
        qga_sock = run_dir / 'qga.sock'
        with live.session(f'{self.vm_name} · installed system'):
            proc = self._launch(disk_path, None, sock, run_dir, nvram_path, qga_sock=qga_sock if provision else None)
            if provision:
                self.make_ready_in_session(proc, sock, qga_sock, run_dir, verify_steps=self.os_def.verify_steps)
            else:
                q = None
                try:
                    q = _QMP(str(sock), ppm)
                    if self.os_def.verify_steps:
                        self._run_steps(q, self.os_def.verify_steps, run_dir, 'verify')
                    self._shutdown(proc, q, grace=60)
                finally:
                    if q:
                        q.close()
                    self._stop(proc, sock)
        console.print(f'[green]Playbook install complete[/green] — screenshots in {run_dir}')

    # -- making the installed desktop ADARE-ready ----------------------------
    def make_ready_in_session(
        self, proc, qmp_sock: Path, qga_sock: Path, run_dir: Path, verify_steps: list | None = None
    ) -> None:
        """Make a booted, freshly installed desktop ADARE-ready, then power it off.

        *proc* is a QEMU booted from the installed disk with a QMP socket and a
        guest-agent port. Shared with the manual creator, which boots its disk
        through build_post_install_qemu_cmd and needs only this engine.
        """
        q = None
        try:
            with live.session(f'{self.vm_name} · installed system'):
                q = _QMP(str(qmp_sock), run_dir / '_frame.ppm')
                if verify_steps:
                    self._run_steps(q, verify_steps, run_dir, 'verify')
                self._make_adare_ready(q, qga_sock, run_dir)
                self._shutdown_via_agent(proc, q, qga_sock)
        finally:
            if q:
                q.close()
            self._stop(proc, qmp_sock)
            if qga_sock.exists():
                qga_sock.unlink()

    def _make_adare_ready(self, q: _QMP, qga_sock: Path, run_dir: Path) -> None:
        """Install the guest agent, provision over it, and prove the result.

        See playbook_provision for what is done and why. Each failure raises with
        a screenshot of the guest next to the install screenshots.
        """
        print_section('Making the guest ADARE-ready')
        live.step('\\[bootstrap] installing the guest agent')
        self._run_steps(q, bootstrap_steps(self.os_def), run_dir, 'bootstrap')
        if not self._wait_for_agent(qga_sock, AGENT_BOOTSTRAP_TIMEOUT_S, 'waiting for the guest agent'):
            self._save_shot(q, run_dir / 'bootstrap_FAILED.png')
            raise PlaybookVMCreationError(
                f'the guest agent did not come up within {AGENT_BOOTSTRAP_TIMEOUT_S:.0f}s of installing it from '
                f'the text console (no network in the guest, or the console login failed); '
                f'see {run_dir / "bootstrap_FAILED.png"}'
            )
        print_step('    guest agent is up')

        for step in provision_steps(self.setup_level, self.os_def.architecture):
            print_step(f'{time.strftime("%H:%M:%S")} \\[provision] {escape(step.name)}')
            live.step(f'\\[provision] {escape(step.name)}')
            self._guest_run(q, qga_sock, run_dir, step.name, step.command, step.timeout_minutes * 60.0)

        print_step(f'{time.strftime("%H:%M:%S")} \\[provision] rebooting to check the result')
        live.step('\\[provision] rebooting to check the result')
        qga_shutdown(qga_sock, 'reboot')
        time.sleep(15)
        if not self._wait_for_agent(qga_sock, AGENT_REBOOT_TIMEOUT_S, 'waiting for the guest agent after reboot'):
            self._save_shot(q, run_dir / 'reboot_FAILED.png')
            raise PlaybookVMCreationError(
                f'the guest agent did not come back within {AGENT_REBOOT_TIMEOUT_S:.0f}s after the provisioning '
                f'reboot; see {run_dir / "reboot_FAILED.png"}'
            )
        self._wait_for_autologin(q, qga_sock, run_dir)
        q.wait_stable(settle=8, timeout=120)
        self._save_shot(q, run_dir / 'ready_desktop.png')
        print_step(f'    guest is ADARE-ready — desktop: {run_dir / "ready_desktop.png"}')

    @staticmethod
    def _wait_for_agent(qga_sock: Path, timeout: float, what: str) -> bool:
        heartbeat = _Heartbeat(what, timeout)
        deadline = time.time() + timeout
        while time.time() < deadline:
            if qga_wait_ready(qga_sock, timeout=min(10.0, max(deadline - time.time(), 1.0))):
                return True
            heartbeat.beat()
        return False

    def _guest_run(self, q: _QMP, qga_sock: Path, run_dir: Path, name: str, command: str, timeout: float) -> str:
        """Run one root command in the guest; any failure fails the build."""
        heartbeat = _Heartbeat(name, timeout)
        try:
            rc, out, err = qga_exec(
                qga_sock,
                command,
                shell='bash',
                timeout=timeout,
                progress_callback=lambda _elapsed: heartbeat.beat(),
                progress_interval=5.0 if live.active else HEARTBEAT_S,
            )
        except QgaError as e:
            self._save_shot(q, run_dir / 'provision_FAILED.png')
            raise PlaybookVMCreationError(f'provisioning step {name!r}: {e}') from e
        log.debug('provision %r: exit %s\nstdout:\n%s\nstderr:\n%s', name, rc, out, err)
        if rc != 0:
            self._save_shot(q, run_dir / 'provision_FAILED.png')
            detail = (err or out).strip().splitlines()[-5:]
            raise PlaybookVMCreationError(
                f'provisioning step {name!r} exited {rc}' + (': ' + ' | '.join(detail) if detail else '')
            )
        return out

    def _wait_for_autologin(self, q: _QMP, qga_sock: Path, run_dir: Path) -> None:
        heartbeat = _Heartbeat('waiting for the automatic login', AUTOLOGIN_TIMEOUT_S)
        deadline = time.time() + AUTOLOGIN_TIMEOUT_S
        while time.time() < deadline:
            try:
                rc, _out, _err = qga_exec(qga_sock, AUTOLOGIN_CHECK_LINUX, shell='bash', timeout=30)
            except QgaError as e:
                log.debug('autologin check: %s', e)
                rc = -1
            if rc == 0:
                print_step('    automatic login works')
                return
            heartbeat.beat()
            time.sleep(5)
        self._save_shot(q, run_dir / 'autologin_FAILED.png')
        raise PlaybookVMCreationError(
            f'no desktop session for the guest user {AUTOLOGIN_TIMEOUT_S:.0f}s after the provisioning reboot: '
            f'automatic login is not working; see {run_dir / "autologin_FAILED.png"}'
        )

    def _shutdown_via_agent(self, proc, q: _QMP, qga_sock: Path, grace: float = 180.0) -> None:
        """Clean OS shutdown through the agent: a logged-in desktop may answer
        the ACPI power button with a dialog instead of powering off."""
        print_step(f'Shutting the guest down (up to {grace:.0f}s)')
        live.step('shutting the guest down')
        try:
            qga_exec(qga_sock, 'sync', shell='bash', timeout=120)
        except QgaError as e:
            log.warning('sync before shutdown failed: %s', e)
        qga_shutdown(qga_sock, 'powerdown')
        heartbeat = _Heartbeat('waiting for the guest to power off', grace)
        deadline = time.time() + grace
        while proc.poll() is None and time.time() < deadline:
            time.sleep(2)
            heartbeat.beat()
        if proc.poll() is None:
            print_step('    guest still running, trying the ACPI power button')
            self._shutdown(proc, q, grace=60)

    # -- qemu lifecycle -----------------------------------------------------
    def _launch(self, disk_path, iso_path, sock, run_dir, nvram_path, qga_sock: Path | None = None):
        arch = qemu_params_for_arch(self.os_def)
        needs_uefi = self.os_def.requires_uefi or self.os_def.architecture == 'aarch64'
        cmd = [
            arch['exe'],
            '-machine',
            'pc,accel=kvm:tcg',
            '-cpu',
            'host',
            '-m',
            str(self.ram_mb),
            '-smp',
            str(self.cpus),
            '-drive',
            f'file={disk_path},format=qcow2,if=virtio,cache=writeback',
            '-vga',
            'qxl',
            '-usb',
            '-device',
            'usb-tablet',
            '-netdev',
            'user,id=n0',
            '-device',
            'virtio-net-pci,netdev=n0',
            '-qmp',
            f'unix:{sock},server,nowait',
            '-serial',
            f'file:{run_dir / "serial.log"}',
            '-name',
            f'{self.vm_name} - ADARE playbook (watch only, input is automated)'.replace(',', ',,'),
        ]
        if iso_path is not None:
            cmd += ['-cdrom', str(iso_path), '-boot', 'd']
        if qga_sock is not None:
            if qga_sock.exists():
                qga_sock.unlink()
            cmd += [
                '-device',
                'virtio-serial-pci',
                '-chardev',
                f'socket,path={qga_sock},server=on,wait=off,id=qga0',
                '-device',
                'virtserialport,chardev=qga0,name=org.qemu.guest_agent.0',
            ]
        if needs_uefi and nvram_path is not None:
            ovmf_code, _ = find_ovmf_firmware(self.os_def.architecture)
            cmd[1:1] = [
                '-drive',
                f'if=pflash,format=raw,readonly=on,file={ovmf_code}',
                '-drive',
                f'if=pflash,format=raw,file={nvram_path}',
            ]
        if sock.exists():
            sock.unlink()
        if self.display:
            proc = self._spawn(cmd + ['-display', 'cocoa' if platform.system() == 'Darwin' else 'gtk'], run_dir)
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                live.window = 'VM window open: watch only, the playbook drives mouse and keyboard'
                return proc
            # This QEMU has no GTK/Cocoa UI, or the desktop session refused it.
            print_step(
                f'[yellow]Could not open the VM window ({escape(self._qemu_log_tail(run_dir))}); '
                'continuing headless[/yellow]'
            )
            self.display = False
        live.window = f'headless: no VM window (--display to show one); screenshots in {escape(str(run_dir))}'
        return self._spawn(cmd + ['-display', 'none'], run_dir)

    @staticmethod
    def _spawn(cmd: list[str], run_dir: Path) -> subprocess.Popen:
        """Start QEMU with its output in ``qemu.log``; nothing reads a pipe, and
        a full one (GTK warnings fill it fast) would block QEMU."""
        log.info('playbook qemu: %s', ' '.join(cmd))
        with open(run_dir / 'qemu.log', 'ab') as out:
            return subprocess.Popen(cmd, stdout=out, stderr=subprocess.STDOUT)

    @staticmethod
    def _qemu_log_tail(run_dir: Path) -> str:
        try:
            lines = (run_dir / 'qemu.log').read_text(errors='replace').strip().splitlines()
        except OSError:
            return 'qemu exited'
        return lines[-1] if lines else 'qemu exited'

    @staticmethod
    def _shutdown(proc, q: _QMP, grace: float) -> None:
        """ACPI power-off, waiting up to ``grace`` s; ``_stop`` kills whatever is left.

        A live session may halt on "remove the installation medium, press ENTER"
        after unmounting everything; that is the fallback case and safe to kill.
        """
        print_step(f'Powering the guest down (up to {grace:.0f}s)')
        live.step('powering the guest down')
        try:
            q.powerdown()
        except (PlaybookVMCreationError, OSError):
            return
        heartbeat = _Heartbeat('waiting for the guest to power off', grace)
        deadline = time.time() + grace
        while proc.poll() is None and time.time() < deadline:
            time.sleep(2)
            heartbeat.beat()
        if proc.poll() is None:
            print_step(f'    guest still running after {grace:.0f}s, stopping qemu')

    @staticmethod
    def _stop(proc, sock):
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                proc.kill()
        if Path(sock).exists():
            Path(sock).unlink()

    # -- step engine --------------------------------------------------------
    def _run_steps(self, q: _QMP, steps: list, run_dir: Path, phase: str) -> None:
        """Run *steps*; one line per step, plus the live block on a terminal.

        On a terminal the line is printed when the step ends, with its duration
        and outcome (the live block shows it while it runs). Elsewhere it is
        printed when the step starts and a ``done in`` line follows long steps.
        """
        for i, step in enumerate(steps):
            action = step['action']
            # escape(): Rich would read a bare '[install 07]' as a style tag and drop it.
            header = f'{time.strftime("%H:%M:%S")} {escape(f"[{phase} {i:02d}]")} {_describe(step)}'
            live.step(f'{escape(f"[{phase} {i + 1}/{len(steps)}]")} {_describe(step)}')
            if not live.active:
                print_step(header)
            started = time.time()
            outcome = None
            try:
                for _ in range(int(step.get('repeat', 1))):
                    outcome = self._run_step(q, step, action) or outcome
            except PlaybookVMCreationError as e:
                if live.active:
                    print_step(header)
                # The screen at the moment of failure is what explains it.
                print_step(f'    [red]failed after {fmt_duration(time.time() - started)}:[/red] {escape(str(e))}')
                self._save_shot(q, run_dir / f'{phase}_{i:02d}_FAILED.png')
                raise
            took = fmt_duration(time.time() - started) if action in ('wait_text', 'wait_stable', 'click_text') else ''
            name = step.get('shot') or (step.get('name') if action == 'shot' else None)
            shot = run_dir / f'{phase}_{i:02d}_{name}.png' if name else None
            if live.active:
                if shot:
                    self._save_shot(q, shot, announce=False)
                summary = ', '.join(part for part in (took, outcome, shot and f'shot {shot.name}') if part)
                print_step(header + (f'  [dim]— {summary}[/dim]' if summary else ''))
                continue
            if took:
                print_step(f'    done in {took}' + (f' ({outcome})' if outcome else ''))
            if shot:
                self._save_shot(q, shot)

    def _run_step(self, q: _QMP, step: dict, action: str) -> str | None:
        """Run one step; returns a note for its summary line (e.g. retries)."""
        if action == 'tap':
            q.tap(*step['coords'])
        elif action == 'click_text':
            return self._click_text(q, step)
        elif action == 'wait_text':
            self._wait_text(q, step)
        elif action == 'type':
            q.type_text(step['text'])
        elif action == 'key':
            q.key(step['keys'], shift=step.get('shift', False))
        elif action == 'wait':
            time.sleep(float(step['seconds']))
        elif action == 'wait_stable':
            settled = q.wait_stable(
                settle=float(step.get('settle', 20)),
                timeout=float(step.get('timeout', 600)),
                poll=float(step.get('poll', 3)),
                min_elapsed=float(step.get('min', 0)),
            )
            if not settled:
                if step.get('required', False):
                    raise PlaybookVMCreationError(f'screen never settled within {step.get("timeout", 600)}s')
                return '[yellow]screen never settled, continuing[/yellow]'
        elif action == 'shot':
            pass
        else:
            raise PlaybookVMCreationError(f'unknown step action: {action!r}')
        if action in ('tap', 'key'):
            time.sleep(float(step.get('pause', 0.4)))
        return None

    # -- CV: locate a control by its on-screen label (ADARE cv-server OCR) ---
    def _click_text(self, q: _QMP, step: dict) -> str | None:
        """Find ``step['text']`` on screen via OCR and click it.

        Robust to window position / resolution / installer version — the button
        label is what stays constant. Retries while the target renders. Optional
        ``dx``/``dy`` offset the click from the found center (e.g. to hit the
        input field to the right of a "Your name" label).
        """
        text = step['text']
        mode = step.get('match_mode', 'substring')
        dx, dy = int(step.get('dx', 0)), int(step.get('dy', 0))
        which = int(step.get('index', 0))
        tries = int(step.get('tries', 10))
        interval = float(step.get('interval', 2.0))
        optional = bool(step.get('optional', False))
        frame = b''
        for attempt in range(tries):
            frame = q.dump()
            loc = self._find_text(frame, text, mode, which)
            if loc:
                x, y = loc
                q.tap(x + dx, y + dy, 1024, 768)
                time.sleep(float(step.get('pause', 0.4)))
                return f'{attempt} {"retry" if attempt == 1 else "retries"}' if attempt else None
            live.detail(f'{escape(repr(text))} not on screen yet: attempt {attempt + 1}/{tries}, every {interval:g}s')
            if attempt < tries - 1:
                time.sleep(interval)
        if optional:
            # A screen that only appears conditionally (e.g. the Ubuntu 24.04
            # 'installer update available' prompt). Absent -> just move on.
            return 'optional text not on screen, skipped'
        # What the screen said instead is what explains the failure.
        raise PlaybookVMCreationError(
            f'on-screen text {text!r} not found after {tries} tries; screen: {self._screen_summary(frame)}'
        )

    @classmethod
    def _screen_summary(cls, frame: bytes) -> str:
        try:
            screen = ' | '.join(line.strip() for line in cls._screen_lines(frame) if line.strip())
        except PlaybookVMCreationError as e:
            return f'({e})'
        return (screen[:200] + ('…' if len(screen) > 200 else '')) or '(no text)'

    def _wait_text(self, q: _QMP, step: dict) -> None:
        """Block until one of ``step['text']`` is on screen (or, with ``gone: true``,
        until none is), failing on timeout or as soon as a ``fail_on`` text shows.

        This is how a playbook proves a phase finished — e.g. that the installer
        reached its "Restart Now" dialog — instead of trusting a still screen,
        which an error dialog or a hung progress bar also produces. Matching is
        case-insensitive substring against every OCR line, one OCR pass per poll.
        """
        wanted = [t.lower() for t in _as_list(step['text'])]
        fail_on = [t.lower() for t in _as_list(step.get('fail_on'))]
        gone = bool(step.get('gone', False))
        timeout = float(step.get('timeout', 600))
        interval = float(step.get('interval', 5))
        deadline = time.time() + timeout
        heartbeat = _Heartbeat(f'waiting for {step["text"]!r}' + (' to go away' if gone else ''), timeout)
        prev_frame, frozen_since = None, time.time()
        while True:
            frame = q.dump()
            if frame != prev_frame:
                prev_frame, frozen_since = frame, time.time()
            raw = self._screen_lines(frame)
            lines = [line.lower() for line in raw]
            failed = next((f for f in fail_on if any(f in line for line in lines)), None)
            if failed:
                raise PlaybookVMCreationError(f'failure text {failed!r} on screen')
            present = any(w in line for w in wanted for line in lines)
            if present != gone:
                return
            if time.time() >= deadline:
                state = 'still on screen' if gone else 'never appeared'
                raise PlaybookVMCreationError(f'text {step["text"]!r} {state} after {timeout:.0f}s')
            heartbeat.beat(self._progress_detail(raw, time.time() - frozen_since))
            time.sleep(interval)

    @staticmethod
    def _progress_detail(lines: list[str], frozen_for: float) -> str:
        """What the screen says now, plus a warning once it stopped changing."""
        screen = ' | '.join(line.strip() for line in lines if line.strip())
        screen = escape(screen[:100] + ('…' if len(screen) > 100 else '')) or '(no text)'
        if frozen_for >= STUCK_S:
            return f'[yellow]screen unchanged for {fmt_duration(frozen_for)}, may be stuck[/yellow] — {screen}'
        return f'screen: {screen}'

    @staticmethod
    def _png_b64(ppm_bytes: bytes) -> str:
        import base64
        import io

        from PIL import Image

        buf = io.BytesIO()
        Image.open(io.BytesIO(ppm_bytes)).save(buf, 'PNG')
        return base64.b64encode(buf.getvalue()).decode()

    @classmethod
    def _screen_lines(cls, ppm_bytes: bytes) -> list[str]:
        import asyncio

        from adare_cv_server import server as cv

        result = asyncio.run(cv.get_all_text(screenshot_base64=cls._png_b64(ppm_bytes)))
        if 'error' in result:
            # An empty read would otherwise satisfy a `gone: true` wait.
            raise PlaybookVMCreationError(f'OCR failed: {result["error"]}')
        return [str(item.get('text', '')) for item in result.get('all_text', [])]

    @classmethod
    def _find_text(cls, ppm_bytes: bytes, text: str, mode: str, which: int) -> tuple[int, int] | None:
        import asyncio

        from adare_cv_server import server as cv

        result = asyncio.run(cv.find_text(text=text, screenshot_base64=cls._png_b64(ppm_bytes), match_mode=mode))
        locs = result.get('locations', [])
        if not locs:
            return None
        # Prefer a match whose detected text IS exactly the label (a button),
        # over substring hits where the word appears inside a longer sentence
        # (e.g. a dialog body "If you continue, ...").
        want = text.strip().lower()
        exact = [m for m in locs if str(m.get('text', '')).strip().lower() == want]
        pool = exact or locs
        if which >= len(pool):
            return None
        loc = pool[which]['location']
        return int(loc['x']), int(loc['y'])

    @staticmethod
    def _save_shot(q: _QMP, path: Path, announce: bool = True) -> None:
        try:
            data = q.dump()
        except PlaybookVMCreationError:
            return
        try:
            import io

            from PIL import Image

            Image.open(io.BytesIO(data)).save(path)
        except (ImportError, OSError):
            # ImportError: no Pillow on this host. OSError: Pillow could not
            # decode or write the frame — PIL.UnidentifiedImageError subclasses
            # OSError, as do its write errors. Either way, keep the raw PPM so
            # the frame is not lost.
            path.with_suffix('.ppm').write_bytes(data)
        if announce:
            print_step(f'    shot -> {path}')


def create_playbook_vm(
    os_def: OsDefinition,
    iso_path: Path | None = None,
    vm_name: str | None = None,
    disk_size: str | None = None,
    ram_mb: int | None = None,
    cpus: int | None = None,
    force: bool = False,
    vm_dir: Path | None = None,
    setup_level: SetupLevel = SetupLevel.FULL,
    display: bool | None = None,
) -> Path:
    """Create a VM by replaying the profile's embedded GUI-installer playbook.

    *display* shows the QEMU window (``None``: when a desktop session exists).
    """
    creator = PlaybookVMCreator(
        os_def=os_def,
        vm_name=vm_name,
        disk_size=disk_size,
        ram_mb=ram_mb,
        cpus=cpus,
        force=force,
        vm_dir=vm_dir,
        iso_path=iso_path,
        setup_level=setup_level,
        display=display,
    )
    return creator.create()
