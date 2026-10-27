"""ADARE_DEV_SESSION_MAX_AGE_DAYS: opt-in expiry of forgotten dev sessions."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from adare.backend.devmode import expiry

pytestmark = pytest.mark.unit

NOW = datetime.now(UTC).replace(tzinfo=None)


def _session(sid, status, days_ago, vm_name=None):
    when = NOW - timedelta(days=days_ago)
    return SimpleNamespace(session_id=sid, status=status, updated_at=when, created_at=when, vm_name=vm_name or sid)


SESSIONS = [
    _session('old-stopped', 'stopped', 40),
    _session('old-crashed', 'crashed', 35),
    _session('old-but-vm-up', 'stopped', 40),
    _session('fresh', 'stopped', 2),
    _session('running', 'running', 90),
]


@pytest.fixture
def no_user_config():
    with patch('adare.config.userconfig.get', return_value=None):
        yield


@pytest.fixture
def sessions():
    with (
        patch('adare.database.api.devmode.DevModeApi') as dev_api,
        patch.object(expiry, '_vm_running', side_effect=lambda name: name == 'old-but-vm-up'),
    ):
        dev_api.return_value.__enter__.return_value.list_sessions.return_value = SESSIONS
        yield


@pytest.fixture
def api():
    api = MagicMock()
    api.devmode.stop_session.return_value = SimpleNamespace(success=True, error=None)
    with patch('adare.api.AdareAPI', return_value=api):
        yield api


class TestMaxAge:
    def test_off_by_default(self, monkeypatch, no_user_config):
        monkeypatch.delenv(expiry.MAX_AGE_ENV, raising=False)
        assert expiry.max_age() is None

    def test_days_from_the_environment(self, monkeypatch, no_user_config):
        monkeypatch.setenv(expiry.MAX_AGE_ENV, '30')
        assert expiry.max_age() == timedelta(days=30)

    def test_falls_back_to_the_user_config(self, monkeypatch):
        monkeypatch.delenv(expiry.MAX_AGE_ENV, raising=False)
        with patch('adare.config.userconfig.get', return_value='14'):
            assert expiry.max_age() == timedelta(days=14)

    @pytest.mark.parametrize('raw', ['soon', '0', '-3'])
    def test_invalid_values_switch_it_off(self, monkeypatch, no_user_config, raw):
        monkeypatch.setenv(expiry.MAX_AGE_ENV, raw)
        assert expiry.max_age() is None


def test_nothing_expires_when_unset(monkeypatch, no_user_config, sessions, api):
    monkeypatch.delenv(expiry.MAX_AGE_ENV, raising=False)
    assert expiry.remove_expired_dev_sessions() == []
    api.devmode.stop_session.assert_not_called()


def test_removes_only_old_stopped_sessions_whose_vm_is_down(monkeypatch, no_user_config, sessions, api):
    monkeypatch.setenv(expiry.MAX_AGE_ENV, '30')

    assert expiry.remove_expired_dev_sessions() == ['old-stopped', 'old-crashed']
    requests = [c.args[0] for c in api.devmode.stop_session.call_args_list]
    assert [r.session_id for r in requests] == ['old-stopped', 'old-crashed']
    assert all(r.remove_resources for r in requests)


def test_dry_run_lists_without_removing(monkeypatch, no_user_config, sessions, api):
    monkeypatch.setenv(expiry.MAX_AGE_ENV, '30')

    assert expiry.remove_expired_dev_sessions(dry_run=True) == ['old-stopped', 'old-crashed']
    api.devmode.stop_session.assert_not_called()


def test_a_failed_removal_is_not_reported_as_removed(monkeypatch, no_user_config, sessions, api):
    monkeypatch.setenv(expiry.MAX_AGE_ENV, '30')
    api.devmode.stop_session.side_effect = [
        SimpleNamespace(success=False, error='busy'),
        SimpleNamespace(success=True, error=None),
    ]

    assert expiry.remove_expired_dev_sessions() == ['old-crashed']


@pytest.mark.parametrize(('dev_mode', 'expected_calls'), [(False, 1), (True, 0)])
def test_runs_expire_sessions_but_a_dev_session_never_does(dev_mode, expected_calls):
    """A dev session's own VM preparation (resume, snapshot restore) must not expire sessions."""
    import asyncio

    from adare.backend.experiment.vm_lifecycle_manager import VMLifecycleManager

    context = SimpleNamespace(config=SimpleNamespace(dev_mode=dev_mode), environment_ulid='env')

    def stop(coro, timeout=None):
        coro.close()
        raise RuntimeError('stop after the expiry step')

    with (
        patch(
            'adare.backend.experiment.vm_lifecycle_manager.environment_database.get_environment_by_ulid',
            return_value={'vm_id': 'vm-1'},
        ),
        patch.object(expiry, 'remove_expired_dev_sessions', return_value=[]) as remove,
        patch('asyncio.wait_for', side_effect=stop),
        pytest.raises(RuntimeError, match='stop after'),
    ):
        asyncio.run(VMLifecycleManager('qemu').create_and_prepare_vm(context))
    assert remove.call_count == expected_calls
