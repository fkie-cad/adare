"""The delete_orphan_run_rows migration removes the rows earlier run deletions left behind."""

import pytest
import sqlalchemy
from sqlalchemy import text

from adare.database.migrations import delete_orphan_run_rows
from adare.database.migrations.runner import MIGRATIONS
from adare.database.models.project_models import ProjectBase

pytestmark = pytest.mark.unit


def _insert_run(conn, run_id: str, files_id: str | None) -> None:
    conn.execute(
        text("INSERT INTO experiment_run (id, files_id, fake, published) VALUES (:id, :files_id, 0, 0)"),
        {'id': run_id, 'files_id': files_id},
    )


def _insert_files(conn, files_id: str, adare_log: str | None, adarevm_log: str | None) -> None:
    for log_id in (adare_log, adarevm_log):
        if log_id:
            conn.execute(
                text("INSERT OR IGNORE INTO log_file (id, name, path) VALUES (:id, :id, :path)"),
                {'id': log_id, 'path': f'/logs/{log_id}'},
            )
    conn.execute(
        text("INSERT INTO experiment_run_files (id, log_adare_id, log_adarevm_id) VALUES (:id, :a, :b)"),
        {'id': files_id, 'a': adare_log, 'b': adarevm_log},
    )


def _insert_execution(conn, execution_id: str, run_id: str | None) -> None:
    conn.execute(
        text(
            "INSERT INTO action_execution (id, playbook_item_id, experiment_run_id, status, result_data) "
            "VALUES (:id, 'item', :run_id, 'success', :blob)"
        ),
        {'id': execution_id, 'run_id': run_id, 'blob': '"' + 'x' * 10_000 + '"'},
    )


def _ids(conn, table: str) -> set[str]:
    return {row[0] for row in conn.execute(text(f"SELECT id FROM {table}"))}


@pytest.fixture
def engine(tmp_path):
    engine = sqlalchemy.create_engine(f'sqlite:///{tmp_path / "project.db"}')
    ProjectBase.metadata.create_all(engine)
    with engine.begin() as conn:
        # A live run with its files, logs and executions.
        _insert_files(conn, 'files-live', 'log-live-a', 'log-live-b')
        _insert_run(conn, 'run-live', 'files-live')
        _insert_execution(conn, 'exec-live', 'run-live')
        # What a deleted run left behind.
        _insert_files(conn, 'files-orphan', 'log-orphan-a', 'log-orphan-b')
        _insert_execution(conn, 'exec-orphan-1', 'run-deleted')
        _insert_execution(conn, 'exec-orphan-2', 'run-deleted')
        # An orphaned files row sharing a log with the live one: that log stays.
        _insert_files(conn, 'files-orphan-shared', 'log-live-a', None)
        # Executions without a run id are kept.
        _insert_execution(conn, 'exec-no-run', None)
        # A run without files must not make NOT IN match nothing.
        _insert_run(conn, 'run-no-files', None)
    yield engine
    engine.dispose()


def _assert_cleaned(conn) -> None:
    assert _ids(conn, 'action_execution') == {'exec-live', 'exec-no-run'}
    assert _ids(conn, 'experiment_run_files') == {'files-live'}
    assert _ids(conn, 'log_file') == {'log-live-a', 'log-live-b'}
    assert _ids(conn, 'experiment_run') == {'run-live', 'run-no-files'}


def test_deletes_orphaned_rows_and_keeps_executions_without_a_run_id(engine):
    with engine.begin() as conn:
        delete_orphan_run_rows.upgrade(conn)

    with engine.connect() as conn:
        _assert_cleaned(conn)


def test_is_idempotent(engine):
    with engine.begin() as conn:
        delete_orphan_run_rows.upgrade(conn)
    with engine.begin() as conn:
        delete_orphan_run_rows.upgrade(conn)

    with engine.connect() as conn:
        _assert_cleaned(conn)


def test_clean_database_is_left_alone(tmp_path):
    engine = sqlalchemy.create_engine(f'sqlite:///{tmp_path / "fresh.db"}')
    ProjectBase.metadata.create_all(engine)
    with engine.begin() as conn:
        delete_orphan_run_rows.upgrade(conn)
    engine.dispose()


def test_skips_a_database_without_the_tables(tmp_path):
    engine = sqlalchemy.create_engine(f'sqlite:///{tmp_path / "empty.db"}')
    with engine.begin() as conn:
        delete_orphan_run_rows.upgrade(conn)
    engine.dispose()


def test_is_registered_as_a_project_migration():
    assert any(m.name == 'delete_orphan_run_rows' and m.scope == 'project' for m in MIGRATIONS)
