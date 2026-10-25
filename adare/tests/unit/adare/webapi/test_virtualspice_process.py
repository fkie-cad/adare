"""Running VirtualSpice: which binary, how it is started, which port the proxy follows."""

import sys
from unittest.mock import patch

import pytest

from adare.webapi import process_manager, vm_watch
from adare.webapi.process_manager import VirtualSpiceManager, supports_data_dir

pytestmark = pytest.mark.unit

posix_only = pytest.mark.skipif(sys.platform == 'win32', reason='fake binaries are shell scripts')


def _fake_binary(path, help_text, body='sleep 30'):
    """A shell script standing in for spice-client: prints help_text for --help, else runs body."""
    path.write_text(f'#!/bin/sh\nif [ "$1" = "--help" ]; then echo "{help_text}"; exit 0; fi\n{body}\n')
    path.chmod(0o755)
    return str(path)


NEW_HELP = 'Commands: serve daemon mcp  Options: --data-dir <PATH>'
OLD_HELP = 'Options: --port <PORT> --listen <ADDR>'


@pytest.fixture(autouse=True)
def _fresh_help_cache():
    supports_data_dir.cache_clear()
    yield
    supports_data_dir.cache_clear()


@posix_only
def test_only_binaries_with_data_dir_and_serve_qualify(tmp_path):
    assert supports_data_dir(_fake_binary(tmp_path / 'new', NEW_HELP)) is True
    assert supports_data_dir(_fake_binary(tmp_path / 'old', OLD_HELP)) is False
    assert supports_data_dir(str(tmp_path / 'missing')) is False


@posix_only
def test_outdated_build_is_skipped_for_a_newer_one(tmp_path):
    old = _fake_binary(tmp_path / 'old', OLD_HELP)
    new = _fake_binary(tmp_path / 'new', NEW_HELP)

    with patch.object(VirtualSpiceManager, '_candidates', return_value=[old, new]):
        assert VirtualSpiceManager().binary_path == new
    with patch.object(VirtualSpiceManager, '_candidates', return_value=[old]):
        assert VirtualSpiceManager().available is False


def test_command_uses_adares_own_data_dir():
    manager = VirtualSpiceManager(port=9000, binary_path='/opt/spice-client')

    assert manager.command() == [
        '/opt/spice-client',
        '--data-dir',
        str(process_manager.VIRTUALSPICE_DATA_DIR),
        'serve',
        '--port',
        '9000',
    ]


def test_a_server_already_on_the_port_is_reused():
    manager = VirtualSpiceManager(port=9000, binary_path='/opt/spice-client')

    with patch.object(manager, 'health_check', return_value=True), patch('subprocess.Popen') as popen:
        assert manager.start() is True

    popen.assert_not_called()
    assert manager.reused is True
    manager.stop()  # leaves the reused server alone


@posix_only
def test_a_server_that_exits_reports_why(tmp_path, monkeypatch):
    monkeypatch.setattr(process_manager, 'VIRTUALSPICE_DATA_DIR', tmp_path / 'vs')
    binary = _fake_binary(
        tmp_path / 'spice', NEW_HELP, body='echo "error: another VirtualSpice server is already running"; exit 1'
    )
    manager = VirtualSpiceManager(port=9000, binary_path=binary)

    with patch.object(manager, 'health_check', return_value=False):
        assert manager.start() is False

    assert 'exited with code 1' in manager.error
    assert 'already running' in manager.error
    assert manager.log_file.parent == tmp_path / 'vs'


@posix_only
def test_a_started_server_is_stopped(tmp_path, monkeypatch):
    monkeypatch.setattr(process_manager, 'VIRTUALSPICE_DATA_DIR', tmp_path / 'vs')
    manager = VirtualSpiceManager(port=9000, binary_path=_fake_binary(tmp_path / 'spice', NEW_HELP))
    answers = iter([False, False, True])  # not running before; answering after a moment

    with patch.object(manager, 'health_check', side_effect=lambda: next(answers, True)):
        assert manager.start() is True
    assert manager.is_running() and not manager.reused

    manager.stop()
    assert not manager.is_running()


def test_spice_port_follows_the_environment(monkeypatch):
    monkeypatch.delenv(vm_watch.SPICE_PORT_ENV, raising=False)
    assert vm_watch.spice_port() == 8081
    monkeypatch.setenv(vm_watch.SPICE_PORT_ENV, '9123')
    assert vm_watch.spice_port() == 9123
    monkeypatch.setenv(vm_watch.SPICE_PORT_ENV, 'nonsense')
    assert vm_watch.spice_port() == 8081


def test_name_lookup_asks_the_configured_port(monkeypatch):
    monkeypatch.setenv(vm_watch.SPICE_PORT_ENV, '9123')
    seen = {}

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return [{'name': 'other', 'uuid': 'u0'}, {'name': 'ubuntu_exp_A', 'uuid': 'u1'}]

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url):
            seen['url'] = url
            return Response()

    monkeypatch.setattr(vm_watch.httpx, 'Client', Client)

    assert vm_watch.resolve_vm_uuid('ubuntu_exp_A') == 'u1'
    assert seen['url'] == 'http://127.0.0.1:9123/api/vms'
    assert vm_watch.resolve_vm_uuid('missing') is None
