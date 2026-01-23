#!/usr/bin/env python3
"""
Database migration: Add overlay_disk_path column to dev_sessions table.

This migration adds the overlay_disk_path field to prevent accidental base disk deletion.

Run this script manually if you have an existing ADARE installation:
    python -m adare.database.migrations.add_overlay_disk_path_to_dev_sessions

For new installations, the column will be created automatically.
"""

import sys
import logging
from pathlib import Path
from sqlalchemy import text

log = logging.getLogger(__name__)


def run_migration():
    """Add overlay_disk_path column to dev_sessions table if it doesn't exist."""
    from adare.database.api.devmode import DevModeApi

    print("Running migration: add_overlay_disk_path_to_dev_sessions")

    try:
        with DevModeApi() as api:
            # Check if column exists
            result = api.engine.execute(text("PRAGMA table_info(dev_sessions)"))
            columns = [row[1] for row in result]

            if 'overlay_disk_path' in columns:
                print("✓ Column 'overlay_disk_path' already exists. No migration needed.")
                return True

            # Add the column
            print("Adding column 'overlay_disk_path' to dev_sessions table...")
            api.engine.execute(text(
                "ALTER TABLE dev_sessions ADD COLUMN overlay_disk_path VARCHAR(1024) NULL"
            ))

            print("✓ Migration completed successfully!")
            print("\nIMPORTANT:")
            print("- Existing dev sessions will have NULL overlay_disk_path")
            print("- New sessions will track overlay disk path automatically")
            print("- Safety check in VM destroy will prevent base disk deletion")

            return True

    except Exception as e:
        print(f"✗ Migration failed: {e}", file=sys.stderr)
        log.error(f"Migration failed: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    success = run_migration()
    sys.exit(0 if success else 1)
