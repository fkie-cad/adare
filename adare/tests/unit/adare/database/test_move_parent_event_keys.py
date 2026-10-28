"""The move_parent_event_keys migration moves action keys out of event.parent_event_id."""

import pytest
import sqlalchemy
from sqlalchemy import text

from adare.database import maintenance
from adare.database.migrations import move_parent_event_keys
from adare.database.migrations.runner import MIGRATIONS
from adare.database.models.project_models import ProjectBase

pytestmark = pytest.mark.unit

RUN = 'run-1'
PARENT_EVENT = '01JAAAAAAAAAAAAAAAAAAAAAAA'


def _insert_event(conn, event_id: str, parent: str | None, group: str) -> None:
    conn.execute(
        text(
            "INSERT INTO event (id, event_type, category, experiment_run_id, parent_event_id, event_group_id) "
            "VALUES (:id, 'action_event', 'action', :run, :parent, :group)"
        ),
        {'id': event_id, 'run': RUN, 'parent': parent, 'group': group},
    )


def _legacy_engine(db_path):
    """A project database as earlier versions wrote it: no parent_group_id, action keys as parents."""
    engine = sqlalchemy.create_engine(f'sqlite:///{db_path}')
    ProjectBase.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text('DROP INDEX ix_event_parent_group_id'))
        conn.execute(text('ALTER TABLE event DROP COLUMN parent_group_id'))
        conn.execute(text("INSERT INTO experiment_run (id, fake, published) VALUES (:id, 0, 0)"), {'id': RUN})
        _insert_event(conn, PARENT_EVENT, None, 'action_0_click_1')
        # Nested events of earlier writers: the parent *action key*, not an event id.
        _insert_event(conn, '01JBBBBBBBBBBBBBBBBBBBBBBB', 'action_0_click_1', 'find_step_2')
        _insert_event(conn, '01JCCCCCCCCCCCCCCCCCCCCCCC', 'action_0_click_1', 'execute_step_3')
        # A real event-id parent is kept as it is.
        _insert_event(conn, '01JDDDDDDDDDDDDDDDDDDDDDDD', PARENT_EVENT, 'child_4')
    return engine


def _rows(conn) -> dict[str, tuple[str | None, str | None]]:
    return {
        row[0]: (row[1], row[2]) for row in conn.execute(text('SELECT id, parent_event_id, parent_group_id FROM event'))
    }


def _index_names(conn) -> set[str]:
    return {row[0] for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type = 'index'"))}


EXPECTED = {
    PARENT_EVENT: (None, None),
    '01JBBBBBBBBBBBBBBBBBBBBBBB': (None, 'action_0_click_1'),
    '01JCCCCCCCCCCCCCCCCCCCCCCC': (None, 'action_0_click_1'),
    '01JDDDDDDDDDDDDDDDDDDDDDDD': (PARENT_EVENT, None),
}


def test_moves_action_keys_and_keeps_real_parents(tmp_path):
    engine = _legacy_engine(tmp_path / 'project.db')
    with engine.begin() as conn:
        move_parent_event_keys.upgrade(conn)

    with engine.connect() as conn:
        assert _rows(conn) == EXPECTED
    engine.dispose()


def test_adds_the_column_and_the_model_index(tmp_path):
    engine = _legacy_engine(tmp_path / 'project.db')
    with engine.begin() as conn:
        move_parent_event_keys.upgrade(conn)

    with engine.connect() as conn:
        columns = {row[1] for row in conn.execute(text('PRAGMA table_info(event)'))}
        assert 'parent_group_id' in columns
        assert 'ix_event_parent_group_id' in _index_names(conn)
    engine.dispose()


def test_new_database_gets_the_same_index_from_the_model(tmp_path):
    engine = sqlalchemy.create_engine(f'sqlite:///{tmp_path / "new.db"}')
    ProjectBase.metadata.create_all(engine)
    with engine.connect() as conn:
        assert 'ix_event_parent_group_id' in _index_names(conn)
    with engine.begin() as conn:
        move_parent_event_keys.upgrade(conn)  # a no-op on a fresh database
    engine.dispose()


def test_is_idempotent(tmp_path):
    engine = _legacy_engine(tmp_path / 'project.db')
    with engine.begin() as conn:
        move_parent_event_keys.upgrade(conn)
    with engine.begin() as conn:
        move_parent_event_keys.upgrade(conn)

    with engine.connect() as conn:
        assert _rows(conn) == EXPECTED
    engine.dispose()


def test_clears_the_foreign_key_violations(tmp_path):
    db_path = tmp_path / 'project.db'
    engine = _legacy_engine(db_path)
    engine.dispose()
    target = maintenance.DatabaseTarget('legacy', db_path)

    before = {(v.table, v.parent): v.count for v in maintenance.check_database(target).foreign_key_violations}
    assert before == {('event', 'event'): 2}

    with engine.begin() as conn:
        move_parent_event_keys.upgrade(conn)
    engine.dispose()

    assert maintenance.check_database(target).foreign_key_violations == []


def test_skips_a_database_without_the_table(tmp_path):
    engine = sqlalchemy.create_engine(f'sqlite:///{tmp_path / "empty.db"}')
    with engine.begin() as conn:
        move_parent_event_keys.upgrade(conn)
    engine.dispose()


def test_is_registered_as_a_project_migration():
    assert any(m.name == 'move_parent_event_keys' and m.scope == 'project' for m in MIGRATIONS)
