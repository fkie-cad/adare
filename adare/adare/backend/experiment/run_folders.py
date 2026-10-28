"""
Safe handling of run folders (``<project>/run/<experiment>/<timestamp>``).

A project's ``run/`` directory also holds things ADARE did not create (users keep
their own script output there), so nothing in it is deleted unless it is clearly
an ADARE run folder. :func:`check_run_folder` is that test; a folder counts only
if ALL of these hold:

* it resolves (symlinks resolved) to a path inside the project's ``run/`` directory,
  and neither it nor its ``<experiment>`` parent is a symlink;
* it sits at depth 2: ``run/<experiment>/<timestamp>``;
* ``<experiment>`` is a known experiment (an ``experiments/<name>`` directory, or a
  name the caller vouches for, e.g. from the run's database row);
* its name is a run timestamp (``ExperimentRunDirectory``: ``%Y-%m-%d_%H-%M-%S``,
  plus ``_<n>`` when two runs started in the same second);
* it contains a ``logs/`` or ``reporting/`` subdirectory;
* nothing in it changed for :data:`MIN_AGE_SECONDS` (the folder, its ``logs/`` and
  ``reporting/`` directories and the files directly in ``logs/``).

:func:`remove_run_folder` (every delete path goes through it) additionally keeps a
folder that a dev session refers to (``DevSession.run_directory_path``, any status,
any project): a dev session's run is a fake run whose folder must survive while the
session can still be resumed. When the dev sessions cannot be read, it keeps the
folder too.

Database run paths are absolute paths from the machine the run happened on. They
are mapped by their ``run/<experiment>/<timestamp>`` tail onto the current project
root (:func:`map_db_run_path`), so a moved or renamed project still matches.
"""

import logging
import os
import re
import shutil
import stat
import time
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from pathlib import Path, PurePath

from adarelib.constants import StatusEnum

log = logging.getLogger(__name__)

#: Name of a run folder: ``ExperimentRunDirectory`` (UTC ``%Y-%m-%d_%H-%M-%S``) + ``_<n>`` suffix.
RUN_FOLDER_NAME_RE = re.compile(r'^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}(_\d+)?$')
#: A folder touched more recently than this may belong to a run still in progress.
MIN_AGE_SECONDS = 3600
#: A run folder has at least one of these (``ExperimentRunDirectory.create``).
MARKER_DIRS = ('logs', 'reporting')
RUN_DIR_NAME = 'run'
FOLDER_NOT_FOUND = 'does not exist'
_NO_RUN_DIR = 'the project has no run/ directory'
DEV_SESSION_FOLDER = 'belongs to a dev session'
#: Run statuses after which nothing writes to a run any more. Anything else (PENDING,
#: RUNNING, PAUSE, NONE, no status) may still be in progress: such runs are never cleaned up.
TERMINAL_RUN_STATUSES = frozenset(
    {
        StatusEnum.SUCCESS,
        StatusEnum.FAILED,
        StatusEnum.WARNING,
        StatusEnum.ERROR,
        StatusEnum.INTERRUPTED,
        StatusEnum.FINISHED,
        StatusEnum.TEST_MISSING,
        StatusEnum.TEST_FAILED,
    }
)


class RunReferencesUnavailableError(Exception):
    """The rows that may refer to run folders could not be read, so no folder may be deleted."""


@dataclass(frozen=True)
class DevSessionRefs:
    """Every dev session's run id (its ``session_id``) and run-folder tail, any project, any status."""

    ids: frozenset[str] = frozenset()
    tails: frozenset[tuple[str, str]] = frozenset()

    def with_run_paths(self, paths: Iterable[str | None]) -> 'DevSessionRefs':
        """These refs plus the tails of ``paths`` (the run rows of dev-session runs)."""
        extra = {tail for path in paths if path and (tail := run_tail(path)) is not None}
        return DevSessionRefs(ids=self.ids, tails=self.tails | extra)

    def refers_to(self, *, run_id: str | None = None, path: str | PurePath | None = None) -> bool:
        """True when the run ``run_id`` or the run folder ``path`` belongs to a dev session."""
        if run_id is not None and run_id in self.ids:
            return True
        return path is not None and run_tail(path) in self.tails


@dataclass(frozen=True)
class RunFolderCheck:
    """Outcome of :func:`check_run_folder`: ``resolved`` is set and ``reason`` is None when it passed."""

    path: Path
    resolved: Path | None = None
    reason: str | None = None
    last_activity: float | None = None

    @property
    def ok(self) -> bool:
        return self.reason is None


@dataclass(frozen=True)
class FolderRemoval:
    """Outcome of :func:`remove_run_folder`."""

    path: Path
    removed: bool
    reason: str | None = None
    missing: bool = False


def load_dev_session_refs() -> DevSessionRefs:
    """The :class:`DevSessionRefs` of every dev session in the global database.

    Raises:
        RunReferencesUnavailableError: The dev sessions could not be read.
    """
    from sqlalchemy import select
    from sqlalchemy.exc import SQLAlchemyError

    from adare.database.api.devmode import DevModeApi
    from adare.database.exceptions import DatabaseError
    from adare.database.models.devsession import DevSession

    try:
        with DevModeApi() as api:
            rows = api._session.execute(select(DevSession.session_id, DevSession.run_directory_path)).all()
    except (SQLAlchemyError, DatabaseError, OSError) as e:
        raise RunReferencesUnavailableError(f'the dev sessions could not be read: {e}') from e
    return DevSessionRefs(
        ids=frozenset(str(session_id) for session_id, _path in rows if session_id),
        tails=frozenset(tail for _id, path in rows if path and (tail := run_tail(path)) is not None),
    )


def try_load_dev_session_refs() -> DevSessionRefs | str:
    """:func:`load_dev_session_refs`, or why they could not be read (then no folder may be deleted)."""
    try:
        return load_dev_session_refs()
    except RunReferencesUnavailableError as e:
        log.warning('run folders kept: %s', e)
        return f'kept to be safe: {e}'


def known_experiments(project_root: Path) -> set[str]:
    """Names of the experiment directories under ``<project_root>/experiments``."""
    experiments_dir = project_root / 'experiments'
    try:
        with os.scandir(experiments_dir) as entries:
            return {entry.name for entry in entries if entry.is_dir(follow_symlinks=False)}
    except (FileNotFoundError, NotADirectoryError):
        return set()


def run_tail(db_path: str | PurePath) -> tuple[str, str] | None:
    """``(experiment, folder name)`` of a ``.../run/<experiment>/<timestamp>`` path, else None."""
    parts = PurePath(db_path).parts
    if len(parts) < 3 or parts[-3] != RUN_DIR_NAME:
        return None
    experiment, name = parts[-2], parts[-1]
    if experiment in ('.', '..') or name in ('.', '..'):
        return None
    return experiment, name


def map_db_run_path(project_root: Path, db_path: str | PurePath) -> Path | None:
    """Map a database ``run.path`` to ``<project_root>/run/<experiment>/<timestamp>``.

    Only the ``run/<experiment>/<timestamp>`` tail is kept, so a run recorded before the
    project was moved still maps into the project. None when the path has no such tail.
    """
    tail = run_tail(db_path)
    if tail is None:
        return None
    return project_root / RUN_DIR_NAME / tail[0] / tail[1]


def _mtime(path: Path) -> float | None:
    try:
        return path.lstat().st_mtime
    except OSError:
        return None


def last_activity(folder: Path) -> float:
    """Newest mtime of ``folder``, its marker directories and the entries directly in ``logs/``.

    Logs are appended while a run is in progress, which changes the files' mtime but not
    their directory's, so the files in ``logs/`` are looked at too.
    """
    times = [t for t in (_mtime(folder), *(_mtime(folder / marker) for marker in MARKER_DIRS)) if t is not None]
    try:
        with os.scandir(folder / 'logs') as entries:
            for entry in entries:
                try:
                    times.append(entry.stat(follow_symlinks=False).st_mtime)
                except OSError:
                    continue
    except OSError:
        pass
    return max(times, default=0.0)


def _refuse(path: Path, reason: str) -> RunFolderCheck:
    return RunFolderCheck(path=path, reason=reason)


def _locate(project_root: Path, path: Path) -> Path | str:
    """``path`` resolved, if it is ``run/<experiment>/<name>`` of the project without symlinks; else why not."""
    if '..' in path.parts:
        return "path contains '..'"
    try:
        run_root = (project_root / RUN_DIR_NAME).resolve(strict=True)
    except (OSError, RuntimeError):
        return _NO_RUN_DIR
    if path.is_symlink() or path.parent.is_symlink():
        return 'is a symlink or inside a symlinked directory'
    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError:
        return FOLDER_NOT_FOUND
    except (OSError, RuntimeError) as e:
        return f'cannot be resolved: {e}'
    try:
        relative = resolved.relative_to(run_root)
    except ValueError:
        return "is outside the project's run/ directory"
    if len(relative.parts) != 2:
        return 'is not at run/<experiment>/<timestamp>'
    if relative.parts != (path.parent.name, path.name):
        return 'resolves to a different folder'
    return resolved


def check_run_folder(
    project_root: Path,
    path: Path,
    *,
    experiments: Collection[str] | None = None,
    now: float | None = None,
    min_age: float = MIN_AGE_SECONDS,
) -> RunFolderCheck:
    """Decide whether ``path`` is an ADARE run folder of ``project_root`` that may be deleted.

    Args:
        project_root: The project directory (holds ``run/``).
        path: Absolute, or relative to ``project_root``.
        experiments: Experiment names ``<experiment>`` may have; defaults to
            :func:`known_experiments`.
        now: Current time (seconds since the epoch) for the age test.
        min_age: Seconds since the last change a folder must have.

    Returns:
        A :class:`RunFolderCheck`; ``reason`` says why it is refused.
    """
    path = Path(path)
    if not path.is_absolute():
        path = project_root / path
    resolved = _locate(project_root, path)
    if isinstance(resolved, str):
        return _refuse(path, resolved)
    if experiments is None:
        experiments = known_experiments(project_root)
    if resolved.parent.name not in experiments:
        return _refuse(path, f"'{resolved.parent.name}' is not a known experiment")
    if not RUN_FOLDER_NAME_RE.match(resolved.name):
        return _refuse(path, 'name is not a run timestamp')
    if not resolved.is_dir():
        return _refuse(path, 'is not a directory')
    if not any((resolved / marker).is_dir() and not (resolved / marker).is_symlink() for marker in MARKER_DIRS):
        return _refuse(path, 'has no logs/ or reporting/ subdirectory')
    activity = last_activity(resolved)
    current = time.time() if now is None else now
    if current - activity < min_age:
        return _refuse(path, f'changed less than {min_age / 3600:g} h ago')
    return RunFolderCheck(path=path, resolved=resolved, last_activity=activity)


def is_run_folder(project_root: Path, path: Path, *, experiments: Collection[str] | None = None) -> bool:
    """True when ``path`` passes :func:`check_run_folder`."""
    return check_run_folder(project_root, path, experiments=experiments).ok


def remove_run_folder(
    project_root: Path,
    path: Path,
    *,
    experiments: Collection[str] | None = None,
    now: float | None = None,
    dev_sessions: DevSessionRefs | str | None = None,
) -> FolderRemoval:
    """Delete ``path`` if it passes :func:`check_run_folder` and no dev session refers to it.

    Otherwise keep it and say why. ``dev_sessions`` are the preloaded
    :func:`try_load_dev_session_refs` (loaded here when None; a string, i.e. they
    could not be read, keeps the folder). Never raises for a refused or failed
    removal; the reason is logged and returned.
    """
    path = Path(path)
    check = check_run_folder(project_root, path, experiments=experiments, now=now)
    if not check.ok or check.resolved is None:
        missing = check.reason in (FOLDER_NOT_FOUND, _NO_RUN_DIR)
        if not missing:
            log.warning('run folder %s kept: %s', path, check.reason)
        return FolderRemoval(path=path, removed=False, reason=check.reason, missing=missing)
    refs = try_load_dev_session_refs() if dev_sessions is None else dev_sessions
    reason = refs if isinstance(refs, str) else None
    if isinstance(refs, DevSessionRefs) and (refs.refers_to(path=path) or refs.refers_to(path=check.resolved)):
        reason = DEV_SESSION_FOLDER
    if reason is not None:
        log.warning('run folder %s kept: %s', path, reason)
        return FolderRemoval(path=path, removed=False, reason=reason)
    try:
        # The validated, resolved folder; rmtree never follows symlinks inside it.
        shutil.rmtree(check.resolved)
    except OSError as e:
        log.warning('failed to delete run folder %s: %s', check.resolved, e)
        return FolderRemoval(path=path, removed=False, reason=f'delete failed: {e}')
    log.info('deleted run folder %s', check.resolved)
    return FolderRemoval(path=path, removed=True)


def remove_db_run_folders(
    project_root: Path, db_paths: Iterable[str], *, dev_sessions: DevSessionRefs | str | None = None
) -> list[FolderRemoval]:
    """Delete the folders of runs whose database rows were just deleted.

    Each ``run.path`` is mapped with :func:`map_db_run_path`; the run's database row
    vouches for its experiment name. Unmappable paths are refused, and so is every
    folder a dev session refers to (``dev_sessions`` as in :func:`remove_run_folder`,
    loaded once here when None).
    """
    db_paths = list(db_paths)
    if dev_sessions is None and db_paths:
        dev_sessions = try_load_dev_session_refs()
    removals = []
    for db_path in db_paths:
        mapped = map_db_run_path(project_root, db_path)
        if mapped is None:
            log.warning('run folder %s kept: not a run/<experiment>/<timestamp> path', db_path)
            removals.append(
                FolderRemoval(path=Path(db_path), removed=False, reason='not a run/<experiment>/<timestamp> path')
            )
            continue
        removals.append(
            remove_run_folder(project_root, mapped, experiments={mapped.parent.name}, dev_sessions=dev_sessions)
        )
    return removals


def folder_size(path: Path) -> int:
    """Bytes allocated by the files under ``path``; never follows symlinks."""
    total = 0
    stack = [str(path)]
    while stack:
        try:
            with os.scandir(stack.pop()) as entries:
                for entry in entries:
                    try:
                        info = entry.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    if stat.S_ISDIR(info.st_mode):
                        stack.append(entry.path)
                    elif stat.S_ISREG(info.st_mode):
                        blocks = getattr(info, 'st_blocks', None)
                        total += blocks * 512 if blocks is not None else info.st_size
        except OSError:
            continue
    return total


def scan_run_folders(
    project_root: Path, experiments: Collection[str], *, now: float | None = None
) -> list[RunFolderCheck]:
    """Every folder under ``<project_root>/run`` that passes :func:`check_run_folder`.

    Only ``run/<experiment>`` directories of a known experiment are looked into, and
    only their direct subdirectories are candidates; sizes are not computed here.
    """
    run_root = project_root / RUN_DIR_NAME
    found = []
    try:
        with os.scandir(run_root) as experiment_entries:
            experiment_dirs = sorted(
                entry.name
                for entry in experiment_entries
                if entry.name in experiments and entry.is_dir(follow_symlinks=False)
            )
    except OSError:
        return []
    for experiment in experiment_dirs:
        try:
            with os.scandir(run_root / experiment) as entries:
                names = sorted(
                    entry.name
                    for entry in entries
                    if RUN_FOLDER_NAME_RE.match(entry.name) and entry.is_dir(follow_symlinks=False)
                )
        except OSError:
            continue
        for name in names:
            check = check_run_folder(project_root, run_root / experiment / name, experiments=experiments, now=now)
            if check.ok:
                found.append(check)
    return found
