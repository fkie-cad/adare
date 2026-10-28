"""Hint that a project database would shrink with ``adare db compact``.

Databases written before action results were stored without their base64
screenshot copies can be dozens of GB; ``adare db compact`` (see
:mod:`adare.database.maintenance`) gives that space back, but nobody knows to
run it. When a project database is opened for the first time in a process,
:func:`check_project_database` decides cheaply whether it is worth a hint
(:func:`needs_compact`) and queues one; the CLI prints the queued hints once on
stderr when the command ends (:func:`emit_hints`) and records the size it hinted
at in a marker file next to the database (``.adare/compact-hint.json``), so the
hint comes back only when the database has grown by half again.

This module only uses ``sqlite3`` and the standard library: it is imported while
a database API is being set up and must not import one.
"""

from __future__ import annotations

import json
import logging
import shlex
import sqlite3
import threading
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

log = logging.getLogger(__name__)

#: Database files smaller than this are never worth a hint.
HINT_MIN_BYTES = 512 * 1024 * 1024
#: The hint comes back when the database has grown to this factor of the size the marker records.
HINT_GROWTH_FACTOR = 1.5
#: A ``result_data`` value longer than this (bytes) holds a screenshot copy, not a plain result.
LARGE_RESULT_BYTES = 256 * 1024
#: Marker file, next to the project database, recording the size the hint was last given at.
MARKER_NAME = 'compact-hint.json'

# Size of a value without reading it: octet_length (SQLite >= 3.43) reads the record
# header only; the fallback loads every value it measures (LIMIT 1 keeps that short
# on a database that needs compacting).
_PROBE_OCTET_LENGTH = 'SELECT 1 FROM action_execution WHERE octet_length(result_data) > ? LIMIT 1'
_PROBE_BLOB_LENGTH = 'SELECT 1 FROM action_execution WHERE length(CAST(result_data AS BLOB)) > ? LIMIT 1'


@dataclass(frozen=True)
class CompactHint:
    """A queued hint: the project database that would shrink, and its size when it was checked."""

    project_path: Path
    db_path: Path
    size: int

    def message(self) -> str:
        gib = self.size / 1024**3
        return (
            f"Hint: the database of project '{self.project_path.name}' is {gib:.1f} GiB, mostly screenshot "
            'copies that older runs stored with their action results. '
            f'`adare db compact -p {shlex.quote(str(self.project_path))}` removes them and shrinks the file.'
        )


_PENDING: dict[str, CompactHint] = {}
_PENDING_LOCK = threading.Lock()


# =============================================================================
# Marker
# =============================================================================


def marker_path(db_path: Path) -> Path:
    """The marker file of the database ``db_path`` (``.adare/compact-hint.json`` of a project)."""
    return db_path.with_name(MARKER_NAME)


def _marker_size(db_path: Path) -> int | None:
    """The size the marker records, or None when there is no readable marker."""
    try:
        data = json.loads(marker_path(db_path).read_text(encoding='utf-8'))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as e:
        log.debug('ignoring unreadable compact hint marker of %s: %s', db_path, e)
        return None
    size = data.get('size') if isinstance(data, dict) else None
    return size if isinstance(size, int) and size >= 0 else None


def write_marker(db_path: Path, size: int | None = None) -> None:
    """Record ``size`` (default: the current file size) as the size the hint was last settled at.

    A marker that cannot be written (read-only project) is skipped: the hint then
    simply comes again.
    """
    try:
        if size is None:
            size = db_path.stat().st_size
        marker_path(db_path).write_text(json.dumps({'size': size}) + '\n', encoding='utf-8')
    except OSError as e:
        log.debug('cannot write the compact hint marker of %s: %s', db_path, e)


def record_compacted(db_path: Path) -> None:
    """``adare db compact`` shrank ``db_path``: drop its queued hint and settle the marker at the new size."""
    with _PENDING_LOCK:
        _PENDING.pop(str(db_path), None)
    write_marker(db_path)


# =============================================================================
# Check
# =============================================================================


def _has_large_result(db_path: Path) -> bool:
    """Does any ``action_execution`` row hold a ``result_data`` over :data:`LARGE_RESULT_BYTES`?"""
    uri = f'{db_path.resolve().as_uri()}?mode=ro'
    with closing(sqlite3.connect(uri, uri=True, timeout=1.0)) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if 'action_execution' not in tables:
            return False
        try:
            row = conn.execute(_PROBE_OCTET_LENGTH, (LARGE_RESULT_BYTES,)).fetchone()
        except sqlite3.OperationalError as e:
            if 'octet_length' not in str(e):
                raise
            row = conn.execute(_PROBE_BLOB_LENGTH, (LARGE_RESULT_BYTES,)).fetchone()
        return row is not None


def needs_compact(db_path: Path) -> bool:
    """Is ``db_path`` worth an ``adare db compact`` hint? Cheap: a ``stat``, a small file, one query.

    True when all of:

    - the file is larger than :data:`HINT_MIN_BYTES`;
    - there is no marker, or the file has grown to :data:`HINT_GROWTH_FACTOR` times
      the size the marker records;
    - an ``action_execution`` row holds a ``result_data`` larger than
      :data:`LARGE_RESULT_BYTES` (a screenshot copy compact can remove).

    When the first two hold but no such row exists, the marker is written with the
    current size, so the query is not repeated until the file has grown again. A
    database that cannot be read is never worth a hint.
    """
    try:
        size = db_path.stat().st_size
    except OSError:
        return False
    if size <= HINT_MIN_BYTES:
        return False
    settled = _marker_size(db_path)
    if settled is not None and size < settled * HINT_GROWTH_FACTOR:
        return False
    try:
        large = _has_large_result(db_path)
    except sqlite3.Error as e:
        log.debug('compact hint check of %s failed: %s', db_path, e)
        return False
    if not large:
        write_marker(db_path, size)
    return large


def check_project_database(project_path: Path, db_path: Path) -> None:
    """Queue a hint for the project database ``db_path`` when :func:`needs_compact` says so."""
    if not needs_compact(db_path):
        return
    try:
        size = db_path.stat().st_size
    except OSError:
        return
    with _PENDING_LOCK:
        _PENDING[str(db_path)] = CompactHint(project_path, db_path, size)


# =============================================================================
# Queue
# =============================================================================


def pending_hints() -> list[CompactHint]:
    """The queued hints, oldest first."""
    with _PENDING_LOCK:
        return list(_PENDING.values())


def clear_hints() -> None:
    """Drop every queued hint (tests, and after printing)."""
    with _PENDING_LOCK:
        _PENDING.clear()


def emit_hints(stream: TextIO, *, quiet: bool = False) -> None:
    """Print each queued hint once on ``stream`` and write its marker; with ``quiet`` print nothing.

    ``quiet`` (json/yaml output) keeps the hints and markers as they are, so the
    next interactive command shows them.
    """
    if quiet:
        return
    with _PENDING_LOCK:
        hints = list(_PENDING.values())
        _PENDING.clear()
    for hint in hints:
        try:
            print(hint.message(), file=stream)
        except (OSError, ValueError) as e:  # closed or broken stderr
            log.debug('cannot print the compact hint: %s', e)
            return
        write_marker(hint.db_path, hint.size)
