#!/usr/bin/env python3
"""
Database migration: Add the run_artifact table to project databases.

``run_artifact`` generalizes ``experiment_run_files``' one-column-per-kind
scheme to artifact kinds that produce N files per run (disk image export,
pcap capture) — see ``adare.database.models.project_models.RunArtifact``.

This is a *project*-scoped migration: it is applied automatically whenever a
project database is opened (see ``adare.database.migrations.runner``). Run it
explicitly against every registered project with:
    adare db migrate
    python -m adare.database.migrations.add_run_artifact_table

For new installations, the table is created automatically from the model.
"""

import logging
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

log = logging.getLogger(__name__)


def upgrade(conn) -> None:
    """Create run_artifact on ``conn`` if it does not already exist (idempotent)."""
    conn.execute(text(
        """
        CREATE TABLE IF NOT EXISTS run_artifact (
            id CHAR(26) NOT NULL PRIMARY KEY,
            experiment_run_id CHAR(26) NOT NULL REFERENCES experiment_run(id) ON DELETE CASCADE,
            machine_name VARCHAR NULL,
            kind VARCHAR NOT NULL,
            format VARCHAR NULL,
            path VARCHAR NOT NULL,
            created_at DATETIME NULL
        )
        """
    ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_run_artifact_experiment_run_id ON run_artifact (experiment_run_id)"
    ))
    print("✓ Table 'run_artifact' present.")


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
    """Add the run_artifact table to every project DB."""
    from adare.database.api.base import GlobalDatabaseApi
    from adare.database.models.global_models import Project

    print("Running migration: add_run_artifact_table")

    try:
        with GlobalDatabaseApi() as api:
            projects = api._session.query(Project).all()
            project_paths = [Path(p.path) for p in projects if p.path]
    except SQLAlchemyError as e:
        print(f"✗ Could not list projects: {e}", file=sys.stderr)
        log.error("Could not list projects: %s", e, exc_info=True)
        return False

    if not project_paths:
        print("No projects registered — nothing to migrate.")
        return True

    all_ok = True
    for project_path in project_paths:
        if not project_path.exists():
            print(f"Project {project_path}: path missing, skipping")
            continue
        all_ok = _migrate_project(project_path) and all_ok

    if all_ok:
        print("✓ Migration completed successfully!")
    return all_ok


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    success = run_migration()
    sys.exit(0 if success else 1)
