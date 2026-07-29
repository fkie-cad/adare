#!/usr/bin/env python3
"""
Database migration: Add testfunction reproducibility pins to project databases.

Adds the columns that record which testfunction *file* (collection) version and
which method version/hash an experiment was created against (on abstract_test)
and which actually executed at run time (on test_events):

    testfunction_file_name       -- str
    testfunction_file_version    -- int
    testfunction_file_sha256     -- str
    testfunction_version         -- int  (per-method)
    testfunction_sha256          -- str  (per-method)

All columns are nullable; NULL means pre-versioning (no pin / unknown).

This is a *project*-scoped migration: it is applied automatically whenever a
project database is opened (see ``adare.database.migrations.runner``). Run it
explicitly against every registered project with:
    adare db migrate
    python -m adare.database.migrations.add_testfunction_pins_to_tests

For new installations, the columns are created automatically from the model.
"""

import logging
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

log = logging.getLogger(__name__)

# column name -> DDL fragment appended after `ADD COLUMN <name>`
_NEW_COLUMNS = {
    'testfunction_file_name': "VARCHAR NULL",
    'testfunction_file_version': "INTEGER NULL",
    'testfunction_file_sha256': "VARCHAR NULL",
    'testfunction_version': "INTEGER NULL",
    'testfunction_sha256': "VARCHAR NULL",
}
_TABLES = ('abstract_test', 'test_events')


def _existing_columns(conn, table: str) -> set[str]:
    return {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}


def _migrate_table(conn, table: str) -> int:
    # A project DB may not have this table yet (very old / partial) — skip cleanly.
    if not _existing_columns(conn, table):
        print(f"  · table '{table}' not present, skipping")
        return 0
    existing = _existing_columns(conn, table)
    added = 0
    for column, ddl in _NEW_COLUMNS.items():
        if column in existing:
            continue
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
        added += 1
    print(f"  · {table}: added {added} column(s)")
    return added


def upgrade(conn) -> None:
    """Add the pin columns to abstract_test + test_events on ``conn`` (idempotent)."""
    for table in _TABLES:
        _migrate_table(conn, table)


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
    """Add pin columns to abstract_test + test_events in every project DB."""
    from adare.database.api.base import GlobalDatabaseApi
    from adare.database.models.global_models import Project

    print("Running migration: add_testfunction_pins_to_tests")

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
        print("- Pre-versioning rows keep NULL pins (treated as 'no pin')")
        print("- New experiments pin file+method version/hash at bind time")
    return all_ok


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    success = run_migration()
    sys.exit(0 if success else 1)
