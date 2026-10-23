#!/usr/bin/env python3
"""
Database migration: record which process holds an active VM instance.

``vm_instance.owner_pid`` lets instance reconciliation distinguish a row left
behind by a crashed run (owner process gone) from one that another live
``adare`` process is still preparing, instead of guessing from hypervisor state.

This is a *global*-scoped migration: it is applied automatically when the global
database is opened (see ``adare.database.migrations.runner``). Run it explicitly
with:
    adare db migrate
    python -m adare.database.migrations.add_owner_pid_to_vm_instance

For new installations, the column is created from the model.
"""

import logging
import sys

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

log = logging.getLogger(__name__)


def upgrade(conn) -> None:
    """Add the owner_pid column to vm_instance on ``conn`` (idempotent)."""
    columns = {row[1] for row in conn.execute(text("PRAGMA table_info(vm_instance)"))}
    if not columns:
        print("· Table 'vm_instance' not present, skipping.")
        return
    if 'owner_pid' in columns:
        print("✓ Column 'owner_pid' already exists. No migration needed.")
        return
    print("Adding column 'owner_pid' to vm_instance table...")
    conn.execute(text("ALTER TABLE vm_instance ADD COLUMN owner_pid INTEGER NULL"))


def run_migration() -> bool:
    """Manual entry point: run :func:`upgrade` against the global database."""
    from adare.database.api.base import GlobalDatabaseApi

    print("Running migration: add_owner_pid_to_vm_instance")
    try:
        with GlobalDatabaseApi() as api, api.engine.begin() as conn:
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
