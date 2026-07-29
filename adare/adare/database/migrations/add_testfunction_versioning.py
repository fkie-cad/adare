#!/usr/bin/env python3
"""
Database migration: Add testfunction versioning + history to the global database.

Adds the columns and tables that make a testfunction update a new immutable
version under a stable identity (instead of a destructive delete+recreate):

    test_function_file.version          -- int, default 1
    test_function.version               -- int, default 1
    test_function.is_current            -- bool, default 1 (True)
    test_function_file_version (table)  -- per-file snapshot registry
    test_function_version (table)       -- per-method version history

Existing rows are backfilled to version=1 / is_current=1 and get a v1 history
row using their current sha256hash.

This migration is applied automatically when the global database is opened
(see ``adare.database.migrations.runner``). Run it explicitly with:
    adare db migrate
    python -m adare.database.migrations.add_testfunction_versioning

For new installations, the columns/tables are created automatically from the
model via create_all (which never ALTERs existing tables — hence this script).
"""

import logging
import sys

import ulid
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

log = logging.getLogger(__name__)


def _existing_columns(conn, table: str) -> set[str]:
    return {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}


def _add_column(conn, table: str, column: str, ddl: str) -> None:
    columns = _existing_columns(conn, table)
    if not columns:
        # Table not present (very old / partial database) — create_all owns it.
        print(f"· Table '{table}' not present, skipping.")
        return
    if column in columns:
        print(f"✓ Column '{table}.{column}' already exists, skipping.")
        return
    print(f"Adding column '{table}.{column}'...")
    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))


def _create_history_tables(conn) -> None:
    conn.execute(text(
        """
        CREATE TABLE IF NOT EXISTS test_function_file_version (
            id CHAR(26) PRIMARY KEY,
            file_id CHAR(26) NOT NULL REFERENCES test_function_file(id) ON DELETE CASCADE,
            version INTEGER NOT NULL,
            sha256hash VARCHAR NOT NULL,
            snapshot_dir VARCHAR NULL,
            created_at DATETIME NULL,
            CONSTRAINT uq_test_function_file_version UNIQUE (file_id, version)
        )
        """
    ))
    conn.execute(text(
        """
        CREATE TABLE IF NOT EXISTS test_function_version (
            id CHAR(26) PRIMARY KEY,
            test_function_id CHAR(26) NOT NULL REFERENCES test_function(id) ON DELETE CASCADE,
            version INTEGER NOT NULL,
            sha256hash VARCHAR NOT NULL,
            file_version INTEGER NULL,
            created_at DATETIME NULL,
            CONSTRAINT uq_test_function_version UNIQUE (test_function_id, version)
        )
        """
    ))


def _backfill(conn) -> None:
    if not _existing_columns(conn, 'test_function_file') or not _existing_columns(conn, 'test_function'):
        print("· Testfunction tables not present, nothing to backfill.")
        return

    # Normalise version/is_current on any rows left NULL by the ALTER.
    conn.execute(text("UPDATE test_function_file SET version = 1 WHERE version IS NULL"))
    conn.execute(text("UPDATE test_function SET version = 1 WHERE version IS NULL"))
    conn.execute(text("UPDATE test_function SET is_current = 1 WHERE is_current IS NULL"))

    # One v1 file-version row per file that has no history yet.
    file_rows = conn.execute(text(
        """
        SELECT f.id, f.sha256hash, f.path
        FROM test_function_file f
        WHERE NOT EXISTS (
            SELECT 1 FROM test_function_file_version v WHERE v.file_id = f.id
        )
        """
    )).fetchall()
    for file_id, sha256hash, path in file_rows:
        snapshot_dir = None
        if path:
            from pathlib import Path
            snapshot_dir = (Path(path).parent / 'versions' / 'v1').as_posix()
        conn.execute(
            text(
                "INSERT INTO test_function_file_version "
                "(id, file_id, version, sha256hash, snapshot_dir, created_at) "
                "VALUES (:id, :file_id, 1, :sha, :snap, datetime('now'))"
            ),
            {'id': str(ulid.ULID()), 'file_id': file_id, 'sha': sha256hash, 'snap': snapshot_dir},
        )

    # One v1 method-version row per method that has no history yet.
    method_rows = conn.execute(text(
        """
        SELECT t.id, t.sha256hash
        FROM test_function t
        WHERE NOT EXISTS (
            SELECT 1 FROM test_function_version v WHERE v.test_function_id = t.id
        )
        """
    )).fetchall()
    for tf_id, sha256hash in method_rows:
        conn.execute(
            text(
                "INSERT INTO test_function_version "
                "(id, test_function_id, version, sha256hash, file_version, created_at) "
                "VALUES (:id, :tf_id, 1, :sha, 1, datetime('now'))"
            ),
            {'id': str(ulid.ULID()), 'tf_id': tf_id, 'sha': sha256hash},
        )

    print(f"✓ Backfilled {len(file_rows)} file version(s) and {len(method_rows)} method version(s).")


def upgrade(conn) -> None:
    """Add versioning columns + history tables on ``conn`` (idempotent)."""
    _add_column(conn, 'test_function_file', 'version', "INTEGER NOT NULL DEFAULT 1")
    _add_column(conn, 'test_function', 'version', "INTEGER NOT NULL DEFAULT 1")
    _add_column(conn, 'test_function', 'is_current', "BOOLEAN NOT NULL DEFAULT 1")
    _create_history_tables(conn)
    _backfill(conn)


def run_migration() -> bool:
    """Manual entry point: run :func:`upgrade` against the global database."""
    from adare.database.api.base import GlobalDatabaseApi

    print("Running migration: add_testfunction_versioning")

    try:
        with GlobalDatabaseApi() as api:
            with api.engine.begin() as conn:
                upgrade(conn)

        print("✓ Migration completed successfully!")
        print("\nIMPORTANT:")
        print("- Existing testfunctions are version 1 / is_current=1")
        print("- Future edits (adare test load / sync) append immutable versions")
        return True

    except SQLAlchemyError as e:
        print(f"✗ Migration failed: {e}", file=sys.stderr)
        log.error("Migration failed: %s", e, exc_info=True)
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    success = run_migration()
    sys.exit(0 if success else 1)
