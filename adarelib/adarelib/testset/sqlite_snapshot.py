"""One snapshot of an SQLite database and the views derived from it, for the ``sqlite`` testfunctions.

The original database and its ``-wal`` / ``-journal`` sidecars are copied once into a temp
directory (:func:`take_snapshot`) and only the copies are ever opened, so querying cannot
checkpoint, roll back or otherwise modify the evidence. Every view is derived from that one
snapshot, so two views (or a difference of them) never mix two moments:

``current``      the database as SQLite sees it, the ``-wal`` replayed
``main_file``    the main database file alone, the ``-wal`` left out. A ``-journal`` is still
                 used, so a hot rollback journal is rolled back and the query sees the last
                 committed state, never the half-written pages of an interrupted transaction
``wal_added``    rows of the query in current but not in main_file (multiset difference)
``wal_removed``  rows of the query in main_file but not in current
``commit:N``     the ``-wal`` replayed through its N-th transaction (commit frame): N >= 1
                 counts from the start, a negative N from the end (``commit:-1`` = the last
                 commit, the same as current); ``commit:0`` is main_file

Standard library only (plus adarelib), importable on Python 3.10.
"""

import contextlib
import hashlib
import os
import re
import shutil
import sqlite3
from collections import Counter
from dataclasses import dataclass, field

from adarelib.testset.sqlite_wal import WalFormatError, frame_offset, parse_wal

# SQLite keeps committed-but-uncheckpointed changes (WAL mode) or an interrupted
# transaction (rollback journal) in files next to the database; a query without
# them sees stale data. -shm is not copied: it is a derived index that SQLite
# rebuilds from the WAL when the copy is opened.
SIDECAR_SUFFIXES = ('-wal', '-journal')
WAL_SUFFIX = '-wal'

# views a query can be run on (query_result / row_count); commit:N is matched by COMMIT_VIEW
VIEWS = ('current', 'main_file', 'wal_added', 'wal_removed')
# views that are one state of the database (values_compare), not a difference of two
STATE_VIEWS = ('current', 'main_file')
COMMIT_VIEW = re.compile(r'commit:(-?\d+)')

_VIEW_DESCRIPTIONS = {
    'current': 'the database with the -wal applied',
    'main_file': 'the main database file alone, the -wal left out',
    'wal_added': 'rows in current, not in main_file',
    'wal_removed': 'rows in main_file, not in current',
}


class ViewError(ValueError):
    """A view that cannot be built from this snapshot (``commit:N`` out of range, unreadable WAL)."""


def commit_number(view: str) -> int | None:
    """N of a ``commit:N`` view, else None."""
    match = COMMIT_VIEW.fullmatch(view) if isinstance(view, str) else None
    return int(match.group(1)) if match else None


def view_parameter_errors(view, allowed: tuple[str, ...] = VIEWS, name: str = 'view') -> list[str]:
    """Why ``view`` is not one of ``allowed`` or ``commit:N``; empty when it is."""
    if (isinstance(view, str) and view in allowed) or commit_number(view) is not None:
        return []
    return [f"invalid {name} {view!r} (allowed: {', '.join(allowed)}, commit:N)"]


def sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def stat_key(path: str):
    try:
        st = os.stat(path)
    except FileNotFoundError:
        return None
    return st.st_size, st.st_mtime_ns


@dataclass
class Snapshot:
    """The copied database (``db_copy``) and its sidecars in ``workdir``."""

    workdir: str
    db_copy: str
    hashes: list[str]  # one '<name> sha256=<hash>' per copied file
    changed: bool  # the originals changed while being copied
    _views: dict = field(default_factory=dict)  # view -> (path, details)

    @property
    def db_name(self) -> str:
        return os.path.basename(self.db_copy)

    @property
    def wal_hash(self) -> str | None:
        """``'<db>-wal sha256=...'`` when the snapshot holds a -wal."""
        wal_name = self.db_name + WAL_SUFFIX
        return next((h for h in self.hashes if h.startswith(wal_name + ' ')), None)

    def details(self, label: str = 'queried snapshot') -> list[str]:
        """``<label>: <file> sha256=...`` per copied file, and a warning if the originals changed."""
        out = [f'{label}: {h}' for h in self.hashes]
        if self.changed:
            out.append('warning: database files changed while being copied; the snapshot may be inconsistent')
        return out

    def view_path(self, view: str) -> tuple[str, list[str]]:
        """The copy that shows the state ``view`` (one of :data:`STATE_VIEWS` or ``commit:N``).

        Derived copies are made from the snapshot; ask for every view before any copy is
        opened by SQLite (closing the current copy checkpoints its -wal into it).

        :return: (path, details naming the view and the -wal it applies or leaves out)
        :raises ViewError: ``commit:N`` with N out of range, no -wal, an unreadable -wal
        :raises OSError: the snapshot cannot be copied
        """
        if view not in self._views:
            self._views[view] = self._make_view(view)
        return self._views[view]

    def _make_view(self, view: str) -> tuple[str, list[str]]:
        if view == 'current':
            return self.db_copy, [f"view: current ({_VIEW_DESCRIPTIONS['current']})"]
        n = commit_number(view)
        if view == 'main_file' or n == 0:
            path = self._derived_copy('main_file' if n is None else 'commit_0', with_wal=False)
            return path, [f"view: {view} ({_VIEW_DESCRIPTIONS['main_file']})"] + self.wal_line('current')
        if n is None:
            raise ViewError(f'{view!r} is not one state of the database')
        return self._commit_view(view, n)

    def wal_line(self, applied_in: str) -> list[str]:
        if self.wal_hash is None:
            return [f'wal: no {self.db_name}{WAL_SUFFIX} next to the database, current and main_file are the same']
        return [f'wal: {self.wal_hash} (applied in {applied_in} only)']

    def _derived_copy(self, name: str, with_wal: bool) -> str:
        """A copy of the snapshot's database and -journal (and -wal) in a directory of its own."""
        directory = os.path.join(self.workdir, name)
        os.mkdir(directory)
        path = os.path.join(directory, self.db_name)
        for suffix in ('',) + SIDECAR_SUFFIXES:
            if suffix == WAL_SUFFIX and not with_wal:
                continue
            if suffix == '' or os.path.isfile(self.db_copy + suffix):
                shutil.copyfile(self.db_copy + suffix, path + suffix)
        return path

    def _commit_view(self, view: str, n: int) -> tuple[str, list[str]]:
        wal = self.db_copy + WAL_SUFFIX
        if not os.path.isfile(wal):
            raise ViewError(f'view {view}: no {self.db_name}{WAL_SUFFIX} next to the database (only commit:0 exists)')
        try:
            info = parse_wal(wal)
        except WalFormatError as e:
            raise ViewError(f'view {view}: {self.db_name}{WAL_SUFFIX}: {e}') from e
        commits = info.commit_frame_indices
        k = n if n > 0 else len(commits) + 1 + n
        if k < 1 or k > len(commits):
            raise ViewError(
                f'view {view}: {self.db_name}{WAL_SUFFIX} holds {len(commits)} commit(s) '
                f'(commit:1 to commit:{len(commits)}, or commit:-1 to commit:-{len(commits)}; commit:0 = main_file)'
            )
        frame = commits[k - 1]
        path = self._derived_copy(f'commit_{k}', with_wal=True)
        os.truncate(path + WAL_SUFFIX, frame_offset(info.page_size, frame))
        return path, [
            f'view: {view} (the database with the -wal replayed through commit {k} of {len(commits)}, '
            f'WAL frame {frame} of {info.valid_frames} valid)',
            f'wal: {self.wal_hash} (truncated after frame {frame})',
        ]


def take_snapshot(db_path: str, workdir: str) -> Snapshot:
    """Copy the database and its existing sidecars into ``workdir``.

    The original files are only ever read, never opened by SQLite.

    :raises OSError: the database cannot be copied
    """
    sources = [db_path] + [db_path + s for s in SIDECAR_SUFFIXES if os.path.isfile(db_path + s)]
    before = {suffix: stat_key(db_path + suffix) for suffix in ('',) + SIDECAR_SUFFIXES}

    db_copy = os.path.join(workdir, os.path.basename(db_path))
    hashes = []
    for src in sources:
        dst = db_copy + src[len(db_path) :]
        try:
            shutil.copyfile(src, dst)
        except FileNotFoundError:
            if src == db_path:
                raise
            # a sidecar vanished (e.g. the app checkpointed on close); the stat
            # comparison below reports the snapshot as changed
            continue
        hashes.append(f'{os.path.basename(src)} sha256={sha256(dst)}')

    after = {suffix: stat_key(db_path + suffix) for suffix in ('',) + SIDECAR_SUFFIXES}
    return Snapshot(workdir=workdir, db_copy=db_copy, hashes=hashes, changed=before != after)


def fetch(db_copy: str, query: str) -> list[sqlite3.Row]:
    """The rows of ``query`` on the copy at ``db_copy``.

    :raises sqlite3.Error: the query fails
    """
    with contextlib.closing(sqlite3.connect(db_copy)) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(query).fetchall()


def difference(rows: list[sqlite3.Row], other: list[sqlite3.Row]) -> list[dict]:
    """Rows of ``rows`` not in ``other`` as multisets, in the order of ``rows``.

    A row twice in ``rows`` and once in ``other`` is left once.
    """
    remaining = Counter(tuple(row) for row in other)
    out = []
    for row in rows:
        key = tuple(row)
        if remaining[key]:
            remaining[key] -= 1
        else:
            out.append(dict(row))
    return out


def difference_details(view: str, snapshot: Snapshot, counts: dict) -> list[str]:
    """Details of a ``wal_added`` / ``wal_removed`` view."""
    return (
        [f'view: {view} ({_VIEW_DESCRIPTIONS[view]})']
        + snapshot.wal_line('current')
        + [f"rows: current {counts['current']}, main_file {counts['main_file']}"]
    )


def checkpoint(db_copy: str) -> None:
    """Fold the copy's -wal into it (``PRAGMA wal_checkpoint(TRUNCATE)``), rolling back a hot journal first.

    :raises sqlite3.Error: the copy is not a usable database
    """
    with contextlib.closing(sqlite3.connect(db_copy)) as conn:
        conn.execute('SELECT count(*) FROM sqlite_master').fetchall()
        conn.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchall()
