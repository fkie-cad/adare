#!/usr/bin/env python3
"""
Database migration: Add recipe-build provenance columns to the vm table.

Adds the columns that let a built disk be traced and de-duplicated back to the
declarative recipe it was produced from:

    build_source  -- 'baked' (default) or 'recipe'
    recipe_hash   -- integrity anchor for recipe environments (nullable)
    iso_sha256    -- expected SHA256 of the installer ISO (nullable)
    profile_name  -- OS profile the disk was built from (nullable)

Run this script manually if you have an existing ADARE installation:
    python -m adare.database.migrations.add_recipe_provenance_to_vm

For new installations, the columns are created automatically from the model.
"""

import logging
import sys

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

log = logging.getLogger(__name__)

# column name -> DDL fragment appended after `ADD COLUMN <name>`
_NEW_COLUMNS = {
    'build_source': "VARCHAR NOT NULL DEFAULT 'baked'",
    'recipe_hash': "VARCHAR NULL",
    'iso_sha256': "VARCHAR NULL",
    'profile_name': "VARCHAR NULL",
}


def run_migration() -> bool:
    """Add recipe provenance columns to the vm table if they don't exist."""
    from adare.database.api.vm import VmApi

    print("Running migration: add_recipe_provenance_to_vm")

    try:
        with VmApi() as api:
            engine = api.engine
            with engine.begin() as conn:
                existing = {
                    row[1]
                    for row in conn.execute(text("PRAGMA table_info(vm)"))
                }

                added = []
                for column, ddl in _NEW_COLUMNS.items():
                    if column in existing:
                        print(f"✓ Column '{column}' already exists, skipping.")
                        continue
                    print(f"Adding column '{column}' to vm table...")
                    conn.execute(text(f"ALTER TABLE vm ADD COLUMN {column} {ddl}"))
                    added.append(column)

                # Index on recipe_hash for fast cache lookups (get_vm_by_recipe_hash).
                if 'recipe_hash' in added or 'recipe_hash' not in existing:
                    conn.execute(text(
                        "CREATE INDEX IF NOT EXISTS ix_vm_recipe_hash ON vm (recipe_hash)"
                    ))

        print("✓ Migration completed successfully!")
        print("\nIMPORTANT:")
        print("- Existing VMs are marked build_source='baked' (unchanged behaviour)")
        print("- Recipe-built VMs will record recipe_hash / iso_sha256 / profile_name")
        return True

    except SQLAlchemyError as e:
        print(f"✗ Migration failed: {e}", file=sys.stderr)
        log.error("Migration failed: %s", e, exc_info=True)
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    success = run_migration()
    sys.exit(0 if success else 1)
