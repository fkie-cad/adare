"""Environment post-setup steps: runner, transports, log file and failure policy."""

import logging
import shlex
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from adare.backend.experiment import postsetup
from adare.backend.experiment.agent_lifecycle import execute_installations_via_qga, execute_installations_via_websocket
from adare.backend.experiment.exceptions import PostSetupStepError
from adare.backend.experiment.postsetup import (
    DEFAULT_STEP_TIMEOUT,
    PostsetupStep,
    QgaStepExecutor,
    StepExecution,
    WebsocketStepExecutor,
    build_qga_linux_command,
    normalize_step,
    run_postsetup_steps,
)
from adare.backend.experiment.stagectxmanager import StageCtxManager
from adare.backend.experiment.websocket_client import WebSocketTimeoutError
from adare.types.stages import InstallationsStage
from adarelib.constants import StatusEnum

pytestmark = pytest.mark.unit

LOG = logging.getLogger('test_postsetup')


class ScriptedExecutor:
    """Executor returning scripted outcomes (by step name) and recording what it was asked."""

    def __init__(self, outcomes=None):
        self.outcomes = outcomes or {}
        self.calls = []

    def rights(self, step):
        return 'admin' if step.admin else 'user'

    async def run(self, step, timeout, stop_event=None):
        self.calls.append((step, timeout))
        return self.outcomes.get(step.name, StepExecution(0, 'out', ''))


class FakeStageCtx:
    def __init__(self):
        self.stage = InstallationsStage()
        self.statuses = []

    def set_status(self, status):
        self.stage.status = status
        self.statuses.append(status)


def step(name, command='true', **kw):
    return PostsetupStep(name=name, command=command, **kw)


# ---------------------------------------------------------------- normalize


def test_normalize_step_defaults_for_rows_without_new_fields():
    raw = SimpleNamespace(name='n', command='c', description=None, cwd='', shell=False)
    s = normalize_step(raw)
    assert (s.admin, s.allow_failure, s.cwd, s.timeout) == (False, False, None, DEFAULT_STEP_TIMEOUT)


def test_normalize_step_reads_new_fields():
    raw = SimpleNamespace(name='n', command='c', cwd='/x', admin=True, allow_failure=True, timeout=30)
    s = normalize_step(raw)
    assert (s.admin, s.allow_failure, s.cwd, s.timeout) == (True, True, '/x', 30.0)


# ------------------------------------------------------------------- runner


@pytest.mark.asyncio
async def test_steps_run_in_order_with_their_timeout(tmp_path):
    ex = ScriptedExecutor()
    steps = [step('a'), step('b', timeout=5.0), step('c')]
    results = await run_postsetup_steps(steps, ex)
    assert [r.step.name for r in results] == ['a', 'b', 'c']
    assert [(s.name, t) for s, t in ex.calls] == [('a', 600.0), ('b', 5.0), ('c', 600.0)]
    assert all(r.ok for r in results)


@pytest.mark.asyncio
async def test_failure_stops_setup_and_names_step_exit_and_stderr_tail():
    stderr = '\n'.join(f'line {i}' for i in range(30))
    ex = ScriptedExecutor({'bad': StepExecution(7, 'some stdout', stderr)})
    with pytest.raises(PostSetupStepError) as err:
        await run_postsetup_steps([step('ok1'), step('bad', 'apt-get x'), step('never')], ex)
    msg = err.value.message
    assert "'bad' (2/3)" in msg and 'exit code 7' in msg and 'apt-get x' in msg
    assert 'Last lines of stderr' in msg and 'line 29' in msg and 'line 10' in msg
    assert 'line 9\n' not in msg  # only the last 20 lines
    assert 'some stdout' not in msg
    assert [s.name for s, _ in ex.calls] == ['ok1', 'bad']  # 'never' did not run


@pytest.mark.asyncio
async def test_failure_message_falls_back_to_stdout():
    ex = ScriptedExecutor({'bad': StepExecution(1, 'only stdout here', '')})
    with pytest.raises(PostSetupStepError) as err:
        await run_postsetup_steps([step('bad')], ex)
    assert 'Last lines of stdout' in err.value.message and 'only stdout here' in err.value.message


@pytest.mark.asyncio
async def test_timeout_and_transport_error_are_failures():
    with pytest.raises(PostSetupStepError, match='timeout after 5s'):
        await run_postsetup_steps(
            [step('slow', timeout=5.0)], ScriptedExecutor({'slow': StepExecution(timed_out=True)})
        )
    with pytest.raises(PostSetupStepError, match='transport error: connection lost'):
        await run_postsetup_steps([step('x')], ScriptedExecutor({'x': StepExecution(error='connection lost')}))


@pytest.mark.asyncio
async def test_allow_failure_warns_and_continues():
    ex = ScriptedExecutor({'flaky': StepExecution(2, '', 'nope')})
    stage = FakeStageCtx()
    results = await run_postsetup_steps([step('flaky', allow_failure=True), step('after')], ex, stage_ctx=stage)
    assert [r.step.name for r in results] == ['flaky', 'after']
    assert stage.stage.status == StatusEnum.WARNING
    assert 'flaky' in stage.stage.sub_msg and '1 step(s) failed (allowed)' in stage.stage.sub_msg
    assert postsetup.summarize_allowed_failures(results) == [
        "post-setup step 'flaky' failed (exit code 2) - allowed, run continued"
    ]


@pytest.mark.asyncio
async def test_stage_ends_failed_when_a_step_fails():
    ex = ScriptedExecutor({'bad': StepExecution(1, '', 'x')})
    ctx = StageCtxManager(InstallationsStage(), '')
    with pytest.raises(PostSetupStepError), ctx as stage_ctx:
        await run_postsetup_steps([step('bad')], ex, stage_ctx=stage_ctx)
    assert ctx.stage.status == StatusEnum.FAILED


@pytest.mark.asyncio
async def test_interrupt_ends_loop_quietly():
    import threading

    stop = threading.Event()

    class StopAfterFirst(ScriptedExecutor):
        async def run(self, step, timeout, stop_event=None):
            self.calls.append(step)
            stop.set()
            return StepExecution(error='Cancelled')

    ex = StopAfterFirst()
    results = await run_postsetup_steps([step('a'), step('b')], ex, stop_event=stop)
    assert results == []  # the cut-short step is not judged, and 'b' never starts
    assert [s.name for s in ex.calls] == ['a']


@pytest.mark.asyncio
async def test_log_file_records_every_step(tmp_path):
    path = tmp_path / 'logs' / 'postsetup.log'
    ex = ScriptedExecutor({'b': StepExecution(3, 'B-OUT', 'B-ERR')})
    steps = [step('a', 'echo a', cwd='/work'), step('b', 'exit 3', admin=True, allow_failure=True)]
    await run_postsetup_steps(steps, ex, log_path=path, machine='m1')
    text = path.read_text()
    assert '=== [1/2] a (machine m1) ===' in text and 'command : echo a' in text
    assert 'cwd     : /work' in text and 'rights  : user' in text
    assert '=== [2/2] b' in text and 'rights  : admin' in text and 'exit    : 3' in text
    assert 'outcome : failed (exit code 3)' in text and 'B-OUT' in text and 'B-ERR' in text
    assert 'duration:' in text


@pytest.mark.asyncio
async def test_failed_step_is_logged_before_raising(tmp_path):
    path = tmp_path / 'postsetup.log'
    with pytest.raises(PostSetupStepError):
        await run_postsetup_steps([step('bad')], ScriptedExecutor({'bad': StepExecution(1, '', 'E')}), log_path=path)
    assert 'outcome : failed' in path.read_text()


# --------------------------------------------------------- websocket transport


def ws_client(**result):
    client = MagicMock()
    client.execute_shell = AsyncMock(return_value=result)
    return client


@pytest.mark.asyncio
async def test_websocket_passes_admin_cwd_timeout_through():
    client = ws_client(returncode=0, stdout='o', stderr='e')
    ex = WebsocketStepExecutor(client, 'linux')
    out = await ex.run(step('s', 'cmd', cwd='/w', admin=True), 42.0)
    client.execute_shell.assert_awaited_once_with(
        'cmd', shell=True, cwd='/w', admin=True, timeout=42.0, websocket_timeout=52.0
    )
    assert (out.returncode, out.stdout, out.stderr) == (0, 'o', 'e')


@pytest.mark.asyncio
async def test_websocket_defaults_run_as_user_without_cwd():
    client = ws_client(returncode=0)
    await WebsocketStepExecutor(client, 'linux').run(step('s'), 600.0)
    kwargs = client.execute_shell.await_args.kwargs
    assert kwargs['admin'] is False and kwargs['cwd'] is None and kwargs['shell'] is True


@pytest.mark.asyncio
async def test_websocket_timeout_error_is_a_timeout():
    client = MagicMock()
    client.execute_shell = AsyncMock(side_effect=WebSocketTimeoutError('late'))
    out = await WebsocketStepExecutor(client).run(step('s'), 1.0)
    assert out.timed_out


@pytest.mark.asyncio
async def test_websocket_connection_error_is_a_transport_error():
    client = MagicMock()
    client.execute_shell = AsyncMock(side_effect=ConnectionError('gone'))
    out = await WebsocketStepExecutor(client).run(step('s'), 1.0)
    assert out.error == 'gone' and not out.timed_out


@pytest.mark.asyncio
async def test_websocket_agent_side_kill_is_a_timeout_and_missing_status_an_error():
    killed = ws_client(returncode=-1, stdout='', stderr='Command timed out after 5 seconds (killed at 5.0s)\n')
    assert (await WebsocketStepExecutor(killed).run(step('s'), 5.0)).timed_out
    broken = ws_client(status='error', message='boom')
    assert (await WebsocketStepExecutor(broken).run(step('s'), 5.0)).error == 'boom'


def test_websocket_rights_labels():
    assert WebsocketStepExecutor(None, 'linux').rights(step('s')) == 'user (VM user)'
    assert WebsocketStepExecutor(None, 'linux').rights(step('s', admin=True)) == 'admin (root)'
    assert 'elevated' in WebsocketStepExecutor(None, 'windows').rights(step('s'))


# ------------------------------------------------------------- QGA transport


def qga_vm(guest_os='ubuntu', returncode=0, stdout='', stderr=''):
    vm = MagicMock()
    vm.guest_os = guest_os
    vm.username = 'adare user'
    vm.run_command = AsyncMock(return_value=SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr))
    return vm


def test_qga_linux_command_drops_to_vm_user_and_quotes():
    cmd = build_qga_linux_command("echo 'hi' && id -un", 'adare', '/my dir')
    assert cmd.startswith('sudo -u adare -H env PATH="$PATH"')
    # the inner script is one quoted argument of bash -c, with cwd quoted
    inner = shlex.split(cmd)[-1]
    assert inner == "cd '/my dir' && echo 'hi' && id -un"
    assert shlex.split(cmd)[-3:-1] == ['bash', '-c']


@pytest.mark.asyncio
async def test_qga_linux_without_admin_runs_as_vm_user():
    vm = qga_vm()
    await QgaStepExecutor(vm).run(step('s', 'id', cwd='/w'), 30.0)
    args, kwargs = vm.run_command.await_args
    assert args[0] == build_qga_linux_command('id', 'adare user', '/w')
    assert kwargs['cwd'] is None and kwargs['admin'] is False and kwargs['timeout'] == 30


@pytest.mark.asyncio
async def test_qga_linux_admin_stays_root_with_cwd():
    vm = qga_vm()
    await QgaStepExecutor(vm).run(step('s', 'id', cwd='/w', admin=True), 30.0)
    args, kwargs = vm.run_command.await_args
    assert args[0] == 'id' and kwargs['cwd'] == '/w' and kwargs['admin'] is True


@pytest.mark.asyncio
async def test_qga_windows_runs_plain_as_system():
    vm = qga_vm('windows11')
    ex = QgaStepExecutor(vm)
    await ex.run(step('s', 'whoami', cwd='C:\\w'), 30.0)
    args, kwargs = vm.run_command.await_args
    assert args[0] == 'whoami' and kwargs['cwd'] == 'C:\\w'
    assert 'SYSTEM' in ex.rights(step('s'))


@pytest.mark.asyncio
async def test_qga_result_mapping():
    ok = await QgaStepExecutor(qga_vm(returncode=0, stdout='o', stderr='e')).run(step('s'), 5.0)
    assert (ok.returncode, ok.stdout, ok.stderr) == (0, 'o', 'e')
    failed = await QgaStepExecutor(qga_vm(returncode=4, stderr='x')).run(step('s'), 5.0)
    assert failed.returncode == 4
    timeout = await QgaStepExecutor(qga_vm(returncode=-1, stderr='Timeout')).run(step('s'), 5.0)
    assert timeout.timed_out
    down = await QgaStepExecutor(qga_vm(returncode=-1, stderr='VM not running')).run(step('s'), 5.0)
    assert down.error == 'VM not running'
    vm = qga_vm()
    vm.run_command = AsyncMock(side_effect=OSError('socket'))
    assert (await QgaStepExecutor(vm).run(step('s'), 5.0)).error == 'socket'


# --------------------------------------------------- environment integration


def fake_context(tmp_path, installations, monkeypatch):
    import adare.backend.environment.database as environment_database

    monkeypatch.setattr(environment_database, 'get_environment_installations', lambda ulid: installations)
    return SimpleNamespace(
        environment_ulid='env',
        guest_platform='linux',
        experiment_run_directory=SimpleNamespace(log_directory=tmp_path / 'logs'),
        user_interrupt_event=None,
        postsetup_warnings=[],
        client=ws_client(returncode=0, stdout='', stderr=''),
        vm=qga_vm(),
    )


@pytest.mark.asyncio
async def test_websocket_caller_runs_rows_logs_and_records_warnings(tmp_path, monkeypatch):
    rows = [
        SimpleNamespace(name='one', command='c1', description='', cwd='', shell=False),
        SimpleNamespace(name='two', command='c2', description='', cwd='', shell=False, allow_failure=True),
    ]
    ctx = fake_context(tmp_path, rows, monkeypatch)
    ctx.client.execute_shell = AsyncMock(
        side_effect=[{'returncode': 0, 'stdout': 'x', 'stderr': ''}, {'returncode': 9, 'stdout': '', 'stderr': 'bad'}]
    )
    stage = FakeStageCtx()
    await execute_installations_via_websocket(ctx, stage)
    assert (tmp_path / 'logs' / 'postsetup.log').read_text().count('=== [') == 2
    assert ctx.postsetup_warnings == ["post-setup step 'two' failed (exit code 9) - allowed, run continued"]


@pytest.mark.asyncio
async def test_qga_caller_raises_on_failure(tmp_path, monkeypatch):
    rows = [SimpleNamespace(name='one', command='c1', description='', cwd='', shell=False)]
    ctx = fake_context(tmp_path, rows, monkeypatch)
    ctx.vm = qga_vm(returncode=1, stderr='denied')
    with pytest.raises(PostSetupStepError, match='denied'):
        await execute_installations_via_qga(ctx, FakeStageCtx())


@pytest.mark.asyncio
async def test_no_installations_is_a_noop(tmp_path, monkeypatch):
    ctx = fake_context(tmp_path, [], monkeypatch)
    await execute_installations_via_websocket(ctx, FakeStageCtx())
    ctx.client.execute_shell.assert_not_called()
    assert not (tmp_path / 'logs').exists()
