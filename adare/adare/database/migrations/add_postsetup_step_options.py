#!/usr/bin/env python3
"""
Database migration: post-setup step options and step order.

Adds to ``post_setup_installation``:

    admin          -- run the step elevated (BOOLEAN NOT NULL DEFAULT 0)
    allow_failure  -- a failing step becomes a warning (BOOLEAN NOT NULL DEFAULT 0)
    timeout        -- per-step budget in seconds, NULL = default (FLOAT NULL)

and to ``mapping_postsetupinstallation_environment``:

    position       -- order of the step in its environment (INTEGER NOT NULL DEFAULT 0)

Existing steps keep their meaning (not elevated, failure fails the run, default
timeout), so an identical step in a re-loaded environment file is still reused
instead of duplicated. Existing mapping rows get ``position`` numbered per
environment in rowid (= insertion) order, the best available approximation of
file order for environments loaded before order was stored.

This is a *global*-scoped migration, applied automatically when the global
database is opened (see ``adare.database.migrations.runner``). Run it explicitly:
    adare db migrate
    python -m adare.database.migrations.add_postsetup_step_options
"""

import logging
import sys

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

log = logging.getLogger(__name__)

_STEP_TABLE = 'post_setup_installation'
_MAPPING_TABLE = 'mapping_postsetupinstallation_environment'

# column name -> DDL fragment appended after `ADD COLUMN <name>`
_STEP_COLUMNS = {
    'admin': 'BOOLEAN NOT NULL DEFAULT 0',
    'allow_failure': 'BOOLEAN NOT NULL DEFAULT 0',
    'timeout': 'FLOAT NULL',
}


def _columns(conn, table: str) -> set[str]:
    return {row[1] for row in conn.execute(text(f'PRAGMA table_info({table})'))}


def upgrade(conn) -> None:
    """Add the step option columns and the mapping ``position`` on ``conn`` (idempotent)."""
    step_columns = _columns(conn, _STEP_TABLE)
    if not step_columns:
        # Table not present (very old / partial database) -- create_all owns it.
        print(f"· Table '{_STEP_TABLE}' not present, skipping.")
    for column, ddl in _STEP_COLUMNS.items():
        if not step_columns or column in step_columns:
            continue
        print(f"Adding column '{column}' to {_STEP_TABLE}...")
        conn.execute(text(f'ALTER TABLE {_STEP_TABLE} ADD COLUMN {column} {ddl}'))

    mapping_columns = _columns(conn, _MAPPING_TABLE)
    if not mapping_columns:
        print(f"· Table '{_MAPPING_TABLE}' not present, skipping.")
        return
    if 'position' in mapping_columns:
        print("✓ Column 'position' already exists, skipping.")
        return
    print(f"Adding column 'position' to {_MAPPING_TABLE} and backfilling...")
    conn.execute(text(f'ALTER TABLE {_MAPPING_TABLE} ADD COLUMN position INTEGER NOT NULL DEFAULT 0'))
    conn.execute(
        text(
            f"""
            UPDATE {_MAPPING_TABLE}
            SET position = (
                SELECT COUNT(*) FROM {_MAPPING_TABLE} AS earlier
                WHERE earlier.environment_id IS {_MAPPING_TABLE}.environment_id
                  AND earlier.rowid < {_MAPPING_TABLE}.rowid
            )
            """
        )
    )


def run_migration() -> bool:
    """Manual entry point: run :func:`upgrade` against the global database."""
    from adare.database.api.environment import EnvironmentDbApi

    print("Running migration: add_postsetup_step_options")

    try:
        with EnvironmentDbApi() as api, api.engine.begin() as conn:
            upgrade(conn)

        print("✓ Migration completed successfully!")
        return True

    except SQLAlchemyError as e:
        print(f"✗ Migration failed: {e}", file=sys.stderr)
        log.error("Migration failed: %s", e, exc_info=True)
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    success = run_migration()
    sys.exit(0 if success else 1)
