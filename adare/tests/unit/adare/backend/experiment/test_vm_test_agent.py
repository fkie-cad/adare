"""`adare vm test` on QEMU gives the guest its agent the way an experiment run does.

Same runtime and wheels, shares and config.json (the lifecycle's file-transfer
strategy), install and launch (``install_and_run_adare_vm``) and connection
(``connect_websocket``), and the agent's start and connection decide the verdict.
"""

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from adare.backend.experiment import agent_lifecycle, agent_wheels, vm_test, vm_test_qemu
from adare.backend.experiment.commands.manage import StageCtxManagerLite
from adare.backend.experiment.directory import ExperimentRunDirectory
from adare.backend.project.directory import ProjectDirectory
from adare.exceptions import LoggedException
from adare.types.stages import VMWebSocketTestStage

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

    assert await vm_test_qemu.start_agent_for_test(context) == (True, None)
    install.assert_awaited_once_with(context, context.user_interrupt_event)


@pytest.mark.asyncio
async def test_failed_agent_start_names_the_cause_and_the_logs(tmp_path, monkeypatch):
    error = LoggedException(logging.getLogger(__name__), 'pip3 not found')
    monkeypatch.setattr(agent_lifecycle, 'install_and_run_adare_vm', AsyncMock(side_effect=error))
    context = _context(tmp_path)

    ok, reason = await vm_test_qemu.start_agent_for_test(context)

    assert not ok
    assert 'pip3 not found' in reason
    assert str(context.experiment_run_directory.log_directory) in reason


@pytest.mark.asyncio
async def test_connection_is_the_experiment_connection(tmp_path, monkeypatch):
    async def connect(context, stage_ctx):
        context.client = SimpleNamespace(connected=True)

    connect_websocket = AsyncMock(side_effect=connect)
    monkeypatch.setattr(agent_lifecycle, 'connect_websocket', connect_websocket)
    context = _context(tmp_path)
    stage_ctx = object()

    assert await vm_test_qemu.connect_agent_for_test(context, stage_ctx) == (True, None)
    connect_websocket.assert_awaited_once_with(context, stage_ctx)


@pytest.mark.asyncio
async def test_cancelled_connection_is_a_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_lifecycle, 'connect_websocket', AsyncMock())

    ok, _ = await vm_test_qemu.connect_agent_for_test(_context(tmp_path), object())

    assert not ok


def _patch_checks(monkeypatch, connected: bool, agent_gui: bool):
    def result(ok):
        return AsyncMock(return_value=(ok, None if ok else 'failed'))

    for name in (
        'test_vm_response',
        'test_shared_folders',
        'test_python_availability',
        'test_uv_availability',
        'test_host_screenshot',
        'test_host_click',
        'start_agent_for_test',
    ):
        monkeypatch.setattr(vm_test, name, result(True))
    monkeypatch.setattr(vm_test, 'connect_agent_for_test', result(connected))
    monkeypatch.setattr(vm_test, 'test_screenshot_command', result(agent_gui))
    monkeypatch.setattr(vm_test, 'test_click_command', result(agent_gui))
    legacy = result(True)
    monkeypatch.setattr(vm_test, 'test_adarevm_server_start', legacy)
    monkeypatch.setattr(vm_test, 'test_websocket_connection', legacy)
    return legacy


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('connected', 'agent_gui', 'compatible'),
    [
        (True, True, True),
        # experiments drive the GUI over QMP: in-guest capture may fail on Wayland
        (True, False, True),
        # but they run their tests through the agent
        (False, False, False),
    ],
)
async def test_qemu_verdict_needs_the_agent(monkeypatch, connected, agent_gui, compatible):
    legacy = _patch_checks(monkeypatch, connected, agent_gui)
    context = SimpleNamespace(hypervisor_type='qemu', guest_platform='linux')

    assert await vm_test.test_vm_compatibility(context, MagicMock()) is compatible
    legacy.assert_not_awaited()


@pytest.mark.asyncio
async def test_connection_check_gets_the_stage_for_its_progress(monkeypatch):
    _patch_checks(monkeypatch, connected=True, agent_gui=True)
    context = SimpleNamespace(hypervisor_type='qemu', guest_platform='linux')

    await vm_test.test_vm_compatibility(context, MagicMock())

    (call,) = vm_test.connect_agent_for_test.await_args_list
    assert isinstance(call.args[1], StageCtxManagerLite)


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
    context = _context(tmp_path, vm_test_passed=passed)
    context.experiment_run_directory.create()

    vm_test_qemu._release_test_files(context)

    assert context.experiment_run_directory.path.exists() is kept
