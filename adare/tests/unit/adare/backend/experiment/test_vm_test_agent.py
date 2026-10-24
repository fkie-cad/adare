"""`adare vm test` on QEMU gives the guest its agent the way an experiment run does.

Same runtime and wheels, shares and config.json (the lifecycle's file-transfer
strategy), install and launch (``install_and_run_adare_vm``) and connection
(``connect_websocket``), and the agent's start and connection decide the verdict.
"""

import dataclasses
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from adare.backend.experiment import agent_lifecycle, agent_wheels, vm_test, vm_test_qemu
from adare.backend.experiment.commands.manage import StageCtxManagerLite
from adare.backend.experiment.directory import ExperimentRunDirectory
from adare.backend.project.directory import ProjectDirectory
from adare.exceptions import LoggedException
from adare.types.stages import VMResponseTestStage, VMWebSocketTestStage

pytestmark = pytest.mark.unit


def _context(tmp_path, **extra):
    context = SimpleNamespace(
        project_directory=ProjectDirectory(tmp_path / 'vm-test'),
        adarevm=tmp_path / 'src' / 'adarevm',
        adarelib=tmp_path / 'src' / 'adarelib',
        vm_name='adare_qemu_test_1',
        user_interrupt_event=MagicMock(),
        client=None,
        **extra,
    )
    context.experiment_run_directory = ExperimentRunDirectory(context.project_directory, context.vm_name)
    return context


def _result(ok: bool):
    return AsyncMock(return_value=(ok, None if ok else 'failed'))


@pytest.mark.asyncio
async def test_share_setup_builds_the_experiment_runtime_and_shares_it_like_a_run(tmp_path, monkeypatch):
    ensure = MagicMock()
    monkeypatch.setattr(agent_wheels, 'ensure_vm_runtime', ensure)
    lifecycle = SimpleNamespace(setup_file_transfer=AsyncMock())
    context = _context(tmp_path, qemu_lifecycle=lifecycle)

    await vm_test_qemu.setup_qemu_share_for_test(context)

    ensure.assert_called_once_with(
        tmp_path / 'vm-test' / 'vm_runtime', {'adarevm': context.adarevm, 'adarelib': context.adarelib}
    )
    assert context.experiment_run_directory.log_directory.is_dir()
    lifecycle.setup_file_transfer.assert_awaited_once_with(context)


@pytest.mark.asyncio
async def test_agent_start_is_the_experiment_install(tmp_path, monkeypatch):
    install = AsyncMock()
    monkeypatch.setattr(agent_lifecycle, 'install_and_run_adare_vm', install)
    context = _context(tmp_path)

    assert await vm_test_qemu.check_agent_start(context, object()) == (True, None)
    install.assert_awaited_once_with(context, context.user_interrupt_event)


@pytest.mark.asyncio
async def test_failed_agent_start_names_the_cause_and_the_logs(tmp_path, monkeypatch):
    error = LoggedException(logging.getLogger(__name__), 'pip3 not found')
    monkeypatch.setattr(agent_lifecycle, 'install_and_run_adare_vm', AsyncMock(side_effect=error))
    context = _context(tmp_path)

    ok, reason = await vm_test_qemu.check_agent_start(context, object())

    assert not ok
    assert 'pip3 not found' in reason
    assert str(context.experiment_run_directory.log_directory) in reason


@pytest.mark.asyncio
async def test_connection_is_the_experiment_connection(tmp_path, monkeypatch):
    async def connect(context, stage):
        context.client = SimpleNamespace(connected=True)

    connect_websocket = AsyncMock(side_effect=connect)
    monkeypatch.setattr(agent_lifecycle, 'connect_websocket', connect_websocket)
    context = _context(tmp_path)
    stage = object()

    assert await vm_test_qemu.check_agent_connection(context, stage) == (True, None)
    connect_websocket.assert_awaited_once_with(context, stage)


@pytest.mark.asyncio
async def test_cancelled_connection_is_a_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_lifecycle, 'connect_websocket', AsyncMock())

    ok, _ = await vm_test_qemu.check_agent_connection(_context(tmp_path), object())

    assert not ok


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('connected', 'agent_gui', 'compatible'),
    [
        (True, True, True),
        # experiments drive the GUI over QMP: in-guest capture may fail on Wayland
        (True, False, True),
        # but they run their tests through the agent
        (False, True, False),
    ],
)
async def test_qemu_verdict_needs_the_agent(monkeypatch, connected, agent_gui, compatible):
    def faked(checks, ok):
        return tuple(dataclasses.replace(check, run=_result(ok(check.key))) for check in checks)

    monkeypatch.setattr(
        vm_test_qemu,
        'QEMU_CHECKS',
        faked(vm_test_qemu.QEMU_CHECKS, lambda key: connected or key != 'websocket_connection'),
    )
    monkeypatch.setattr(vm_test_qemu, 'AGENT_GUI_CHECKS', faked(vm_test.AGENT_GUI_CHECKS, lambda key: agent_gui))
    compat = vm_test.CompatRun(SimpleNamespace(), MagicMock())

    assert await vm_test_qemu.check_qemu_compatibility(compat) is compatible
    # the agent's GUI commands only run on a connected agent
    assert ('screenshot_command' in compat.results) is connected


class TestCompatRun:
    @pytest.mark.asyncio
    async def test_check_runs_under_its_stage_and_its_result_is_kept(self):
        check = vm_test.CompatCheck('websocket_connection', VMWebSocketTestStage, _result(True))
        context = SimpleNamespace()
        compat = vm_test.CompatRun(context, MagicMock())

        await compat.run([check])

        assert compat.results == {'websocket_connection': True}
        assert compat.failures == []
        (call,) = check.run.await_args_list
        assert call.args[0] is context
        assert isinstance(call.args[1], StageCtxManagerLite)

    @pytest.mark.asyncio
    async def test_failure_keeps_the_decoded_reason_for_after_the_tree(self):
        fails = AsyncMock(return_value=(False, 'Failed to start. stderr: line one\nline one\nline two'))
        compat = vm_test.CompatRun(SimpleNamespace(), MagicMock())

        await compat.run([vm_test.CompatCheck('vm_responsive', VMResponseTestStage, fails)])

        assert compat.results == {'vm_responsive': False}
        assert compat.failures == [(VMResponseTestStage.msg, 'Failed to start.', 'line one\nline two')]

    def test_passed_needs_every_key_to_have_run_and_passed(self):
        compat = vm_test.CompatRun(SimpleNamespace(), MagicMock(), results={'a': True, 'b': False})

        assert compat.passed(['a'])
        assert not compat.passed(['a', 'b'])
        assert not compat.passed(['a', 'never_ran'])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('platform', 'command'),
    [
        ('linux', 'test -f /adare/run/config.json && test -f /adare/vm/adarevm/pyproject.toml'),
        (
            'windows',
            "if ((Test-Path 'C:\\adare\\run\\config.json') -and "
            "(Test-Path 'C:\\adare\\vm\\adarevm\\pyproject.toml')) { exit 0 } else { exit 1 }",
        ),
    ],
)
async def test_share_check_probes_the_experiment_layout(platform, command):
    vm = SimpleNamespace(run_command=AsyncMock(return_value=SimpleNamespace(returncode=0)))
    context = SimpleNamespace(guest_platform=platform, vm=vm, user_interrupt_event=None)

    assert await vm_test_qemu.check_experiment_shares(context, object()) == (True, None)
    assert vm.run_command.await_args.args[0] == command


def test_stage_lite_shows_progress_like_the_experiment_stage():
    flow_console = MagicMock()
    stage_ctx = StageCtxManagerLite(VMWebSocketTestStage(), flow_console)
    stage_ctx.stage.sub_msg = 'Retrying connection (attempt 2/6)'

    stage_ctx.set_status(stage_ctx.stage.status)

    flow_console.change_log_message.assert_called_once_with(
        stage_ctx.stage_id, f'{VMWebSocketTestStage.msg}: Retrying connection (attempt 2/6)'
    )


@pytest.mark.parametrize(('passed', 'kept'), [(True, False), (False, True)])
def test_run_directory_is_kept_only_after_a_failed_test(tmp_path, passed, kept):
    context = _context(tmp_path, qemu_lifecycle=SimpleNamespace(file_transfer=SimpleNamespace()))
    context.experiment_run_directory.create()

    vm_test_qemu._release_test_files(context, passed)

    assert context.experiment_run_directory.path.exists() is kept
