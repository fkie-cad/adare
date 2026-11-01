"""Backend selection precedence and the HostsideClient surface."""

import asyncio
from types import SimpleNamespace

import pytest

from adare.backend.hostside import backend as backend_module
from adare.backend.hostside.backend import BACKEND_AGENT, BACKEND_HOSTSIDE, is_hostside, resolve_backend
from adare.backend.hostside.client import HostsideClient, HostsideUnsupportedError
from adare.backend.hostside.commands import CommandPlanner, guest_tzinfo
from adare.backend.hostside.guestfs import StagedOp

pytestmark = pytest.mark.unit


def test_default_is_agent(monkeypatch):
    monkeypatch.delenv(backend_module.ENV_VAR, raising=False)
    assert resolve_backend() == BACKEND_AGENT


def test_precedence_cli_env_playbook(monkeypatch):
    monkeypatch.delenv(backend_module.ENV_VAR, raising=False)
    settings = SimpleNamespace(backend='hostside')
    assert resolve_backend(None, settings) == BACKEND_HOSTSIDE
    monkeypatch.setenv(backend_module.ENV_VAR, 'agent')
    assert resolve_backend(None, settings) == BACKEND_AGENT
    assert resolve_backend('hostside', settings) == BACKEND_HOSTSIDE


def test_invalid_backend_is_rejected(monkeypatch):
    monkeypatch.delenv(backend_module.ENV_VAR, raising=False)
    with pytest.raises(ValueError, match='Invalid backend'):
        resolve_backend('nope')


def test_is_hostside():
    assert is_hostside(SimpleNamespace(config=SimpleNamespace(backend='hostside')))
    assert not is_hostside(SimpleNamespace(config=SimpleNamespace(backend='agent')))
    assert not is_hostside(SimpleNamespace())


class _FakeSession:
    guest_tz = guest_tzinfo('UTC')

    def __init__(self):
        self.pulls = []
        plan = CommandPlanner(now=1.0).plan('rm -f /x')
        self.plans = {'rm -f /x': plan}

    def handle_command(self, command, **kwargs):
        from adare.backend.hostside.session import HostsideSession

        return HostsideSession.handle_command(self, command, **kwargs)

    markers = SimpleNamespace(marker=lambda *a, **k: None)

    def defer_pull(self, guest_path, host_path):
        self.pulls.append((guest_path, host_path))


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(
        'adare.backend.experiment.execution.qemu_host_gui_executor.QEMUHostGUIExecutor', lambda vm: SimpleNamespace()
    )
    return HostsideClient(vm=None, session=_FakeSession())


def test_staged_command_succeeds_and_unknown_fails_loudly(client):
    result = asyncio.run(client.execute_shell('rm -f /x'))
    assert result['status'] == 'success' and result['returncode'] == 0
    with pytest.raises(HostsideUnsupportedError):
        asyncio.run(client.execute_shell('ls /tmp'))


def test_timestamp_is_the_host_clock_with_guest_zone(client):
    result = asyncio.run(client.get_timestamp(use_local=True))
    assert result['timezone'] == 'UTC' and result['source'] == 'host-clock' and 'local_time' in result


def test_pull_is_deferred(client):
    result = asyncio.run(client.pull_file_chunked('/a/b', '/tmp/out'))
    assert result['metadata']['deferred'] is True
    assert client.session.pulls == [('/a/b', __import__('pathlib').Path('/tmp/out'))]


def test_in_guest_snapshot_is_unsupported(client):
    with pytest.raises(HostsideUnsupportedError):
        asyncio.run(client.get_filesystem_snapshot())


def test_staged_op_defaults():
    op = StagedOp('write', '/a', content=b'x')
    assert (op.uid, op.gid) == (1000, 1000)
