"""Guest tool diagnostics: no secrets in logs, actionable import-failure hints."""

import logging
from unittest.mock import AsyncMock

import pytest

from adarevm.core.tools import system_tools
from adarevm.core.tools.test_tools import load_failure_hints


class _Shell(system_tools.SystemToolsMixin):
    tools_paths: list[str] = []

    def __init__(self):
        self.send_event = AsyncMock()


@pytest.mark.asyncio
async def test_execute_shell_never_logs_environment_values(monkeypatch, caplog):
    monkeypatch.setenv('ADARE_TEST_INHERITED_SECRET', 'inherited-s3cr3t')
    captured = {}

    def fake_execute(command, **options):
        captured.update(options)
        return {'returncode': 0, 'stdout': '', 'stderr': ''}

    monkeypatch.setattr(system_tools, 'execute_on_shell', fake_execute)
    caplog.set_level(logging.DEBUG)

    result = await _Shell()._execute_shell(None, 'echo hi', shell=True, env={'API_TOKEN': 'passed-s3cr3t'})

    assert result['status'] == 'success'
    assert captured['env']['API_TOKEN'] == 'passed-s3cr3t'  # still handed to the command
    assert 's3cr3t' not in caplog.text
    assert 'API_TOKEN' in caplog.text  # override keys stay visible for debugging


@pytest.mark.parametrize(
    ('exc_type', 'message'),
    [
        ('ImportError', "cannot import name 'testfunction' from 'adarelib.testset.api'"),
        ('ModuleNotFoundError', "No module named 'adarelib.testset.api'"),
    ],
)
def test_missing_adarelib_api_points_at_agent_reinstall(exc_type, message):
    hints = load_failure_hints(exc_type, message)
    assert any('adarelib' in h and 'lacks an API' in h for h in hints)
    assert not any('uv add' in h for h in hints)


def test_missing_third_party_module_suggests_install():
    hints = load_failure_hints('ModuleNotFoundError', "No module named 'openpyxl'")
    assert hints[0] == 'Install missing dependency: uv add openpyxl'


def test_other_failures_have_no_hints():
    assert load_failure_hints('SyntaxError', 'invalid syntax') == []
    assert load_failure_hints('ImportError', 'something unrelated') == []
