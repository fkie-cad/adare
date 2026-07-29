#!/usr/bin/env python3
"""
Database migration: give project entities a persistent remote (server) identity.

Adds, to project databases:

    experiment.sync_metadata_id  -- CHAR(26) NULL, FK -> sync_metadata.id
    abstract_test.remote_ulid    -- VARCHAR  NULL

The ``sync_metadata`` table itself is created by ``create_all`` (it is a brand-new
table, and create_all does build missing tables); only these two ALTERs need doing
by hand.

Why: ``ExperimentApi.sync_experiment`` used to assign ``remote_ulid`` /
``remote_url`` / ``published`` onto the Experiment and ``remote_ulid`` onto each
AbstractTest. None of those was a mapped column, so SQLAlchemy treated the
assignment as an ordinary Python attribute and ``commit()`` persisted nothing —
the server identity vanished with the session. ``adare web publish <run>`` then
looked the experiment up on the server by its *local* ULID and aborted with
"Experiment X is not published on the server" for an experiment that was.

All columns are nullable; NULL means "never published from this machine".

This is a *project*-scoped migration: it is applied automatically whenever a
project database is opened (see ``adare.database.migrations.runner``). Run it
explicitly against every registered project with:
    adare db migrate
    python -m adare.database.migrations.add_remote_identity_to_project_db
"""

import logging
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

log = logging.getLogger(__name__)

# table -> {column name: DDL fragment appended after `ADD COLUMN <name>`}
_NEW_COLUMNS = {
    'experiment': {
        # No REFERENCES clause: SQLite cannot add a column with a foreign-key
        # constraint to an existing table, and the ORM enforces the relationship
        # anyway. New installations get the real FK from create_all.
        'sync_metadata_id': 'CHAR(26) NULL',
    },
    'abstract_test': {
        'remote_ulid': 'VARCHAR NULL',
    },
}


def _existing_columns(conn, table: str) -> set[str]:
    return {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}


def _migrate_table(conn, table: str, columns: dict[str, str]) -> int:
    # A project DB may not have this table yet (very old / partial) — skip cleanly.
    existing = _existing_columns(conn, table)
    if not existing:
        print(f"  · table '{table}' not present, skipping")
        return 0
    added = 0
    for column, ddl in columns.items():
        if column in existing:
            continue
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
        added += 1
    print(f"  · {table}: added {added} column(s)")
    return added


def upgrade(conn) -> None:
    """Add the remote-identity columns on ``conn`` (idempotent)."""
    for table, columns in _NEW_COLUMNS.items():
        _migrate_table(conn, table, columns)


def _migrate_project(project_path: Path) -> bool:
    from adare.database.api.base import ProjectDatabaseApi

    print(f"Project {project_path}:")
    try:
        with ProjectDatabaseApi(project_path) as api:
            with api.engine.begin() as conn:
                upgrade(conn)
        return True
    except SQLAlchemyError as e:
        print(f"  ✗ failed: {e}", file=sys.stderr)
        log.error("Migration failed for %s: %s", project_path, e, exc_info=True)
        return False


def run_migration() -> bool:
    """Add the remote-identity columns in every project DB."""
    from adare.database.api.base import GlobalDatabaseApi
    from adare.database.models.global_models import Project

    print("Running migration: add_remote_identity_to_project_db")

    try:
        with GlobalDatabaseApi() as api:
            projects = api._session.query(Project).all()
            project_paths = [Path(p.path) for p in projects if p.path]
    except SQLAlchemyError as e:
        print(f"✗ Could not list projects: {e}", file=sys.stderr)
        log.error("Could not list projects: %s", e, exc_info=True)
        return False

    if not project_paths:
        print("No projects registered — nothing to migrate.")
        return True

    all_ok = True
    for project_path in project_paths:
        if not project_path.exists():
            print(f"Project {project_path}: path missing, skipping")
            continue
        all_ok = _migrate_project(project_path) and all_ok

    if all_ok:
        print("✓ Migration completed successfully!")
        print("\nIMPORTANT:")
        print("- Existing experiments start with NULL (= never published from here)")
        print("- Run `adare web sync` to repopulate the server identity for published ones")
    return all_ok


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    success = run_migration()
    sys.exit(0 if success else 1)
