#!/usr/bin/env python3
"""
Database migration: Add run_directory_path column to dev_sessions table.

This migration adds the run_directory_path field to prevent "None" directory creation
by storing the exact run directory path and reusing it across operations.

Run this script manually if you have an existing ADARE installation:
    python -m adare.database.migrations.add_run_directory_path_to_dev_sessions

For new installations, the column will be created automatically.
"""

import sys
import logging
from pathlib import Path
from sqlalchemy import text

log = logging.getLogger(__name__)


def run_migration():
    """Add run_directory_path column to dev_sessions table if it doesn't exist."""
    from adare.database.api.devmode import DevModeApi

    print("Running migration: add_run_directory_path_to_dev_sessions")

    try:
        with DevModeApi() as api:
            # Check if column exists
            result = api.engine.execute(text("PRAGMA table_info(dev_sessions)"))
            columns = [row[1] for row in result]

            if 'run_directory_path' in columns:
                print("✓ Column 'run_directory_path' already exists. No migration needed.")
                return True

            # Add the column
            print("Adding column 'run_directory_path' to dev_sessions table...")
            api.engine.execute(text(
                "ALTER TABLE dev_sessions ADD COLUMN run_directory_path VARCHAR(1024) NULL"
            ))

            print("✓ Migration completed successfully!")
            print("\nIMPORTANT:")
            print("- Existing dev sessions will have NULL run_directory_path")
            print("- New sessions will store run directory path automatically")
            print("- Restoration will fall back to recreation for old sessions")
            print("- This prevents 'None' directories from being created")

            return True

    except Exception as e:
        print(f"✗ Migration failed: {e}", file=sys.stderr)
        log.error(f"Migration failed: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    success = run_migration()
    sys.exit(0 if success else 1)
