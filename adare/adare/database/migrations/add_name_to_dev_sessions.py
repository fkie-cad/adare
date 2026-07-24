#!/usr/bin/env python3
"""
Database migration: Add name column to dev_sessions table.

This migration adds the optional ``name`` field so dev sessions can carry a
human-friendly label that ``-s``/``--session`` accepts in place of a ULID.
The column is not unique — collisions are resolved at lookup time.

This is a *global*-scoped migration: it is applied automatically when the global
database is opened (see ``adare.database.migrations.runner``). Run it explicitly
with:
    adare db migrate
    python -m adare.database.migrations.add_name_to_dev_sessions

For new installations, the column will be created automatically.
"""

import logging
import sys

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

log = logging.getLogger(__name__)


def upgrade(conn) -> None:
    """Add the name column to dev_sessions on ``conn`` (idempotent)."""
    columns = {row[1] for row in conn.execute(text("PRAGMA table_info(dev_sessions)"))}

    if not columns:
        # Table not present (very old / partial database) — create_all owns it.
        print("· Table 'dev_sessions' not present, skipping.")
        return

    if 'name' in columns:
        print("✓ Column 'name' already exists. No migration needed.")
        return

    print("Adding column 'name' to dev_sessions table...")
    conn.execute(text("ALTER TABLE dev_sessions ADD COLUMN name VARCHAR(255) NULL"))


def run_migration() -> bool:
    """Manual entry point: run :func:`upgrade` against the global database."""
    from adare.database.api.devmode import DevModeApi

    print("Running migration: add_name_to_dev_sessions")

    try:
        with DevModeApi() as api:
            with api.engine.begin() as conn:
                upgrade(conn)

        print("✓ Migration completed successfully!")
        print("\nIMPORTANT:")
        print("- Existing dev sessions will have NULL name")
        print("- Start a session with a label: adare dev start -e <env> --name <name>")
        print("- Select by name: adare dev <command> -s <name>")
        return True

    except (SQLAlchemyError, OSError) as e:
        print(f"✗ Migration failed: {e}", file=sys.stderr)
        log.error("Migration failed: %s", e, exc_info=True)
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    success = run_migration()
    sys.exit(0 if success else 1)
