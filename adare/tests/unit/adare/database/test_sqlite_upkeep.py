"""SQLite upkeep: ``PRAGMA optimize`` when a command ends (``optimize_engines``) and the WAL size cap."""

import os
import sqlite3
import sys
from contextlib import closing

import pytest

from adare.database import maintenance
from adare.database.api import base
from adare.database.api.base import ProjectDatabaseApi, optimize_engines

pytestmark = pytest.mark.unit

needs_permissions = pytest.mark.skipif(
    sys.platform == 'win32' or os.geteuid() == 0, reason='POSIX permissions not enforced (Windows or root)'
)


def _analyzed(db_path) -> bool:
    """Has ANALYZE written statistics (``sqlite_stat1``) to the file?"""
    with closing(sqlite3.connect(db_path)) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        return 'sqlite_stat1' in tables and conn.execute('SELECT COUNT(*) FROM sqlite_stat1').fetchone()[0] > 0


def _project_with_rows(tmp_path):
    api = ProjectDatabaseApi(tmp_path / 'proj')
    with api.engine.begin() as conn:
        conn.exec_driver_sql("INSERT INTO experiment (id, name, sha256) VALUES ('e1', 'exp', 'x')")
    return api.db_path


def test_optimize_engines_analyzes_and_keeps_the_engine_usable(tmp_path):
    db_path = _project_with_rows(tmp_path)
    engine = base._ENGINES[str(db_path)][0]

    optimize_engines()

    assert _analyzed(db_path)
    assert base._ENGINES[str(db_path)][0] is engine  # still cached ...
    assert engine.pool.checkedin() == 0  # ... but its connections were closed
    with engine.connect() as conn:  # and it reconnects
        assert conn.exec_driver_sql('SELECT COUNT(*) FROM experiment').scalar_one() == 1


def test_optimize_engines_does_not_recreate_a_deleted_database(tmp_path):
    db_path = _project_with_rows(tmp_path)
    for path in tmp_path.joinpath('proj', '.adare').glob('project.db.sqlite3*'):
        path.unlink()

    optimize_engines()

    assert not db_path.exists()


def test_optimize_engines_skips_a_write_locked_database(tmp_path):
    db_path = _project_with_rows(tmp_path)
    base._ENGINES[str(db_path)][0].dispose()
    with closing(sqlite3.connect(db_path, isolation_level=None)) as writer:
        writer.execute('BEGIN IMMEDIATE')
        writer.execute("INSERT INTO experiment (id, name, sha256) VALUES ('e2', 'exp2', 'y')")

        optimize_engines()  # waits at most OPTIMIZE_BUSY_TIMEOUT_MS, then gives up quietly

        writer.execute('ROLLBACK')
    assert not _analyzed(db_path)


@needs_permissions
def test_optimize_engines_skips_a_read_only_database(tmp_path):
    db_path = _project_with_rows(tmp_path)
    base._ENGINES[str(db_path)][0].dispose()
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute('PRAGMA journal_mode=DELETE')  # no -wal/-shm needed to read
    db_path.chmod(0o444)
    try:
        optimize_engines()
    finally:
        db_path.chmod(0o644)
    assert not _analyzed(db_path)


def test_optimize_engines_without_engines():
    base.dispose_engines()
    optimize_engines()


def test_compact_connection_caps_the_wal(tmp_path):
    db_path = tmp_path / 'a.sqlite3'
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute('CREATE TABLE t (x)')

    with closing(maintenance._open_for_writing(db_path)) as conn:
        assert conn.execute('PRAGMA journal_size_limit').fetchone()[0] == 64 * 1024 * 1024
