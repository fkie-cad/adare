"""Database maintenance behind ``adare db compact`` and ``adare db check``.

Both work on the SQLite files directly through raw ``sqlite3`` connections: they
never open a database API (which would create schema and run migrations), and
``check`` and ``compact --dry-run`` open the file read-only.

``compact`` removes the base64 screenshot copies that old ``action_execution``
rows carry in ``result_data`` -- new rows are stored without them
(:func:`adare.database.api.playbook.strip_bulky_values`), rows written before
that never were. A row's image data is removed only when every image in it has
a matching PNG on disk, referenced by the row's ``screenshot_path`` (see
:class:`_ScreenshotResolver`); otherwise the row is left byte-for-byte as it
is. The database is then vacuumed to give the space back to the file system.

``check`` runs ``PRAGMA quick_check`` and ``PRAGMA foreign_key_check`` and
counts the orphaned rows earlier run deletions left behind.
"""

from __future__ import annotations

import json
import logging
import shutil
import sqlite3
import time
from collections import Counter
from collections.abc import Callable, Iterator
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from adare.core.dto.manage import DbCheckEntry, DbCompactEntry, ForeignKeyViolationCount
from adare.database.api.base import dispose_engines
from adare.database.api.playbook import MAX_RESULT_STRING, strip_bulky_values
from adare.database.migrations.delete_orphan_run_rows import (
    _DELETE_ORPHAN_ACTION_EXECUTIONS,
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
#: Rows whose ``result_data`` is not longer than this cannot hold anything to strip.
PREFILTER_MIN_LENGTH = MAX_RESULT_STRING

_RUN_ORPHAN_TABLES = frozenset({'experiment_run', 'action_execution', 'experiment_run_files', 'log_file'})


def _count_sql(delete_sql: str) -> str:
    """``DELETE FROM t WHERE ...`` -> ``SELECT COUNT(*) FROM t WHERE ...``."""
    statement = delete_sql.strip()
    if not statement.startswith('DELETE FROM'):
        raise ValueError(f'not a DELETE statement: {statement[:40]!r}')
    return 'SELECT COUNT(*) FROM' + statement[len('DELETE FROM') :]


#: Orphan counts reported by ``check``, as ``name -> (count SQL, tables it needs)``: the
#: row sets the ``delete_orphan_run_rows`` migration deletes (its SQL, counted instead
#: of deleted), plus executions whose playbook item is gone (``PlaybookApi`` replaces
#: an experiment's items when the experiment is loaded again).
ORPHAN_QUERIES: dict[str, tuple[str, frozenset[str]]] = {
    'action_execution_without_run': (_count_sql(_DELETE_ORPHAN_ACTION_EXECUTIONS), _RUN_ORPHAN_TABLES),
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
    """The database of the project at ``project_path``."""
    from adare.config.database import get_project_database_location

    return DatabaseTarget(label or project_path.name, get_project_database_location(project_path), project_path)


def all_targets() -> list[DatabaseTarget]:
    """The global database and the database of every registered project that exists on disk.

    Same set ``adare db migrate`` walks (:func:`adare.database.init.migrate_database_system`).
    """
    from adare.database.api.base import GlobalDatabaseApi
    from adare.database.models.global_models import Project

    with GlobalDatabaseApi() as api:
        projects = [(str(p.name or ''), Path(p.path)) for p in api._session.query(Project).all() if p.path]
    targets = [global_target()]
    targets.extend(project_target(path, name or None) for name, path in projects if path.exists())
    return targets


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
# Row planning
# =============================================================================


@dataclass
class _Bulk:
    """The bulky content of one decoded ``result_data`` value."""

    images: list[str] = field(default_factory=list)
    oversized_strings: int = 0
    screenshot_paths: list[str] = field(default_factory=list)


def _collect(value: Any, bulk: _Bulk) -> None:
    """Walk ``value`` the way :func:`strip_bulky_values` does, recording what it would remove."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key == 'data' and isinstance(item, str) and 'format' in value:
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


def _base64_decoded_size(data: str) -> int | None:
    """Byte length ``data`` decodes to, or None when it is not plain padded base64."""
    if not data or len(data) % 4:
        return None
    padding = 2 if data.endswith('==') else 1 if data.endswith('=') else 0
    return len(data) // 4 * 3 - padding


def _images_on_disk(bulk: _Bulk, run_id: str | None, resolver: _ScreenshotResolver) -> bool:
    """True when every image of the row has a referenced file on disk of exactly its decoded size."""
    sizes = set()
    for screenshot_path in bulk.screenshot_paths:
        resolved = resolver.resolve(screenshot_path, run_id)
        if resolved is not None:
            sizes.add(resolved.stat().st_size)
    if not sizes:
        return False
    return all(_base64_decoded_size(image) in sizes for image in bulk.images)


@dataclass
class _Tally:
    examined: int = 0
    stripped: int = 0
    kept_missing_file: int = 0
    non_image_stripped: int = 0
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
    if bulk.images:
        if not _images_on_disk(bulk, run_id, resolver):
            tally.kept_missing_file += 1
            return None
    elif not bulk.oversized_strings:
        return None
    # Serialised like SQLAlchemy's JSON type writes it (json.dumps defaults).
    new_text = json.dumps(strip_bulky_values(value))
    old_length = len(raw)
    if len(new_text) >= old_length:
        return None
    tally.reclaimable_bytes += old_length - len(new_text)
    if bulk.images:
        tally.stripped += 1
    else:
        tally.non_image_stripped += 1
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


def _vacuum(conn: sqlite3.Connection, db_path: Path, entry: DbCompactEntry) -> None:
    """Checkpoint, check free space, VACUUM, checkpoint again (so the ``-wal`` shrinks too).

    In WAL mode VACUUM builds the new database in a temporary file and writes it
    back through the WAL, so it needs about the database's size in free space.
    """
    dispose_engines()  # this process's pooled connections must not pin the WAL
    conn.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()
    db_size = database_sizes(db_path)[0]
    free = shutil.disk_usage(db_path.parent).free
    if free < db_size:
        entry.vacuum_message = (
            f'VACUUM skipped: it needs {db_size} bytes free next to the database, only {free} are available. '
            'The row rewrite is kept; free some space and run `adare db compact` again.'
        )
        return
    try:
        conn.execute('VACUUM')
    except sqlite3.OperationalError as e:
        entry.vacuum_message = f'VACUUM failed: {e} (the row rewrite is kept)'
        return
    busy, _log_pages, _checkpointed = conn.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()
    entry.vacuumed = True
    if busy:
        entry.vacuum_message = 'VACUUM done, but another connection kept the WAL from being truncated'


def compact_database(
    target: DatabaseTarget, *, dry_run: bool = False, progress: Progress | None = None
) -> DbCompactEntry:
    """Strip image copies from old ``action_execution`` rows and VACUUM one database.

    With ``dry_run`` the file is opened read-only and nothing is written; the entry
    reports what would be removed. Expected failures (database in use, unreadable
    file) are reported in the entry's ``status``/``message`` instead of raised.
    """
    started = time.monotonic()
    db_path = target.db_path
    entry = DbCompactEntry(label=target.label, path=db_path, status='dry-run' if dry_run else 'compacted')
    entry.size_before, entry.wal_size_before = database_sizes(db_path)
    if not db_path.is_file():
        entry.status, entry.message = 'missing', 'no database file'
        return entry

    try:
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

    entry.rows_examined = tally.examined
    entry.rows_stripped = tally.stripped
    entry.rows_kept_missing_file = tally.kept_missing_file
    entry.rows_non_image_stripped = tally.non_image_stripped
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
    if not db_path.is_file():
        entry.message = 'no database file'
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
