"""Environment post-setup steps: one runner, every transport.

An environment's ``postsetupinstallations`` run after boot and before the experiment.
This module is the single place that decides *how* they run, whatever carries the
command into the guest (the WebSocket agent, QEMU guest-agent exec, or the dev-mode
session, which reuses the WebSocket path):

* steps run strictly in list order;
* a step fails on a non-zero exit code, a timeout (``timeout`` or 600 s) or a
  transport error; without ``allow_failure`` the first failure stops the setup and
  raises :class:`~adare.backend.experiment.exceptions.PostSetupStepError`
  (stage and run end FAILED); with ``allow_failure`` it becomes a stage warning and a
  line in the run summary and the run goes on;
* every step (command, rights, cwd, exit code, duration, stdout, stderr) is appended
  to ``<run>/logs/postsetup.log``.

Rights (see :meth:`WebsocketStepExecutor.rights` and :meth:`QgaStepExecutor.rights`):
the VM user by default, root / elevated with ``admin``. The host-side backend plans
the same steps offline (``backend/hostside/session.py``) with the same ``admin`` and
``cwd`` semantics.
"""

import logging
import shlex
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from websockets.exceptions import WebSocketException

from adare.backend.experiment.exceptions import PostSetupStepError
from adare.backend.experiment.websocket_client import WebSocketTimeoutError
from adarelib.constants import StatusEnum

log = logging.getLogger(__name__)

#: Seconds a step may run when it sets no ``timeout`` (installers are slow).
DEFAULT_STEP_TIMEOUT = 600.0
#: Lines of stderr (or stdout) quoted in a failure message.
FAILURE_TAIL_LINES = 20
#: File in the run's ``logs/`` directory.
POSTSETUP_LOG_NAME = 'postsetup.log'

# What QEMU's guest-exec wrapper (hypervisor/qemu/mixins/commands.py) reports when no process
# status came back: -1 with this text. Anything else with -1 is a transport problem or a signal.
_QGA_TIMEOUT_MARKER = 'Timeout'
# What the guest agent (adarevm automation/shell.py) puts in stderr when it kills a command.
_AGENT_TIMEOUT_MARKER = 'timed out after'


@dataclass(frozen=True)
class PostsetupStep:
    """One post-setup step with every optional field resolved."""

    name: str
    command: str
    description: str = ''
    cwd: str | None = None
    shell: bool = False
    admin: bool = False
    allow_failure: bool = False
    timeout: float = DEFAULT_STEP_TIMEOUT


def normalize_step(raw: Any, index: int = 1) -> PostsetupStep:
    """A :class:`PostsetupStep` from a DB row or ``PostsetupInstallations``.

    ``admin``, ``allow_failure`` and ``timeout`` are read defensively: rows stored before
    those fields existed simply do not have them.
    """
    timeout = getattr(raw, 'timeout', None)
    return PostsetupStep(
        name=getattr(raw, 'name', None) or f'Installation {index}',
        command=getattr(raw, 'command', None) or str(raw),
        description=getattr(raw, 'description', None) or '',
        cwd=getattr(raw, 'cwd', None) or None,
        shell=bool(getattr(raw, 'shell', False)),
        admin=bool(getattr(raw, 'admin', False)),
        allow_failure=bool(getattr(raw, 'allow_failure', False)),
        timeout=float(timeout) if timeout else DEFAULT_STEP_TIMEOUT,
    )


@dataclass
class StepExecution:
    """What a transport reports back for one command.

    ``returncode`` is ``None`` when no exit status came back; then ``timed_out`` or
    ``error`` says why.
    """

    returncode: int | None = None
    stdout: str = ''
    stderr: str = ''
    timed_out: bool = False
    error: str | None = None


@dataclass
class PostsetupStepResult:
    """Outcome of one step, as recorded in ``postsetup.log`` and the failure message."""

    step: PostsetupStep
    index: int
    total: int
    rights: str
    execution: StepExecution
    duration_s: float

    @property
    def ok(self) -> bool:
        e = self.execution
        return not e.timed_out and e.error is None and e.returncode == 0

    @property
    def outcome(self) -> str:
        """``ok`` | ``failed`` (non-zero exit) | ``timeout`` | ``error`` (transport)."""
        e = self.execution
        if e.timed_out:
            return 'timeout'
        if e.error is not None:
            return 'error'
        return 'ok' if e.returncode == 0 else 'failed'

    @property
    def detail(self) -> str:
        """How the step ended, in words (``exit code 3``, ``timeout`` ...)."""
        e = self.execution
        if e.timed_out:
            return f'timeout after {self.step.timeout:g}s'
        if e.error is not None:
            return f'transport error: {e.error}'
        return f'exit code {e.returncode}'


class StepExecutor(Protocol):
    """Carries one command into the guest. Implementations never raise for a failed command."""

    def rights(self, step: PostsetupStep) -> str: ...

    async def run(self, step: PostsetupStep, timeout: float, stop_event: Any = None) -> StepExecution: ...


# ---------------------------------------------------------------------------
# Executors
# ---------------------------------------------------------------------------


class WebsocketStepExecutor:
    """Runs steps through the guest agent (``execute_shell``).

    The agent runs elevated (root on Linux, an elevated account on Windows). Without
    ``admin`` it drops to the VM user on Linux; on Windows it is elevated either way
    (the agent does not drop privileges there), which is why ``rights`` says so.

    A step's command is always a shell command line: ``shell`` is a bool in the
    environment definition (it cannot pick an interpreter) and ``shell=False`` would break
    ``&&`` / pipes and, on Linux, ``admin``. So the agent is always asked for a shell.
    """

    def __init__(self, client: Any, guest_platform: str | None = None):
        self._client = client
        self._windows = 'windows' in (guest_platform or '').lower()

    def rights(self, step: PostsetupStep) -> str:
        if self._windows:
            return 'admin (elevated agent; Windows steps are elevated with or without admin)'
        return 'admin (root)' if step.admin else 'user (VM user)'

    async def run(self, step: PostsetupStep, timeout: float, stop_event: Any = None) -> StepExecution:
        try:
            result = await self._client.execute_shell(
                step.command,
                shell=step.shell or True,
                cwd=step.cwd,
                admin=step.admin,
                timeout=timeout,
                websocket_timeout=timeout + 10,
            )
        except WebSocketTimeoutError:
            return StepExecution(timed_out=True)
        except (OSError, ConnectionError, RuntimeError, WebSocketException) as e:
            return StepExecution(error=str(e) or type(e).__name__)

        returncode = result.get('returncode')
        stderr = result.get('stderr') or ''
        if returncode is None:
            return StepExecution(stdout=result.get('stdout') or '', error=result.get('message') or 'no exit status')
        if returncode == -1 and _AGENT_TIMEOUT_MARKER in stderr:
            return StepExecution(returncode, result.get('stdout') or '', stderr, timed_out=True)
        return StepExecution(returncode, result.get('stdout') or '', stderr)


def build_qga_linux_command(command: str, user: str, cwd: str | None = None) -> str:
    """``command`` as the Linux VM *user*: guest-exec runs as root, so drop with ``sudo -u``.

    PATH, DISPLAY and (when known) XAUTHORITY are carried over, like for ``admin`` commands.
    """
    inner = f'cd {shlex.quote(cwd)} && {command}' if cwd else command
    return (
        f'sudo -u {shlex.quote(user)} -H env PATH="$PATH" DISPLAY="${{DISPLAY:-:0}}" '
        f'${{XAUTHORITY:+XAUTHORITY="$XAUTHORITY"}} bash -c {shlex.quote(inner)}'
    )


class QgaStepExecutor:
    """Runs steps through QEMU guest-exec (``vm.run_command``), without the WebSocket agent.

    guest-exec runs as root (Linux) / SYSTEM (Windows). On Linux a step without ``admin``
    is dropped to the VM user with ``sudo -u``; ``admin`` keeps root. On Windows there is
    no such drop (the old behaviour: SYSTEM) and ``admin`` changes nothing.
    """

    def __init__(self, vm: Any):
        self._vm = vm

    @property
    def _windows(self) -> bool:
        return 'windows' in str(getattr(self._vm, 'guest_os', '')).lower()

    def rights(self, step: PostsetupStep) -> str:
        if self._windows:
            return 'admin (QGA runs as SYSTEM; the admin flag has no effect on Windows)'
        return 'admin (root)' if step.admin else f'user ({self._vm.username})'

    async def run(self, step: PostsetupStep, timeout: float, stop_event: Any = None) -> StepExecution:
        if self._windows or step.admin:
            command, cwd = step.command, step.cwd
        else:
            command, cwd = build_qga_linux_command(step.command, self._vm.username, step.cwd), None
        try:
            result = await self._vm.run_command(
                command, silent=False, stop_event=stop_event, cwd=cwd, admin=step.admin, timeout=int(timeout)
            )
        except (OSError, ConnectionError, RuntimeError, TimeoutError) as e:
            return StepExecution(error=str(e) or type(e).__name__)

        stdout, stderr = result.stdout or '', result.stderr or ''
        if result.returncode == -1:
            # -1 is "no exit status": the wrapper's own failures (VM down, no agent socket, wait timeout) or a signal
            if stderr.strip() == _QGA_TIMEOUT_MARKER:
                return StepExecution(timed_out=True)
            return StepExecution(stdout=stdout, error=stderr.strip() or 'command ended without an exit status')
        return StepExecution(result.returncode, stdout, stderr)


# ---------------------------------------------------------------------------
# Log and message
# ---------------------------------------------------------------------------


def tail_lines(text: str, count: int = FAILURE_TAIL_LINES) -> str:
    lines = text.strip().splitlines()
    return '\n'.join(lines[-count:])


def build_failure_message(result: PostsetupStepResult) -> str:
    """The text of a :class:`PostSetupStepError`: step, outcome, duration, last output lines."""
    step, e = result.step, result.execution
    command = step.command if len(step.command) <= 200 else step.command[:200] + ' ...'
    lines = [
        f"Post-setup step '{step.name}' ({result.index}/{result.total}) failed: {result.detail} "
        f'after {result.duration_s:.1f}s.',
        f'Command: {command}',
    ]
    source, text = ('stderr', e.stderr) if e.stderr.strip() else ('stdout', e.stdout)
    if text.strip():
        lines.append(f'Last lines of {source}:')
        lines.extend(f'  {line}' for line in tail_lines(text).splitlines())
    else:
        lines.append('The step produced no output.')
    return '\n'.join(lines)


def format_log_entry(result: PostsetupStepResult, machine: str | None = None) -> str:
    """One ``postsetup.log`` block."""
    step, e = result.step, result.execution
    head = f'=== [{result.index}/{result.total}] {step.name}'
    if machine:
        head += f' (machine {machine})'
    parts = [
        head + ' ===',
        f'command : {step.command}',
        f'rights  : {result.rights}',
        f'cwd     : {step.cwd or "(default)"}',
        f'exit    : {e.returncode if e.returncode is not None else "-"}',
        f'outcome : {result.outcome}' + ('' if result.ok else f' ({result.detail})'),
        f'duration: {result.duration_s:.1f}s',
        '--- stdout ---',
        e.stdout.rstrip('\n'),
        '--- stderr ---',
        e.stderr.rstrip('\n'),
        '',
        '',
    ]
    return '\n'.join(parts)


def format_planned_entry(step: PostsetupStep, index: int, total: int, rights: str, verdict: str) -> str:
    """A ``postsetup.log`` block for the host-side backend: it plans steps offline, nothing runs (no exit code)."""
    return '\n'.join(
        [
            f'=== [{index}/{total}] {step.name} ===',
            f'command : {step.command}',
            f'rights  : {rights}',
            f'cwd     : {step.cwd or "(default)"}',
            f'outcome : {verdict}',
            '',
            '',
        ]
    )


def append_log(log_path: Path | None, text: str) -> None:
    if log_path is None:
        return
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, 'a', encoding='utf-8') as handle:
            handle.write(text)
    except OSError as e:
        log.warning(f'Could not write {log_path}: {e}')


# ---------------------------------------------------------------------------
# The runner
# ---------------------------------------------------------------------------


async def run_postsetup_steps(
    steps: list[PostsetupStep],
    executor: StepExecutor,
    *,
    log_path: Path | None = None,
    stage_ctx: Any = None,
    stop_event: Any = None,
    machine: str | None = None,
) -> list[PostsetupStepResult]:
    """Run ``steps`` in order through ``executor``.

    Returns one result per step that ran. Raises :class:`PostSetupStepError` at the first
    failed step that is not ``allow_failure``; failed-but-allowed steps put a warning on
    ``stage_ctx`` and the run goes on. A set ``stop_event`` (user interrupt) ends the loop
    quietly: the caller's stage handling reports the interruption.
    """
    results: list[PostsetupStepResult] = []
    total = len(steps)
    for index, step in enumerate(steps, 1):
        if stop_event is not None and stop_event.is_set():
            log.info('Post-setup interrupted; remaining steps are not run')
            break
        if stage_ctx is not None:
            stage_ctx.stage.sub_msg = f'[{index}/{total}] {step.name}'
            stage_ctx.set_status(stage_ctx.stage.status)
        log.info(f"Post-setup step [{index}/{total}] '{step.name}': {step.command}")
        if step.description:
            log.info(f'Description: {step.description}')

        rights = executor.rights(step)
        started = time.monotonic()
        execution = await executor.run(step, step.timeout, stop_event)
        result = PostsetupStepResult(step, index, total, rights, execution, time.monotonic() - started)
        if stop_event is not None and stop_event.is_set():
            log.info(f"Post-setup step '{step.name}' was cut short by an interrupt")
            break
        results.append(result)
        append_log(log_path, format_log_entry(result, machine))
        log.debug(f"Post-setup step '{step.name}' stdout: {execution.stdout}")

        if result.ok:
            log.info(f"Post-setup step '{step.name}' completed in {result.duration_s:.1f}s")
            continue

        message = build_failure_message(result)
        if not step.allow_failure:
            raise PostSetupStepError(
                log,
                message,
                step.name,
                [
                    f'Read the full output in logs/{POSTSETUP_LOG_NAME} of the run',
                    'Fix the command, or set `allow_failure: true` on the step if it is optional',
                    'Try the step interactively with `adare dev start`',
                ],
            )
        log.warning(f'{message}\nThe step is allow_failure: continuing.')

    allowed = [r for r in results if not r.ok]
    if allowed and stage_ctx is not None:
        stage_ctx.stage.sub_msg = f'{len(allowed)} step(s) failed (allowed): ' + ', '.join(r.step.name for r in allowed)
        stage_ctx.set_status(StatusEnum.WARNING)
    return results


def summarize_allowed_failures(results: list[PostsetupStepResult]) -> list[str]:
    """One line per failed-but-allowed step, for the run summary."""
    return [
        f"post-setup step '{r.step.name}' failed ({r.detail}) - allowed, run continued" for r in results if not r.ok
    ]


async def run_environment_postsetup(context: Any, stage_ctx: Any, executor: StepExecutor) -> list[PostsetupStepResult]:
    """The environment's post-setup steps for ``context`` (one machine), through ``executor``.

    Writes ``logs/postsetup.log`` in the context's run directory when it has one and records
    failed-but-allowed steps in ``context.postsetup_warnings`` for the run summary.
    """
    import adare.backend.environment.database as environment_database

    installations = environment_database.get_environment_installations(context.environment_ulid)
    if not installations:
        log.info('No installations to execute')
        return []
    steps = [normalize_step(raw, index) for index, raw in enumerate(installations, 1)]

    run_directory = getattr(context, 'experiment_run_directory', None)
    log_path = Path(run_directory.log_directory) / POSTSETUP_LOG_NAME if run_directory is not None else None

    log.info(f'Executing {len(steps)} post-setup step(s) from the environment')
    results = await run_postsetup_steps(
        steps,
        executor,
        log_path=log_path,
        stage_ctx=stage_ctx,
        stop_event=getattr(context, 'user_interrupt_event', None),
        machine=getattr(context, 'machine_key', None),
    )
    warnings = getattr(context, 'postsetup_warnings', None)
    if warnings is not None:
        warnings.extend(summarize_allowed_failures(results))
    log.info('All post-setup steps completed')
    return results
