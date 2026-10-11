"""The `adare tui` command must not import trogon until it is invoked."""

import subprocess
import sys
import types

import click
import pytest

pytestmark = pytest.mark.unit


def test_importing_the_cli_does_not_import_trogon():
    code = 'import sys, adare.run; print("trogon" in sys.modules, "textual" in sys.modules)'
    out = subprocess.run([sys.executable, '-c', code], check=True, capture_output=True, text=True).stdout
    assert out.split() == ['False', 'False']


def test_tui_command_is_registered_like_trogons_decorator():
    from adare import run

    cmd = run.cli.commands['tui']
    assert cmd.help == 'Open Textual TUI.'
    assert 'tui' in run.cli.list_commands(click.Context(run.cli))


def test_tui_command_runs_trogon_on_the_root_group(monkeypatch):
    from adare import run

    calls = []

    class FakeTrogon:
        def __init__(self, app, app_name=None, command_name='tui', click_context=None):
            calls.append((app, app_name, command_name, click_context))

        def run(self):
            calls.append('run')

    monkeypatch.setitem(sys.modules, 'trogon', types.SimpleNamespace(Trogon=FakeTrogon))

    root_ctx = click.Context(run.cli, info_name='adare')
    tui_ctx = click.Context(run.cli.commands['tui'], info_name='tui', parent=root_ctx)
    run.cli.commands['tui'].invoke(tui_ctx)

    assert calls == [(run.cli, None, 'tui', tui_ctx), 'run']
