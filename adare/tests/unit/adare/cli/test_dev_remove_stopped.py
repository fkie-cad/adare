"""`adare dev remove --stopped`: stopped sessions each keep a full VM disk until removed."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from adare.cli.dev import session as dev_session

pytestmark = pytest.mark.unit

NOW = datetime.now(UTC).replace(tzinfo=None)


def _session(sid, status, days_ago, vm_name):
    return SimpleNamespace(
        session_id=sid,
        status=status,
        updated_at=NOW - timedelta(days=days_ago),
        created_at=NOW - timedelta(days=days_ago),
        vm_name=vm_name,
        experiment_name='exp',
        environment_name='env',
    )


SESSIONS = [
    _session('old-stopped', 'stopped', 40, 'vm_a'),
    _session('old-crashed', 'crashed', 20, 'vm_b'),
    _session('fresh-stopped', 'stopped', 2, 'vm_c'),
    _session('running', 'running', 40, 'vm_d'),
]


@pytest.fixture
def api():
    api = MagicMock()
    api.devmode.stop_session.return_value = SimpleNamespace(success=True, error=None)
    with (
        patch('adare.database.api.devmode.DevModeApi') as dev_api,
        patch(
            'adare.backend.system.storage.group_disk_owners',
            return_value=[SimpleNamespace(name='vm_a', bytes=5 * 1024**3)],
        ),
    ):
        dev_api.return_value.__enter__.return_value.list_sessions.return_value = SESSIONS
        yield api


def _removed(api):
    return [c.args[0].session_id for c in api.devmode.stop_session.call_args_list]


def test_removes_only_stopped_sessions_older_than_the_limit(api, capsys):
    dev_session._exec_dev_remove_stopped(api, '14d', assume_yes=True)

    assert _removed(api) == ['old-stopped', 'old-crashed']
    assert all(c.args[0].remove_resources for c in api.devmode.stop_session.call_args_list)
    assert '5.0 GiB' in capsys.readouterr().out


def test_without_an_age_every_stopped_session_goes_but_never_a_running_one(api):
    dev_session._exec_dev_remove_stopped(api, None, assume_yes=True)

    assert _removed(api) == ['old-stopped', 'old-crashed', 'fresh-stopped']


def test_nothing_is_removed_without_confirmation(api):
    with patch('click.confirm', return_value=False):
        dev_session._exec_dev_remove_stopped(api, None, assume_yes=False)

    api.devmode.stop_session.assert_not_called()


@pytest.mark.parametrize(
    ('text', 'expected'), [('14d', timedelta(days=14)), ('12h', timedelta(hours=12)), ('7', timedelta(days=7))]
)
def test_parse_age(text, expected):
    assert dev_session.parse_age(text) == expected


def test_parse_age_rejects_garbage():
    with pytest.raises(ValueError):
        dev_session.parse_age('soon')
