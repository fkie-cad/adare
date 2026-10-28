"""
``adare runs prune``: find and remove run folders without a database row, and fake runs.

:func:`plan_prune` only reads (the dry run); :func:`execute_prune` deletes exactly the
planned entries. Folders are only ever selected and deleted through
:mod:`adare.backend.experiment.run_folders`, so anything that is not clearly an ADARE
run folder (user files in ``run/``, symlinks out of it, folders still being written)
is never listed.

Targets:

* ``orphan`` -- a run folder that passes the run-folder test and that nothing refers
  to: no run row's ``path``, no dev session, and no run row without a ``path`` (a run
  that failed before it recorded one, e.g. during VM preparation) of its experiment
  that started within :data:`PATHLESS_RUN_WINDOW` of the folder's timestamp name.
  The run rows of every registered project whose ``run/`` resolves to the same
  directory count too; when one of them cannot be read, nothing is pruned.
* ``fake`` (with ``fake=True``) -- a fake (test-mode) run in a terminal status
  (:data:`~adare.backend.experiment.run_folders.TERMINAL_RUN_STATUSES`) that is not a
  dev session's run and started at least
  :data:`~adare.backend.experiment.run_folders.MIN_AGE_SECONDS` ago: its rows, and its
  folder when that passes the run-folder test.

:func:`retain_test_runs` (run after every test-mode experiment run) uses the same
``fake`` selection to keep only the newest ``ADARE_TEST_RUNS_KEEP`` test runs of an
experiment.
"""

import logging
import time
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from adare.backend.experiment.run_folders import (
    FOLDER_NOT_FOUND,
    MIN_AGE_SECONDS,
    RUN_DIR_NAME,
    TERMINAL_RUN_STATUSES,
    DevSessionRefs,
    RunReferencesUnavailableError,
    check_run_folder,
    folder_size,
    known_experiments,
    load_dev_session_refs,
    remove_run_folder,
    run_tail,
    scan_run_folders,
)
from adare.core.dto.show import RunPruneEntry
from adarelib.constants import StatusEnum

log = logging.getLogger(__name__)

_CHUNK = 500
_DAY = 86400.0
_FOLDER_TIME_FORMAT = '%Y-%m-%d_%H-%M-%S'
#: How far from a folder's timestamp name a run row without a ``path`` of the same
#: experiment may have started and still keep that folder. The folder name
#: (``ExperimentRunDirectory``) and ``start_time`` are both UTC, and the folder is
#: created seconds to minutes after ``start_time``; ``created_at`` is SQLite
#: ``CURRENT_TIMESTAMP`` (UTC). Folder names and start times written before mid-2024
#: were local time, so up to 14 h (the largest UTC offset) of local/UTC mix-up is
#: covered on top of 2 h of slack.
PATHLESS_RUN_WINDOW = timedelta(hours=16)


@dataclass(frozen=True)
class _DbRun:
    id: str
    tail: tuple[str, str] | None
    fake: bool
    status: StatusEnum | None
    started: float | None
    experiment: str | None = None
    #: Naive UTC ``start_time`` and ``created_at`` (whichever are set).
    times: tuple[datetime, ...] = ()


@dataclass
class _References:
    """What keeps a run folder: run-row paths, dev sessions, and runs without a path."""

    tails: set[tuple[str, str]] = field(default_factory=set)
    #: experiment name (None: a run without an experiment) -> times of its runs without a path
    pathless: defaultdict[str | None, list[datetime]] = field(default_factory=lambda: defaultdict(list))

    def add_runs(self, runs: Iterable[_DbRun]) -> None:
        for run in runs:
            if run.tail is not None:
                self.tails.add(run.tail)
            else:
                # No path, or one that does not map to run/<experiment>/<timestamp>.
                self.pathless[run.experiment].extend(run.times)

    def refers_to(self, experiment: str, name: str) -> bool:
        if (experiment, name) in self.tails:
            return True
        candidates = [*self.pathless.get(experiment, ()), *self.pathless.get(None, ())]
        if not candidates:
            return False
        try:
            when = datetime.strptime(name[:19], _FOLDER_TIME_FORMAT)
        except ValueError:
            return True  # the folder cannot be placed in time: keep it
        return any(abs(when - started) <= PATHLESS_RUN_WINDOW for started in candidates)


def _epoch(value: datetime | None) -> float | None:
    """Seconds since the epoch; naive database timestamps are UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.timestamp()


def _naive_utc(value: datetime | None) -> datetime | None:
    """Database timestamps are naive UTC; an aware one is converted to that."""
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


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
                Experiment.name,
            ).outerjoin(Experiment, ExperimentRun.experiment_id == Experiment.id)
        ).all()
        names = {str(name) for name in api._session.execute(select(Experiment.name)).scalars() if name}
    runs = [
        _DbRun(
            id=str(run_id),
            tail=run_tail(path) if path else None,
            fake=bool(fake),
            status=status,
            started=_epoch(start_time) or _epoch(created_at),
            experiment=str(experiment) if experiment else None,
            times=tuple(t for t in (_naive_utc(start_time), _naive_utc(created_at)) if t is not None),
        )
        for run_id, path, fake, status, start_time, created_at, experiment in rows
    ]
    return runs, names


def _registered_project_paths() -> list[str]:
    from adare.database.api.base import GlobalDatabaseApi
    from adare.database.models.global_models import Project

    with GlobalDatabaseApi() as api:
        return [str(path) for path in api._session.execute(select(Project.path)).scalars() if path]


def _sharing_projects(project_root: Path) -> list[Path]:
    """Other registered projects whose ``run/`` resolves to this project's ``run/`` directory.

    Raises:
        RunReferencesUnavailableError: The registered projects could not be read, or
            for one of them it cannot be told whether it shares the directory.
    """
    from adare.database.exceptions import DatabaseError

    try:
        own_run = (project_root / RUN_DIR_NAME).resolve(strict=True)
        own_root = project_root.resolve()
    except (OSError, RuntimeError):
        return []  # no run/ directory: nothing to prune anyway
    try:
        paths = _registered_project_paths()
    except (SQLAlchemyError, DatabaseError, OSError) as e:
        raise RunReferencesUnavailableError(f'the registered projects could not be read: {e}') from e
    sharing, unknown = [], []
    for raw in paths:
        other = Path(raw)
        try:
            if other.resolve() == own_root:
                continue
            other_run = (other / RUN_DIR_NAME).resolve(strict=True)
        except FileNotFoundError:
            continue  # no run/ there (or the project is gone): it cannot share ours
        except (OSError, RuntimeError) as e:
            unknown.append(f'{other}: {e}')
            continue
        if other_run == own_run:
            sharing.append(other)
    if unknown:
        raise RunReferencesUnavailableError(
            f"cannot tell whether these projects share this run/ directory: {'; '.join(unknown)}"
        )
    return sharing


def _sharing_project_runs(project_root: Path) -> list[_DbRun]:
    """The runs of every other registered project sharing this project's ``run/`` directory.

    Raises:
        RunReferencesUnavailableError: One of those projects' databases could not be read.
    """
    from adare.database.exceptions import DatabaseError

    runs: list[_DbRun] = []
    unreadable = []
    for other in _sharing_projects(project_root):
        # Only read a database that exists; never create one in another project.
        if not (other / '.adare' / 'project.db.sqlite3').is_file():
            unreadable.append(f'{other}: no project database')
            continue
        try:
            other_runs, _names = _load_runs(other)
        except (SQLAlchemyError, DatabaseError, OSError) as e:
            unreadable.append(f'{other}: {e}')
            continue
        runs.extend(other_runs)
    if unreadable:
        raise RunReferencesUnavailableError(
            f"other projects share this run/ directory but their runs could not be read ({'; '.join(unreadable)})"
        )
    return runs


def _old_enough(timestamp: float | None, now: float, older_than_days: float | None) -> bool:
    if older_than_days is None:
        return True
    return timestamp is not None and now - timestamp >= older_than_days * _DAY


def _prunable_fake(
    run_id: str, tail: tuple[str, str] | None, fake: bool, status: StatusEnum | None, dev: DevSessionRefs
) -> bool:
    """A fake run in a terminal status that is not a dev session's run."""
    if not fake or status not in TERMINAL_RUN_STATUSES or run_id in dev.ids:
        return False
    return tail is None or tail not in dev.tails


def _fake_entries(
    project_root: Path, runs: Iterable[_DbRun], now: float, older_than_days: float | None, dev: DevSessionRefs
) -> list[RunPruneEntry]:
    entries = []
    for run in runs:
        if not _prunable_fake(run.id, run.tail, run.fake, run.status, dev):
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
        RunReferencesUnavailableError: Something that may refer to a run folder (dev
            sessions, another project sharing ``run/``) could not be read.
    """
    current = time.time() if now is None else now
    runs, experiment_names = _load_runs(project_root)
    dev = load_dev_session_refs()
    references = _References(tails=set(dev.tails))
    references.add_runs(runs)
    references.add_runs(_sharing_project_runs(project_root))
    experiments = known_experiments(project_root) | experiment_names | {tail[0] for tail in references.tails}

    entries = []
    for check in scan_run_folders(project_root, experiments, now=current):
        experiment, name = check.path.parent.name, check.path.name
        if references.refers_to(experiment, name) or not _old_enough(check.last_activity, current, older_than_days):
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
        entries.extend(_fake_entries(project_root, runs, current, older_than_days, dev))
    return entries


def _delete_fake_rows(project_root: Path, run_ids: list[str], dev: DevSessionRefs) -> set[str]:
    """Delete the still-prunable fake runs among ``run_ids`` in one transaction; return their ids."""
    from adare.database.api.experiment import ExperimentApi
    from adare.database.api.run_cleanup import delete_runs
    from adare.database.models.project_models import ExperimentRun

    with ExperimentApi(project_root) as api:
        runs = []
        for start in range(0, len(run_ids), _CHUNK):
            chunk = run_ids[start : start + _CHUNK]
            runs.extend(api._session.query(ExperimentRun).filter(ExperimentRun.id.in_(chunk), ExperimentRun.fake).all())
        runs = [
            run
            for run in runs
            if _prunable_fake(str(run.id), run_tail(run.path) if run.path else None, bool(run.fake), run.status, dev)
        ]
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
        RunReferencesUnavailableError: The dev sessions could not be read (nothing was deleted).
    """
    dev = load_dev_session_refs()
    fake_ids = [entry.run_ulid for entry in entries if entry.kind == 'fake' and entry.run_ulid]
    deleted_ids = _delete_fake_rows(project_root, fake_ids, dev) if fake_ids else set()

    for entry in entries:
        if entry.kind == 'fake':
            if entry.run_ulid not in deleted_ids:
                entry.note = 'skipped: no longer a prunable fake run'
                continue
            entry.removed = True
        if entry.folder is None:
            continue
        removal = remove_run_folder(
            project_root, Path(entry.folder), experiments={entry.experiment}, now=now, dev_sessions=dev
        )
        entry.folder_removed = removal.removed
        entry.removed = entry.removed or removal.removed
        if not removal.removed:
            entry.note = f'folder kept: {removal.reason}'
    log.info('pruned %d run row(s) and %d folder(s)', len(deleted_ids), sum(1 for e in entries if e.folder_removed))
    return len(deleted_ids)


#: The setting (``adare system settings``) for how many test runs per experiment are kept.
TEST_RUNS_KEEP_SETTING = 'ADARE_TEST_RUNS_KEEP'


@dataclass(frozen=True)
class RetentionResult:
    """Outcome of :func:`retain_test_runs`."""

    #: Fake run rows deleted.
    removed: int = 0
    #: Bytes of the run folders deleted with them.
    bytes_freed: int = 0
    folders_removed: int = 0


def _newest_first(run: _DbRun) -> tuple[float, str]:
    # A run without any timestamp ranks as the oldest; the ULID breaks ties in start order.
    return (run.started if run.started is not None else float('-inf'), run.id)


def retain_test_runs(
    project_root: Path, experiment_name: str, keep: int, current_run_id: str | None, *, now: float | None = None
) -> RetentionResult:
    """Keep the ``keep`` newest test (fake) runs of ``experiment_name``; delete the older ones.

    The candidates are the experiment's fake runs that ``adare runs prune --fake`` would
    target: in a terminal status and not a dev session's run. They are ranked by
    ``start_time`` (``created_at`` when it is missing), newest first. The current run
    (``current_run_id``) takes one of the ``keep`` places and is never deleted, so
    ``keep`` 0 and 1 both leave only the current run; without a current run, ``keep``
    0 targets every candidate. Beyond the kept places, a run is still kept when it
    started less than :data:`~adare.backend.experiment.run_folders.MIN_AGE_SECONDS`
    ago, or when its folder exists but fails
    :func:`~adare.backend.experiment.run_folders.check_run_folder` (then its row stays
    too). Non-terminal runs, dev sessions' runs, real runs and other experiments' runs
    are never touched and take no place.

    The rows go first, in one transaction (:func:`execute_prune`), then the folders.

    Raises:
        SQLAlchemyError: The project database could not be read or written (nothing was deleted).
        RunReferencesUnavailableError: The dev sessions could not be read (nothing was deleted).
    """
    current = time.time() if now is None else now
    runs, _names = _load_runs(project_root)
    dev = load_dev_session_refs()
    candidates = sorted(
        (
            run
            for run in runs
            if run.experiment == experiment_name
            and run.id != current_run_id
            and _prunable_fake(run.id, run.tail, run.fake, run.status, dev)
        ),
        key=_newest_first,
        reverse=True,
    )
    older_places = max(keep - (1 if current_run_id else 0), 0)
    # older_than_days=None: _fake_entries applies the MIN_AGE_SECONDS floor itself. An entry
    # with a note has a folder that failed check_run_folder: that run is kept whole.
    entries = [
        entry for entry in _fake_entries(project_root, candidates[older_places:], current, None, dev) if not entry.note
    ]
    if not entries:
        return RetentionResult()
    removed = execute_prune(project_root, entries, now=current)
    folders = [entry for entry in entries if entry.folder_removed]
    return RetentionResult(
        removed=removed, bytes_freed=sum(entry.size_bytes for entry in folders), folders_removed=len(folders)
    )


def apply_test_run_retention(project_root: Path, experiment_name: str, current_run_id: str | None) -> str | None:
    """After a test run: :func:`retain_test_runs` with the ``ADARE_TEST_RUNS_KEEP`` setting.

    Never fails the run: when the runs cannot be read or deleted, a warning is logged and
    everything is kept. Returns a line to print when something was removed, else None.
    """
    from adare.config import settings
    from adare.database.exceptions import DatabaseError

    configured = settings.get(TEST_RUNS_KEEP_SETTING)
    keep = int(configured) if configured is not None else 0
    try:
        result = retain_test_runs(project_root, experiment_name, keep, current_run_id)
    except (RunReferencesUnavailableError, SQLAlchemyError, DatabaseError, OSError) as e:
        log.warning('older test runs of %s kept: %s', experiment_name, e)
        return None
    if not result.removed:
        return None
    from adare.cli.system import _size

    noun = 'test run' if result.removed == 1 else 'test runs'
    message = f'removed {result.removed} older {noun} ({_size(result.bytes_freed)}; {TEST_RUNS_KEEP_SETTING}={keep})'
    log.info('%s of experiment %s', message, experiment_name)
    return message
