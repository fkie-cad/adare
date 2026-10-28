"""
``adare runs prune``: find and remove run folders without a database row, and fake runs.

:func:`plan_prune` only reads (the dry run); :func:`execute_prune` deletes exactly the
planned entries. Folders are only ever selected and deleted through
:mod:`adare.backend.experiment.run_folders`, so anything that is not clearly an ADARE
run folder (user files in ``run/``, symlinks out of it, folders still being written)
is never listed.

Targets:

* ``orphan`` -- a run folder that passes the run-folder test and that no run row of
  the project (and no dev session) refers to.
* ``fake`` (with ``fake=True``) -- a fake (test-mode) run that is not RUNNING and
  started at least :data:`~adare.backend.experiment.run_folders.MIN_AGE_SECONDS` ago:
  its rows, and its folder when that passes the run-folder test.
"""

import logging
import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from adare.backend.experiment.run_folders import (
    FOLDER_NOT_FOUND,
    MIN_AGE_SECONDS,
    RUN_DIR_NAME,
    check_run_folder,
    folder_size,
    known_experiments,
    remove_run_folder,
    run_tail,
    scan_run_folders,
)
from adare.core.dto.show import RunPruneEntry
from adarelib.constants import StatusEnum

log = logging.getLogger(__name__)

_CHUNK = 500
_DAY = 86400.0


@dataclass(frozen=True)
class _DbRun:
    id: str
    tail: tuple[str, str] | None
    fake: bool
    status: StatusEnum | None
    started: float | None


def _epoch(value: datetime | None) -> float | None:
    """Seconds since the epoch; naive database timestamps are UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.timestamp()


def _load_runs(project_root: Path) -> tuple[list[_DbRun], set[str]]:
    """The project's runs and experiment names."""
    from adare.database.api.experiment import ExperimentApi
    from adare.database.models.project_models import Experiment, ExperimentRun

    with ExperimentApi(project_root) as api:
        rows = api._session.execute(
            select(
                ExperimentRun.id,
                ExperimentRun.path,
                ExperimentRun.fake,
                ExperimentRun.status,
                ExperimentRun.start_time,
                ExperimentRun.created_at,
            )
        ).all()
        names = {str(name) for name in api._session.execute(select(Experiment.name)).scalars() if name}
    runs = [
        _DbRun(
            id=str(run_id),
            tail=run_tail(path) if path else None,
            fake=bool(fake),
            status=status,
            started=_epoch(start_time) or _epoch(created_at),
        )
        for run_id, path, fake, status, start_time, created_at in rows
    ]
    return runs, names


def _dev_session_tails() -> set[tuple[str, str]]:
    """``run/<experiment>/<timestamp>`` tails of every dev session's run folder (any project, any status)."""
    from adare.database.api.devmode import DevModeApi
    from adare.database.models.devsession import DevSession

    with DevModeApi() as api:
        paths = api._session.execute(select(DevSession.run_directory_path)).scalars().all()
    return {tail for path in paths if path and (tail := run_tail(path)) is not None}


def _old_enough(timestamp: float | None, now: float, older_than_days: float | None) -> bool:
    if older_than_days is None:
        return True
    return timestamp is not None and now - timestamp >= older_than_days * _DAY


def _fake_entries(
    project_root: Path, runs: Iterable[_DbRun], now: float, older_than_days: float | None
) -> list[RunPruneEntry]:
    entries = []
    for run in runs:
        if not run.fake or run.status == StatusEnum.RUNNING:
            continue
        if run.started is not None and now - run.started < MIN_AGE_SECONDS:
            continue
        folder: Path | None = None
        note = None
        size = 0
        activity = None
        if run.tail is not None:
            # Mapped by its run/<experiment>/<timestamp> tail, so a moved project still matches.
            mapped = project_root / RUN_DIR_NAME / run.tail[0] / run.tail[1]
            check = check_run_folder(project_root, mapped, experiments={run.tail[0]}, now=now)
            if check.ok and check.resolved is not None:
                folder, activity = mapped, check.last_activity
            elif check.reason != FOLDER_NOT_FOUND:
                note = f'folder kept: {check.reason}'
        if not _old_enough(run.started if run.started is not None else activity, now, older_than_days):
            continue
        if folder is not None:
            size = folder_size(folder)
        entries.append(
            RunPruneEntry(
                kind='fake',
                experiment=run.tail[0] if run.tail else '',
                folder=str(folder) if folder else None,
                size_bytes=size,
                run_ulid=run.id,
                last_activity=datetime.fromtimestamp(activity, UTC) if activity else None,
                note=note,
            )
        )
    return entries


def plan_prune(
    project_root: Path, *, fake: bool = False, older_than_days: float | None = None, now: float | None = None
) -> list[RunPruneEntry]:
    """What :func:`execute_prune` would remove; reads only.

    Raises:
        SQLAlchemyError: The project or global database could not be read.
    """
    current = time.time() if now is None else now
    runs, experiment_names = _load_runs(project_root)
    referenced = {run.tail for run in runs if run.tail is not None} | _dev_session_tails()
    experiments = known_experiments(project_root) | experiment_names | {tail[0] for tail in referenced}

    entries = []
    for check in scan_run_folders(project_root, experiments, now=current):
        experiment, name = check.path.parent.name, check.path.name
        if (experiment, name) in referenced or not _old_enough(check.last_activity, current, older_than_days):
            continue
        entries.append(
            RunPruneEntry(
                kind='orphan',
                experiment=experiment,
                folder=str(check.path),
                size_bytes=folder_size(check.path),
                last_activity=datetime.fromtimestamp(check.last_activity, UTC) if check.last_activity else None,
            )
        )
    if fake:
        entries.extend(_fake_entries(project_root, runs, current, older_than_days))
    return entries


def _delete_fake_rows(project_root: Path, run_ids: list[str]) -> set[str]:
    """Delete the still-prunable fake runs among ``run_ids`` in one transaction; return their ids."""
    from adare.database.api.experiment import ExperimentApi
    from adare.database.api.run_cleanup import delete_runs
    from adare.database.models.project_models import ExperimentRun

    with ExperimentApi(project_root) as api:
        runs = []
        for start in range(0, len(run_ids), _CHUNK):
            chunk = run_ids[start : start + _CHUNK]
            runs.extend(api._session.query(ExperimentRun).filter(ExperimentRun.id.in_(chunk), ExperimentRun.fake).all())
        runs = [run for run in runs if run.status != StatusEnum.RUNNING]
        deleted = {str(run.id) for run in runs}
        delete_runs(api._session, runs)
        api._session.commit()
    return deleted


def execute_prune(project_root: Path, entries: list[RunPruneEntry], *, now: float | None = None) -> int:
    """Remove exactly ``entries`` (from :func:`plan_prune`); mark each ``removed``/``note``.

    Fake run rows go first, in one transaction; then the folders, each re-checked by
    the safe delete helper. Returns the number of run rows deleted.

    Raises:
        SQLAlchemyError: Deleting the fake run rows failed (nothing was deleted).
    """
    fake_ids = [entry.run_ulid for entry in entries if entry.kind == 'fake' and entry.run_ulid]
    deleted_ids = _delete_fake_rows(project_root, fake_ids) if fake_ids else set()

    for entry in entries:
        if entry.kind == 'fake':
            if entry.run_ulid not in deleted_ids:
                entry.note = 'skipped: no longer a prunable fake run'
                continue
            entry.removed = True
        if entry.folder is None:
            continue
        removal = remove_run_folder(project_root, Path(entry.folder), experiments={entry.experiment}, now=now)
        entry.folder_removed = removal.removed
        entry.removed = entry.removed or removal.removed
        if not removal.removed:
            entry.note = f'folder kept: {removal.reason}'
    log.info('pruned %d run row(s) and %d folder(s)', len(deleted_ids), sum(1 for e in entries if e.folder_removed))
    return len(deleted_ids)
