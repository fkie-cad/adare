"""`adare db compact` / `adare db check`: CLI -> ManageAPI -> ManageService -> maintenance, end to end."""

import base64
import json
import sqlite3
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from adare.database import maintenance

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _no_dev_sessions(tmp_path, monkeypatch):
    monkeypatch.setattr(maintenance, '_default_global_db_path', lambda: tmp_path / 'no-global.db')


def _make_db(tmp_path, *, corrupt: bool = False) -> maintenance.DatabaseTarget:
    project_root = tmp_path / 'proj'
    db_path = project_root / '.adare' / 'project.db.sqlite3'
    db_path.parent.mkdir(parents=True)
    png = bytes(range(256)) * 200
    (project_root / 'shot.png').write_bytes(png)
    image = {'image': {'data': base64.b64encode(png).decode('ascii'), 'format': 'png'}, 'screenshot_path': 'shot.png'}
    with sqlite3.connect(db_path) as conn:
        conn.execute('CREATE TABLE action_execution (id TEXT, experiment_run_id TEXT, result_data JSON)')
        conn.execute("INSERT INTO action_execution VALUES ('e1', NULL, ?)", (json.dumps({'out': 'x' * 20_000}),))
        conn.execute("INSERT INTO action_execution VALUES ('e2', NULL, ?)", (json.dumps(image),))
        conn.executemany('INSERT INTO action_execution VALUES (?, NULL, ?)', [(str(i), '{}') for i in range(500)])
    conn.close()
    if corrupt:
        data = bytearray(db_path.read_bytes())
        page_size = int.from_bytes(data[16:18], 'big')
        data[page_size:] = b'\xa5' * (len(data) - page_size)
        db_path.write_bytes(bytes(data))
    return maintenance.DatabaseTarget('proj', db_path, project_root)


def _invoke(*args):
    from adare.run import cli

    return CliRunner().invoke(cli, ['db', *args])


def test_compact_json_shape(tmp_path):
    target = _make_db(tmp_path)

    with patch('adare.database.maintenance.all_targets', return_value=[target]):
        result = _invoke('compact', '--all', '--json')

    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data['dry_run'] is False and data['ok'] is True
    [entry] = data['databases']
    assert entry['label'] == 'proj'
    assert entry['path'] == str(target.db_path)
    assert entry['status'] == 'compacted'
    assert entry['rows'] == {
        'examined': 2,
        'stripped': 1,
        'kept_missing_file': 0,
        'kept_mismatch': 0,
        'non_image_kept': 1,
    }
    assert entry['stale_runs_ignored'] == 0
    assert entry['reclaimable_bytes'] > 60_000
    assert entry['vacuum']['done'] is True
    assert set(entry['size_before']) == set(entry['size_after']) == {'db', 'wal'}
    assert entry['size_after']['db'] < entry['size_before']['db']
    assert isinstance(entry['duration_seconds'], float)


def test_compact_dry_run_flag_reaches_the_maintenance_layer(tmp_path):
    target = _make_db(tmp_path)
    before = target.db_path.read_bytes()

    with patch('adare.database.maintenance.all_targets', return_value=[target]):
        result = _invoke('compact', '--all', '--dry-run', '--json')

    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data['dry_run'] is True
    assert data['databases'][0]['status'] == 'dry-run'
    assert target.db_path.read_bytes() == before


@pytest.mark.parametrize(('flags', 'expected'), [(['--dry-run'], 'would strip'), ([], 'size after')])
def test_compact_rich_output(tmp_path, flags, expected):
    target = _make_db(tmp_path)

    with patch('adare.database.maintenance.all_targets', return_value=[target]):
        result = _invoke('compact', '--all', *flags, '--format', 'rich')

    assert result.exit_code == 0, result.output
    assert expected in result.output
    assert 'oversized non-image text (kept)' in result.output
    assert 'screenshot file differs' in result.output


def test_compact_exits_1_when_the_database_is_in_use(tmp_path, monkeypatch):
    target = _make_db(tmp_path)
    monkeypatch.setattr(maintenance, 'LOCK_TIMEOUT_SECONDS', 0.1)
    writer = sqlite3.connect(target.db_path, isolation_level=None)
    writer.execute('BEGIN IMMEDIATE')
    try:
        with patch('adare.database.maintenance.all_targets', return_value=[target]):
            result = _invoke('compact', '--all', '--json')
    finally:
        writer.execute('ROLLBACK')
        writer.close()

    assert result.exit_code == 1
    data = json.loads(result.stdout)
    assert data['ok'] is False
    assert data['databases'][0]['status'] == 'in-use'


def test_check_json_shape(tmp_path):
    target = _make_db(tmp_path)

    with patch('adare.database.maintenance.all_targets', return_value=[target]):
        result = _invoke('check', '--all', '--json')

    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data['ok'] is True
    [entry] = data['databases']
    assert entry == {
        'label': 'proj',
        'path': str(target.db_path),
        'status': 'checked',
        'integrity_ok': True,
        'problems': [],
        'foreign_key_violations': [],
        'orphans': {},
        'message': None,
    }


def test_check_exits_1_on_a_corrupt_database(tmp_path):
    target = _make_db(tmp_path, corrupt=True)

    with patch('adare.database.maintenance.all_targets', return_value=[target]):
        result = _invoke('check', '--all', '--json')

    assert result.exit_code == 1
    data = json.loads(result.stdout)
    assert data['ok'] is False
    assert data['databases'][0]['integrity_ok'] is False
    assert data['databases'][0]['problems']


def test_check_rich_output_labels_runless_executions_as_kept(tmp_path, monkeypatch):
    monkeypatch.setenv('COLUMNS', '300')
    target = _make_db(tmp_path)
    entry = maintenance.check_database(target)
    entry.orphans = {'action_execution_without_run': 3}

    with (
        patch('adare.database.maintenance.all_targets', return_value=[target]),
        patch('adare.database.maintenance.check_database', return_value=entry),
    ):
        result = _invoke('check', '--all', '--format', 'rich')

    assert result.exit_code == 0, result.output
    assert 'dev-session consoles or runs deleted by older versions; kept' in result.output
    assert 'adare db migrate' not in result.output


def test_check_all_reports_a_vanished_project_and_checks_the_rest(tmp_path):
    good = _make_db(tmp_path)
    gone = maintenance.DatabaseTarget('gone', tmp_path / 'gone' / '.adare' / 'project.db.sqlite3', tmp_path / 'gone')

    with patch('adare.database.maintenance.all_targets', return_value=[gone, good]):
        result = _invoke('check', '--all', '--json')

    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert [entry['status'] for entry in data['databases']] == ['missing', 'checked']
    assert not (tmp_path / 'gone').exists()


def test_without_a_project_it_fails_with_a_hint(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    result = _invoke('check', '--json')

    assert result.exit_code != 0
    assert '--all' in result.output
