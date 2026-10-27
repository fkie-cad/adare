#!/usr/bin/env python3
"""
Database migration: Index the columns that look up a run's rows in project databases.

The per-run tables (event, stage_in_run, action_execution) and the playbook item
tree were only indexed by primary key, so loading one run's events scanned every
event of every run: ``adare runs list`` took 150 s on a project with 4.5k runs.

This is a *project*-scoped migration: it is applied automatically whenever a
project database is opened (see ``adare.database.migrations.runner``). Run it
explicitly against every registered project with:
    adare db migrate
    python -m adare.database.migrations.add_run_lookup_indexes

For new installations, the indexes are created automatically from the model
(``index=True`` on the same columns, so the names match).
"""

import logging
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

log = logging.getLogger(__name__)

#: (table, column) pairs indexed as ``ix_<table>_<column>``, SQLAlchemy's name for ``index=True``.
INDEXED_COLUMNS = [
    ('event', 'experiment_run_id'),
    ('event', 'parent_event_id'),
    ('test_events', 'abstract_test_id'),
    ('stage_in_run', 'run_id'),
    ('playbook_item', 'playbook_id'),
    ('playbook_item', 'parent_id'),
    ('action_execution', 'experiment_run_id'),
    ('action_execution', 'playbook_item_id'),
]


def upgrade(conn) -> None:
    """Create the run lookup indexes on ``conn`` (idempotent)."""
    tables = {row[0] for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type = 'table'"))}
    for table, column in INDEXED_COLUMNS:
        if table not in tables:
            print(f"· Table '{table}' not present, skipping.")
            continue
        conn.execute(text(f"CREATE INDEX IF NOT EXISTS ix_{table}_{column} ON {table} ({column})"))
    print("✓ Run lookup indexes present.")


def _migrate_project(project_path: Path) -> bool:
    from adare.database.api.base import ProjectDatabaseApi

    print(f"Project {project_path}:")
    try:
        with ProjectDatabaseApi(project_path) as api, api.engine.begin() as conn:
            upgrade(conn)
        return True
    except SQLAlchemyError as e:
        print(f"  ✗ failed: {e}", file=sys.stderr)
        log.error("Migration failed for %s: %s", project_path, e, exc_info=True)
        return False


def run_migration() -> bool:
    """Create the run lookup indexes in every project DB."""
    from adare.database.api.base import GlobalDatabaseApi
    from adare.database.models.global_models import Project

    print("Running migration: add_run_lookup_indexes")
    try:
        with GlobalDatabaseApi() as api:
            project_paths = [Path(p.path) for p in api._session.query(Project).all() if p.path]
    except SQLAlchemyError as e:
        print(f"✗ Could not list projects: {e}", file=sys.stderr)
        log.error("Could not list projects: %s", e, exc_info=True)
        return False
    ok = True
    for project_path in project_paths:
        if project_path.exists():
            ok = _migrate_project(project_path) and ok
    return ok


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(0 if run_migration() else 1)
