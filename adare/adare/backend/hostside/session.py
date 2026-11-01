"""HostsideSession: one agent-free experiment run.

Owns everything the host-side backend does around an unchanged playbook run:

1. **stage** (before first boot): classify every ``command:`` of the playbook and
   of the environment's installations; apply the file-effect ones (class c) to
   the run overlay; fail the run *before boot* on the rest, naming their class.
2. **boot**: start the VM and wait until the screen has settled (no guest agent
   to ask).
3. **run**: the playbook runs through :class:`HostsideClient`; steps are marked
   into the qemufile run directory; ``test:`` actions are *deferred*.
4. **quiesce**: clean (ACPI) shutdown so the disk is consistent; then the
   deferred tests are evaluated against the right filesystem state, pulls are
   extracted, system info is read, the filesystem diff and the agent-footprint
   report are produced - all from the image.

Why tests are deferred, not run at their position: a guest's page cache and
journal are invisible on its disk image, and reading a qcow2 that QEMU is
writing races with it. A test is therefore evaluated against a *state point*:
``initial`` (base image + staged operations; for tests placed before the first
GUI input) or ``final`` (the quiesced overlay). Mid-run test points need the
RAM-first extractor (``LiveGuestFS``).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from adare.backend.hostside import fsdiff
from adare.backend.hostside.client import HostsideClient, HostsideUnsupportedError
from adare.backend.hostside.commands import CLASS_INJECT, CommandPlan, CommandPlanner, guest_tzinfo
from adare.backend.hostside.guestfs import (
    GuestFS,
    GuestFSError,
    OfflineDiskGuestFS,
    PatchedGuestFS,
    StagedOp,
)
from adare.backend.hostside.injector import InjectionError, select_injector
from adare.backend.hostside.markers import NullMarkerSink, open_markers
from adare.exceptions import LoggedException

log = logging.getLogger(__name__)

#: Playbook actions that put input into the GUI: the first of them ends the "initial" state.
_INTERACTION_ACTIONS = ('ClickAction', 'DragAction', 'KeyboardAction', 'ScrollAction', 'GotoAction')

SETTLE_SECONDS = 12.0
#: A frame needs at least this share of non-black pixels to count as a desktop (not "Display output is not active.")
DESKTOP_CONTENT_SHARE = 0.3
MIN_BOOT_SECONDS = 25.0
CONFIRM_AFTER_SECONDS = 6.0


@dataclass
class DeferredTest:
    index: int  # 1-based playbook index
    name: str
    state: str  # 'initial' | 'final'


@dataclass
class HostsideTimings:
    stage_s: float = 0.0
    inject_s: float = 0.0
    boot_wait_s: float = 0.0
    run_s: float = 0.0
    quiesce_s: float = 0.0
    evaluate_s: float = 0.0
    diff_s: float = 0.0
    extra: dict[str, float] = field(default_factory=dict)


class HostsideSession:
    """State and operations of one host-side run (see module docstring)."""

    def __init__(self, context):
        self.context = context
        self.vm: Any = None
        self.markers: Any = NullMarkerSink()
        self.plans: dict[str, CommandPlan] = {}
        self.staged_ops: list[StagedOp] = []
        self.late_ops: list[str] = []
        self.unsupported: list[CommandPlan] = []
        self.deferred: list[DeferredTest] = []
        self.test_states: dict[str, str] = {}
        self.pending_pulls: list[tuple[str, Path]] = []
        self.pull_results: list[dict] = []
        self.timings = HostsideTimings()
        self.guest_tz = guest_tzinfo(None)
        self.injection: dict | None = None
        self.shutdown: dict | None = None
        self.quiesced = False
        self.interaction_index: int | None = None
        self.testfunctions: dict = {}
        self._base_fs: OfflineDiskGuestFS | None = None
        self._initial_fs: PatchedGuestFS | None = None
        self._final_fs: OfflineDiskGuestFS | None = None
        self._stage_time = 0.0
        self._run_started = 0.0
        self.test_results: dict[str, str] = {}
        self.last_diff: dict | None = None
        self.pslist: dict | None = None

    # ------------------------------------------------------------------ paths

    @property
    def run_dir(self) -> Path:
        return Path(self.context.experiment_run_directory.path)

    @property
    def hs_dir(self) -> Path:
        path = self.run_dir / 'hostside'
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def stage_time(self) -> float:
        """Epoch of the start of this run's staging (everything in the guest's logs after it is this run's)."""
        return self._stage_time

    @property
    def overlay(self) -> Path:
        return Path(self.vm.config.disk_path)

    @property
    def base_image(self) -> Path:
        return Path(self.vm.get_base_disk_path())

    # --------------------------------------------------------------- planning

    def _resolver(self):
        """The variable resolution the playbook controller will use (automatic + user variables)."""
        import jinja2

        from adare.backend.experiment.variable_resolver import VariableResolver
        from adare.config import get_vm_credentials
        from adarelib.common.automatic_variables import AutomaticVariables
        from adarelib.common.variables import TimestampMetadata

        playbook = self.context.playbook
        registry = getattr(playbook, 'variables', None)
        vm_os = self.context.guest_platform
        vm_user = get_vm_credentials(vm_os)[0] if vm_os else None
        if vm_os and vm_user:
            automatic = AutomaticVariables.get_automatic_variables(vm_os, vm_user)
            registry = AutomaticVariables.merge_with_user_variables(automatic, registry) if registry else automatic
        env = jinja2.Environment()
        if registry:
            env.filters.update(TimestampMetadata().get_jinja_filters(registry))
        context = registry.to_execution_context(for_tests=False) if registry else {}
        return VariableResolver(variable_registry=registry, jinja_env=env), context, vm_user

    def _users(self, fs: GuestFS) -> dict[str, tuple[int, int]]:
        users: dict[str, tuple[int, int]] = {}
        with contextlib.suppress(GuestFSError):
            for line in fs.read_text('/etc/passwd').splitlines():
                f = line.split(':')
                if len(f) > 3 and f[2].isdigit() and f[3].isdigit():
                    users[f[0]] = (int(f[2]), int(f[3]))
        return users

    def analyze(self, base_fs: GuestFS) -> None:
        """Classify commands and tests; fills :attr:`plans`, :attr:`staged_ops`, :attr:`test_states`."""
        from adare.backend.environment import database as environment_database
        from adare.types.playbook import CommandAction

        users = self._users(base_fs)
        resolver, resolve_ctx, vm_user = self._resolver()
        uid, gid = users.get(vm_user or '', (1000, 1000))
        planner = CommandPlanner(uid=uid, gid=gid, tz=self.guest_tz, now=self._stage_time, users=users)

        # environment installations run before the playbook
        installations = []
        if self.context.environment_ulid:
            installations = environment_database.get_environment_installations(self.context.environment_ulid) or []
        for inst in installations:
            command = getattr(inst, 'command', str(inst))
            plan = planner.plan(command, shell=True, admin=True)
            plan.reason = f"environment installation '{getattr(inst, 'name', '?')}': {plan.reason}".rstrip(': ')
            self._take(plan)

        actions = list(getattr(self.context.playbook, 'actions', []) or [])
        for i, action in enumerate(actions, start=1):
            name = type(action).__name__
            if self.interaction_index is None and name in _INTERACTION_ACTIONS:
                self.interaction_index = i
            if isinstance(action, CommandAction):
                try:
                    resolved = resolver.resolve_action_variables(action, resolve_ctx)
                except (ValueError, KeyError, TypeError, AttributeError) as e:
                    plan = CommandPlan(action.command, 'd', reason=f'cannot resolve variables before boot: {e}')
                    self._take(plan)
                    continue
                plan = planner.plan(
                    resolved.command, shell=bool(resolved.shell), admin=bool(resolved.admin), cwd=resolved.cwd
                )
                if plan.stageable and self.interaction_index is not None and i > self.interaction_index:
                    self.late_ops.append(f'action {i}: {resolved.command!r}')
                self._take(plan, key=resolved.command.strip())
        for i, action in enumerate(actions, start=1):
            if type(action).__name__ == 'ActionTestAction':
                state = 'initial' if (self.interaction_index is None or i < self.interaction_index) else 'final'
                self.test_states.setdefault(action.name, state)

    def _take(self, plan: CommandPlan, key: str | None = None) -> None:
        self.plans[key or plan.command.strip()] = plan
        if plan.category == CLASS_INJECT:
            self.staged_ops.extend(plan.ops)
        else:
            self.unsupported.append(plan)

    def state_of(self, test_name: str) -> str:
        return self.test_states.get(test_name, 'final')

    def preflight_report(self) -> str:
        lines = []
        for plan in self.unsupported:
            lines.append(f"  - class ({plan.category}) {plan.command[:100]!r}: {plan.reason}")
        return '\n'.join(lines)

    # ------------------------------------------------------------------ stage

    async def stage(self) -> None:
        """Before first boot: open markers, plan, preflight, inject (see module docstring)."""
        started = time.monotonic()
        self.vm = self.context.vm
        self._stage_time = time.time()
        ctx = self.context
        images = {'base': str(self.base_image), 'overlay': str(self.overlay)}
        spec = {
            'name': ctx.config.experiment_name,
            'backend': 'hostside',
            'adare_run': ctx.experiment_run_ulid,
            'environment': ctx.config.environment_name,
            'description': 'ADARE host-side (agent-free) experiment run; step markers by the orchestrator',
        }
        self.markers = open_markers(self.run_dir / 'qfm', ctx.experiment_run_ulid or 'adare-run', spec, images)
        self.markers.marker('adare.hostside.stage.start', vm=self.vm.vm_name)

        base_fs = await asyncio.to_thread(OfflineDiskGuestFS, self.overlay)
        try:
            tz_name = None
            with contextlib.suppress(GuestFSError):
                tz_name = base_fs.read_text('/etc/timezone').strip()
            self.guest_tz = guest_tzinfo(tz_name)
            self.analyze(base_fs)

            await asyncio.to_thread(self._load_testfunctions)
            problems = self._test_preflight()
            if self.unsupported or problems:
                text = self.preflight_report() + ''.join(f'\n  - {p}' for p in problems)
                self.markers.marker(
                    'adare.hostside.preflight.failed', unsupported=len(self.unsupported) + len(problems)
                )
                raise LoggedException(
                    log,
                    'Host-side backend pre-flight failed: these cannot run without a component in the guest '
                    f'(see docs/guide/hostside-backend, inventory):\n{text}\n'
                    'Re-run with --backend agent, or move the effect to image build time / the GUI.',
                )
            for note in self.late_ops:
                log.warning(
                    f"Host-side backend: {note} is a file effect that the playbook performs mid-run; it is applied "
                    "before first boot instead (the ordering relative to the GUI steps is lost)."
                )
            if self.staged_ops and os.environ.get('ADARE_HOSTSIDE_SKIP_INJECT'):
                log.warning('ADARE_HOSTSIDE_SKIP_INJECT is set: staged operations are NOT applied (debugging only)')
            elif self.staged_ops:
                injector = select_injector()
                self.markers.marker('adare.hostside.inject.start', engine=injector.name, ops=len(self.staged_ops))
                t0 = time.monotonic()
                try:
                    self.injection = await asyncio.to_thread(injector.apply, self.overlay, self.staged_ops, base_fs)
                except InjectionError as e:
                    raise LoggedException(log, f'Host-side backend: offline injection failed: {e}') from e
                self.timings.inject_s = time.monotonic() - t0
                self.markers.marker(
                    'adare.hostside.inject.end', seconds=round(self.timings.inject_s, 2), **(self.injection or {})
                )
        finally:
            base_fs.close()
        self.timings.stage_s = time.monotonic() - started
        self.markers.marker(
            'adare.hostside.stage.end',
            staged_ops=len(self.staged_ops),
            tests=len(self.test_states),
            interaction_index=self.interaction_index,
        )

    def _load_testfunctions(self) -> None:
        from adare.config.configdirectory import STATE_DIR
        from adarelib.testset.testfunction import import_basictest_subclasses

        path = STATE_DIR / 'testfunctions'
        self.testfunctions = import_basictest_subclasses(directory=path) if path.exists() else {}

    def _test_preflight(self) -> list[str]:
        from adare.backend.hostside.testing import HostsideTestExecutor

        tests = getattr(self.context.playbook, 'tests', None) or []
        return HostsideTestExecutor.validate_offline(tests, self.testfunctions) if tests else []

    # ------------------------------------------------------------------- boot

    async def boot(self) -> None:
        """Start the VM and wait for a settled screen. Replaces the QGA-based readiness wait."""
        from adare.backend.experiment.stagectxmanager import StageCtxManager
        from adare.hypervisor.qemu.boot_watch import BootScreenWatch
        from adare.types.stages import VMDisplayWaitStage, VMStartStage

        ctx = self.context
        timeout = float(os.environ.get('ADARE_VM_READY_TIMEOUT', '420'))
        with StageCtxManager(VMStartStage(), ctx.experiment_run_ulid, ctx.user_interrupt_event) as start_stage:
            self.markers.marker('adare.vm.start')
            await self.vm.start(stop_event=ctx.user_interrupt_event, stage_ctx=start_stage)
        started = time.monotonic()
        watch = BootScreenWatch(self.vm)
        with StageCtxManager(VMDisplayWaitStage(), ctx.experiment_run_ulid, ctx.user_interrupt_event):
            while True:
                if ctx.user_interrupt_event and ctx.user_interrupt_event.is_set():
                    raise LoggedException(log, 'VM boot cancelled by user')
                await watch.sample()
                elapsed = time.monotonic() - started
                if (
                    elapsed >= MIN_BOOT_SECONDS
                    and watch.settled_for() >= SETTLE_SECONDS
                    and watch.content_share() >= DESKTOP_CONTENT_SHARE
                ):
                    break
                if elapsed > timeout:
                    raise LoggedException(
                        log,
                        f'Guest screen did not settle within {timeout:.0f}s (host-side readiness has no guest agent to ask)',
                    )
                await asyncio.sleep(3.0)
        self.timings.boot_wait_s = time.monotonic() - started
        ctx.timestamp_before_vm_start = ctx.timestamp_before_vm_start or datetime.now(UTC)
        self.markers.marker(
            'adare.vm.ready', waited_s=round(self.timings.boot_wait_s, 1), settled_s=round(watch.settled_for(), 1)
        )
        self._run_started = time.monotonic()

    def make_client(self) -> HostsideClient:
        return HostsideClient(self.vm, self)

    # ---------------------------------------------------------- run-time hooks

    def handle_command(self, command: str, *, shell: bool = False, admin: bool = False, cwd: str | None = None) -> dict:
        plan = self.plans.get(command.strip())
        if plan is None:
            raise HostsideUnsupportedError(
                f'command {command[:80]!r} was not discovered by the pre-boot analysis (nested in a block/loop or built '
                'from runtime values); it cannot be staged offline (class d)'
            )
        if plan.category != CLASS_INJECT:
            raise HostsideUnsupportedError(f'class ({plan.category}): {plan.reason}')
        self.markers.marker('adare.command.staged', command=command[:200], ops=len(plan.ops), note=plan.reason or None)
        return {
            'status': 'success',
            'returncode': 0,
            'stdout': '',
            'stderr': '',
            'message': f'staged offline before first boot ({len(plan.ops)} file operation(s))',
            'hostside': {'class': 'c', 'ops': [(o.kind, o.path) for o in plan.ops]},
        }

    def defer_pull(self, guest_path: str, host_path: Path) -> None:
        """Queue a pull for the quiesced image; once quiesced (e.g. an auto-pull after a failed test) read it now."""
        self.pending_pulls.append((guest_path, host_path))
        if self.quiesced:
            self.finalize_pulls()
            return
        self.markers.marker('adare.pull.deferred', path=guest_path)

    def defer_test(self, index: int, name: str) -> None:
        state = self.state_of(name)
        self.deferred.append(DeferredTest(index, name, state))
        self.markers.marker('adare.test.deferred', step=index, test=name, state=state)

    # --------------------------------------------------------------- GuestFS

    def fs_for_test(self, test_name: str) -> GuestFS:
        if self.state_of(test_name) == 'initial':
            return self.initial_fs()
        return self.final_fs()

    def initial_fs(self) -> PatchedGuestFS:
        if self._initial_fs is None:
            self._base_fs = OfflineDiskGuestFS(self.base_image)
            self._initial_fs = PatchedGuestFS(self._base_fs, list(self.staged_ops), now=self._stage_time)
        return self._initial_fs

    def final_fs(self) -> OfflineDiskGuestFS:
        if not self.quiesced:
            raise GuestFSError('the guest is still running: its disk image is only readable after quiesce')
        if self._final_fs is None:
            self._final_fs = OfflineDiskGuestFS(self.overlay)
        return self._final_fs

    # ------------------------------------------------------------- live check

    def sample_processes(self) -> dict | None:
        """Host-side process list of the *running* guest (qemufile VMI layer); writes ``hostside/pslist.json``.

        Opt-in (``ADARE_HOSTSIDE_PSLIST=1``): it pauses the guest for the RAM dump (seconds). It is the
        evidence that no ``adarevm`` (and, with the agent channel removed, no ``qemu-ga``) process ran.
        """
        import re

        from adare.backend.hostside import vmi_bridge

        try:
            result = vmi_bridge.list_processes(self.vm.config.qmp_socket_path, self.base_image)
        except (vmi_bridge.VmiUnavailable, OSError, RuntimeError, ValueError, KeyError) as e:
            log.warning(f'Host-side process list unavailable: {e}')
            self.markers.marker('adare.vmi.pslist.failed', error=str(e)[:200])
            result = {'error': str(e)}
        else:
            rx = re.compile(r'adarevm|qemu-ga|qemu-guest|python', re.I)
            result['agent_like'] = [p for p in result['processes'] if rx.search(p['comm'])]
            self.markers.marker(
                'adare.vmi.pslist',
                processes=len(result['processes']),
                agent_like=len(result['agent_like']),
                paused_s=result['intervention_span_s'],
            )
        (self.hs_dir / 'pslist.json').write_text(json.dumps(result, indent=2))
        self.pslist = result
        return result

    # ------------------------------------------------------------- quiesce

    async def quiesce(self) -> None:
        """Clean shutdown, so the overlay is consistent and safe to read (a stopped VM holds no write lock)."""
        from adare.backend.experiment.stagectxmanager import StageCtxManager
        from adare.types.stages import HostsideQuiesceStage

        ctx = self.context
        self.timings.run_s = time.monotonic() - self._run_started if self._run_started else 0.0
        timeout = int(os.environ.get('ADARE_HOSTSIDE_SHUTDOWN_TIMEOUT', '120'))
        started = time.monotonic()
        if os.environ.get('ADARE_HOSTSIDE_PSLIST', '').lower() in ('1', 'true', 'yes', 'on'):
            await asyncio.to_thread(self.sample_processes)
        with StageCtxManager(HostsideQuiesceStage(), ctx.experiment_run_ulid, cast(Any, None)):
            self.markers.marker('adare.vm.quiesce.start', method='acpi-powerdown', timeout_s=timeout)
            await self._acpi_shutdown(timeout)
        elapsed = time.monotonic() - started
        self.timings.quiesce_s = elapsed
        clean = self.shutdown is not None and self.shutdown.get('clean', False)
        self.quiesced = True
        self.markers.marker('adare.vm.quiesce.end', seconds=round(elapsed, 1), clean=clean)
        if not clean:
            log.warning(
                'Host-side backend: the guest did not shut down cleanly in time and was destroyed; the image may lack '
                'unflushed data and an unreplayed journal (dissect does not replay it). Results are best-effort.'
            )

    async def _acpi_shutdown(self, timeout: int) -> None:
        """ACPI shutdown through the hypervisor layer (libvirt ``shutdown``, polled; destroy after ``timeout``).

        GNOME answers the power button with a "Power Off" dialog, so Enter is sent once after a few
        seconds to confirm it (a user pressing the default button).
        """
        pressed: list[bool] = []

        async def confirm_dialog() -> None:
            await asyncio.sleep(CONFIRM_AFTER_SECONDS)
            await self.vm.send_qmp_keyboard(
                [
                    {'type': 'key', 'data': {'down': True, 'key': {'type': 'qcode', 'data': 'ret'}}},
                    {'type': 'key', 'data': {'down': False, 'key': {'type': 'qcode', 'data': 'ret'}}},
                ]
            )
            pressed.append(True)

        helper = asyncio.create_task(confirm_dialog())
        t0 = time.monotonic()
        try:
            await self.vm.stop(force=False, timeout=timeout)
        finally:
            helper.cancel()
            with contextlib.suppress(asyncio.CancelledError, OSError, RuntimeError, ConnectionError, TimeoutError):
                await helper
        elapsed = time.monotonic() - t0
        # vm.stop() destroys the domain when the graceful path outlasts its timeout
        clean = elapsed < timeout - 2
        self.shutdown = {
            'clean': clean,
            'method': 'acpi' if clean else 'destroy-after-timeout',
            'enter_pressed': bool(pressed),
            'seconds': round(elapsed, 1),
        }

    # ------------------------------------------------------- post-run outputs

    def finalize_pulls(self) -> None:
        fs = self.final_fs()
        pending, self.pending_pulls = self.pending_pulls, []
        for guest_path, host_path in pending:
            try:
                fs.extract(guest_path, host_path)
                size = host_path.stat().st_size if host_path.is_file() else 0
                self.pull_results.append({'src': guest_path, 'dst': str(host_path), 'ok': True, 'size': size})
            except (GuestFSError, OSError) as e:
                self.pull_results.append({'src': guest_path, 'dst': str(host_path), 'ok': False, 'error': str(e)})
                log.error(f'Host-side pull of {guest_path} failed: {e}')
        if self.pull_results:
            self.markers.marker(
                'adare.pull.done', ok=sum(1 for r in self.pull_results if r['ok']), total=len(self.pull_results)
            )

    def collect_system_info(self, output_file: Path) -> bool:
        """Minimal system info from the image (``/etc/os-release``); the agent backend asks the guest."""
        import yaml

        try:
            fs = self.final_fs() if self.quiesced else self.initial_fs()
            osr = {}
            for line in fs.read_text('/etc/os-release').splitlines():
                if '=' in line:
                    k, _, v = line.partition('=')
                    osr[k] = v.strip('"')
            info = {
                'os_info': {
                    'name': osr.get('NAME'),
                    'version_id': osr.get('VERSION_ID'),
                    'version': osr.get('VERSION'),
                    'source': 'offline image (/etc/os-release)',
                },
            }
            output_file.write_text(yaml.safe_dump(info, sort_keys=False))
            return True
        except (GuestFSError, OSError, yaml.YAMLError) as e:
            log.warning(f'Host-side system info failed: {e}')
            return False

    def run_diff(self) -> dict | None:
        """Offline base-vs-overlay diff (called after quiesce, before the overlay is removed)."""
        started = time.monotonic()
        try:
            base = self._base_fs or OfflineDiskGuestFS(self.base_image)
            self._base_fs = base
            result = fsdiff.diff(base, self.final_fs())
        except (GuestFSError, OSError) as e:
            log.warning(f'Host-side filesystem diff failed: {e}')
            return None
        self.timings.diff_s = time.monotonic() - started
        self.last_diff = result
        self.markers.marker(
            'adare.fsdiff', seconds=round(self.timings.diff_s, 1), **{k: len(v) for k, v in result.items()}
        )
        return result

    def close(self) -> None:
        for fs in (self._final_fs, self._base_fs):
            if fs is not None:
                fs.close()
        self.markers.close()

    def to_report(self) -> dict[str, Any]:
        return {
            'backend': 'hostside',
            'staged_ops': [(o.kind, o.path, o.source[:120]) for o in self.staged_ops],
            'injection': self.injection,
            'plans': {
                k[:120]: {'class': p.category, 'ops': len(p.ops), 'note': p.reason} for k, p in self.plans.items()
            },
            'test_states': self.test_states,
            'interaction_index': self.interaction_index,
            'deferred_tests': [d.__dict__ for d in self.deferred],
            'shutdown': self.shutdown,
            'pulls': self.pull_results,
            'timings': {**{k: round(v, 2) for k, v in self.timings.__dict__.items() if isinstance(v, float)}},
            'late_ops': self.late_ops,
        }

    def write_report(self, extra: dict | None = None) -> Path:
        path = self.hs_dir / 'hostside-report.json'
        path.write_text(json.dumps({**self.to_report(), **(extra or {})}, indent=2, default=str))
        return path
