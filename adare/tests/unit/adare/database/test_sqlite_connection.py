"""SQLite connection settings (WAL, synchronous, busy_timeout, journal_size_limit) and database file removal."""

import os
import sqlite3
import subprocess
import sys
import textwrap
from unittest.mock import patch

import pytest
import sqlalchemy

from adare.database import init as db_init
from adare.database.api import base
from adare.database.api.base import (
    ProjectDatabaseApi,
    configure_sqlite,
    create_sqlite_engine,
    remove_database_files,
)

pytestmark = pytest.mark.unit

SIDECARS = ('-wal', '-shm', '-journal')


def _pragmas(engine: sqlalchemy.Engine) -> tuple[str, int, int, int, int]:
    with engine.connect() as conn:
        return (
            conn.exec_driver_sql('PRAGMA journal_mode').scalar_one(),
            conn.exec_driver_sql('PRAGMA synchronous').scalar_one(),
            conn.exec_driver_sql('PRAGMA busy_timeout').scalar_one(),
            conn.exec_driver_sql('PRAGMA foreign_keys').scalar_one(),
            conn.exec_driver_sql('PRAGMA journal_size_limit').scalar_one(),
        )


# synchronous=NORMAL reads back as 1; foreign keys stay off by decision; the WAL is capped at 64 MiB.
EXPECTED = ('wal', 1, 30000, 0, 67108864)


def test_new_engine_gets_the_connection_pragmas(tmp_path):
    engine = create_sqlite_engine(tmp_path / 'a.sqlite3')
    try:
        assert _pragmas(engine) == EXPECTED
    finally:
        engine.dispose()


def test_cached_api_engine_gets_the_connection_pragmas(tmp_path):
    api = ProjectDatabaseApi(tmp_path)

    assert _pragmas(api.engine) == EXPECTED
    assert base._engine_for(api.db_path)[0] is api.engine


def test_schema_engine_of_db_init_gets_the_connection_pragmas(tmp_path):
    engine = db_init._engine_for(tmp_path / 'b.sqlite3')
    try:
        assert _pragmas(engine) == EXPECTED
    finally:
        engine.dispose()


def test_every_pooled_connection_is_configured(tmp_path):
    engine = create_sqlite_engine(tmp_path / 'c.sqlite3')
    try:
        with engine.connect() as first, engine.connect() as second:
            for conn in (first, second):
                assert conn.exec_driver_sql('PRAGMA busy_timeout').scalar_one() == 30000
                assert conn.exec_driver_sql('PRAGMA synchronous').scalar_one() == 1
    finally:
        engine.dispose()


def test_in_memory_engine_keeps_memory_journal():
    engine = configure_sqlite(sqlalchemy.create_engine('sqlite:///:memory:'))
    try:
        journal_mode, synchronous, busy_timeout, _fk, _limit = _pragmas(engine)
    finally:
        engine.dispose()

    assert journal_mode == 'memory'  # WAL does not apply to in-memory databases
    assert (synchronous, busy_timeout) == (1, 30000)


def test_wal_mode_is_persistent_in_the_file(tmp_path):
    db_path = tmp_path / 'd.sqlite3'
    engine = create_sqlite_engine(db_path)
    with engine.begin() as conn:
        conn.exec_driver_sql('CREATE TABLE t (x INTEGER)')
    engine.dispose()

    plain = sqlite3.connect(db_path)
    try:
        assert plain.execute('PRAGMA journal_mode').fetchone()[0] == 'wal'
    finally:
        plain.close()


# --- read-only databases ------------------------------------------------------

needs_permissions = pytest.mark.skipif(
    sys.platform == 'win32' or os.geteuid() == 0, reason='POSIX permissions not enforced (Windows or root)'
)


def _rollback_journal_db(db_path):
    """A database in the default (delete) journal mode, as an older adare wrote it."""
    plain = sqlite3.connect(db_path)
    try:
        plain.execute('CREATE TABLE t (x INTEGER)')
        plain.execute('INSERT INTO t VALUES (7)')
        plain.commit()
    finally:
        plain.close()
    return db_path


def _read_through_engine(db_path) -> tuple[list[int], str, int, int]:
    engine = create_sqlite_engine(db_path)
    try:
        with engine.connect() as conn:
            rows = [row[0] for row in conn.exec_driver_sql('SELECT x FROM t')]
            return (
                rows,
                conn.exec_driver_sql('PRAGMA journal_mode').scalar_one(),
                conn.exec_driver_sql('PRAGMA busy_timeout').scalar_one(),
                conn.exec_driver_sql('PRAGMA synchronous').scalar_one(),
            )
    finally:
        engine.dispose()


@needs_permissions
def test_read_only_database_file_stays_readable(tmp_path):
    db_path = _rollback_journal_db(tmp_path / 'ro.sqlite3')
    db_path.chmod(0o444)
    try:
        assert _read_through_engine(db_path) == ([7], 'delete', 30000, 1)
    finally:
        db_path.chmod(0o644)


@needs_permissions
def test_database_in_a_read_only_directory_stays_readable(tmp_path):
    directory = tmp_path / 'ro-dir'
    directory.mkdir()
    db_path = _rollback_journal_db(directory / 'db.sqlite3')
    directory.chmod(0o555)
    try:
        assert _read_through_engine(db_path) == ([7], 'delete', 30000, 1)
    finally:
        directory.chmod(0o755)


def test_only_an_operational_error_of_the_wal_switch_is_swallowed(tmp_path):
    """Any other pragma failure still surfaces."""
    engine = create_sqlite_engine(tmp_path / 'e.sqlite3')
    with patch.object(base, 'SQLITE_CONNECT_PRAGMAS', ('PRAGMA busy_timeout=30000', 'PRAGMA no_such_syntax(')):
        try:
            with pytest.raises(sqlalchemy.exc.OperationalError), engine.connect():
                pass
        finally:
            engine.dispose()


# --- removing database files -------------------------------------------------


def _with_sidecars(db_path):
    db_path.write_bytes(b'db')
    for suffix in SIDECARS:
        db_path.with_name(db_path.name + suffix).write_bytes(b'stale')
    return db_path


def _leftovers(db_path):
    return sorted(p.name for p in db_path.parent.iterdir() if p.name.startswith(db_path.name))


def test_wal_database_sidecar_names_match(tmp_path):
    """A live WAL database really keeps the -wal/-shm files we delete."""
    db_path = tmp_path / 'live.sqlite3'
    engine = create_sqlite_engine(db_path)
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql('CREATE TABLE t (x INTEGER)')
            conn.commit()
            assert {f'{db_path.name}-wal', f'{db_path.name}-shm'} <= set(_leftovers(db_path))
    finally:
        engine.dispose()


def test_remove_database_files_deletes_main_file_and_sidecars(tmp_path):
    db_path = _with_sidecars(tmp_path / 'e.sqlite3')

    assert remove_database_files(db_path) is True
    assert _leftovers(db_path) == []


def test_remove_database_files_removes_orphaned_sidecars(tmp_path):
    db_path = _with_sidecars(tmp_path / 'f.sqlite3')
    db_path.unlink()

    assert remove_database_files(db_path) is True
    assert _leftovers(db_path) == []


def test_remove_database_files_without_files(tmp_path):
    assert remove_database_files(tmp_path / 'missing.sqlite3') is False


def test_remove_database_files_disposes_cached_engines(tmp_path):
    api = ProjectDatabaseApi(tmp_path)

    remove_database_files(api.db_path)

    assert base._ENGINES == {}
    assert not api.db_path.exists()


def test_reset_db_removes_sidecars(tmp_path):
    from adare.services.manage_service import ManageService

    db_path = _with_sidecars(tmp_path / 'global.db.sqlite3')
    with patch('adare.services.manage_service.get_global_database_location', return_value=db_path):
        result = ManageService().reset_db()

    assert result.success is True
    assert result.data.was_reset is True
    assert _leftovers(db_path) == []


def test_clean_install_removes_sidecars(tmp_path):
    db_path = _with_sidecars(tmp_path / 'global.db.sqlite3')
    with (
        patch.object(db_init, 'get_global_database_location', return_value=db_path),
        patch.object(db_init, 'initialize_database_system', return_value={'global_db_initialized': True}),
    ):
        results = db_init.clean_install_database_system()

    assert results['installed'] is True
    assert 'Removed existing global database' in results['actions_taken']
    assert _leftovers(db_path) == []


def test_project_directory_remove_disposes_engines(tmp_path):
    from adare.backend.project.directory import ProjectDirectory

    project = tmp_path / 'proj'
    api = ProjectDatabaseApi(project)
    assert str(api.db_path) in base._ENGINES

    ProjectDirectory(project).remove()

    assert base._ENGINES == {}
    assert not project.exists()


# --- concurrency -------------------------------------------------------------

_READER = textwrap.dedent(
    """
    import sys
    from pathlib import Path

    import sqlalchemy

    from adare.database.api.base import create_sqlite_engine

    db_path, mode = Path(sys.argv[1]), sys.argv[2]
    if mode == 'wal':
        engine = create_sqlite_engine(db_path)
    else:
        engine = sqlalchemy.create_engine(f'sqlite:///{db_path.as_posix()}')
    with engine.connect() as conn:
        # Fail fast instead of waiting out the 30 s busy timeout.
        conn.exec_driver_sql('PRAGMA busy_timeout=200')
        try:
            print(conn.exec_driver_sql('SELECT count(*) FROM t').scalar_one())
        except sqlalchemy.exc.OperationalError as e:
            print(f'ERROR {e.orig}')
    engine.dispose()
    """
)


@pytest.mark.parametrize(('mode', 'expect_locked'), [('wal', False), ('rollback', True)])
def test_readers_are_not_blocked_by_a_writer(tmp_path, mode, expect_locked):
    """Two reader processes read while a third holds an open write transaction.

    The rollback-journal case is the control: the same setup locks the readers out.
    """
    db_path = tmp_path / f'{mode}.sqlite3'
    if mode == 'wal':
        engine = create_sqlite_engine(db_path)
    else:
        engine = sqlalchemy.create_engine(f'sqlite:///{db_path.as_posix()}')
    with engine.begin() as conn:
        conn.exec_driver_sql('CREATE TABLE t (x INTEGER)')
        conn.exec_driver_sql('INSERT INTO t VALUES (1)')

    raw = engine.raw_connection()
    try:
        cursor = raw.cursor()
        # EXCLUSIVE keeps rollback-journal readers out; WAL readers keep reading
        # the last committed snapshot.
        cursor.execute('BEGIN EXCLUSIVE')
        cursor.execute('INSERT INTO t VALUES (2)')

        readers = [
            subprocess.Popen(
                [sys.executable, '-c', _READER, str(db_path), mode],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for _ in range(2)
        ]
        outputs = [reader.communicate(timeout=60) for reader in readers]

        raw.commit()
    finally:
        raw.close()
        engine.dispose()

    for (stdout, stderr), reader in zip(outputs, readers, strict=True):
        assert reader.returncode == 0, stderr
        if expect_locked:
            assert 'database is locked' in stdout
        else:
            assert stdout.strip() == '1'  # the uncommitted row is not visible
