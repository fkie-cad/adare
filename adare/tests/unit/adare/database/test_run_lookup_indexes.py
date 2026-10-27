"""The run lookup indexes exist on new databases and are added to existing ones."""

import pytest
import sqlalchemy
from sqlalchemy import text

from adare.database.migrations import add_run_lookup_indexes
from adare.database.migrations.add_run_lookup_indexes import INDEXED_COLUMNS
from adare.database.models.project_models import ProjectBase

pytestmark = pytest.mark.unit

EXPECTED = {f'ix_{table}_{column}' for table, column in INDEXED_COLUMNS}


def _index_names(conn) -> set[str]:
    return {row[0] for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type = 'index'"))}


def test_new_database_gets_the_indexes_from_the_model(tmp_path):
    engine = sqlalchemy.create_engine(f'sqlite:///{tmp_path / "new.db"}')
    ProjectBase.metadata.create_all(engine)

    with engine.connect() as conn:
        assert _index_names(conn) >= EXPECTED


def test_upgrade_adds_the_indexes_to_an_existing_database(tmp_path):
    engine = sqlalchemy.create_engine(f'sqlite:///{tmp_path / "old.db"}')
    ProjectBase.metadata.create_all(engine)
    with engine.begin() as conn:
        for name in EXPECTED:
            conn.execute(text(f'DROP INDEX {name}'))

    with engine.begin() as conn:
        add_run_lookup_indexes.upgrade(conn)
        add_run_lookup_indexes.upgrade(conn)  # idempotent

    with engine.connect() as conn:
        assert _index_names(conn) >= EXPECTED


def test_loading_a_runs_events_uses_the_index(tmp_path):
    engine = sqlalchemy.create_engine(f'sqlite:///{tmp_path / "plan.db"}')
    ProjectBase.metadata.create_all(engine)

    with engine.connect() as conn:
        plan = conn.execute(text("EXPLAIN QUERY PLAN SELECT * FROM event WHERE experiment_run_id = 'x'")).fetchall()

    assert any('ix_event_experiment_run_id' in str(row) for row in plan)
