#!/usr/bin/env python3
"""
Database migration: Add the build_record column to the vm table.

``build_record`` holds the image record (JSON, see
``adare.backend.vm.image_record``): how the disk was built, its package list
summary, where it is published, and the checks run on it.

This is a *global*-scoped migration: it is applied automatically when the global
database is opened (see ``adare.database.migrations.runner``). Run it explicitly
with:
    adare db migrate
    python -m adare.database.migrations.add_build_record_to_vm

For new installations, the column is created automatically from the model.
"""

import logging
import sys

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

log = logging.getLogger(__name__)


def upgrade(conn) -> None:
    """Add vm.build_record on ``conn`` (idempotent)."""
    existing = {row[1] for row in conn.execute(text("PRAGMA table_info(vm)"))}
    if not existing:
        print("· Table 'vm' not present, skipping.")
        return
    if 'build_record' in existing:
        print("✓ Column 'build_record' already exists, skipping.")
        return
    print("Adding column 'build_record' to vm table...")
    conn.execute(text("ALTER TABLE vm ADD COLUMN build_record TEXT NULL"))


def run_migration() -> bool:
    """Manual entry point: run :func:`upgrade` against the global database."""
    from adare.database.api.vm import VmApi

    print("Running migration: add_build_record_to_vm")
    try:
        with VmApi() as api, api.engine.begin() as conn:
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
