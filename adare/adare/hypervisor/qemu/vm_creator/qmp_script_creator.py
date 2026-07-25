"""Deterministic GUI-installer replay — ``install_mode: gui-script``.

Sits between :mod:`manual_creator` (a human clicks through the installer) and
:mod:`gui_creator` (a vision-LLM agent clicks through it). This creator replays a
hand-calibrated YAML playbook of key/type/tap/wait steps: **no vision model, no CV
server, no ``ADARE_VLLM_*`` configuration**, and the same playbook produces the
same disk on any host with QEMU.

Robustness comes from ``wait_stable`` (see :mod:`qmp_replay`) rather than from
image recognition: each step waits until the guest screen stops changing, so the
replay self-paces to the host instead of relying on fixed sleeps.

Flow (``_run_installation``):
  1. Boot the installer ISO headless, with a QMP socket and ``-vga qxl``.
  2. Replay the playbook's ``install`` steps, saving a screenshot per step.
  3. Power down, reboot from the installed disk, replay the ``verify`` steps.

Playbooks live next to the other templates as ``qmpinstall_<stem>.yaml`` and are
resolved with the same stem lookup ``gui_creator`` uses, so ``template: ubuntu1804``
keeps per-version isolation. Calibrate new coordinates with the authoring tool in
``scripts/gui-install/`` (``--keep-running`` plus ``qmp_drive.py shot``), then drop
the playbook in here for replay.
"""

import logging
import platform
import subprocess
from pathlib import Path

import yaml
from rich.markup import escape

from adare.config.configdirectory import VM_TEMPLATES_DIR
from adare.console import console, print_section, print_step
from adare.hypervisor.qemu.firmware import find_ovmf_firmware
from adare.hypervisor.qemu.vm_creator.base_creator import BaseVMCreator, VMCreationError
from adare.hypervisor.qemu.vm_creator.gui_creator import _template_stems
from adare.hypervisor.qemu.vm_creator.linux_creator import _download_and_cache_iso
from adare.hypervisor.qemu.vm_creator.os_catalog import OsDefinition, SetupLevel
from adare.hypervisor.qemu.vm_creator.qmp_replay import (
    QMPReplayError,
    QMPReplaySession,
    run_steps,
    unlink_socket,
    wait_for_qmp_socket,
)
from adare.hypervisor.qemu.vm_creator.qmp_utils import qemu_params_for_arch

log = logging.getLogger(__name__)

_BUNDLED_TEMPLATES_DIR = Path(__file__).parent / 'templates'

# `-vga std`'s tablet applies a 2x coordinate scaling, which puts every absolute
# click at double the intended offset and makes the right half of the screen
# unreachable. qxl is the adapter every playbook coordinate was calibrated on, so
# it is asserted here rather than left to the profile.
_REQUIRED_VGA = 'qxl'

# Playbook coordinates are pixel offsets and only mean anything at the frame size
# they were recorded at. 1024x768 is what qxl renders for these installers.
_DEFAULT_FRAME = (1024, 768)


class QMPScriptVMCreationError(VMCreationError):
    """Raised when a scripted GUI install fails."""

    def __init__(self, detail: str):
        super().__init__(f'gui-script: {detail}')


class QMPScriptVMCreator(BaseVMCreator):
    """Create a VM by replaying a QMP playbook against its graphical installer."""

    def __init__(self, *args, template: str | None = None, keep_running: bool = False,
                 skip_verify: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self.template = template
        self.keep_running = keep_running
        self.skip_verify = skip_verify

    # ── hooks ────────────────────────────────────────────────────────

    def _ensure_iso(self) -> None:
        """Validate the installer ISO, downloading it when the profile bakes a URL."""
        print_section('ISO & Prerequisites')
        if self.iso_path is not None:
            if not self.iso_path.is_file():
                raise QMPScriptVMCreationError(f'ISO file not found: {self.iso_path}')
            return

        if not self.os_def.iso_url:
            raise QMPScriptVMCreationError(
                f'ISO required for a scripted GUI install of {self.os_def.display_name}. '
                f'Use: adare vm create {self.os_def.name} --iso /path/to/installer.iso'
            )
        # Profiles that bake iso_url/iso_sha256 get the same cache-and-verify
        # path as the unattended creators: cached on hit, re-downloaded on a
        # SHA-256 mismatch, hard failure if the fresh download also mismatches.
        self.iso_path = _download_and_cache_iso(self.os_def)

    def _run_installation(self, disk_path: Path, nvram_path: Path | None) -> None:
        playbook_path, playbook = self._load_playbook()
        print_step(f'Replaying GUI playbook: [dim]{playbook_path}[/dim]')

        frame = self._frame_size(playbook)
        shot_dir = disk_path.parent / f'{self.vm_name}_gui-script'
        sock_path = disk_path.parent / f'.{disk_path.stem}-replay-qmp.sock'
        serial_log = disk_path.parent / f'{disk_path.stem}_install.log'

        install_steps = playbook.get('install') or []
        if not install_steps:
            raise QMPScriptVMCreationError(f'{playbook_path} has no "install" steps')

        self._validate_steps(install_steps, frame, playbook_path)
        verify_steps = playbook.get('verify') or []
        self._validate_steps(verify_steps, frame, playbook_path)

        # ── 1. drive the installer ────────────────────────────────────
        print_section('Scripted GUI installation')
        console.print(
            f'  Replaying [bold]{len(install_steps)}[/bold] steps against the installer '
            f'at {frame[0]}x{frame[1]} [dim](no vision model in the loop)[/dim]'
        )
        warnings = self._replay(
            steps=install_steps,
            disk_path=disk_path,
            nvram_path=nvram_path,
            iso_path=self.iso_path,
            sock_path=sock_path,
            serial_log=serial_log,
            shot_dir=shot_dir / 'install',
            phase='install',
        )

        # ── 2. reboot from the installed disk and verify ──────────────
        if verify_steps and not self.skip_verify:
            print_section('Booting installed system')
            warnings += self._replay(
                steps=verify_steps,
                disk_path=disk_path,
                nvram_path=nvram_path,
                iso_path=None,          # boot the disk, not the ISO
                sock_path=sock_path,
                serial_log=serial_log,
                shot_dir=shot_dir / 'verify',
                phase='verify',
            )
        elif not verify_steps:
            log.warning('%s has no "verify" steps; the installed disk is unchecked',
                        playbook_path)

        console.print(f'\n  Screenshots: [dim]{shot_dir}[/dim]')
        if warnings:
            # A wait_stable timeout does not necessarily mean the install failed,
            # but it does mean a step ran against a screen that never settled —
            # which is exactly how a mis-calibrated coordinate presents.
            console.print('  [yellow]Replay warnings:[/yellow]')
            for warning in warnings:
                console.print(f'    - {warning}')
            console.print(f'  [yellow]Check the screenshots in {shot_dir} before '
                          f'trusting this disk.[/yellow]')

        if credentials := playbook.get('credentials'):
            console.print(f'  Credentials: [dim]{credentials}[/dim]')

    # ── playbook resolution ──────────────────────────────────────────

    def _load_playbook(self) -> tuple[Path, dict]:
        """Find and parse ``qmpinstall_<stem>.yaml``, user dir before bundled."""
        stems = _template_stems(self.os_def, self.template)
        for stem in stems:
            for root in (VM_TEMPLATES_DIR, _BUNDLED_TEMPLATES_DIR):
                candidate = Path(root) / f'qmpinstall_{stem}.yaml'
                if not candidate.is_file():
                    continue
                log.info('Using QMP install playbook: %s', candidate)
                try:
                    data = yaml.safe_load(candidate.read_text())
                except (OSError, yaml.YAMLError) as e:
                    raise QMPScriptVMCreationError(f'could not read {candidate}: {e}') from e
                if not isinstance(data, dict):
                    raise QMPScriptVMCreationError(f'{candidate} is not a YAML mapping')
                return candidate, data

        raise QMPScriptVMCreationError(
            f'no QMP install playbook for {self.os_def.name} (looked for '
            f'qmpinstall_<{"|".join(stems)}>.yaml in {VM_TEMPLATES_DIR} and '
            f'{_BUNDLED_TEMPLATES_DIR})'
        )

    def _frame_size(self, playbook: dict) -> tuple[int, int]:
        vm_block = playbook.get('vm') or {}
        frame = vm_block.get('frame') or {}
        return (
            int(frame.get('width', _DEFAULT_FRAME[0])),
            int(frame.get('height', _DEFAULT_FRAME[1])),
        )

    def _validate_steps(self, steps: list, frame: tuple[int, int], source: Path) -> None:
        """Reject tap coordinates that do not match the playbook's frame.

        A coordinate recorded at a different resolution silently mis-clicks, which
        is far more expensive to diagnose after a 40-minute install than now.
        """
        width, height = frame
        for index, step in enumerate(steps):
            if not isinstance(step, dict):
                raise QMPScriptVMCreationError(f'{source} step {index} is not a mapping')
            if step.get('action') != 'tap':
                continue
            coords = step.get('coords')
            if not isinstance(coords, (list, tuple)) or len(coords) != 4:
                raise QMPScriptVMCreationError(
                    f'{source} step {index}: tap needs coords [x, y, width, height]'
                )
            x, y, step_w, step_h = (int(c) for c in coords)
            if (step_w, step_h) != (width, height):
                raise QMPScriptVMCreationError(
                    f'{source} step {index}: tap coords are for a {step_w}x{step_h} '
                    f'frame but the playbook declares {width}x{height}'
                )
            if not (0 <= x < step_w and 0 <= y < step_h):
                raise QMPScriptVMCreationError(
                    f'{source} step {index}: tap ({x}, {y}) is outside the '
                    f'{step_w}x{step_h} frame'
                )

    # ── QEMU + replay ────────────────────────────────────────────────

    def _qemu_cmd(self, disk_path: Path, nvram_path: Path | None, iso_path: Path | None,
                  sock_path: Path, serial_log: Path) -> list[str]:
        arch_params = qemu_params_for_arch(self.os_def, self.allow_emulation)
        needs_uefi = self.os_def.requires_uefi or self.os_def.architecture == 'aarch64'

        cmd = [
            arch_params['exe'],
            '-machine', arch_params['machine'],
            '-cpu', arch_params['cpu'],
            '-m', str(self.ram_mb),
            '-smp', str(self.cpus),
            '-drive', f'file={disk_path},format=qcow2,if=virtio,cache=writeback',
            # See _REQUIRED_VGA — qxl, never std.
            '-vga', _REQUIRED_VGA,
            # usb-tablet gives absolute pointer coordinates, which is what the
            # playbook's tap coords are expressed in.
            '-device', 'qemu-xhci',
            '-device', 'usb-tablet',
            '-device', 'usb-kbd',
            '-netdev', 'user,id=net0',
            '-device', 'virtio-net-pci,netdev=net0',
            '-device', 'virtio-rng-pci',
            '-qmp', f'unix:{sock_path},server=on,wait=off',
            '-serial', f'file:{serial_log}',
        ]

        # Headless by default: the replay drives the guest over QMP and captures
        # its own screenshots, so a host window is only useful for watching.
        if self.keep_running:
            cmd.extend(['-display', 'cocoa' if platform.system() == 'Darwin' else 'gtk'])
        else:
            cmd.extend(['-display', 'none'])

        if iso_path is not None:
            cmd.extend(['-cdrom', str(iso_path)])
            if self.os_def.architecture != 'aarch64':
                cmd.extend(['-boot', 'd'])

        if needs_uefi and nvram_path is not None:
            ovmf_code, _ = find_ovmf_firmware(self.os_def.architecture)
            pflash_args = [
                '-drive', f'if=pflash,format=raw,readonly=on,file={ovmf_code}',
                '-drive', f'if=pflash,format=raw,file={nvram_path}',
            ]
            machine_idx = cmd.index('-machine') + 2
            cmd[machine_idx:machine_idx] = pflash_args

        return cmd

    def _replay(self, steps: list, disk_path: Path, nvram_path: Path | None,
                iso_path: Path | None, sock_path: Path, serial_log: Path,
                shot_dir: Path, phase: str) -> list[str]:
        """Boot QEMU, replay ``steps``, then power the guest down."""
        unlink_socket(sock_path)
        cmd = self._qemu_cmd(disk_path, nvram_path, iso_path, sock_path, serial_log)
        log.info('Starting QEMU for %s replay: %s', phase, ' '.join(cmd))

        # QEMU's own output goes to a file, not a pipe: an install runs for tens
        # of minutes and nothing here drains a pipe, so a chatty QEMU would fill
        # the buffer and block the guest mid-install.
        qemu_log = disk_path.parent / f'{disk_path.stem}_qemu-{phase}.log'
        session: QMPReplaySession | None = None
        with qemu_log.open('wb') as log_fh:
            process = subprocess.Popen(cmd, stdout=log_fh, stderr=subprocess.STDOUT)
            try:
                wait_for_qmp_socket(sock_path, process, qemu_log=qemu_log)
                session = QMPReplaySession(sock_path)
                return run_steps(
                    session, steps, shot_dir,
                    # Playbook notes are free text; escape them so a stray '['
                    # cannot crash a running install in rich's markup parser.
                    on_progress=lambda label, note: console.print(
                        f'    [dim]{escape(label):<20}[/dim] {escape(note)}'
                    ),
                )
            except QMPReplayError as e:
                raise QMPScriptVMCreationError(
                    f'{phase} replay failed: {e} (QEMU log: {qemu_log})'
                ) from e
            finally:
                self._shut_down(process, session, sock_path, phase)

    def _shut_down(self, process: subprocess.Popen, session: QMPReplaySession | None,
                   sock_path: Path, phase: str) -> None:
        if self.keep_running:
            console.print(
                f'  [yellow]Leaving the VM running after {phase} (--keep-running); '
                f'QMP socket: {sock_path}[/yellow]'
            )
            if session is not None:
                session.close()
            return

        if session is not None:
            try:
                session.powerdown()
            except QMPReplayError as e:
                log.debug('ACPI powerdown after %s failed: %s', phase, e)
            session.close()
            try:
                process.wait(timeout=120)
            except subprocess.TimeoutExpired:
                log.warning('Guest did not power down within 120s after %s; terminating', phase)

        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill()
        unlink_socket(sock_path)


def create_qmp_script_vm(
    os_def: OsDefinition,
    iso_path: Path | None = None,
    vm_name: str | None = None,
    disk_size: str | None = None,
    ram_mb: int | None = None,
    cpus: int | None = None,
    force: bool = False,
    vm_dir: Path | None = None,
    setup_level: SetupLevel = SetupLevel.FULL,
    compress: bool = True,
    allow_emulation: bool = False,
    *,
    template: str | None = None,
    keep_running: bool = False,
    skip_verify: bool = False,
) -> Path:
    """Create a VM by replaying a QMP playbook against its graphical installer."""
    creator = QMPScriptVMCreator(
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
        template=template,
        keep_running=keep_running,
        skip_verify=skip_verify,
    )
    return creator.create()
