"""GUI-automated VM creation — a vision-LLM agent drives a GUI installer.

Modeled on :mod:`manual_creator`, but the human click-through is replaced by
an autonomous agent (record) or deterministic playbook replay. Unlike the
other creators (raw ``qemu`` subprocess), this one boots the installer as a
libvirt ``QEMUVM`` so the host-side QMP GUI engine (screenshot + mouse +
keyboard) can drive it.

Flow (``_run_installation``):
  1. Boot the installer: QEMUVM with the ISO attached + ``boot_from_cdrom``.
  2. Drive it — replay a cached playbook (no LLM) or record a new one with the
     :class:`GuiAgent`, writing the playbook + a screenshot report.
  3. Stop, flip ``boot_from_cdrom`` off, boot the installed disk.
  4. Run Phase 3b acceptance checks; a failure fails the build.
"""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

import yaml

from adare.config import get_vm_credentials
from adare.config.configdirectory import VM_TEMPLATES_DIR
from adare.config.server import (
    GUI_AGENT_MAX_STEPS,
    GUI_AGENT_STALL_LIMIT,
    GUI_AGENT_WALL_CLOCK_SECONDS,
    VLLM_API_KEY,
    VLLM_BASE_URL,
    VLLM_COORD_SPACE,
    VLLM_MODEL,
)
from adare.console import console, print_section, print_step
from adare.hypervisor.qemu.vm_creator.base_creator import BaseVMCreator, VMCreationError
from adare.hypervisor.qemu.vm_creator.os_catalog import OsDefinition, SetupLevel

log = logging.getLogger(__name__)

_BUNDLED_TEMPLATES_DIR = Path(__file__).parent / 'templates'


class GUIVMCreationError(VMCreationError):
    """Raised when GUI-automated VM creation fails."""

    def __init__(self, detail: str):
        super().__init__(f'GUI-auto: {detail}')


def _template_stems(os_def: OsDefinition, override: str | None) -> list[str]:
    """Candidate basenames for the gui goal/spec + playbook, most specific first."""
    stems: list[str] = []
    if override:
        stems.append(override)
    if os_def.template:
        stems.append(re.sub(r'\.ya?ml$', '', os_def.template))
    # 'kubuntu2404' -> 'kubuntu'
    stems.append(re.sub(r'[-_]?\d.*$', '', os_def.name) or os_def.name)
    stems.append(os_def.distribution)
    # De-duplicate, preserve order.
    seen: set[str] = set()
    return [s for s in stems if s and not (s in seen or seen.add(s))]


class GUIVMCreator(BaseVMCreator):
    """Create a VM by driving its GUI installer with a vision-LLM agent."""

    def __init__(self, *args, record: bool = False, relearn: bool = False,
                 display: bool = False, template: str | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.record = record
        self.relearn = relearn
        self.display = display
        self.template = template

    # -- hooks --------------------------------------------------------------

    def _ensure_iso(self) -> None:
        if self.iso_path is None:
            raise GUIVMCreationError(
                f'ISO required for GUI-automated install. '
                f'Use --iso /path/to/{self.os_def.display_name}.iso'
            )
        if not self.iso_path.is_file():
            raise GUIVMCreationError(f'ISO file not found: {self.iso_path}')

    def _run_installation(self, disk_path: Path, nvram_path: Path | None) -> None:
        goal_spec = self._load_goal_spec()
        playbook_path, is_cached = self._resolve_playbook()

        should_record = self.record or self.relearn or not is_cached
        if should_record and self.relearn and playbook_path.exists():
            print_step(f'[yellow]Discarding cached playbook[/yellow]: {playbook_path}')

        run_dir = disk_path.parent / f'{self.vm_name}_gui'
        run_dir.mkdir(parents=True, exist_ok=True)

        asyncio.run(self._drive(disk_path, goal_spec, playbook_path, should_record, run_dir))

    # -- template / playbook resolution ------------------------------------

    def _load_goal_spec(self) -> dict:
        """Load the record-run goal/acceptance/hints from a bundled/user template."""
        for stem in _template_stems(self.os_def, self.template):
            for root in (VM_TEMPLATES_DIR, _BUNDLED_TEMPLATES_DIR):
                candidate = Path(root) / f'gui_{stem}.yaml'
                if candidate.is_file():
                    log.info('Using GUI goal/spec template: %s', candidate)
                    with candidate.open() as fh:
                        data = yaml.safe_load(fh) or {}
                    if not data.get('goal'):
                        raise GUIVMCreationError(f'Template {candidate} has no "goal"')
                    return data
        raise GUIVMCreationError(
            f'No gui goal/spec template found for {self.os_def.name} '
            f'(looked for gui_<{"|".join(_template_stems(self.os_def, self.template))}>.yaml '
            f'in {VM_TEMPLATES_DIR} and {_BUNDLED_TEMPLATES_DIR})'
        )

    def _resolve_playbook(self) -> tuple[Path, bool]:
        """Return (playbook_path, is_cached).

        Read order for an existing playbook is user dir then bundled; a freshly
        recorded playbook is always written to the user ``VM_TEMPLATES_DIR``.
        """
        stems = _template_stems(self.os_def, self.template)
        primary_stem = stems[0]
        write_path = Path(VM_TEMPLATES_DIR) / f'gui_{primary_stem}.play.yaml'

        for stem in stems:
            for root in (VM_TEMPLATES_DIR, _BUNDLED_TEMPLATES_DIR):
                candidate = Path(root) / f'gui_{stem}.play.yaml'
                if candidate.is_file():
                    return candidate, True
        return write_path, False

    # -- driving ------------------------------------------------------------

    def _make_vm(self, disk_path: Path, boot_from_cdrom: bool):
        from adare.hypervisor.qemu.accel import resolve_accel
        from adare.hypervisor.qemu.manager import QEMUManager

        manager = QEMUManager()
        try:
            username, password = get_vm_credentials(self.os_def.name)
        except (KeyError, ValueError):
            username, password = 'adare', 'adare'

        from adare.hypervisor.qemu.vm import QEMUVM

        accel = resolve_accel(self.os_def.architecture, self.allow_emulation)
        machine = 'virt' if self.os_def.architecture == 'aarch64' else 'pc'
        vm = QEMUVM(
            vm_name=self.vm_name,
            guest_os=self.os_def.name,
            manager=manager,
            username=username,
            password=password,
            executables=manager.executables,
            cpus=self.cpus,
            ram=self.ram_mb,
            machine=machine,
            accel=accel,
            disk_path=str(disk_path),
            architecture=self.os_def.architecture,
            iso_path=str(self.iso_path),
            boot_from_cdrom=boot_from_cdrom,
        )
        # Calamares-class installers need UEFI; profiles declare requires_uefi.
        if self.os_def.requires_uefi or self.os_def.architecture == 'aarch64':
            vm.config.boot_mode = 'uefi'
        vm.config.display_enabled = self.display
        vm._save_vm_config()
        return vm

    async def _drive(self, disk_path: Path, goal_spec: dict, playbook_path: Path,
                     should_record: bool, run_dir: Path) -> None:
        from adare.backend.experiment.execution.qemu_host_gui_executor import QEMUHostGUIExecutor
        from adare.backend.experiment.vlm import (
            GuiAgent,
            PlaybookRecorder,
            VLMClient,
            run_acceptance_checks,
            run_playbook,
        )

        goal = goal_spec['goal']
        acceptance = goal_spec.get('acceptance', {})
        hints = goal_spec.get('hints', [])

        client = self._make_client()

        # ── 1. boot the installer ─────────────────────────────────────────
        print_section('GUI installer boot')
        vm = self._make_vm(disk_path, boot_from_cdrom=True)
        await vm.start()

        try:
            executor = QEMUHostGUIExecutor(vm=vm)
            if should_record:
                if client is None:
                    raise GUIVMCreationError(
                        'Recording a playbook needs a vLLM endpoint. Set ADARE_VLLM_BASE_URL '
                        'or ship a validated playbook alongside the profile.'
                    )
                print_step('[cyan]Recording[/cyan] a new playbook with the vision agent...')
                recorder = PlaybookRecorder(playbook_path, goal=goal)
                agent = GuiAgent(
                    executor, client, goal,
                    acceptance_spec=acceptance, recorder=recorder,
                    run_dir=run_dir, hints=hints, coord_space=VLLM_COORD_SPACE,
                    max_steps=GUI_AGENT_MAX_STEPS, stall_limit=GUI_AGENT_STALL_LIMIT,
                    wall_clock_seconds=GUI_AGENT_WALL_CLOCK_SECONDS,
                )
                result = await agent.run()
                if not result.success:
                    raise GUIVMCreationError(f'agent did not finish: {result.reason}')
                console.print(f'[green]Playbook recorded[/green]: {result.playbook_path}')
            else:
                print_step(f'[cyan]Replaying[/cyan] cached playbook: {playbook_path}')
                replay = await run_playbook(
                    vm, playbook_path, heal=client is not None, client=client,
                    coord_space=VLLM_COORD_SPACE, goal=goal,
                )
                if not replay.success:
                    raise GUIVMCreationError(
                        f'replay failed at {len(replay.failures)} step(s): {replay.failures}'
                    )
                if replay.healed:
                    console.print(f'[yellow]Self-healed steps[/yellow]: {replay.healed}')
        except GUIVMCreationError:
            if self.display:
                console.print('[yellow]Leaving the VM running for inspection (--display).[/yellow]')
            else:
                await vm.stop(force=True)
            raise

        # ── 2. reboot from the installed disk ─────────────────────────────
        print_section('Booting installed system')
        await vm.stop()
        vm.config.boot_from_cdrom = False
        vm._boot_from_cdrom = False
        vm._save_vm_config()
        await vm.start()

        # ── 3. acceptance checks ──────────────────────────────────────────
        try:
            checks = await run_acceptance_checks(
                vm, acceptance, client=client, disk_path=disk_path, run_dir=run_dir,
            )
            console.print(checks.to_markdown())
        finally:
            await vm.stop()

        if not checks.passed:
            raise GUIVMCreationError(
                f'acceptance checks failed — see {run_dir / "acceptance.md"}'
            )

    def _make_client(self):
        from adare.backend.experiment.vlm import VLMClient

        if not VLLM_BASE_URL:
            return None
        return VLMClient(base_url=VLLM_BASE_URL, model=VLLM_MODEL, api_key=VLLM_API_KEY)


def create_gui_vm(
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
    *,
    record: bool = False,
    relearn: bool = False,
    display: bool = False,
    template: str | None = None,
) -> Path:
    """Create a VM by GUI-automating its installer. Records a playbook on the
    first run for a profile, then replays it deterministically thereafter."""
    creator = GUIVMCreator(
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
        record=record,
        relearn=relearn,
        display=display,
        template=template,
    )
    return creator.create()
