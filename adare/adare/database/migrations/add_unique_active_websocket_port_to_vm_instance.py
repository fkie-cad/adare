#!/usr/bin/env python3
"""
Database migration: enforce a unique websocket_port among active VM instances.

`VmInstance.websocket_port` previously had only a plain (non-unique) index.
Two OS processes racing `create_new_instance()` / `reuse_instance()` could each
independently compute "first free port" from an unsynchronized scan and write
the *same* port to two different active instances. This migration adds a
partial unique index — ``websocket_port`` unique among rows where
``status = 'active'`` — so SQLite itself rejects the second writer, letting
the existing retry-on-``IntegrityError`` logic in ``reserve_port_atomically()``
/ ``claim_available_vm_instance()`` actually do its job.

This is a *global*-scoped migration: it is applied automatically when the global
database is opened (see ``adare.database.migrations.runner``). Run it explicitly
with:
    adare db migrate
    python -m adare.database.migrations.add_unique_active_websocket_port_to_vm_instance

For new installations, the index is created automatically from the model.
"""

import logging
import sys

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

log = logging.getLogger(__name__)

_INDEX_NAME = 'idx_vm_instance_active_websocket_port'


def _resolve_duplicate_active_ports(conn) -> int:
    """
    Clear ``websocket_port`` on all but the most-recently-used active row for
    each port that is currently held by more than one active instance.

    A plausible artifact of the very race this migration closes — without
    this, ``CREATE UNIQUE INDEX`` would fail outright on any database that
    already has the corruption, hard-blocking ``adare`` from starting.

    Returns:
        Number of rows cleared.
    """
    dupes = conn.execute(text(
        """
        SELECT websocket_port
        FROM vm_instance
        WHERE status = 'active' AND websocket_port IS NOT NULL
        GROUP BY websocket_port
        HAVING COUNT(*) > 1
        """
    )).fetchall()

    cleared = 0
    for (port,) in dupes:
        rows = conn.execute(text(
            """
            SELECT id FROM vm_instance
            WHERE status = 'active' AND websocket_port = :port
            ORDER BY last_used_at DESC
            """
        ), {'port': port}).fetchall()

        # Keep the most-recently-used row, clear the port on the rest.
        for (instance_id,) in rows[1:]:
            conn.execute(text(
                "UPDATE vm_instance SET websocket_port = NULL WHERE id = :id"
            ), {'id': instance_id})
            cleared += 1
            log.warning(
                "Cleared duplicate active websocket_port %s from vm_instance %s",
                port, instance_id,
            )

    return cleared


def upgrade(conn) -> None:
    """Add the partial unique websocket_port index on ``conn`` (idempotent)."""
    existing = {row[1] for row in conn.execute(text("PRAGMA table_info(vm_instance)"))}

    if not existing:
        # Table not present (very old / partial database) — create_all owns it.
        print("· Table 'vm_instance' not present, skipping.")
        return

    cleared = _resolve_duplicate_active_ports(conn)
    if cleared:
        print(f"Cleared {cleared} duplicate active websocket_port value(s) before adding unique index.")
    else:
        print("No duplicate active websocket_port values found.")

    print(f"Creating unique index '{_INDEX_NAME}'...")
    conn.execute(text(
        f"CREATE UNIQUE INDEX IF NOT EXISTS {_INDEX_NAME} "
        f"ON vm_instance (websocket_port) WHERE status = 'active'"
    ))


def run_migration() -> bool:
    """Manual entry point: run :func:`upgrade` against the global database."""
    from adare.database.api.vm import VmApi

    print("Running migration: add_unique_active_websocket_port_to_vm_instance")

    try:
        with VmApi() as api:
            with api.engine.begin() as conn:
                upgrade(conn)

        print("✓ Migration completed successfully!")
        print("\nIMPORTANT:")
        print("- Any pre-existing duplicate active websocket_port values were resolved")
        print("  by clearing the port on all but the most-recently-used instance")
        return True

    except SQLAlchemyError as e:
        print(f"✗ Migration failed: {e}", file=sys.stderr)
        log.error("Migration failed: %s", e, exc_info=True)
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    success = run_migration()
    sys.exit(0 if success else 1)
