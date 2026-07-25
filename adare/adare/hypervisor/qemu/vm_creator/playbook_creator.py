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
coordinates are stable across hosts.
"""
from __future__ import annotations

import json
import logging
import platform
import socket
import subprocess
import time
from pathlib import Path

from adare.console import console, print_section, print_step
from adare.hypervisor.qemu.firmware import find_ovmf_firmware
from adare.hypervisor.qemu.vm_creator.base_creator import BaseVMCreator, VMCreationError
from adare.hypervisor.qemu.vm_creator.os_catalog import OsDefinition, SetupLevel
from adare.hypervisor.qemu.vm_creator.qmp_utils import qemu_params_for_arch

log = logging.getLogger(__name__)

# char -> (qcode, needs_shift) for type()
_BASE = {
    '\n': ('ret', False), ' ': ('spc', False), '\t': ('tab', False),
    '-': ('minus', False), '=': ('equal', False), '.': ('dot', False),
    ',': ('comma', False), '/': ('slash', False), ';': ('semicolon', False),
    "'": ('apostrophe', False), '`': ('grave_accent', False),
    '[': ('bracket_left', False), ']': ('bracket_right', False), '\\': ('backslash', False),
}
_SHIFTED = {
    '_': 'minus', '+': 'equal', ':': 'semicolon', '"': 'apostrophe', '?': 'slash',
    '<': 'comma', '>': 'dot', '~': 'grave_accent', '{': 'bracket_left',
    '}': 'bracket_right', '|': 'backslash', '!': '1', '@': '2', '#': '3', '$': '4',
    '%': '5', '^': '6', '&': '7', '*': '8', '(': '9', ')': '0',
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
        self.cmd('input-send-event', events=[
            {'type': 'abs', 'data': {'axis': 'x', 'value': ax}},
            {'type': 'abs', 'data': {'axis': 'y', 'value': ay}},
        ])
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

    def wait_stable(self, settle=20.0, timeout=600.0, poll=3.0, min_elapsed=0.0):
        start = time.time()
        deadline = start + timeout
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
                    return
            else:
                stable_since = None
        print_step('[yellow]wait_stable timed out[/yellow]')


class PlaybookVMCreator(BaseVMCreator):
    """Create a VM by replaying a profile's embedded GUI-installer playbook."""

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
            f'No ISO for {self.os_def.display_name}. Set iso_url in the profile or '
            f'pass --iso /path/to/installer.iso'
        )

    def _run_installation(self, disk_path: Path, nvram_path: Path | None) -> None:
        if not self.os_def.install_steps:
            raise PlaybookVMCreationError(
                f'{self.os_def.name} has install_mode=playbook but no install_steps'
            )
        run_dir = disk_path.parent / f'{self.vm_name}_playbook'
        run_dir.mkdir(parents=True, exist_ok=True)
        sock = run_dir / 'qmp.sock'
        ppm = run_dir / '_frame.ppm'

        # ── 1. boot the installer, replay install_steps ───────────────────
        print_section('GUI installer (deterministic playbook)')
        proc = self._launch(disk_path, self.iso_path, sock, run_dir, nvram_path)
        try:
            q = _QMP(str(sock), ppm)
            self._run_steps(q, self.os_def.install_steps, run_dir, 'install')
            q.close()
        finally:
            self._stop(proc, sock)

        # ── 2. reboot from the installed disk, verify ─────────────────────
        print_section('Booting installed system')
        proc = self._launch(disk_path, None, sock, run_dir, nvram_path)
        q = None
        try:
            q = _QMP(str(sock), ppm)
            if self.os_def.verify_steps:
                self._run_steps(q, self.os_def.verify_steps, run_dir, 'verify')
            q.powerdown()
            for _ in range(30):
                if proc.poll() is not None:
                    break
                time.sleep(2)
        except PlaybookVMCreationError:
            raise
        finally:
            if q:
                q.close()
            self._stop(proc, sock)
        console.print(f'[green]Playbook install complete[/green] — screenshots in {run_dir}')

    # -- qemu lifecycle -----------------------------------------------------
    def _launch(self, disk_path, iso_path, sock, run_dir, nvram_path):
        arch = qemu_params_for_arch(self.os_def)
        needs_uefi = self.os_def.requires_uefi or self.os_def.architecture == 'aarch64'
        cmd = [
            arch['exe'],
            '-machine', 'pc,accel=kvm:tcg',
            '-cpu', 'host',
            '-m', str(self.ram_mb),
            '-smp', str(self.cpus),
            '-drive', f'file={disk_path},format=qcow2,if=virtio,cache=writeback',
            '-vga', 'qxl',
            '-usb', '-device', 'usb-tablet',
            '-netdev', 'user,id=n0', '-device', 'virtio-net-pci,netdev=n0',
            '-qmp', f'unix:{sock},server,nowait',
            '-serial', f'file:{run_dir / "serial.log"}',
            '-display', 'none',
        ]
        if iso_path is not None:
            cmd += ['-cdrom', str(iso_path), '-boot', 'd']
        if needs_uefi and nvram_path is not None:
            ovmf_code, _ = find_ovmf_firmware(self.os_def.architecture)
            cmd[1:1] = [
                '-drive', f'if=pflash,format=raw,readonly=on,file={ovmf_code}',
                '-drive', f'if=pflash,format=raw,file={nvram_path}',
            ]
        if sock.exists():
            sock.unlink()
        log.info('playbook qemu: %s', ' '.join(cmd))
        return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

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
        for i, step in enumerate(steps):
            action = step['action']
            note = step.get('note', '')
            repeat = int(step.get('repeat', 1))
            print_step(f'[{phase} {i:02d}] {action}' + (f' x{repeat}' if repeat > 1 else '')
                       + (f'  {note}' if note else ''))
            for _ in range(repeat):
                if action == 'tap':
                    q.tap(*step['coords'])
                elif action == 'click_text':
                    self._click_text(q, step)
                elif action == 'type':
                    q.type_text(step['text'])
                elif action == 'key':
                    q.key(step['keys'], shift=step.get('shift', False))
                elif action == 'wait':
                    time.sleep(float(step['seconds']))
                elif action == 'wait_stable':
                    q.wait_stable(settle=float(step.get('settle', 20)),
                                  timeout=float(step.get('timeout', 600)),
                                  poll=float(step.get('poll', 3)),
                                  min_elapsed=float(step.get('min', 0)))
                elif action == 'shot':
                    pass
                else:
                    raise PlaybookVMCreationError(f'unknown step action: {action!r}')
                if action in ('tap', 'key', 'click_text'):
                    time.sleep(float(step.get('pause', 0.4)))
            name = step.get('shot') or (step.get('name') if action == 'shot' else None)
            if name:
                self._save_shot(q, run_dir / f'{phase}_{i:02d}_{name}.png')

    # -- CV: locate a control by its on-screen label (ADARE cv-server OCR) ---
    def _click_text(self, q: _QMP, step: dict) -> None:
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
        for attempt in range(tries):
            loc = self._find_text(q.dump(), text, mode, which)
            if loc:
                x, y = loc
                q.tap(x + dx, y + dy, 1024, 768)
                return
            time.sleep(interval)
        raise PlaybookVMCreationError(f'on-screen text {text!r} not found after {tries} tries')

    @staticmethod
    def _find_text(ppm_bytes: bytes, text: str, mode: str, which: int) -> tuple[int, int] | None:
        import asyncio
        import base64
        import io
        from PIL import Image
        from adare_cv_server import server as cv

        buf = io.BytesIO()
        Image.open(io.BytesIO(ppm_bytes)).save(buf, 'PNG')
        b64 = base64.b64encode(buf.getvalue()).decode()
        result = asyncio.run(cv.find_text(text=text, screenshot_base64=b64, match_mode=mode))
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
    def _save_shot(q: _QMP, path: Path) -> None:
        try:
            data = q.dump()
        except PlaybookVMCreationError:
            return
        try:
            from PIL import Image
            import io
            Image.open(io.BytesIO(data)).save(path)
        except Exception:
            path.with_suffix('.ppm').write_bytes(data)
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
) -> Path:
    """Create a VM by replaying the profile's embedded GUI-installer playbook."""
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
    )
    return creator.create()
