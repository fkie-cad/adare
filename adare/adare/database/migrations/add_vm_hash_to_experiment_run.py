#!/usr/bin/env python3
"""
Database migration: Add vm_hash to the experiment_run table of project databases.

``vm_hash`` records the sha256 of the disk image a run booted, so a run names
its image even if the environment or its VM row changes later.

This is a *project*-scoped migration: it is applied automatically whenever a
project database is opened (see ``adare.database.migrations.runner``). Run it
explicitly against every registered project with:
    adare db migrate
    python -m adare.database.migrations.add_vm_hash_to_experiment_run

For new installations, the column is created automatically from the model.
"""

import logging
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

log = logging.getLogger(__name__)


def upgrade(conn) -> None:
    """Add experiment_run.vm_hash on ``conn`` (idempotent)."""
    existing = {row[1] for row in conn.execute(text("PRAGMA table_info(experiment_run)"))}
    if not existing:
        print("· Table 'experiment_run' not present, skipping.")
        return
    if 'vm_hash' in existing:
        print("✓ Column 'vm_hash' already exists, skipping.")
        return
    print("Adding column 'vm_hash' to experiment_run table...")
    conn.execute(text("ALTER TABLE experiment_run ADD COLUMN vm_hash VARCHAR NULL"))


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
    """Add experiment_run.vm_hash to every project DB."""
    from adare.database.api.base import GlobalDatabaseApi
    from adare.database.models.global_models import Project

    print("Running migration: add_vm_hash_to_experiment_run")
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
