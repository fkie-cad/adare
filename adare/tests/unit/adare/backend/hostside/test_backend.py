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


# ---------------------------------------------------------------------------
# Hostside probes answer like agent mode; the pre-flight refuses what has no screen
# ---------------------------------------------------------------------------


class _ProbeFS:
    """Just what the probe proxies read: ``/etc/passwd``, one file's inode, name lookups."""

    origin = 'probe-fs'
    consistency = 'quiesced'

    def __init__(self, passwd='alice:x:1001:1001::/home/alice:/bin/sh\n', mode=0o100644):
        self.passwd = passwd
        self.mode = mode

    def read_text(self, path):
        from adare.backend.hostside.guestfs import GuestFileNotFound

        if path != '/etc/passwd':
            raise GuestFileNotFound(path)
        return self.passwd

    def stat(self, path, follow=True):
        from adare.backend.hostside.guestfs import GuestFileNotFound

        if path != '/home/alice/f':
            raise GuestFileNotFound(path)
        return SimpleNamespace(permissions=self.mode, uid=1001, gid=1001, mtime=100.0, atime=100.0, ctime=100.0)

    def name_of_uid(self, uid):
        return 'alice'

    def name_of_gid(self, gid):
        return 'alice'

    def glob(self, pattern):
        return ['/home/alice/f'] if pattern == '/home/alice/*' else []


def _run_hostside(function, fs, **parameter):
    from adare.backend.hostside.testing import HostsideTestExecutor
    from adarelib.testset.basictest import HostModeCategory

    session = SimpleNamespace(
        fs_for_test=lambda name: fs,
        state_of=lambda name: 'final',
        markers=SimpleNamespace(marker=lambda *a, **k: None),
        guest_tz=guest_tzinfo('Europe/Berlin'),
    )
    instance = type('ProbeTest', (), {'host_mode_category': HostModeCategory.QGA_PROBE})()
    instance.parameter = SimpleNamespace(**parameter)
    executor = HostsideTestExecutor(session, {})
    try:
        return asyncio.run(executor.execute_test('t', function, instance))
    finally:
        executor.cleanup()


class TestHostsideUserExists:
    @pytest.mark.parametrize(
        ('parameter', 'status'),
        [
            ({'username': 'alice'}, 'SUCCESS'),
            ({'username': 'alice', 'uid': 1001}, 'SUCCESS'),
            ({'username': 'alice', 'uid': 1002}, 'FAILED'),
            ({'username': 'alice', 'home_dir': '/home/alice'}, 'SUCCESS'),
            ({'username': 'alice', 'home_dir': '/home/other'}, 'FAILED'),
            ({'username': 'ghost'}, 'FAILED'),
        ],
    )
    def test_uid_and_home_dir_are_checked(self, parameter, status):
        result = _run_hostside('linux.user_exists', _ProbeFS(), **parameter)
        assert result.status.name == status


class TestHostsideFileMetadata:
    def test_missing_file_is_an_error_not_a_failure(self):
        for function, parameter in (
            ('standard.file_permissions', {'dst': '/home/alice/gone', 'expected_permissions': '644'}),
            ('standard.file_timestamps', {'dst': '/home/alice/gone', 'comparison_type': 'after', 'expected_time': 1}),
        ):
            assert _run_hostside(function, _ProbeFS(), **parameter).status.name == 'ERROR'

    def test_mode_bits_only(self):
        # the inode's type bits are not part of the mode
        result = _run_hostside('standard.file_permissions', _ProbeFS(), dst='/home/alice/f', expected_permissions='644')
        assert result.status.name == 'SUCCESS'

    def test_glob_resolves(self):
        result = _run_hostside('standard.file_permissions', _ProbeFS(), dst='/home/alice/*', expected_permissions='644')
        assert result.status.name == 'SUCCESS'

    def test_naive_dates_are_read_in_the_image_time_zone(self):
        # 100 s after the epoch is 01:01:40 in Europe/Berlin (UTC+1 in January 1970)
        result = _run_hostside(
            'standard.file_timestamps',
            _ProbeFS(),
            dst='/home/alice/f',
            comparison_type='equals',
            expected_time='1970-01-01 01:01:40',
        )
        assert result.status.name == 'SUCCESS'


class TestHostsidePreflight:
    @staticmethod
    def _collection():
        from pathlib import Path

        from adarelib.testset.testfunction import import_basictest_subclasses

        return import_basictest_subclasses(directory=Path(__file__).resolve().parents[5] / 'appdata' / 'testfunctions')

    def test_visual_tests_are_refused_before_boot(self):
        from adare.backend.hostside.testing import HostsideTestExecutor

        tests = [SimpleNamespace(name='icon_visible', function='visual.exists')]
        issues = HostsideTestExecutor.validate_offline(tests, self._collection())
        assert len(issues) == 1
        assert 'icon_visible' in issues[0] and 'screen' in issues[0]

    def test_file_tests_and_offline_probes_pass(self):
        from adare.backend.hostside.testing import HostsideTestExecutor

        tests = [
            SimpleNamespace(name='a', function='standard.file_exists'),
            SimpleNamespace(name='b', function='linux.user_exists'),
            SimpleNamespace(name='c', function='standard.file_permissions'),
        ]
        assert HostsideTestExecutor.validate_offline(tests, self._collection()) == []

    def test_live_state_tests_are_still_refused(self):
        from adare.backend.hostside.testing import HostsideTestExecutor

        tests = [SimpleNamespace(name='p', function='linux.process_running')]
        assert len(HostsideTestExecutor.validate_offline(tests, self._collection())) == 1
