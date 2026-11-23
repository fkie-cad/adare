"""QEMU control-socket paths must fit the OS ``sun_path`` limit, and a too-long one is reported with a fix."""

from pathlib import Path

import pytest

from adare.backend.vm.run_instances import run_instance_name
from adare.hypervisor.qemu import socket_paths
from adare.hypervisor.qemu.mixins import configuration
from adare.hypervisor.qemu.socket_paths import (
    SocketPathTooLongError,
    check_run_socket_paths,
    check_socket_paths,
    unix_socket_path_limit,
)

pytestmark = pytest.mark.unit

# The directory of the live-run failure: a deep ADARE_HOME (the old check allowed up to 107 only)
DEEP_HOME = Path('/Users/someone/Documents/Projects/ADARE/experiments/some-long-study-name/runs/home-for-this-run')


@pytest.fixture
def deep_home(monkeypatch):
    monkeypatch.setattr(socket_paths, 'QEMU_STATE_DIR', DEEP_HOME / 'qemu')
    monkeypatch.setenv('ADARE_HOME', str(DEEP_HOME))
    return DEEP_HOME / 'qemu' / 'run'


class TestLimit:
    @pytest.mark.parametrize(('system', 'limit'), [('Darwin', 103), ('Linux', 107), ('Windows', 107), ('FreeBSD', 103)])
    def test_limit_leaves_room_for_the_nul(self, system, limit):
        assert unix_socket_path_limit(system) == limit

    def test_limit_defaults_to_the_host(self, monkeypatch):
        monkeypatch.setattr(socket_paths.platform, 'system', lambda: 'Darwin')
        assert unix_socket_path_limit() == 103


class TestCheckSocketPaths:
    def test_short_home_passes(self):
        check_socket_paths('vm_run_0123abcd', Path('/tmp/adare/qemu/run'), system='Darwin')

    @pytest.mark.parametrize(('system', 'limit'), [('Darwin', 103), ('Linux', 107)])
    def test_boundary_is_exact(self, system, limit):
        run_dir = Path('/r')
        name_len = limit - len('/r/') - len('.qmp')
        check_socket_paths('n' * name_len, run_dir, system=system)  # exactly at the limit
        with pytest.raises(SocketPathTooLongError):
            check_socket_paths('n' * (name_len + 1), run_dir, system=system)

    def test_macos_is_stricter_than_linux(self):
        run_dir = Path('/r')
        name = 'n' * (105 - len('/r/') - len('.qmp'))  # 105 chars: fine on Linux, too long on macOS
        check_socket_paths(name, run_dir, system='Linux')
        with pytest.raises(SocketPathTooLongError):
            check_socket_paths(name, run_dir, system='Darwin')

    def test_error_names_path_length_limit_and_fix(self, deep_home):
        with pytest.raises(SocketPathTooLongError) as excinfo:
            check_socket_paths('disk_run_01234567', system='Linux')
        error = excinfo.value
        path = str(deep_home / 'disk_run_01234567.qmp')
        assert path in error.message
        assert f'({len(path)} > 107 characters on Linux)' in error.message
        assert any('shorter ADARE_HOME' in s for s in error.possible_solutions)

    def test_unset_home_suggests_setting_it(self, deep_home, monkeypatch):
        monkeypatch.delenv('ADARE_HOME')
        with pytest.raises(SocketPathTooLongError) as excinfo:
            check_socket_paths('vm_run_01234567', system='Linux')
        assert any('Set ADARE_HOME' in s for s in excinfo.value.possible_solutions)

    def test_directory_alone_too_long_says_so(self, monkeypatch):
        monkeypatch.setattr(socket_paths, 'QEMU_STATE_DIR', Path('/' + 'd' * 120))
        with pytest.raises(SocketPathTooLongError) as excinfo:
            check_socket_paths('v', system='Linux')
        assert any('socket directory' in s for s in excinfo.value.possible_solutions)


class TestRunSocketPaths:
    def test_name_matches_run_instance_name(self, monkeypatch):
        seen = []
        monkeypatch.setattr(socket_paths, 'check_socket_paths', lambda name, runtime_dir=None: seen.append(name))
        check_run_socket_paths('win11', None)
        check_run_socket_paths('win11', 'client side')
        assert seen == [
            run_instance_name('win11', '0' * 26),
            run_instance_name('win11', '0' * 26, 'client side'),
        ]

    def test_deep_home_is_rejected(self, deep_home, monkeypatch):
        monkeypatch.setattr(socket_paths.platform, 'system', lambda: 'Darwin')
        with pytest.raises(SocketPathTooLongError, match='too long'):
            check_run_socket_paths('ubuntu2510-libre-20260714')

    def test_short_home_is_accepted(self, monkeypatch):
        monkeypatch.setattr(socket_paths, 'QEMU_STATE_DIR', Path('/tmp/adare/qemu'))
        monkeypatch.setattr(socket_paths.platform, 'system', lambda: 'Darwin')
        check_run_socket_paths('ubuntu2510')


def test_runtime_dir_is_still_under_the_state_dir(tmp_path, monkeypatch):
    """The sockets are not relocated: libvirt access, the stale sweep and run cleanup rely on this directory."""
    monkeypatch.setattr(socket_paths, 'QEMU_STATE_DIR', tmp_path / 'qemu')
    assert configuration.get_qemu_runtime_dir() == tmp_path / 'qemu' / 'run'
    assert (tmp_path / 'qemu' / 'run').is_dir()
