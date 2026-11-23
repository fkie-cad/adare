# external imports
import contextlib
from collections import Counter
import hashlib
import os
import shutil
import sqlite3
import tempfile

# internal imports
from adarelib.testset.api import testfunction, TestContext
from adarelib.testset.basictest import HostModeCategory
from adarelib.event.event import TestResult
from adarelib.testset.sqlite_wal import FRAME_KINDS, WalFormatError, parse_wal
from adarelib.testset.structured import compare_count, count_parameter_errors

# configure logging
import logging

log = logging.getLogger(__name__)

# SQLite keeps committed-but-uncheckpointed changes (WAL mode) or an interrupted
# transaction (rollback journal) in files next to the database; a query without
# them sees stale data. -shm is not copied: it is a derived index that SQLite
# rebuilds from the WAL when the copy is opened.
SIDECAR_SUFFIXES = ('-wal', '-journal')
WAL_SUFFIX = '-wal'

# view parameter of query_result / row_count, all derived from one snapshot:
#   current      the database as SQLite sees it, the -wal replayed
#   main_file    the main database file alone: the -wal left out. A -journal is still
#                used, so a hot rollback journal is rolled back and the query sees the
#                last committed state, never the half-written pages of an interrupted
#                transaction (the journal belongs to rollback mode, not to the WAL)
#   wal_added    rows of the query in current but not in main_file (multiset difference)
#   wal_removed  rows of the query in main_file but not in current
VIEWS = ('current', 'main_file', 'wal_added', 'wal_removed')

# The rows read are reported in every result after the query ran; longer
# reports are cut so a large SELECT cannot flood the run record.
MAX_RESULT_DETAIL_CHARS = 2000


def _result_detail(result: list) -> str:
    text = str(result)
    if len(text) > MAX_RESULT_DETAIL_CHARS:
        text = text[:MAX_RESULT_DETAIL_CHARS] + f'... (truncated, {len(result)} rows)'
    return f'query result: {text}'


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _stat_key(path: str):
    try:
        st = os.stat(path)
    except FileNotFoundError:
        return None
    return st.st_size, st.st_mtime_ns


def _snapshot(db_path: str, workdir: str) -> tuple[str, list[str], bool]:
    """Copy the database and its existing sidecars into workdir.

    The original files are only ever read, never opened by SQLite, so querying
    cannot checkpoint, roll back or otherwise modify them.

    :return: (path of the copied database, one 'name sha256=...' entry per copied
             file, whether the source files changed while being copied)
    """
    sources = [db_path] + [db_path + s for s in SIDECAR_SUFFIXES if os.path.isfile(db_path + s)]
    before = {suffix: _stat_key(db_path + suffix) for suffix in ('',) + SIDECAR_SUFFIXES}

    db_copy = os.path.join(workdir, os.path.basename(db_path))
    hashes = []
    for src in sources:
        dst = db_copy + src[len(db_path) :]
        try:
            shutil.copyfile(src, dst)
        except FileNotFoundError:
            # a sidecar vanished (e.g. the app checkpointed on close); the stat
            # comparison below reports the snapshot as changed
            continue
        hashes.append(f'{os.path.basename(src)} sha256={_sha256(dst)}')

    after = {suffix: _stat_key(db_path + suffix) for suffix in ('',) + SIDECAR_SUFFIXES}
    return db_copy, hashes, before != after


def _view_parameter_errors(view) -> list[str]:
    if view not in VIEWS:
        return [f"invalid view {view!r} (allowed: {', '.join(VIEWS)})"]
    return []


def _main_file_copy(db_copy: str, workdir: str) -> str:
    """Copy the snapshot's database and -journal, not its -wal, into a directory of their own.

    Derived from the snapshot (not the original files), so both views show the same moment.
    Must run before the snapshot copy is opened: closing it checkpoints the -wal into it.
    """
    main_dir = os.path.join(workdir, 'main_file')
    os.mkdir(main_dir)
    main_copy = os.path.join(main_dir, os.path.basename(db_copy))
    for suffix in ('',) + tuple(s for s in SIDECAR_SUFFIXES if s != WAL_SUFFIX):
        if suffix == '' or os.path.isfile(db_copy + suffix):
            shutil.copyfile(db_copy + suffix, main_copy + suffix)
    return main_copy


def _fetch(db_copy: str, query: str) -> list[sqlite3.Row]:
    with contextlib.closing(sqlite3.connect(db_copy)) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(query).fetchall()


def _difference(rows: list[sqlite3.Row], other: list[sqlite3.Row]) -> list[dict]:
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


_VIEW_DESCRIPTIONS = {
    'current': 'the database with the -wal applied',
    'main_file': 'the main database file alone, the -wal left out',
    'wal_added': 'rows in current, not in main_file',
    'wal_removed': 'rows in main_file, not in current',
}


def _view_details(view: str, db_name: str, hashes: list[str], counts: dict) -> list[str]:
    """Which view was queried and the -wal it applies or leaves out."""
    wal_name = db_name + WAL_SUFFIX
    wal_hash = next((h for h in hashes if h.startswith(wal_name + ' ')), None)
    details = [f'view: {view} ({_VIEW_DESCRIPTIONS[view]})']
    if view != 'current':
        if wal_hash is None:
            details.append(f'wal: no {wal_name} next to the database, current and main_file are the same')
        else:
            details.append(f'wal: {wal_hash} (applied in current only)')
    if len(counts) == 2:
        details.append(f"rows: current {counts['current']}, main_file {counts['main_file']}")
    return details


def _run_query(
    ctx: TestContext, dst: str, query: str, view: str = 'current'
) -> tuple[list[dict], list[str], TestResult | None]:
    """Run ``query`` on the ``view`` (see :data:`VIEWS`) of one snapshot of the database ``dst``.

    The original files are copied once (:func:`_snapshot`); main_file is a second copy made
    from the snapshot without its -wal, so a difference never mixes two moments.

    :return: (rows as ``{column: value}`` dicts, the view and ``queried snapshot`` details,
             an ERROR result when the database cannot be found or the query fails, else None)
    """
    dst_resolved, status = ctx.resolve_globfilepath(dst)
    if not dst_resolved:
        return (
            [],
            [],
            TestResult.error(
                [
                    f'database file {dst} can\'t be used, because no unambiguous file could be identified (because {status})'
                ]
            ),
        )
    if not os.path.isfile(dst_resolved):
        return [], [], TestResult.error([f'database file {dst} does not exist'])

    log.debug(f'dst database {dst_resolved} will be used for query {query!r} (view {view})')

    with tempfile.TemporaryDirectory(prefix='adare_sqlite_') as workdir:
        db_copy, hashes, changed = _snapshot(dst_resolved, workdir)
        snapshot_details = [f'queried snapshot: {h}' for h in hashes]
        if changed:
            snapshot_details.append(
                'warning: database files changed while being copied; the snapshot may be inconsistent'
            )
        copies = {}
        if view != 'main_file':
            copies['current'] = db_copy
        if view != 'current':
            try:
                copies['main_file'] = _main_file_copy(db_copy, workdir)
            except OSError as e:
                return [], snapshot_details, TestResult.error([f'could not copy the snapshot: {e}'] + snapshot_details)
        fetched = {}
        for name, copy in copies.items():
            try:
                fetched[name] = _fetch(copy, query)
            except sqlite3.Error as e:
                where = '' if view == 'current' else f' ({name} view)'
                return (
                    [],
                    snapshot_details,
                    TestResult.error([f'SQLite error executing query{where}: {query} - {e}'] + snapshot_details),
                )
    if view == 'wal_added':
        rows = _difference(fetched['current'], fetched['main_file'])
    elif view == 'wal_removed':
        rows = _difference(fetched['main_file'], fetched['current'])
    else:
        rows = [dict(row) for row in fetched[view]]
    counts = {name: len(found) for name, found in fetched.items()}
    details = _view_details(view, os.path.basename(dst_resolved), hashes, counts)
    return rows, details + snapshot_details, None


@testfunction(
    name='query_result',
    description='executes SQL query against SQLite database and validates result',
    category=HostModeCategory.FILE_CONTENT,
)
def query_result(
    ctx: TestContext,
    dst: str,
    query: str,
    expected_count: int | None = None,
    expected_result: list | None = None,
    comparison_type: str = 'equals',
    view: str = 'current',
):
    """Pass when ``query`` runs on the SQLite database and its result matches the expectations.

    Use for: asserting that a row was written, changed or removed; which rows exist only in
    the write-ahead log, not yet checkpointed into the main file (``view: wal_added``), or are
    still in the main file but deleted or changed in the WAL (``view: wal_removed``). The
    original file is never opened: ``dst`` and any ``-wal``/``-journal``
    sidecar are copied to a temp dir and the copy is queried, so uncheckpointed changes are
    seen and the evidence is not modified. Details report ``queried snapshot: <file> sha256=...``
    per copied file and, once the query ran, the rows read (``query result: [...]``, also on
    success). With neither expectation set, it passes whenever the query runs. To only count
    rows use sqlite.row_count. Timestamps stored as numbers (Unix seconds, microseconds
    since 1601) are compared with ``!timestamp`` and its ``epoch``/``unit`` options.

    A test fails only when the query ran and its result does not match. When it cannot be
    evaluated (missing database, SQL error) it ends with an error, so ``expect_to_fail``
    never turns an unreadable database into a pass.

    Args:
        dst: Guest path to the database; a glob must match exactly one file (otherwise an
            error). A missing file is an error.
        query: SQL to execute, e.g. ``SELECT name FROM items WHERE name LIKE '%example%'``. A
            SQL error (syntax, unknown table, unreadable database) is an error.
        expected_count: Number of rows the query must return, compared with
            ``comparison_type``; ``None`` skips the check. Use ``0`` to assert a row is gone.
            A negative number or a non-integer is an error.
        expected_result: Exact expected rows as a list of ``{column: value}`` mappings, in
            query order; ``None`` skips the check. Placeholders compare the stringified result.
        comparison_type: ``equals`` (default), ``greater``, ``less``, ``greater_equal`` or
            ``less_equal`` for ``expected_count``; other values are an error.
        view: Which state of the database the query sees, compared with
            ``expected_count`` / ``expected_result``; all views come from one snapshot
            (the files are copied once). ``current`` (default): the database as SQLite sees
            it, the ``-wal`` replayed. ``main_file``: the main database file alone, the
            ``-wal`` left out. ``wal_added``: the result rows of ``current`` that are not in
            ``main_file``; ``wal_removed``: the rows of ``main_file`` not in ``current``
            (multiset difference of whole rows, in query order). Select identifying columns
            for the differences: a changed row appears in both. A ``-journal`` is used in
            every view, so a hot rollback journal is rolled back. Details name the view and
            the ``-wal`` sha256. Other values are an error.

    Example:
        function: sqlite.query_result
        parameter:
          dst: /home/user/data/app.db
          query: SELECT name FROM items WHERE name LIKE '%example%'
          expected_count: 0
    """
    problems = _view_parameter_errors(view)
    if expected_count is not None or comparison_type != 'equals':
        problems += count_parameter_errors(expected_count, comparison_type)
    if problems:
        return TestResult.error(problems)

    result, snapshot_details, error = _run_query(ctx, dst, query, view)
    if error is not None:
        return error

    if expected_count is not None:
        ok, message = compare_count(len(result), expected_count, comparison_type)
        if not ok:
            return TestResult.failed([f'row count: {message}', _result_detail(result)] + snapshot_details)

    # Check expected result content
    if expected_result is not None:
        expected_str = str(expected_result)
        if ctx.has_placeholders(expected_str):
            # For complex result comparison with placeholders, convert to string and use placeholder system
            success, message = ctx.handle_placeholders_comparison(str(result), expected_str)
            if not success:
                return TestResult.failed(
                    [f'query result placeholder comparison failed: {message}', _result_detail(result)]
                    + snapshot_details
                )
        elif result != expected_result:
            return TestResult.failed([f'query result does not match expected result. Got: {result}'] + snapshot_details)

    return TestResult.success([f'query returned {len(result)} rows', _result_detail(result)] + snapshot_details)


@testfunction(
    name='row_count',
    description='tests the number of rows an SQL query returns on an SQLite database',
    category=HostModeCategory.FILE_CONTENT,
)
def row_count(
    ctx: TestContext,
    dst: str,
    query: str,
    expected_count: int,
    comparison_type: str = 'equals',
    view: str = 'current',
):
    """Pass when the number of rows ``query`` returns on the SQLite database satisfies ``comparison_type``.

    Use for: asserting how many records an action left behind (exactly one history entry
    for a URL); asserting a record is gone: ``expected_count: 0``; asserting a row is only in
    the write-ahead log, not yet checkpointed into the main file: one test with
    ``view: wal_added`` and ``expected_count: 1``. Queried like
    sqlite.query_result: ``dst`` and any ``-wal``/``-journal`` sidecar are copied to a temp
    dir and the copy is queried, so uncheckpointed changes are seen and the evidence is not
    modified. Details report the count, the rows read (``query result: [...]``) and
    ``queried snapshot: <file> sha256=...`` per copied file. To check the row contents use
    sqlite.query_result with ``expected_result``.

    Args:
        dst: Guest path to the database; a glob must match exactly one file (otherwise an
            error). A missing file is an error.
        query: SQL to execute, e.g. ``SELECT id FROM items WHERE name = 'example'``; every
            returned row counts (``SELECT COUNT(*)`` returns one row). A SQL error (syntax,
            unknown table, unreadable database) is an error.
        expected_count: Non-negative integer to compare against; anything else is an error.
        comparison_type: ``equals`` (default), ``greater``, ``less``, ``greater_equal`` or
            ``less_equal``; other values are an error.
        view: Which state of the database is counted; all views come from one snapshot
            (the files are copied once). ``current`` (default): the database as SQLite sees
            it, the ``-wal`` replayed. ``main_file``: the main database file alone, the
            ``-wal`` left out. ``wal_added``: the result rows of ``current`` that are not in
            ``main_file``; ``wal_removed``: the rows of ``main_file`` not in ``current``
            (multiset difference of whole rows; their number is counted). Select identifying
            columns for the differences: a changed row appears in both. A ``-journal`` is
            used in every view, so a hot rollback journal is rolled back. Details name the
            view and the ``-wal`` sha256. Other values are an error.

    Example:
        function: sqlite.row_count
        parameter:
          dst: /home/user/data/app.db
          query: SELECT id FROM items WHERE name LIKE '%example%'
          expected_count: 1
    """
    problems = count_parameter_errors(expected_count, comparison_type) + _view_parameter_errors(view)
    if not isinstance(query, str) or not query.strip():
        problems.append(f'query must be a non-empty SQL string, got {query!r}')
    if problems:
        return TestResult.error(problems)

    result, snapshot_details, error = _run_query(ctx, dst, query, view)
    if error is not None:
        return error

    ok, message = compare_count(len(result), expected_count, comparison_type)
    details = [f'query returned {len(result)} rows', message, _result_detail(result)] + snapshot_details
    return TestResult.success(details) if ok else TestResult.failed(details)


def _wal_path(ctx: TestContext, dst: str) -> tuple[str, TestResult | None]:
    """The WAL file ``dst`` names: ``dst + '-wal'`` for a database, or a ``-wal`` file itself.

    :return: (path of the WAL, which may not exist next to a database; an ERROR result
             when ``dst`` cannot be used, else None)
    """
    dst_resolved, status = ctx.resolve_globfilepath(dst)
    if not dst_resolved:
        return '', TestResult.error(
            [f"database file {dst} can't be used, because no unambiguous file could be identified (because {status})"]
        )
    if dst_resolved.endswith(WAL_SUFFIX):
        if not os.path.isfile(dst_resolved):
            return '', TestResult.error(
                [f'WAL file {dst} does not exist (pass the database path to count a missing WAL as 0 frames)']
            )
        return dst_resolved, None
    if not os.path.isfile(dst_resolved):
        return '', TestResult.error([f'database file {dst} does not exist'])
    return dst_resolved + WAL_SUFFIX, None


@testfunction(
    name='wal_frame_count',
    description='tests the number of frames in the write-ahead log (-wal) of an SQLite database',
    category=HostModeCategory.FILE_CONTENT,
)
def wal_frame_count(
    ctx: TestContext,
    dst: str,
    expected_count: int,
    comparison_type: str = 'equals',
    frames: str = 'valid',
):
    """Pass when the number of ``frames`` in the SQLite write-ahead log satisfies ``comparison_type``.

    Use for: asserting that changes are still in the WAL, not yet checkpointed into the main
    file (``frames: valid`` greater than 0), how many transactions the WAL holds
    (``frames: commits``), or that a checkpoint emptied it (``expected_count: 0``); finding
    old frames a WAL reset left behind that SQLite no longer reads (``frames: stale``).
    The WAL is parsed per the SQLite file format, without SQLite: header magic and version,
    page size, salts and the checksum chain. A copy of the WAL is read, never the original.
    Details report the header fields, all four counts and ``read snapshot: <file> sha256=...``.
    To find which rows live only in the WAL use sqlite.row_count with ``view: wal_added``.

    Args:
        dst: Guest path to the database; its ``<dst>-wal`` is read. A missing ``-wal`` next
            to an existing database counts as 0 frames, a missing database is an error. May
            also name the ``-wal`` file itself (then it must exist). A glob must match
            exactly one file.
        expected_count: Non-negative integer to compare against; anything else is an error.
        comparison_type: ``equals`` (default), ``greater``, ``less``, ``greater_equal`` or
            ``less_equal``; other values are an error.
        frames: ``valid`` (default): the frames SQLite replays, i.e. salts matching the header
            and an intact checksum chain, up to the last commit frame; ``commits``: commit
            frames among them (one per transaction); ``all``: every complete frame in the
            file; ``stale``: ``all`` minus ``valid`` (frames from before a WAL reset, an
            unfinished transaction). Other values are an error.

    A WAL that is not empty but too short for its 32-byte header, has a wrong magic, version
    or page size, or a header checksum mismatch is an error; an empty (0-byte) WAL has 0
    frames.

    Example:
        function: sqlite.wal_frame_count
        parameter:
          dst: /home/user/app/data.db
          expected_count: 1
          comparison_type: greater_equal
          frames: commits
    """
    problems = count_parameter_errors(expected_count, comparison_type)
    if frames not in FRAME_KINDS:
        problems.append(f"invalid frames {frames!r} (allowed: {', '.join(FRAME_KINDS)})")
    if problems:
        return TestResult.error(problems)

    wal_path, error = _wal_path(ctx, dst)
    if error is not None:
        return error
    name = os.path.basename(wal_path)
    if not os.path.isfile(wal_path):
        ok, message = compare_count(0, expected_count, comparison_type)
        details = [f'{frames} frames: 0 (no {name} next to the database)', message]
        return TestResult.success(details) if ok else TestResult.failed(details)

    with tempfile.TemporaryDirectory(prefix='adare_sqlite_wal_') as workdir:
        wal_copy = os.path.join(workdir, name)
        before = _stat_key(wal_path)
        try:
            shutil.copyfile(wal_path, wal_copy)
            snapshot = [f'read snapshot: {name} sha256={_sha256(wal_copy)}']
            info = parse_wal(wal_copy)
        except WalFormatError as e:
            return TestResult.error([f'{name}: {e}'] + snapshot)
        except OSError as e:
            return TestResult.error([f'WAL file {wal_path} could not be read: {e}'])
    if _stat_key(wal_path) != before:
        snapshot.append('warning: the WAL changed while being copied; the snapshot may be inconsistent')

    count = info.count(frames)
    ok, message = compare_count(count, expected_count, comparison_type)
    details = [
        f'{frames} frames: {count}',
        message,
        f'frames: all={info.total_frames} valid={info.valid_frames} commits={info.commit_frames} '
        f'stale={info.stale_frames}',
    ]
    if info.page_size:
        details.append(
            f"WAL header: {'big' if info.big_endian_checksums else 'little'}-endian checksums, "
            f'page size {info.page_size}, checkpoint sequence {info.checkpoint_sequence}, '
            f'salt-1 0x{info.salt1:08x}, salt-2 0x{info.salt2:08x}'
        )
    else:
        details.append('WAL is empty (0 bytes)')
    if info.trailing_bytes:
        details.append(f'{info.trailing_bytes} bytes after the last complete frame (not counted)')
    details += snapshot
    return TestResult.success(details) if ok else TestResult.failed(details)


# Host mode pulls these next to dst. Set on the class rather than via a decorator
# argument so this module still loads with older adarelib versions preinstalled in
# guest images (testfunctions are uploaded fresh each run, adarelib is not).
query_result._test_class.host_mode_sidecars = SIDECAR_SUFFIXES
row_count._test_class.host_mode_sidecars = SIDECAR_SUFFIXES
# wal_frame_count reads only the -wal; with dst naming the -wal itself the pull of
# '<dst>-wal' finds nothing, which is harmless.
wal_frame_count._test_class.host_mode_sidecars = (WAL_SUFFIX,)
