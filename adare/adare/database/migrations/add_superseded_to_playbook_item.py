#!/usr/bin/env python3
"""
Database migration: Add superseded to the playbook_item table of project databases.

Re-ingesting a playbook used to delete every item of the experiment's playbook,
leaving the ``action_execution`` rows of earlier runs pointing at deleted items.
Re-ingest now keeps the items executions reference and marks them
``superseded = 1``; the current playbook is the items with ``superseded = 0``.
Existing items are all current, so the column is added with default 0.

This is a *project*-scoped migration: it is applied automatically whenever a
project database is opened (see ``adare.database.migrations.runner``). Run it
explicitly against every registered project with:
    adare db migrate
    python -m adare.database.migrations.add_superseded_to_playbook_item

For new installations, the column is created automatically from the model.
"""

import logging
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

log = logging.getLogger(__name__)


def upgrade(conn) -> None:
    """Add playbook_item.superseded on ``conn`` (idempotent)."""
    existing = {row[1] for row in conn.execute(text("PRAGMA table_info(playbook_item)"))}
    if not existing:
        print("· Table 'playbook_item' not present, skipping.")
        return
    if 'superseded' in existing:
        print("✓ Column 'superseded' already exists, skipping.")
        return
    print("Adding column 'superseded' to playbook_item table...")
    conn.execute(text("ALTER TABLE playbook_item ADD COLUMN superseded BOOLEAN NOT NULL DEFAULT '0'"))


def _migrate_project(project_path: Path) -> bool:
    from adare.database.api.base import ProjectDatabaseApi

    print(f"Project {project_path}:")
    try:
        with ProjectDatabaseApi(project_path) as api, api.engine.begin() as conn:
            upgrade(conn)
        return True
    except SQLAlchemyError as e:
        print(f"  ✗ failed: {e}", file=sys.stderr)
        log.error("Migration failed for %s: %s", project_path, e, exc_info=True)
        return False


def run_migration() -> bool:
    """Add playbook_item.superseded to every project DB."""
    from adare.database.api.base import GlobalDatabaseApi
    from adare.database.models.global_models import Project

    print("Running migration: add_superseded_to_playbook_item")
    try:
        with GlobalDatabaseApi() as api:
            project_paths = [Path(p.path) for p in api._session.query(Project).all() if p.path]
    except SQLAlchemyError as e:
        print(f"✗ Could not list projects: {e}", file=sys.stderr)
        log.error("Could not list projects: %s", e, exc_info=True)
        return False
    ok = True
    for project_path in project_paths:
        if project_path.exists():
            ok = _migrate_project(project_path) and ok
    return ok


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(0 if run_migration() else 1)
