#!/usr/bin/env python3
"""
Database migration: Move action keys out of ``event.parent_event_id`` into ``event.parent_group_id``.

``event.parent_event_id`` is declared as a foreign key to ``event.id``, but the
event writers stored the enclosing action's *key* there (its ``event_group_id``,
e.g. ``action_3_click_1700000000000``), never an event id. Every nested event was
therefore a foreign-key violation (``PRAGMA foreign_key_check``; foreign keys stay
off, so nothing failed at write time). The key now lives in the new
``event.parent_group_id`` column, and this migration moves what earlier writers
stored:

* add ``event.parent_group_id`` and its index ``ix_event_parent_group_id`` (the
  name SQLAlchemy gives ``index=True``, so fresh and migrated databases agree);
* move every ``parent_event_id`` that names no event into ``parent_group_id`` and
  clear it. A value that does name an event is a real parent and is kept.

Set-based SQL only. Idempotent: a second run finds nothing to move.

This is a *project*-scoped migration: it is applied automatically whenever a
project database is opened (see ``adare.database.migrations.runner``). Run it
explicitly against every registered project with:
    adare db migrate
    python -m adare.database.migrations.move_parent_event_keys
"""

import logging
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

log = logging.getLogger(__name__)

#: Action keys stored as a parent event id: values that name no event. ``event.id``
#: is the primary key and never NULL, so ``NOT IN`` is safe here.
_MOVE_KEYS = """
UPDATE event
SET parent_group_id = COALESCE(parent_group_id, parent_event_id),
    parent_event_id = NULL
WHERE parent_event_id IS NOT NULL
  AND parent_event_id NOT IN (SELECT id FROM event)
"""


def upgrade(conn) -> None:
    """Add event.parent_group_id and move action keys into it from parent_event_id (idempotent)."""
    columns = {row[1] for row in conn.execute(text("PRAGMA table_info(event)"))}
    if not columns:
        print("· Table 'event' not present, skipping.")
        return
    if 'parent_group_id' not in columns:
        conn.execute(text("ALTER TABLE event ADD COLUMN parent_group_id VARCHAR"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_event_parent_group_id ON event (parent_group_id)"))
    moved = conn.execute(text(_MOVE_KEYS)).rowcount
    print(f"✓ Moved {moved} action key(s) from event.parent_event_id to event.parent_group_id.")


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
    """Move parent action keys in every project DB."""
    from adare.database.api.base import GlobalDatabaseApi
    from adare.database.models.global_models import Project

    print("Running migration: move_parent_event_keys")
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
