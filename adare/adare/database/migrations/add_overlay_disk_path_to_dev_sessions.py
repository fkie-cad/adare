#!/usr/bin/env python3
"""
Database migration: Add overlay_disk_path column to dev_sessions table.

This migration adds the overlay_disk_path field to prevent accidental base disk deletion.

This is a *global*-scoped migration: it is applied automatically when the global
database is opened (see ``adare.database.migrations.runner``). Run it explicitly
with:
    adare db migrate
    python -m adare.database.migrations.add_overlay_disk_path_to_dev_sessions

For new installations, the column will be created automatically.
"""

import logging
import sys

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

log = logging.getLogger(__name__)


def upgrade(conn) -> None:
    """Add overlay_disk_path to dev_sessions on ``conn`` (idempotent)."""
    columns = {row[1] for row in conn.execute(text("PRAGMA table_info(dev_sessions)"))}

    if not columns:
        # Table not present (very old / partial database) — create_all owns it.
        print("· Table 'dev_sessions' not present, skipping.")
        return

    if 'overlay_disk_path' in columns:
        print("✓ Column 'overlay_disk_path' already exists. No migration needed.")
        return

    print("Adding column 'overlay_disk_path' to dev_sessions table...")
    conn.execute(text(
        "ALTER TABLE dev_sessions ADD COLUMN overlay_disk_path VARCHAR(1024) NULL"
    ))


def run_migration() -> bool:
    """Manual entry point: run :func:`upgrade` against the global database."""
    from adare.database.api.devmode import DevModeApi

    print("Running migration: add_overlay_disk_path_to_dev_sessions")

    try:
        with DevModeApi() as api:
            with api.engine.begin() as conn:
                upgrade(conn)

        print("✓ Migration completed successfully!")
        print("\nIMPORTANT:")
        print("- Existing dev sessions will have NULL overlay_disk_path")
        print("- New sessions will track overlay disk path automatically")
        print("- Safety check in VM destroy will prevent base disk deletion")
        return True

    except (SQLAlchemyError, OSError) as e:
        print(f"✗ Migration failed: {e}", file=sys.stderr)
        log.error("Migration failed: %s", e, exc_info=True)
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    success = run_migration()
    sys.exit(0 if success else 1)
