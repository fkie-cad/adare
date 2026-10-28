"""`adare db compact` / `adare db check` logic (adare.database.maintenance) on synthetic project databases."""

import base64
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import text

from adare.database import maintenance
from adare.database.api.base import create_sqlite_engine
from adare.database.models.project_models import ProjectBase

pytestmark = pytest.mark.unit

RUN_ID = 'run-1'
# The project was moved: the run's stored path still has the old prefix.
OLD_RUN_PATH = '/old/place/proj/run/exp/2026-01-01_00-00-00'
RUN_TAIL = Path('run/exp/2026-01-01_00-00-00')


def _png(size: int, seed: int = 0) -> bytes:
    return bytes((i * 31 + seed) % 256 for i in range(size))


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode('ascii')


def _image_result(data: bytes, screenshot_path: str | None) -> dict:
    result = {'status': 'success', 'image': {'data': _b64(data), 'format': 'png'}}
    if screenshot_path is not None:
        result['screenshot_path'] = screenshot_path
    return result


def _insert_execution(conn, execution_id: str, run_id: str | None, result_data, playbook_item_id: str = 'item'):
    conn.execute(
        text(
            "INSERT INTO action_execution (id, playbook_item_id, experiment_run_id, status, result_data) "
            "VALUES (:id, :item, :run_id, 'success', :data)"
        ),
        {'id': execution_id, 'item': playbook_item_id, 'run_id': run_id, 'data': json.dumps(result_data)},
    )


def _raw(db_path: Path, execution_id: str) -> str:
    with sqlite3.connect(db_path) as conn:
        return conn.execute('SELECT result_data FROM action_execution WHERE id = ?', (execution_id,)).fetchone()[0]


def _build_db(project_root: Path, populate) -> Path:
    db_path = project_root / '.adare' / 'project.db.sqlite3'
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_sqlite_engine(db_path)
    ProjectBase.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO experiment (id, name, sha256) VALUES ('exp', 'exp', 'x')"))
        conn.execute(text("INSERT INTO playbook (id, experiment_id, name) VALUES ('pb', 'exp', 'pb')"))
        conn.execute(
            text(
                "INSERT INTO playbook_item (id, playbook_id, item_type, sequence_order, parameters) "
                "VALUES ('item', 'pb', 'action', 0, '{}')"
            )
        )
        conn.execute(
            text("INSERT INTO experiment_run (id, path, fake, published) VALUES (:id, :path, 0, 0)"),
            {'id': RUN_ID, 'path': OLD_RUN_PATH},
        )
        populate(conn)
    engine.dispose()
    return db_path


@pytest.fixture
def project(tmp_path):
    """A moved project with one run, its screenshot on disk, and rows of every kind."""
    project_root = tmp_path / 'proj'
    screenshots = project_root / RUN_TAIL / 'reporting' / 'screenshots'
    screenshots.mkdir(parents=True)
    on_disk = _png(30_000)
    (screenshots / 'a.png').write_bytes(on_disk)
    absolute_png = tmp_path / 'elsewhere.png'
    absolute_png.write_bytes(_png(25_000, seed=3))

    def populate(conn):
        _insert_execution(conn, 'exec-ok', RUN_ID, _image_result(on_disk, 'reporting/screenshots/a.png'))
        _insert_execution(conn, 'exec-absolute', None, _image_result(_png(25_000, seed=3), str(absolute_png)))
        _insert_execution(conn, 'exec-missing', RUN_ID, _image_result(on_disk, 'reporting/screenshots/gone.png'))
        _insert_execution(conn, 'exec-nopath', RUN_ID, _image_result(on_disk, None))
        _insert_execution(conn, 'exec-mismatch', RUN_ID, _image_result(_png(40_000), 'reporting/screenshots/a.png'))
        _insert_execution(conn, 'exec-text', RUN_ID, {'status': 'success', 'output': 'x' * 20_000})
        _insert_execution(conn, 'exec-small', RUN_ID, {'status': 'success', 'x': 1})

    db_path = _build_db(project_root, populate)
    return maintenance.DatabaseTarget('proj', db_path, project_root)


KEPT = ('exec-missing', 'exec-nopath', 'exec-mismatch', 'exec-small')


class TestCompact:
    def test_strips_backed_images_and_keeps_rows_whose_file_is_missing(self, project):
        before = {execution_id: _raw(project.db_path, execution_id) for execution_id in KEPT}

        entry = maintenance.compact_database(project)

        assert entry.status == 'compacted', entry.message
        assert entry.rows_stripped == 2
        assert entry.rows_kept_missing_file == 3
        assert entry.rows_non_image_stripped == 1
        assert entry.vacuumed
        for execution_id in ('exec-ok', 'exec-absolute'):
            stripped = json.loads(_raw(project.db_path, execution_id))
            assert stripped['image']['data'].startswith('<omitted: ')
            assert stripped['image']['format'] == 'png'
            assert stripped['screenshot_path']
        assert json.loads(_raw(project.db_path, 'exec-text'))['output'] == '<omitted: 20000 chars>'
        for execution_id in KEPT:
            assert _raw(project.db_path, execution_id) == before[execution_id]

    def test_second_run_finds_nothing_left(self, project):
        maintenance.compact_database(project)

        entry = maintenance.compact_database(project)

        assert entry.rows_stripped == entry.rows_non_image_stripped == entry.reclaimable_bytes == 0
        assert entry.rows_kept_missing_file == 3

    def test_dry_run_writes_nothing_and_reports_reclaimable_bytes(self, project):
        db_path = project.db_path
        digest, mtime = hashlib.sha256(db_path.read_bytes()).hexdigest(), db_path.stat().st_mtime_ns
        stripped_ids = ('exec-ok', 'exec-absolute', 'exec-text')
        rows = {execution_id: _raw(db_path, execution_id) for execution_id in (*stripped_ids, *KEPT)}
        expected = sum(
            len(rows[execution_id]) - len(json.dumps(maintenance.strip_bulky_values(json.loads(rows[execution_id]))))
            for execution_id in stripped_ids
        )

        entry = maintenance.compact_database(project, dry_run=True)

        assert entry.status == 'dry-run'
        assert entry.rows_stripped == 2 and entry.rows_kept_missing_file == 3 and entry.rows_non_image_stripped == 1
        assert entry.reclaimable_bytes == expected > 50_000
        assert not entry.vacuumed
        assert hashlib.sha256(db_path.read_bytes()).hexdigest() == digest
        assert db_path.stat().st_mtime_ns == mtime
        for execution_id, raw in rows.items():
            assert _raw(db_path, execution_id) == raw

    def test_vacuum_shrinks_the_file(self, tmp_path):
        project_root = tmp_path / 'big'
        screenshots = project_root / RUN_TAIL / 'reporting' / 'screenshots'
        screenshots.mkdir(parents=True)

        def populate(conn):
            for index in range(40):
                image = _png(150_000, seed=index)
                (screenshots / f'{index}.png').write_bytes(image)
                _insert_execution(
                    conn, f'exec-{index}', RUN_ID, _image_result(image, f'reporting/screenshots/{index}.png')
                )

        db_path = _build_db(project_root, populate)
        size_before = db_path.stat().st_size

        entry = maintenance.compact_database(maintenance.DatabaseTarget('big', db_path, project_root))

        assert entry.rows_stripped == 40
        assert entry.vacuumed and entry.vacuum_message is None
        assert entry.size_before == size_before
        assert entry.size_after == db_path.stat().st_size < size_before // 10
        assert entry.wal_size_after == 0

    def test_skips_vacuum_without_enough_free_space(self, project, monkeypatch):
        monkeypatch.setattr(maintenance.shutil, 'disk_usage', lambda _path: _Usage(free=0))

        entry = maintenance.compact_database(project)

        assert entry.status == 'compacted'
        assert entry.rows_stripped == 2  # the row rewrite stands
        assert not entry.vacuumed
        assert 'VACUUM skipped' in entry.vacuum_message

    def test_refuses_while_another_connection_holds_the_write_lock(self, project, monkeypatch):
        monkeypatch.setattr(maintenance, 'LOCK_TIMEOUT_SECONDS', 0.1)
        before = _raw(project.db_path, 'exec-ok')
        writer = sqlite3.connect(project.db_path, isolation_level=None)
        try:
            writer.execute('BEGIN IMMEDIATE')

            entry = maintenance.compact_database(project)
        finally:
            writer.execute('ROLLBACK')
            writer.close()

        assert entry.status == 'in-use'
        assert entry.failed
        assert 'in use' in entry.message
        assert _raw(project.db_path, 'exec-ok') == before

    def test_missing_database_file(self, tmp_path):
        entry = maintenance.compact_database(maintenance.DatabaseTarget('x', tmp_path / 'none.db', tmp_path))

        assert entry.status == 'missing'
        assert not (tmp_path / 'none.db').exists()

    def test_a_database_without_action_results_is_only_vacuumed(self, tmp_path):
        db_path = tmp_path / 'global.db'
        with sqlite3.connect(db_path) as conn:
            conn.execute('CREATE TABLE project (id TEXT)')
        conn.close()

        entry = maintenance.compact_database(maintenance.DatabaseTarget('global', db_path))

        assert entry.status == 'compacted'
        assert entry.rows_examined == 0
        assert entry.vacuumed


class _Usage:
    def __init__(self, free):
        self.free = free


class TestResolveRunDir:
    def test_path_under_the_project_is_used_as_is(self, tmp_path):
        assert maintenance._resolve_run_dir(str(tmp_path / 'run/e/t'), tmp_path) == tmp_path / 'run/e/t'

    def test_moved_project_is_rebased_on_the_current_root(self, tmp_path):
        assert maintenance._resolve_run_dir('/old/p/diff/e/t', tmp_path) == tmp_path / 'diff/e/t'

    def test_relative_path_is_taken_from_the_project_root(self, tmp_path):
        assert maintenance._resolve_run_dir('run/e/t', tmp_path) == tmp_path / 'run/e/t'

    def test_unrecognisable_path_is_unresolved(self, tmp_path):
        assert maintenance._resolve_run_dir('/somewhere/else', tmp_path) is None
        assert maintenance._resolve_run_dir(None, tmp_path) is None


def _orphaned_db(tmp_path) -> maintenance.DatabaseTarget:
    project_root = tmp_path / 'orphans'

    def populate(conn):
        conn.execute(text("INSERT INTO log_file (id, name, path) VALUES ('log-orphan', 'l', '/l')"))
        conn.execute(text("INSERT INTO experiment_run_files (id, log_adare_id) VALUES ('files-orphan', 'log-orphan')"))
        _insert_execution(conn, 'exec-live', RUN_ID, {'ok': True})
        _insert_execution(conn, 'exec-deleted-run-1', 'run-gone', {'ok': True})
        _insert_execution(conn, 'exec-deleted-run-2', 'run-gone', {'ok': True})
        _insert_execution(conn, 'exec-dangling', RUN_ID, {'ok': True}, playbook_item_id='item-gone')
        _insert_execution(conn, 'exec-dev', None, {'ok': True})

    return maintenance.DatabaseTarget('orphans', _build_db(project_root, populate), project_root)


class TestCheck:
    def test_reports_orphans_and_foreign_key_violations(self, tmp_path):
        target = _orphaned_db(tmp_path)
        digest = hashlib.sha256(target.db_path.read_bytes()).hexdigest()

        entry = maintenance.check_database(target)

        assert entry.integrity_ok
        assert entry.problems == []
        assert entry.orphans == {
            'action_execution_without_run': 2,
            'experiment_run_files_unreferenced': 1,
            'log_file_unreferenced': 1,
            'action_execution_dangling_playbook_item': 1,
        }
        violations = {(v.table, v.parent): v.count for v in entry.foreign_key_violations}
        assert violations == {('action_execution', 'playbook_item'): 1}
        assert hashlib.sha256(target.db_path.read_bytes()).hexdigest() == digest

    def test_clean_database(self, project):
        entry = maintenance.check_database(project)

        assert entry.integrity_ok
        assert entry.foreign_key_violations == []
        assert set(entry.orphans.values()) == {0}

    def test_corrupt_file_fails_integrity(self, tmp_path):
        target = _orphaned_db(tmp_path)
        corrupt = _corrupt_copy(target.db_path, tmp_path / 'corrupt.db')

        entry = maintenance.check_database(maintenance.DatabaseTarget('corrupt', corrupt))

        assert not entry.integrity_ok
        assert entry.problems

    def test_not_a_database(self, tmp_path):
        bogus = tmp_path / 'bogus.db'
        bogus.write_bytes(b'not a database at all' * 500)

        entry = maintenance.check_database(maintenance.DatabaseTarget('bogus', bogus))

        assert not entry.integrity_ok
        assert any('not a database' in problem for problem in entry.problems)

    def test_missing_file_is_not_corrupt(self, tmp_path):
        entry = maintenance.check_database(maintenance.DatabaseTarget('none', tmp_path / 'none.db'))

        assert entry.integrity_ok
        assert entry.message == 'no database file'


def _corrupt_copy(db_path: Path, destination: Path) -> Path:
    """Copy of ``db_path`` with every page after the schema page overwritten by garbage."""
    data = bytearray(db_path.read_bytes())
    page_size = int.from_bytes(data[16:18], 'big')
    for offset in range(page_size, len(data)):
        data[offset] = 0xA5
    destination.write_bytes(bytes(data))
    return destination


def test_orphan_queries_count_what_the_migration_deletes():
    for name, (sql, _tables) in maintenance.ORPHAN_QUERIES.items():
        assert sql.lstrip().startswith('SELECT COUNT(*) FROM'), name
