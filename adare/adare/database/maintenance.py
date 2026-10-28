"""Database maintenance behind ``adare db compact`` and ``adare db check``.

Both work on the SQLite files directly through raw ``sqlite3`` connections: they
never open a database API (which would create schema and run migrations), and
``check`` and ``compact --dry-run`` open the file read-only.

``compact`` removes the base64 screenshot copies that old ``action_execution``
rows carry in ``result_data`` -- new rows are stored without them
(:func:`adare.database.api.playbook.strip_bulky_values`), rows written before
that never were. Only image payloads are removed, and only when every image of
the row is byte-for-byte identical to a PNG on disk referenced by the row's
``screenshot_path`` (see :class:`_ScreenshotResolver`); any other row -- and
any other value, however large -- is left exactly as it is. The database is
then vacuumed to give the space back to the file system.

``compact`` refuses to touch a database another process may be writing to: a
held write lock, a run of the project with recent activity, or a live dev
session (see :func:`find_activity`).

``check`` runs ``PRAGMA quick_check`` and ``PRAGMA foreign_key_check`` and
counts orphaned rows.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import shutil
import sqlite3
import tempfile
import time
from collections import Counter
from collections.abc import Callable, Iterator
from contextlib import closing
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from adare.core.dto.manage import DbCheckEntry, DbCompactEntry, ForeignKeyViolationCount
from adare.database.api.base import dispose_engines
from adare.database.api.playbook import MAX_RESULT_STRING, is_image_payload, omitted_image_marker
from adare.database.migrations.delete_orphan_run_rows import (
    _DELETE_ORPHAN_EXECUTIONS,
    _DELETE_ORPHAN_FILES,
    _DELETE_ORPHAN_LOG_FILES,
)

log = logging.getLogger(__name__)

#: How long ``compact`` waits for another process's write lock before it calls the database in use.
LOCK_TIMEOUT_SECONDS = 2.0
#: Busy timeout once ``compact`` runs: a short competing write between batches is waited for.
WORK_BUSY_TIMEOUT_MS = 30_000
#: Rows rewritten (and committed) per batch; bounds memory and the size of the WAL.
BATCH_SIZE = 200
#: Rows whose ``result_data`` is not longer than this are not worth decoding.
PREFILTER_MIN_LENGTH = MAX_RESULT_STRING
#: A run or dev session that showed activity this recently may still write to the database.
ACTIVITY_WINDOW_SECONDS = 30 * 60
#: Run statuses (``StatusEnum`` names, as SQLAlchemy stores them) of runs that have not ended.
NON_TERMINAL_RUN_STATUSES = ('RUNNING', 'PENDING', 'PAUSE')
#: VACUUM needs free space of this many times the live data (temporary copy + WAL, 10 % margin).
VACUUM_SPACE_FACTOR = 2.2
#: Prefix of the marker an image's base64 data is replaced with (already stripped = not an image).
_OMITTED_PREFIX = '<omitted: '
_COMPARE_CHUNK = 1024 * 1024

_RUN_ORPHAN_TABLES = frozenset({'experiment_run', 'action_execution', 'experiment_run_files', 'log_file'})


def _count_sql(delete_sql: str) -> str:
    """``DELETE FROM t WHERE ...`` -> ``SELECT COUNT(*) FROM t WHERE ...``."""
    statement = delete_sql.strip()
    if not statement.startswith('DELETE FROM'):
        raise ValueError(f'not a DELETE statement: {statement[:40]!r}')
    return 'SELECT COUNT(*) FROM' + statement[len('DELETE FROM') :]


#: Orphan counts reported by ``check``, as ``name -> (count SQL, tables it needs)``:
#:
#: - the executions, files and log rows the ``delete_orphan_run_rows`` migration deletes (its
#:   SQL, counted): leftovers of runs deleted by older versions;
#: - executions whose playbook item is gone (``PlaybookApi`` replaces an experiment's items
#:   when the experiment is loaded again).
ORPHAN_QUERIES: dict[str, tuple[str, frozenset[str]]] = {
    'action_execution_without_run': (_count_sql(_DELETE_ORPHAN_EXECUTIONS), _RUN_ORPHAN_TABLES),
    'experiment_run_files_unreferenced': (_count_sql(_DELETE_ORPHAN_FILES), _RUN_ORPHAN_TABLES),
    'log_file_unreferenced': (_count_sql(_DELETE_ORPHAN_LOG_FILES), _RUN_ORPHAN_TABLES),
    'action_execution_dangling_playbook_item': (
        'SELECT COUNT(*) FROM action_execution WHERE playbook_item_id NOT IN (SELECT id FROM playbook_item)',
        frozenset({'action_execution', 'playbook_item'}),
    ),
}

#: Progress callback: (rowid reached, highest rowid).
Progress = Callable[[int, int], None]


class DatabaseInUseError(Exception):
    """Another connection holds the write lock of a database ``compact`` was asked to change."""


@dataclass(frozen=True)
class DatabaseTarget:
    """A database file to maintain; ``project_path`` is None for the global database."""

    label: str
    db_path: Path
    project_path: Path | None = None


# =============================================================================
# Targets
# =============================================================================


def global_target() -> DatabaseTarget:
    """The global database."""
    from adare.config.database import get_global_database_location

    return DatabaseTarget('global', get_global_database_location())


def project_target(project_path: Path, label: str | None = None) -> DatabaseTarget:
    """The database of the project at ``project_path``; nothing is created on disk."""
    from adare.config.database import get_project_database_location

    return DatabaseTarget(
        label or project_path.name, get_project_database_location(project_path, create=False), project_path
    )


def all_targets() -> list[DatabaseTarget]:
    """The global database and the database of every registered project.

    Same set ``adare db migrate`` walks (:func:`adare.database.init.migrate_database_system`).
    A project whose directory or database file is gone is still listed; ``compact`` and
    ``check`` report it as ``missing``.
    """
    from adare.database.api.base import GlobalDatabaseApi
    from adare.database.models.global_models import Project

    with GlobalDatabaseApi() as api:
        projects = [(str(p.name or ''), Path(p.path)) for p in api._session.query(Project).all() if p.path]
    targets = [global_target()]
    targets.extend(project_target(path, name or None) for name, path in projects)
    return targets


def _default_global_db_path() -> Path | None:
    """The global database file, or None when the config directory is not set up."""
    from adare.config.database import get_global_database_location
    from adare.config.exceptions import ConfigDirectoryError

    try:
        return Path(get_global_database_location())
    except ConfigDirectoryError:
        return None


def _missing_reason(target: DatabaseTarget) -> str | None:
    """Why the target's database cannot be found, or None when its file exists."""
    if target.project_path is not None and not target.project_path.is_dir():
        return f'project directory {target.project_path} not found'
    if not target.db_path.is_file():
        return 'no database file'
    return None


# =============================================================================
# Connections and sizes
# =============================================================================


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except FileNotFoundError:
        return 0


def database_sizes(db_path: Path) -> tuple[int, int]:
    """Sizes in bytes of the database file and its ``-wal`` file (0 when absent)."""
    return _file_size(db_path), _file_size(db_path.with_name(db_path.name + '-wal'))


def open_read_only(db_path: Path) -> sqlite3.Connection:
    """Read-only connection that never writes to the database file.

    A WAL database needs its ``-shm`` index even to read; SQLite creates it (and
    an empty ``-wal``) next to the file when it can. Where it cannot and there is
    no WAL content to miss, the file is opened ``immutable`` instead.
    """
    uri = f'{db_path.resolve().as_uri()}?mode=ro'
    conn = sqlite3.connect(uri, uri=True)
    try:
        conn.execute('SELECT COUNT(*) FROM sqlite_master').fetchone()
        return conn
    except sqlite3.OperationalError as e:
        conn.close()
        wal_bytes = database_sizes(db_path)[1]
        if 'unable to open' not in str(e) or wal_bytes:
            raise
        log.debug('read-only open of %s failed (%s); retrying immutable', db_path, e)
        return sqlite3.connect(f'{uri}&immutable=1', uri=True)


def _open_for_writing(db_path: Path) -> sqlite3.Connection:
    """Autocommit connection holding no lock yet; raises DatabaseInUseError when it cannot get one.

    ``BEGIN IMMEDIATE`` with a short timeout is the probe: it fails while another
    connection writes. The probe transaction is rolled back right away.
    """
    conn = sqlite3.connect(db_path, timeout=LOCK_TIMEOUT_SECONDS, isolation_level=None)
    try:
        conn.execute('BEGIN IMMEDIATE')
        conn.execute('ROLLBACK')
    except sqlite3.OperationalError as e:
        conn.close()
        if _is_busy(e):
            raise DatabaseInUseError(str(e)) from e
        raise
    conn.execute(f'PRAGMA busy_timeout={WORK_BUSY_TIMEOUT_MS}')
    conn.execute('PRAGMA synchronous=NORMAL')
    return conn


def _is_busy(error: sqlite3.OperationalError) -> bool:
    message = str(error).lower()
    return 'locked' in message or 'busy' in message


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


def _length_function(conn: sqlite3.Connection) -> str:
    """``octet_length`` (SQLite >= 3.43) reads a value's size without loading it; ``length`` otherwise."""
    try:
        conn.execute('SELECT octet_length(NULL)').fetchone()
        return 'octet_length'
    except sqlite3.OperationalError:
        return 'length'


# =============================================================================
# Screenshot resolution
# =============================================================================


def _resolve_run_dir(stored: str | None, project_root: Path) -> Path | None:
    """The run directory of a stored ``experiment_run.path``, under the *current* project root.

    Run paths are stored absolute (``<project>/run/<experiment>/<timestamp>``, diff
    runs under ``diff/``). A project that was moved still has the old prefix, so a
    path outside the project root is rebased by its last three parts.
    """
    if not stored:
        return None
    path = Path(stored)
    if not path.is_absolute():
        return project_root / path
    if path.is_relative_to(project_root):
        return path
    parts = path.parts
    if len(parts) >= 3 and parts[-3] in ('run', 'diff'):
        return project_root.joinpath(*parts[-3:])
    return None


class _ScreenshotResolver:
    """Resolves a row's ``screenshot_path`` to a file on disk.

    ``screenshot_path`` is a key of ``result_data`` written next to the image by the
    screenshot / wait / find actions. Its value is relative to the run directory
    (``reporting/screenshots/<file>.png``); absolute values are taken as they are.
    Relative ones are tried under the run directory, then under the project root.
    A path that does not resolve to an existing file counts as missing.
    """

    def __init__(self, conn: sqlite3.Connection, project_root: Path | None, tables: set[str]) -> None:
        self._project_root = project_root
        self._run_paths: dict[str, str | None] = {}
        if 'experiment_run' in tables:
            self._run_paths = {row[0]: row[1] for row in conn.execute('SELECT id, path FROM experiment_run')}
        self._run_dirs: dict[str, Path | None] = {}

    def _run_dir(self, run_id: str | None) -> Path | None:
        if run_id is None or self._project_root is None:
            return None
        if run_id not in self._run_dirs:
            self._run_dirs[run_id] = _resolve_run_dir(self._run_paths.get(run_id), self._project_root)
        return self._run_dirs[run_id]

    def resolve(self, screenshot_path: str, run_id: str | None) -> Path | None:
        path = Path(screenshot_path)
        candidates = [path] if path.is_absolute() else []
        if not path.is_absolute():
            run_dir = self._run_dir(run_id)
            if run_dir is not None:
                candidates.append(run_dir / path)
            if self._project_root is not None:
                candidates.append(self._project_root / path)
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        return None


# =============================================================================
# Is the database in use?
# =============================================================================


@dataclass
class Activity:
    """What may write to a database: ``active`` describes each blocker; ``stale_runs`` were ignored."""

    active: list[str] = field(default_factory=list)
    stale_runs: int = 0


def _timestamp(value: Any) -> float | None:
    """POSIX time of a stored DateTime (naive values are UTC, as adare writes them); None if unreadable."""
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.timestamp()


def _ago(timestamp: float, now: float) -> str:
    minutes = int((now - timestamp) // 60)
    return 'just now' if minutes < 1 else f'{minutes} min ago'


def _run_last_activity(path: str | None, times: tuple[Any, ...], project_root: Path) -> float | None:
    """Newest of the run's stored times and its folder's activity (``logs/`` files, folder mtime)."""
    from adare.backend.experiment.run_folders import last_activity

    candidates = [t for t in (_timestamp(value) for value in times) if t is not None]
    run_dir = _resolve_run_dir(path, project_root)
    if run_dir is not None and run_dir.is_dir():
        candidates.append(last_activity(run_dir))
    return max(candidates, default=None)


def _run_activity(conn: sqlite3.Connection, project_root: Path, now: float, activity: Activity) -> None:
    """Non-terminal runs with activity within :data:`ACTIVITY_WINDOW_SECONDS` block; older ones are stale."""
    tables = _tables(conn)
    if 'experiment_run' not in tables:
        return
    experiment = 'e.name' if 'experiment' in tables else 'NULL'
    join = 'LEFT JOIN experiment e ON e.id = r.experiment_id ' if 'experiment' in tables else ''
    placeholders = ', '.join('?' * len(NON_TERMINAL_RUN_STATUSES))
    query = (
        f'SELECT r.id, r.path, r.status, r.start_time, r.created_at, {experiment} '
        f'FROM experiment_run r {join}WHERE r.status IN ({placeholders})'
    )
    cutoff = now - ACTIVITY_WINDOW_SECONDS
    for run_id, path, status, start_time, created_at, experiment_name in conn.execute(
        query, NON_TERMINAL_RUN_STATUSES
    ).fetchall():
        last = _run_last_activity(path, (start_time, created_at), project_root)
        if last is None or last < cutoff:
            activity.stale_runs += 1
            continue
        activity.active.append(
            f"run {run_id} of experiment '{experiment_name or '?'}' ({status}, last activity {_ago(last, now)})"
        )


def _dev_session_vm_alive(conn: sqlite3.Connection, environment_name: str, vm_name: str, tables: set[str]) -> bool:
    """Is the dev session's VM running? Asks the hypervisor, like ``adare dev cleanup`` does.

    The hypervisor is read from the global database's ``environment`` table (by
    ULID or name) with plain SQL, so no database API is opened; dev mode runs on
    QEMU, which is assumed when the environment is gone.
    """
    from adare.backend.devmode.vm_state_checker import is_vm_running

    row = None
    if 'environment' in tables:
        row = conn.execute(
            'SELECT hypervisor FROM environment WHERE id = ? OR name = ? LIMIT 1', (environment_name, environment_name)
        ).fetchone()
    return is_vm_running(vm_name, row[0] if row and row[0] else 'qemu')


def _dev_session_activity(global_db_path: Path | None, now: float, activity: Activity) -> None:
    """Dev sessions marked running whose VM is alive (or that changed state within the window) block."""
    if global_db_path is None or not global_db_path.is_file():
        return
    cutoff = now - ACTIVITY_WINDOW_SECONDS
    with closing(open_read_only(global_db_path)) as conn:
        tables = _tables(conn)
        if 'dev_sessions' not in tables:
            return
        rows = conn.execute(
            'SELECT session_id, name, project_path, environment_name, vm_name, updated_at '
            "FROM dev_sessions WHERE status = 'running'"
        ).fetchall()
        for session_id, name, project_path, environment_name, vm_name, updated_at in rows:
            updated = _timestamp(updated_at)
            recent = updated is not None and updated >= cutoff
            if not recent and not _dev_session_vm_alive(conn, environment_name, vm_name, tables):
                continue
            label = f"'{name}' ({session_id})" if name else session_id
            activity.active.append(f'dev session {label} of {project_path} (VM {vm_name})')


def find_activity(target: DatabaseTarget, global_db_path: Path | None, now: float | None = None) -> Activity:
    """What may write to ``target`` while ``compact`` runs.

    - a run of the project whose status has not ended (``RUNNING``, ``PENDING``,
      ``PAUSE``) and that shows activity within the last 30 minutes: its start or
      creation time, or the mtime of its run folder and the files in ``logs/``. A
      run without such activity was left behind by a crash and counts as stale;
    - for every database: a dev session marked running whose VM is alive or whose
      state changed within the last 30 minutes.
    """
    now = time.time() if now is None else now
    activity = Activity()
    if target.project_path is not None:
        with closing(open_read_only(target.db_path)) as conn:
            _run_activity(conn, target.project_path, now, activity)
    _dev_session_activity(global_db_path, now, activity)
    return activity


def _stale_note(stale_runs: int) -> str:
    return (
        f'{stale_runs} unfinished run(s) without activity in the last {ACTIVITY_WINDOW_SECONDS // 60} min '
        'were taken as stale (crashed) and ignored'
    )


def _in_use_message(activity: Activity) -> str:
    message = (
        'database is in use: ' + '; '.join(activity.active) + '. Nothing was changed. '
        'Let the run finish (or stop the dev session with `adare dev stop`), then try again.'
    )
    if activity.stale_runs:
        message += f' ({_stale_note(activity.stale_runs)})'
    return message


# =============================================================================
# Row planning
# =============================================================================


@dataclass
class _Bulk:
    """The bulky content of one decoded ``result_data`` value."""

    images: list[str] = field(default_factory=list)
    oversized_strings: int = 0
    screenshot_paths: list[str] = field(default_factory=list)


def _is_image(container: dict, key: Any, item: Any) -> bool:
    """An image payload that still holds its data (not yet replaced by the omitted marker)."""
    return is_image_payload(container, key, item) and not item.startswith(_OMITTED_PREFIX)


def _collect(value: Any, bulk: _Bulk) -> None:
    """Record the images, screenshot paths and oversized non-image strings of ``value``."""
    if isinstance(value, dict):
        for key, item in value.items():
            if is_image_payload(value, key, item):
                if not item.startswith(_OMITTED_PREFIX):
                    bulk.images.append(item)
                continue
            if key == 'screenshot_path' and isinstance(item, str) and item:
                bulk.screenshot_paths.append(item)
            _collect(item, bulk)
    elif isinstance(value, list | tuple):
        for item in value:
            _collect(item, bulk)
    elif isinstance(value, str) and len(value) > MAX_RESULT_STRING:
        bulk.oversized_strings += 1


def strip_images(value: Any) -> Any:
    """Copy of an action result with only the image payloads replaced by the omitted marker.

    The marker is the one :func:`~adare.database.api.playbook.strip_bulky_values`
    writes for new rows; every other value, however large, is kept as it is.
    """
    if isinstance(value, dict):
        return {
            key: omitted_image_marker(item, value['format']) if _is_image(value, key, item) else strip_images(item)
            for key, item in value.items()
        }
    if isinstance(value, list | tuple):
        return [strip_images(item) for item in value]
    return value


def _base64_decoded_size(data: str) -> int | None:
    """Byte length ``data`` decodes to, or None when it is not plain padded base64."""
    if not data or len(data) % 4:
        return None
    padding = 2 if data.endswith('==') else 1 if data.endswith('=') else 0
    return len(data) // 4 * 3 - padding


def _decode_image(data: str) -> bytes | None:
    try:
        return base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError):
        return None


def _file_equals(path: Path, expected: bytes) -> bool:
    """True when the file at ``path`` holds exactly ``expected``; compared in chunks.

    Slices of ``bytes`` compare with memcmp; a ``memoryview`` compares element by element (~20x slower).
    """
    offset = 0
    try:
        with path.open('rb') as handle:
            while chunk := handle.read(_COMPARE_CHUNK):
                if expected[offset : offset + len(chunk)] != chunk:
                    return False
                offset += len(chunk)
    except OSError:
        return False
    return offset == len(expected)


def _verify_images(bulk: _Bulk, run_id: str | None, resolver: _ScreenshotResolver) -> str:
    """``ok`` when every image equals a referenced file byte for byte; else ``missing`` or ``mismatch``.

    The decoded size is compared first (cheap); only a file of the right size is
    read and compared with the decoded image.
    """
    sizes: dict[Path, int] = {}
    for screenshot_path in bulk.screenshot_paths:
        resolved = resolver.resolve(screenshot_path, run_id)
        if resolved is None:
            continue
        try:
            sizes[resolved] = resolved.stat().st_size
        except OSError:
            continue
    if not sizes:
        return 'missing'
    for image in bulk.images:
        if _base64_decoded_size(image) not in sizes.values():
            return 'mismatch'
        decoded = _decode_image(image)
        if decoded is None:
            return 'mismatch'
        if not any(size == len(decoded) and _file_equals(path, decoded) for path, size in sizes.items()):
            return 'mismatch'
    return 'ok'


@dataclass
class _Tally:
    examined: int = 0
    stripped: int = 0
    kept_missing_file: int = 0
    kept_mismatch: int = 0
    non_image_kept: int = 0
    reclaimable_bytes: int = 0
    undecodable: int = 0


def _plan_row(raw: str | bytes | None, run_id: str | None, resolver: _ScreenshotResolver, tally: _Tally) -> str | None:
    """New ``result_data`` text for one row, or None to leave the row unchanged."""
    tally.examined += 1
    if raw is None:
        return None
    try:
        value = json.loads(raw)
    except (ValueError, TypeError):
        tally.undecodable += 1
        return None
    bulk = _Bulk()
    _collect(value, bulk)
    if bulk.oversized_strings:
        tally.non_image_kept += 1
    if not bulk.images:
        return None
    verdict = _verify_images(bulk, run_id, resolver)
    if verdict == 'missing':
        tally.kept_missing_file += 1
        return None
    if verdict == 'mismatch':
        tally.kept_mismatch += 1
        return None
    # Serialised like SQLAlchemy's JSON type writes it (json.dumps defaults).
    new_text = json.dumps(strip_images(value))
    old_length = len(raw)
    if len(new_text) >= old_length:
        return None
    tally.reclaimable_bytes += old_length - len(new_text)
    tally.stripped += 1
    return new_text


def _candidate_batches(
    conn: sqlite3.Connection, length_fn: str, begin: Callable[[], None]
) -> Iterator[list[tuple[int, str | None, Any]]]:
    """Batches of ``(rowid, experiment_run_id, result_data)`` worth decoding, in rowid order.

    ``begin`` runs before each batch is read, so a writer reads and rewrites a
    batch inside one transaction. Small rows are filtered out in SQL and never loaded.
    """
    query = (
        'SELECT rowid, experiment_run_id, result_data FROM action_execution '
        f'WHERE rowid > ? AND {length_fn}(result_data) > ? ORDER BY rowid LIMIT ?'
    )
    last_rowid = 0
    while True:
        begin()
        rows = conn.execute(query, (last_rowid, PREFILTER_MIN_LENGTH, BATCH_SIZE)).fetchall()
        if not rows:
            return
        yield rows
        last_rowid = rows[-1][0]


# =============================================================================
# compact
# =============================================================================


def _scan(
    conn: sqlite3.Connection,
    project_root: Path | None,
    *,
    write: bool,
    progress: Progress | None,
) -> _Tally:
    """Plan (and, with ``write``, apply) the row rewrite; one committed transaction per batch."""
    tally = _Tally()
    tables = _tables(conn)
    if 'action_execution' not in tables:
        return tally
    resolver = _ScreenshotResolver(conn, project_root, tables)
    length_fn = _length_function(conn)
    max_rowid = conn.execute('SELECT COALESCE(MAX(rowid), 0) FROM action_execution').fetchone()[0]

    def begin() -> None:
        if write:
            conn.execute('BEGIN IMMEDIATE')

    batches = _candidate_batches(conn, length_fn, begin)
    try:
        for rows in batches:
            updates = []
            for rowid, run_id, raw in rows:
                new_text = _plan_row(raw, run_id, resolver, tally)
                if new_text is not None:
                    updates.append((new_text, rowid))
            if write:
                if updates:
                    conn.executemany('UPDATE action_execution SET result_data = ? WHERE rowid = ?', updates)
                conn.execute('COMMIT')
            if progress is not None:
                progress(rows[-1][0], max_rowid)
        if write:
            conn.execute('COMMIT')  # the transaction opened by the final, empty read
    except sqlite3.Error:
        if write and conn.in_transaction:
            conn.execute('ROLLBACK')
        raise
    if tally.undecodable:
        log.warning('%d action_execution row(s) hold result_data that is not JSON; left unchanged', tally.undecodable)
    return tally


def _free_pages_bytes(conn: sqlite3.Connection) -> int:
    page_size = conn.execute('PRAGMA page_size').fetchone()[0]
    free_pages = conn.execute('PRAGMA freelist_count').fetchone()[0]
    return int(page_size) * int(free_pages)


def _live_bytes(conn: sqlite3.Connection) -> int:
    """Bytes of the pages in use: ``(page_count - freelist_count) * page_size``."""
    page_size = conn.execute('PRAGMA page_size').fetchone()[0]
    page_count = conn.execute('PRAGMA page_count').fetchone()[0]
    free_pages = conn.execute('PRAGMA freelist_count').fetchone()[0]
    return int(page_size) * (int(page_count) - int(free_pages))


def _space_shortfall(db_path: Path, needed: int) -> str | None:
    """Why VACUUM must not run for lack of space, or None when every volume it writes to has ``needed``.

    VACUUM writes a temporary copy of the database (in the temporary directory)
    and, in WAL mode, pushes the whole content through the ``-wal`` next to the file.
    """
    directories = [db_path.parent]
    temp_dir = Path(tempfile.gettempdir())
    if not _same_volume(db_path.parent, temp_dir):
        directories.append(temp_dir)
    for directory in directories:
        try:
            free = shutil.disk_usage(directory).free
        except OSError as e:
            return f'unknown bytes free in {directory} ({e})'
        if free < needed:
            return f'{free} bytes free in {directory}'
    return None


def _same_volume(first: Path, second: Path) -> bool:
    try:
        return first.stat().st_dev == second.stat().st_dev
    except OSError as e:
        log.debug('cannot compare the volumes of %s and %s: %s', first, second, e)
        return False


def _checkpoint_quietly(conn: sqlite3.Connection) -> None:
    """Truncate the ``-wal`` after a failed VACUUM so it does not stay large."""
    try:
        conn.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()
    except sqlite3.OperationalError as e:
        log.debug('WAL checkpoint after the failed VACUUM failed: %s', e)


def _vacuum(conn: sqlite3.Connection, db_path: Path, entry: DbCompactEntry) -> None:
    """Checkpoint, check free space, VACUUM, checkpoint again (so the ``-wal`` shrinks too)."""
    dispose_engines()  # this process's pooled connections must not pin the WAL
    conn.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()
    needed = int(_live_bytes(conn) * VACUUM_SPACE_FACTOR)
    shortfall = _space_shortfall(db_path, needed)
    if shortfall is not None:
        entry.vacuum_message = (
            f'VACUUM skipped: it needs {needed} bytes free (twice the live data plus 10 %) next to the '
            f'database and in the temporary directory, but there are {shortfall}. '
            'The row rewrite is kept; free some space and run `adare db compact` again.'
        )
        return
    try:
        conn.execute('VACUUM')
    except sqlite3.OperationalError as e:
        entry.vacuum_message = f'VACUUM failed: {e} (the row rewrite is kept)'
        _checkpoint_quietly(conn)
        return
    busy, _log_pages, _checkpointed = conn.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()
    entry.vacuumed = True
    if busy:
        entry.vacuum_message = 'VACUUM done, but another connection kept the WAL from being truncated'


def compact_database(
    target: DatabaseTarget,
    *,
    dry_run: bool = False,
    progress: Progress | None = None,
    global_db_path: Path | None = None,
) -> DbCompactEntry:
    """Strip image copies from old ``action_execution`` rows and VACUUM one database.

    With ``dry_run`` the file is opened read-only and nothing is written; the entry
    reports what would be removed. Expected failures (database in use, unreadable
    file) are reported in the entry's ``status``/``message`` instead of raised.
    ``global_db_path`` is where live dev sessions are looked up (default: the global database).
    """
    started = time.monotonic()
    db_path = target.db_path
    entry = DbCompactEntry(label=target.label, path=db_path, status='dry-run' if dry_run else 'compacted')
    entry.size_before, entry.wal_size_before = database_sizes(db_path)
    missing = _missing_reason(target)
    if missing is not None:
        entry.status, entry.message = 'missing', missing
        return entry

    try:
        activity = find_activity(target, global_db_path or _default_global_db_path())
        entry.stale_runs_ignored = activity.stale_runs
        if activity.active and not dry_run:
            entry.status, entry.message = 'in-use', _in_use_message(activity)
            return _finish(entry, started)
        if dry_run:
            with closing(open_read_only(db_path)) as conn:
                tally = _scan(conn, target.project_path, write=False, progress=progress)
                entry.free_pages_bytes = _free_pages_bytes(conn)
        else:
            dispose_engines()
            with closing(_open_for_writing(db_path)) as conn:
                tally = _scan(conn, target.project_path, write=True, progress=progress)
                entry.free_pages_bytes = _free_pages_bytes(conn)
                _vacuum(conn, db_path, entry)
    except DatabaseInUseError:
        entry.status = 'in-use'
        entry.message = (
            'database is in use by another process (could not get the write lock within '
            f'{LOCK_TIMEOUT_SECONDS:g} s); nothing was changed. Stop running experiments, '
            'dev sessions and `adare ui`, then try again.'
        )
        return _finish(entry, started)
    except sqlite3.Error as e:
        entry.status, entry.message = 'error', f'{type(e).__name__}: {e}'
        if not dry_run:
            entry.message += ' (batches committed before the error stay compacted; running again resumes)'
        return _finish(entry, started)

    notes = []
    if activity.active:
        notes.append('compact would refuse now, the database is in use: ' + '; '.join(activity.active))
    if activity.stale_runs:
        notes.append(_stale_note(activity.stale_runs))
    entry.message = '; '.join(notes) or None
    entry.rows_examined = tally.examined
    entry.rows_stripped = tally.stripped
    entry.rows_kept_missing_file = tally.kept_missing_file
    entry.rows_kept_mismatch = tally.kept_mismatch
    entry.rows_non_image_kept = tally.non_image_kept
    entry.reclaimable_bytes = tally.reclaimable_bytes
    return _finish(entry, started)


def _finish(entry: DbCompactEntry, started: float) -> DbCompactEntry:
    entry.size_after, entry.wal_size_after = database_sizes(entry.path)
    entry.duration_seconds = time.monotonic() - started
    return entry


# =============================================================================
# check
# =============================================================================


def _foreign_key_summary(conn: sqlite3.Connection) -> list[ForeignKeyViolationCount]:
    """``PRAGMA foreign_key_check`` counted per (table, parent); works with foreign_keys off."""
    counts: Counter[tuple[str, str]] = Counter()
    for table, _rowid, parent, _fkid in conn.execute('PRAGMA foreign_key_check'):
        counts[(table, parent)] += 1
    return [ForeignKeyViolationCount(table, parent, count) for (table, parent), count in sorted(counts.items())]


def _orphan_counts(conn: sqlite3.Connection) -> dict[str, int]:
    tables = _tables(conn)
    counts = {}
    for name, (sql, required) in ORPHAN_QUERIES.items():
        if required <= tables:
            counts[name] = int(conn.execute(sql).fetchone()[0])
    return counts


def check_database(target: DatabaseTarget) -> DbCheckEntry:
    """Read-only health check of one database: quick_check, foreign keys, orphaned rows."""
    db_path = target.db_path
    entry = DbCheckEntry(label=target.label, path=db_path, integrity_ok=True)
    missing = _missing_reason(target)
    if missing is not None:
        entry.status, entry.message = 'missing', missing
        return entry
    try:
        with closing(open_read_only(db_path)) as conn:
            results = [str(row[0]) for row in conn.execute('PRAGMA quick_check')]
            if results != ['ok']:
                entry.integrity_ok = False
                entry.problems = results
            # Both below read every table: on a damaged file they may fail, which
            # the integrity result already reports.
            entry.foreign_key_violations = _foreign_key_summary(conn)
            entry.orphans = _orphan_counts(conn)
    except sqlite3.DatabaseError as e:
        entry.problems.append(f'{type(e).__name__}: {e}')
        entry.integrity_ok = False
    return entry
