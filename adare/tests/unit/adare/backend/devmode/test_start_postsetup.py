"""``adare dev start`` runs the environment's post-setup steps; ``--no-postsetup`` skips them."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from adare.backend.devmode.session import DevModeSession
from adare.backend.experiment.exceptions import PostSetupStepError
from adare.core.dto.devmode import DevSessionStartRequest

pytestmark = pytest.mark.unit


def _start_session(run_postsetup, install_effect=None):
    """Run DevModeSession.start() with every VM/DB step mocked; return (result, install mock)."""
    session = DevModeSession(
        session_id='sid', project_path=Path('/nonexistent'), environment_name='env', run_postsetup=run_postsetup
    )
    install = AsyncMock(side_effect=install_effect)
    ctx = MagicMock()
    ctx.mcp_server = None
    ctx.experiment_run_directory.path = Path('/nonexistent/run')
    run = 'adare.backend.experiment.run'
    with (
        patch(f'{run}.step_initialize'),
        patch(f'{run}.step_prepare_run_environment'),
        patch(f'{run}.step_start_mcp_server', new=AsyncMock()),
        patch(f'{run}.step_install_and_run_websocket_server', new=AsyncMock()),
        patch(f'{run}.step_connect_websocket', new=AsyncMock()),
        patch(f'{run}.step_execute_installations', new=install),
        patch('adare.backend.devmode.session.lifecycle.ExperimentRunCtx', return_value=ctx),
        patch('adare.backend.devmode.session.lifecycle.VMLifecycleManager') as manager,
        patch('adare.backend.devmode.session.lifecycle.StageCtxManager'),
        patch('adare.database.api.experiment.ExperimentApi'),
        patch.object(DevModeSession, '_setup_bare_session'),
        patch.object(DevModeSession, '_initialize_session_logging'),
        patch.object(DevModeSession, 'stop', new=AsyncMock()),
    ):
        for name in ('create_and_prepare_vm', 'setup_file_transfer', 'setup_networking', 'start_vm'):
            setattr(manager.return_value, name, AsyncMock())
        import asyncio

        result = asyncio.run(session.start())
    return result, install, ctx


def test_start_runs_postsetup_after_connect():
    result, install, ctx = _start_session(True)
    assert result.success
    install.assert_awaited_once()
    assert install.await_args.args[0] is ctx


def test_start_skips_postsetup_when_disabled():
    result, install, _ = _start_session(False)
    assert result.success
    install.assert_not_called()


def test_failing_step_fails_start_with_the_step_message():
    import logging

    error = PostSetupStepError(logging.getLogger('t'), "Post-setup step 'apt' (1/1) failed: exit code 100", 'apt')
    result, _, _ = _start_session(True, install_effect=error)
    assert not result.success
    assert "Post-setup step 'apt' (1/1) failed: exit code 100" in result.error.message


def test_request_runs_postsetup_by_default():
    request = DevSessionStartRequest(project_path=Path('/p'), environment_name='e')
    assert request.run_postsetup is True


@pytest.mark.parametrize(('flags', 'expected'), [([], False), (['--no-postsetup'], True)])
def test_cli_flag_reaches_the_command(flags, expected):
    import click

    from adare.cli.groups.dev_commands import register

    class Group(click.Group):
        def add_alias(self, alias, name):
            self.commands[alias] = self.commands[name]

    seen = []
    root = Group('adare')
    register(root, Group, lambda func, args: seen.append(args))  # no global CLI import: it mutates config
    result = CliRunner().invoke(root, ['dev', 'start', '-e', 'env', *flags])
    assert result.exit_code == 0, result.output
    assert seen[0].no_postsetup is expected


def test_cli_passes_flag_into_the_session_request():
    from adare.cli.dev import session as dev_session

    api = MagicMock()
    api.devmode.start_session.return_value = SimpleNamespace(success=False)
    args = SimpleNamespace(environment='env', no_postsetup=True, shared_dir=None, reuse=False, project=None)
    with (
        patch.object(dev_session, 'AdareAPI', return_value=api),
        patch.object(dev_session, 'get_project_path', return_value=Path('/p')),
        patch.object(dev_session, '_handle_start_reuse_or_warn', return_value=None),
        patch.object(dev_session, 'handle_api_error'),
        patch.object(dev_session, '_start_event_listeners'),
        patch.object(dev_session, '_stop_event_listeners'),
        patch('adare.backend.experiment.print.ExperimentFlowConsole'),
    ):
        dev_session.exec_dev_start(args)
    assert api.devmode.start_session.call_args.args[0].run_postsetup is False
