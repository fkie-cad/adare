"""`adare db compact` refuses while a run or a dev session may write; missing projects are reported, not created."""

import json
import os
import sqlite3
import time
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import text

from adare.database import maintenance

from .test_maintenance import RUN_TAIL, _build_db, _image_result, _insert_execution, _png, _raw

pytestmark = pytest.mark.unit

HOUR = 3600
EXPERIMENT_ID = 'exp'


def _stamp(seconds_ago: float) -> str:
    """A DateTime as adare stores it: naive UTC text."""
    return datetime.fromtimestamp(time.time() - seconds_ago, UTC).strftime('%Y-%m-%d %H:%M:%S.%f')


def _insert_run(conn, run_id, status, *, path=None, start_ago=None, created_ago=None):
    conn.execute(
        text(
            'INSERT INTO experiment_run (id, experiment_id, path, status, start_time, created_at, fake, published) '
            'VALUES (:id, :exp, :path, :status, :start, :created, 0, 0)'
        ),
        {
            'id': run_id,
            'exp': EXPERIMENT_ID,
            'path': path,
            'status': status,
            'start': None if start_ago is None else _stamp(start_ago),
            'created': None if created_ago is None else _stamp(created_ago),
        },
    )


def _age(path: Path, seconds_ago: float) -> None:
    stamp = time.time() - seconds_ago
    os.utime(path, (stamp, stamp))


def _make_project(tmp_path, runs) -> maintenance.DatabaseTarget:
    """A project with one compactable row; ``runs(conn, project_root)`` adds runs."""
    project_root = tmp_path / 'proj'
    screenshots = project_root / RUN_TAIL / 'reporting' / 'screenshots'
    screenshots.mkdir(parents=True)
    image = _png(30_000)
    (screenshots / 'a.png').write_bytes(image)

    def populate(conn):
        _insert_execution(conn, 'exec-ok', 'run-1', _image_result(image, 'reporting/screenshots/a.png'))
        runs(conn, project_root)

    return maintenance.DatabaseTarget('proj', _build_db(project_root, populate), project_root)


def _old_run_folder(project_root: Path, name: str, *, log_ago: float | None = None) -> Path:
    """A run folder with a log file; everything older than the activity window unless ``log_ago``."""
    folder = project_root / 'run' / 'exp' / name
    (folder / 'logs').mkdir(parents=True)
    log_file = folder / 'logs' / 'adare.log'
    log_file.write_text('...')
    _age(log_file, 2 * HOUR if log_ago is None else log_ago)
    for directory in (folder / 'logs', folder):
        _age(directory, 2 * HOUR)
    return folder


@pytest.fixture
def no_dev_sessions(tmp_path, monkeypatch):
    monkeypatch.setattr(maintenance, '_default_global_db_path', lambda: tmp_path / 'no-global.db')


def _compact_refused(target) -> bool:
    before = _raw(target.db_path, 'exec-ok')
    entry = maintenance.compact_database(target)
    if entry.status == 'in-use':
        assert entry.failed
        assert _raw(target.db_path, 'exec-ok') == before
        return True
    assert entry.status == 'compacted', entry.message
    return False


@pytest.mark.usefixtures('no_dev_sessions')
class TestRunActivity:
    def test_a_recently_started_run_blocks(self, tmp_path):
        target = _make_project(tmp_path, lambda conn, _root: _insert_run(conn, 'run-live', 'RUNNING', start_ago=60))

        entry = maintenance.compact_database(target)

        assert entry.status == 'in-use'
        assert "run run-live of experiment 'exp' (RUNNING" in entry.message
        assert not json.loads(_raw(target.db_path, 'exec-ok'))['image']['data'].startswith('<omitted')

    @pytest.mark.parametrize('status', ['PENDING', 'PAUSE'])
    def test_other_unfinished_statuses_block_too(self, tmp_path, status):
        target = _make_project(tmp_path, lambda conn, _root: _insert_run(conn, 'run-x', status, created_ago=60))

        assert _compact_refused(target)

    def test_an_old_run_still_writing_its_logs_blocks(self, tmp_path):
        def runs(conn, root):
            folder = _old_run_folder(root, 'long', log_ago=30)
            _insert_run(conn, 'run-long', 'RUNNING', path=str(folder), start_ago=5 * HOUR)

        assert _compact_refused(_make_project(tmp_path, runs))

    def test_a_moved_project_run_folder_is_found(self, tmp_path):
        def runs(conn, root):
            _old_run_folder(root, 'moved', log_ago=30)
            _insert_run(conn, 'run-moved', 'RUNNING', path='/old/place/proj/run/exp/moved', start_ago=5 * HOUR)

        assert _compact_refused(_make_project(tmp_path, runs))

    def test_stale_running_rows_of_crashed_runs_are_ignored_and_reported(self, tmp_path):
        def runs(conn, root):
            for index in range(3):
                folder = _old_run_folder(root, f'crashed-{index}')
                _insert_run(conn, f'run-crashed-{index}', 'RUNNING', path=str(folder), start_ago=10 * 24 * HOUR)
            _insert_run(conn, 'run-no-folder', 'RUNNING', path=None, start_ago=3 * HOUR)
            _insert_run(conn, 'run-done', 'SUCCESS', start_ago=60)  # finished: never a blocker

        target = _make_project(tmp_path, runs)

        entry = maintenance.compact_database(target)

        assert entry.status == 'compacted', entry.message
        assert entry.rows_stripped == 1
        assert entry.stale_runs_ignored == 4
        assert '4 unfinished run(s)' in entry.message
        assert entry.to_dict()['stale_runs_ignored'] == 4

    def test_the_refusal_names_the_stale_runs_it_ignored(self, tmp_path):
        def runs(conn, _root):
            _insert_run(conn, 'run-live', 'RUNNING', start_ago=60)
            _insert_run(conn, 'run-crashed', 'RUNNING', start_ago=48 * HOUR)

        entry = maintenance.compact_database(_make_project(tmp_path, runs))

        assert entry.status == 'in-use'
        assert entry.stale_runs_ignored == 1
        assert 'run-live' in entry.message and 'run-crashed' not in entry.message
        assert '1 unfinished run(s)' in entry.message

    def test_a_future_timestamp_counts_as_recent(self, tmp_path):
        target = _make_project(tmp_path, lambda conn, _root: _insert_run(conn, 'run-tz', 'RUNNING', start_ago=-HOUR))

        assert _compact_refused(target)

    def test_dry_run_is_not_refused_but_says_it_would_be(self, tmp_path):
        target = _make_project(tmp_path, lambda conn, _root: _insert_run(conn, 'run-live', 'RUNNING', start_ago=60))

        entry = maintenance.compact_database(target, dry_run=True)

        assert entry.status == 'dry-run'
        assert entry.rows_stripped == 1
        assert 'would refuse' in entry.message and 'run-live' in entry.message


def _global_db(path: Path, sessions) -> Path:
    with closing(sqlite3.connect(path)) as conn:
        conn.execute('CREATE TABLE environment (id TEXT, name TEXT, hypervisor TEXT)')
        conn.execute("INSERT INTO environment VALUES ('01ENV', 'ubuntu', 'qemu')")
        conn.execute(
            'CREATE TABLE dev_sessions (session_id TEXT, name TEXT, project_path TEXT, environment_name TEXT, '
            'vm_name TEXT, status TEXT, updated_at DATETIME)'
        )
        conn.executemany('INSERT INTO dev_sessions VALUES (?, ?, ?, ?, ?, ?, ?)', sessions)
        conn.commit()
    return path


def _session(session_id, status='running', updated_ago=5 * HOUR, name=None):
    return (session_id, name, '/projects/p', 'ubuntu', f'vm-{session_id}', status, _stamp(updated_ago))


class TestDevSessionActivity:
    @pytest.fixture
    def plain_project(self, tmp_path):
        return _make_project(tmp_path, lambda _conn, _root: None)

    def _compact(self, target, global_db, alive):
        with patch('adare.backend.devmode.vm_state_checker.is_vm_running', side_effect=alive) as probe:
            entry = maintenance.compact_database(target, global_db_path=global_db)
        return entry, probe

    def test_a_running_session_with_a_live_vm_blocks_every_database(self, tmp_path, plain_project):
        global_db = _global_db(tmp_path / 'global.db', [_session('S1', name='poke')])

        entry, probe = self._compact(plain_project, global_db, lambda _vm, _hv: True)

        assert entry.status == 'in-use'
        assert "dev session 'poke' (S1)" in entry.message
        assert 'adare dev stop' in entry.message
        probe.assert_called_once_with('vm-S1', 'qemu')

        other = maintenance.DatabaseTarget('global', global_db)
        with patch('adare.backend.devmode.vm_state_checker.is_vm_running', return_value=True):
            assert maintenance.compact_database(other, global_db_path=global_db).status == 'in-use'

    def test_a_running_row_whose_vm_is_gone_is_stale(self, tmp_path, plain_project):
        global_db = _global_db(tmp_path / 'global.db', [_session('S1')])

        entry, probe = self._compact(plain_project, global_db, lambda _vm, _hv: False)

        assert entry.status == 'compacted', entry.message
        probe.assert_called_once()

    def test_a_session_that_changed_state_recently_blocks_without_asking_the_hypervisor(self, tmp_path, plain_project):
        global_db = _global_db(tmp_path / 'global.db', [_session('S2', updated_ago=60)])

        entry, probe = self._compact(plain_project, global_db, lambda _vm, _hv: False)

        assert entry.status == 'in-use'
        assert 'dev session S2' in entry.message
        probe.assert_not_called()

    def test_stopped_sessions_are_ignored(self, tmp_path, plain_project):
        global_db = _global_db(tmp_path / 'global.db', [_session('S3', status='stopped', updated_ago=60)])

        entry, probe = self._compact(plain_project, global_db, lambda _vm, _hv: True)

        assert entry.status == 'compacted', entry.message
        probe.assert_not_called()


@pytest.mark.usefixtures('no_dev_sessions')
class TestMissingTargets:
    def test_project_target_creates_nothing(self, tmp_path):
        project_root = tmp_path / 'p'
        project_root.mkdir()

        target = maintenance.project_target(project_root)

        assert target.db_path == project_root / '.adare' / 'project.db.sqlite3'
        assert not (project_root / '.adare').exists()

    def test_a_vanished_project_directory_is_missing(self, tmp_path):
        target = maintenance.project_target(tmp_path / 'gone')

        compact = maintenance.compact_database(target)
        check = maintenance.check_database(target)

        assert compact.status == check.status == 'missing'
        assert 'project directory' in compact.message and 'not found' in check.message
        assert not compact.failed and check.integrity_ok
        assert not (tmp_path / 'gone').exists()

    @pytest.mark.skipif(os.name == 'nt' or os.geteuid() == 0, reason='POSIX permissions not enforced')
    def test_a_read_only_project_without_a_database_is_missing(self, tmp_path):
        project_root = tmp_path / 'ro'
        project_root.mkdir()
        project_root.chmod(0o555)
        try:
            target = maintenance.project_target(project_root)
            assert maintenance.check_database(target).status == 'missing'
            assert maintenance.compact_database(target, dry_run=True).status == 'missing'
        finally:
            project_root.chmod(0o755)
        assert not (project_root / '.adare').exists()

    def test_all_targets_lists_vanished_projects_without_creating_anything(self, tmp_path):
        existing = tmp_path / 'here'
        existing.mkdir()
        projects = [
            SimpleNamespace(name='here', path=str(existing)),
            SimpleNamespace(name='gone', path=str(tmp_path / 'x')),
        ]

        class _FakeGlobalApi:
            def __enter__(self):
                self._session = SimpleNamespace(query=lambda _model: SimpleNamespace(all=lambda: projects))
                return self

            def __exit__(self, *exc):
                return False

        with patch('adare.database.api.base.GlobalDatabaseApi', _FakeGlobalApi):
            targets = maintenance.all_targets()

        assert [target.label for target in targets] == ['global', 'here', 'gone']
        assert not (existing / '.adare').exists()
        assert not (tmp_path / 'x').exists()
        assert [maintenance.check_database(target).status for target in targets[1:]] == ['missing', 'missing']
