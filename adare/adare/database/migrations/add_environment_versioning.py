#!/usr/bin/env python3
"""
Database migration: keep superseded environment versions instead of deleting them.

``adare env load --force`` used to delete the existing environment -- and with it
every experiment run that referenced it, across all projects -- before loading
the changed file. Environments are now versioned: the old row stays with
``superseded_at`` set, and only one *current* row per name is allowed.

Changes:
- ``environment.superseded_at`` (NULL = current version)
- ``environment.vm_hash`` (disk hash the version was loaded against), backfilled
  from the referenced ``vm.hash``
- ``ix_environment_name`` becomes a plain index; uniqueness moves to the partial
  index ``idx_environment_current_name`` (name unique WHERE superseded_at IS NULL)

This is a *global*-scoped migration: it is applied automatically when the global
database is opened (see ``adare.database.migrations.runner``). Run it explicitly
with:
    adare db migrate
    python -m adare.database.migrations.add_environment_versioning

For new installations, the columns and indexes are created from the model.
"""

import logging
import sys

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

log = logging.getLogger(__name__)


def upgrade(conn) -> None:
    """Add versioning columns and swap the name uniqueness index on ``conn`` (idempotent)."""
    columns = {row[1] for row in conn.execute(text("PRAGMA table_info(environment)"))}
    if not columns:
        print("· Table 'environment' not present, skipping.")
        return

    if 'superseded_at' not in columns:
        print("Adding column 'superseded_at' to environment table...")
        conn.execute(text("ALTER TABLE environment ADD COLUMN superseded_at DATETIME NULL"))
    if 'vm_hash' not in columns:
        print("Adding column 'vm_hash' to environment table...")
        conn.execute(text("ALTER TABLE environment ADD COLUMN vm_hash VARCHAR NULL"))
        conn.execute(text("UPDATE environment SET vm_hash = (SELECT vm.hash FROM vm WHERE vm.id = environment.vm_id)"))

    indexes = {row[1]: bool(row[2]) for row in conn.execute(text("PRAGMA index_list(environment)"))}
    if indexes.get('ix_environment_name'):
        print("Relaxing unique index 'ix_environment_name' to a plain index...")
        conn.execute(text("DROP INDEX ix_environment_name"))
        indexes.pop('ix_environment_name')
    if 'ix_environment_name' not in indexes:
        conn.execute(text("CREATE INDEX ix_environment_name ON environment (name)"))
    if 'ix_environment_superseded_at' not in indexes:
        conn.execute(text("CREATE INDEX ix_environment_superseded_at ON environment (superseded_at)"))
    if 'idx_environment_current_name' not in indexes:
        conn.execute(
            text("CREATE UNIQUE INDEX idx_environment_current_name ON environment (name) WHERE superseded_at IS NULL")
        )


def run_migration() -> bool:
    """Manual entry point: run :func:`upgrade` against the global database."""
    from adare.database.api.base import GlobalDatabaseApi

    print("Running migration: add_environment_versioning")

    try:
        with GlobalDatabaseApi() as api, api.engine.begin() as conn:
            upgrade(conn)

        print("✓ Migration completed successfully!")
        print("\nIMPORTANT:")
        print("- Existing environments are the current version of their name")
        print("- 'adare env load --force' now keeps the previous version and its runs")
        return True

    except SQLAlchemyError as e:
        print(f"✗ Migration failed: {e}", file=sys.stderr)
        log.error("Migration failed: %s", e, exc_info=True)
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    success = run_migration()
    sys.exit(0 if success else 1)
