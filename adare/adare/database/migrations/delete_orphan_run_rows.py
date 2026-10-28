#!/usr/bin/env python3
"""
Database migration: Delete the rows that deleted runs left behind in project databases.

Foreign keys are off in SQLite and run deletion used to rely on the ORM cascade,
which does not reach a run's ``action_execution`` rows (no FK, no relationship)
nor its ``experiment_run_files`` row and that row's ``log_file`` rows. Every
deleted run therefore left them behind; on a large project that is gigabytes of
action-result blobs nothing can reach. Run deletion now goes through
:func:`adare.database.api.run_cleanup.delete_runs`; this migration removes what
earlier deletions left:

* ``action_execution`` rows whose non-NULL ``experiment_run_id`` names no run.
  Rows with a NULL run id come from dev sessions and are kept.
* ``experiment_run_files`` rows no run references (``experiment_run.files_id``),
  and the ``log_file`` rows only those rows referenced.

Set-based SQL only -- blob columns are never read. Idempotent: a second run
finds nothing to delete.

This is a *project*-scoped migration: it is applied automatically whenever a
project database is opened (see ``adare.database.migrations.runner``). Run it
explicitly against every registered project with:
    adare db migrate
    python -m adare.database.migrations.delete_orphan_run_rows

The freed pages stay in the database file until it is vacuumed.
"""

import logging
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

log = logging.getLogger(__name__)

REQUIRED_TABLES = {'experiment_run', 'action_execution', 'experiment_run_files', 'log_file'}

#: action_execution rows of runs that no longer exist (NULL run id = dev session, kept).
_DELETE_ORPHAN_ACTION_EXECUTIONS = """
DELETE FROM action_execution
WHERE experiment_run_id IS NOT NULL
  AND experiment_run_id NOT IN (SELECT id FROM experiment_run)
"""

#: experiment_run_files ids some run points at (NULLs filtered: ``NOT IN`` with a NULL matches nothing).
_LIVE_FILES = "SELECT files_id FROM experiment_run WHERE files_id IS NOT NULL"

#: log_file rows referenced by an orphaned files row and by no live one.
_DELETE_ORPHAN_LOG_FILES = f"""
DELETE FROM log_file
WHERE id IN (
        SELECT log_adare_id FROM experiment_run_files WHERE id NOT IN ({_LIVE_FILES})
        UNION
        SELECT log_adarevm_id FROM experiment_run_files WHERE id NOT IN ({_LIVE_FILES})
    )
  AND id NOT IN (
        SELECT log_adare_id FROM experiment_run_files
        WHERE log_adare_id IS NOT NULL AND id IN ({_LIVE_FILES})
        UNION
        SELECT log_adarevm_id FROM experiment_run_files
        WHERE log_adarevm_id IS NOT NULL AND id IN ({_LIVE_FILES})
    )
"""

#: experiment_run_files rows no run points at.
_DELETE_ORPHAN_FILES = f"DELETE FROM experiment_run_files WHERE id NOT IN ({_LIVE_FILES})"


def upgrade(conn) -> None:
    """Delete orphaned action_execution, experiment_run_files and log_file rows (idempotent)."""
    tables = {row[0] for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type = 'table'"))}
    missing = REQUIRED_TABLES - tables
    if missing:
        print(f"· Tables {sorted(missing)} not present, skipping.")
        return

    executions = conn.execute(text(_DELETE_ORPHAN_ACTION_EXECUTIONS)).rowcount
    # Log files first: they are found through the orphaned files rows deleted next.
    log_files = conn.execute(text(_DELETE_ORPHAN_LOG_FILES)).rowcount
    files = conn.execute(text(_DELETE_ORPHAN_FILES)).rowcount
    print(
        f"✓ Deleted {executions} orphaned action_execution, {files} experiment_run_files "
        f"and {log_files} log_file row(s)."
    )


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
    """Delete orphaned run rows in every project DB."""
    from adare.database.api.base import GlobalDatabaseApi
    from adare.database.models.global_models import Project

    print("Running migration: delete_orphan_run_rows")
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
