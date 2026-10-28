"""
Complete deletion of experiment runs from a project database.

Foreign keys are off in SQLite, so ``ON DELETE CASCADE`` never fires and a plain
``session.delete(run)`` only removes what the ORM cascades (events, stages,
artifacts). A run also owns rows the ORM does not cascade to:

* ``action_execution`` rows -- linked by the indexed ``experiment_run_id`` column
  (no FK, no relationship). They can hold large blobs, so they are bulk-deleted
  without being loaded.
* its ``experiment_run_files`` row -- the run holds the FK (``files_id``), one
  row per run -- and that row's two ``log_file`` rows (``log_adare_id``,
  ``log_adarevm_id``).

:func:`delete_runs` removes all of it. It never commits: the caller owns the
transaction (the ``with api:`` block commits, or the caller commits explicitly).
"""

import logging
from collections.abc import Iterable, Sequence

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from adare.database.models.project_models import ActionExecution, ExperimentRun, ExperimentRunFiles, LogFile

log = logging.getLogger(__name__)

#: Ids per ``IN (...)`` clause, well below SQLite's bound-parameter limit.
_CHUNK = 500


def _chunks(ids: Sequence[str]) -> Iterable[list[str]]:
    for start in range(0, len(ids), _CHUNK):
        yield list(ids[start : start + _CHUNK])


def _still_referenced_files_ids(session: Session, files_ids: list[str]) -> set[str]:
    """The ``experiment_run_files`` ids among ``files_ids`` some remaining run still uses."""
    referenced: set[str] = set()
    for chunk in _chunks(files_ids):
        referenced.update(
            session.execute(select(ExperimentRun.files_id).where(ExperimentRun.files_id.in_(chunk))).scalars()
        )
    return referenced


def _delete_files_rows(session: Session, files_ids: list[str]) -> None:
    """Delete ``experiment_run_files`` rows and the ``log_file`` rows only they referenced."""
    log_ids: set[str] = set()
    for chunk in _chunks(files_ids):
        for adare_id, adarevm_id in session.execute(
            select(ExperimentRunFiles.log_adare_id, ExperimentRunFiles.log_adarevm_id).where(
                ExperimentRunFiles.id.in_(chunk)
            )
        ):
            log_ids.update(log_id for log_id in (adare_id, adarevm_id) if log_id)
        session.execute(delete(ExperimentRunFiles).where(ExperimentRunFiles.id.in_(chunk)))

    if not log_ids:
        return
    candidates = sorted(log_ids)
    shared: set[str] = set()
    for chunk in _chunks(candidates):
        for adare_id, adarevm_id in session.execute(
            select(ExperimentRunFiles.log_adare_id, ExperimentRunFiles.log_adarevm_id).where(
                or_(ExperimentRunFiles.log_adare_id.in_(chunk), ExperimentRunFiles.log_adarevm_id.in_(chunk))
            )
        ):
            shared.update(log_id for log_id in (adare_id, adarevm_id) if log_id)
    orphaned = [log_id for log_id in candidates if log_id not in shared]
    for chunk in _chunks(orphaned):
        session.execute(delete(LogFile).where(LogFile.id.in_(chunk)))


def delete_runs(session: Session, runs: Iterable[ExperimentRun]) -> list[str]:
    """Delete ``runs`` and every row they own; return the deleted runs' ``path`` values.

    Removes each run's ``action_execution`` rows (bulk, never loaded), the run
    itself via ``session.delete`` (so the ORM cascades to events, stages and
    artifacts keep working), then its ``experiment_run_files`` row and that row's
    ``log_file`` rows -- each only if no remaining run / files row still uses it.

    Flushes but never commits; the caller owns the transaction.

    Args:
        session: Session of the project database the runs belong to.
        runs: Persistent runs of that session.

    Returns:
        The non-empty ``path`` of every deleted run (run directories to remove),
        in the order given. Runs that never got a directory are not listed.
    """
    runs = list(runs)
    if not runs:
        return []
    # autoflush is off: make pending changes (e.g. a just-assigned files_id) visible to the SQL below.
    session.flush()

    # str(): the legacy Column-typed models give mypy Column[str] for these attributes.
    run_ids = [str(run.id) for run in runs]
    paths = [str(run.path) for run in runs if run.path]
    files_ids = sorted({str(run.files_id) for run in runs if run.files_id})

    for chunk in _chunks(run_ids):
        session.execute(delete(ActionExecution).where(ActionExecution.experiment_run_id.in_(chunk)))

    for run in runs:
        session.delete(run)
    session.flush()

    if files_ids:
        still_used = _still_referenced_files_ids(session, files_ids)
        _delete_files_rows(session, [files_id for files_id in files_ids if files_id not in still_used])

    log.debug('deleted %d run(s) with their action executions, files and log rows', len(runs))
    return paths
