# external imports
import os
import shutil
import sqlite3
import tempfile

# internal imports
from adarelib.constants import StatusEnum
from adarelib.testset import binary
from adarelib.testset.api import testfunction, TestContext
from adarelib.testset.basictest import HostModeCategory
from adarelib.testset.compare import regex_expected_problem
from adarelib.event.event import TestResult
from adarelib.testset.ordering import OrderingError
from adarelib.testset.sqlite_freespace import REGION_KINDS, FreeSpace, SqliteFreeSpaceError, read_free_space
from adarelib.testset.sqlite_snapshot import (
    SIDECAR_SUFFIXES,
    STATE_VIEWS,
    WAL_SUFFIX,
    Snapshot,
    ViewError,
    checkpoint,
    difference,
    difference_details,
    fetch,
    sha256,
    stat_key,
    take_snapshot,
    view_parameter_errors,
)
from adarelib.testset.sqlite_wal import FRAME_KINDS, WalFormatError, parse_wal
from adarelib.testset.structured import compare_count, count_parameter_errors, text
from adarelib.testset.valuecompare import build_comparison, compare_pair

# configure logging
import logging

log = logging.getLogger(__name__)

# The views (current, main_file, wal_added, wal_removed, commit:N) and the one snapshot they
# are derived from are described in adarelib.testset.sqlite_snapshot.

# The rows read are reported in every result after the query ran; longer
# reports are cut so a large SELECT cannot flood the run record.
MAX_RESULT_DETAIL_CHARS = 2000

# free_space_pattern_count: which free space is searched
FREE_SPACE_REGIONS = {
    'all': REGION_KINDS,
    'freelist': ('freelist',),
    'freeblocks': ('freeblock',),
    'unallocated': ('unallocated',),
}
FREE_SPACE_VIEWS = ('main_file', 'current')
# matching regions named in the details; the rest is summarised
MAX_MATCH_DETAILS = 20


def _result_detail(result: list) -> str:
    text = str(result)
    if len(text) > MAX_RESULT_DETAIL_CHARS:
        text = text[:MAX_RESULT_DETAIL_CHARS] + f'... (truncated, {len(result)} rows)'
    return f'query result: {text}'


def _checked_db(dst: str, dst_resolved: str, status: str, what: str = 'database file') -> TestResult | None:
    """An ERROR result when ``dst`` (resolved to ``dst_resolved``) is no existing file, else None."""
    if not dst_resolved:
        return TestResult.error(
            [f"{what} {dst} can't be used, because no unambiguous file could be identified (because {status})"]
        )
    if not os.path.isfile(dst_resolved):
        return TestResult.error([f'{what} {dst} does not exist'])
    return None


def _query_error(query: str, name: str, e: sqlite3.Error, details: list[str]) -> TestResult:
    where = '' if name is None else f' ({name} view)'
    return TestResult.error([f'SQLite error executing query{where}: {query} - {e}'] + details)


def _run_query(
    ctx: TestContext, dst: str, query: str, view: str = 'current'
) -> tuple[list[dict], list[str], TestResult | None]:
    """Run ``query`` on the ``view`` of one snapshot of the database ``dst``.

    The original files are copied once (:func:`take_snapshot`); every other view is a copy made
    from the snapshot, so a difference never mixes two moments.

    :return: (rows as ``{column: value}`` dicts, the view and ``queried snapshot`` details,
             an ERROR result when the database cannot be found or the query fails, else None)
    """
    dst_resolved, status = ctx.resolve_globfilepath(dst)
    error = _checked_db(dst, dst_resolved, status)
    if error is not None:
        return [], [], error

    log.debug(f'dst database {dst_resolved} will be used for query {query!r} (view {view})')

    states = ['current', 'main_file'] if view in ('wal_added', 'wal_removed') else [view]
    with tempfile.TemporaryDirectory(prefix='adare_sqlite_') as workdir:
        try:
            snapshot = take_snapshot(dst_resolved, workdir)
        except OSError as e:
            return [], [], TestResult.error([f'could not copy the database {dst_resolved}: {e}'])
        snapshot_details = snapshot.details()
        try:
            # every copy is made before any is opened (closing current checkpoints its -wal)
            copies = {name: snapshot.view_path(name) for name in states}
        except ViewError as e:
            return [], snapshot_details, TestResult.error([str(e)] + snapshot_details)
        except OSError as e:
            return [], snapshot_details, TestResult.error([f'could not copy the snapshot: {e}'] + snapshot_details)
        fetched = {}
        for name, (copy, _) in copies.items():
            try:
                fetched[name] = fetch(copy, query)
            except sqlite3.Error as e:
                return (
                    [],
                    snapshot_details,
                    _query_error(query, None if view == 'current' else name, e, snapshot_details),
                )
    if len(states) == 2:
        rows = difference(fetched['current'], fetched['main_file']) if view == 'wal_added' else []
        if view == 'wal_removed':
            rows = difference(fetched['main_file'], fetched['current'])
        counts = {name: len(found) for name, found in fetched.items()}
        details = difference_details(view, snapshot, counts)
    else:
        rows = [dict(row) for row in fetched[view]]
        details = copies[view][1]
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
    still in the main file but deleted or changed in the WAL (``view: wal_removed``); the
    state after one transaction of several in the WAL (``view: commit:N``). The
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
            for the differences: a changed row appears in both. ``commit:N``: the ``-wal``
            replayed through its N-th transaction (``commit:1`` the first, ``commit:-1`` the
            last, ``commit:0`` = ``main_file``); an N beyond the commits in the ``-wal``, or
            any N but 0 without a ``-wal``, is an error. A ``-journal`` is used in every
            view, so a hot rollback journal is rolled back. Details name the view, the
            ``-wal`` sha256 and, for ``commit:N``, the WAL frame it stops at. Other values
            are an error.

    Example:
        function: sqlite.query_result
        parameter:
          dst: /home/user/data/app.db
          query: SELECT name FROM items WHERE name LIKE '%example%'
          expected_count: 0
    """
    problems = view_parameter_errors(view)
    if expected_count is not None or comparison_type != 'equals':
        problems += count_parameter_errors(expected_count, comparison_type)
    if problems:
        return TestResult.error(problems)
    if expected_result is not None:
        # a regex placeholder in expected_result is checked before a count mismatch can hide it
        regex_problem = regex_expected_problem(ctx, [str(expected_result)], many_placeholders=True)
        if regex_problem is not None:
            return regex_problem

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
            columns for the differences: a changed row appears in both. ``commit:N``: the
            ``-wal`` replayed through its N-th transaction (``commit:1`` the first,
            ``commit:-1`` the last, ``commit:0`` = ``main_file``); an N beyond the commits in
            the ``-wal``, or any N but 0 without a ``-wal``, is an error. A ``-journal`` is
            used in every view, so a hot rollback journal is rolled back. Details name the
            view, the ``-wal`` sha256 and, for ``commit:N``, the WAL frame it stops at. Other
            values are an error.

    Example:
        function: sqlite.row_count
        parameter:
          dst: /home/user/data/app.db
          query: SELECT id FROM items WHERE name LIKE '%example%'
          expected_count: 1
    """
    problems = count_parameter_errors(expected_count, comparison_type) + view_parameter_errors(view)
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
        before = stat_key(wal_path)
        try:
            shutil.copyfile(wal_path, wal_copy)
            snapshot = [f'read snapshot: {name} sha256={sha256(wal_copy)}']
            info = parse_wal(wal_copy)
        except WalFormatError as e:
            return TestResult.error([f'{name}: {e}'] + snapshot)
        except OSError as e:
            return TestResult.error([f'WAL file {wal_path} could not be read: {e}'])
    if stat_key(wal_path) != before:
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


def _single_value(label: str, rows: list[sqlite3.Row]) -> tuple[list, TestResult | None]:
    """The first column of the one row a side's query returns; FAILED for no row, ERROR for several."""
    if not rows:
        return [], TestResult.failed([f'{label} returned no row'])
    if len(rows) > 1:
        shown = ', '.join(text(row[0]) for row in rows[:5])
        return [], TestResult.error(
            [f'{label} returned {len(rows)} rows (first column: {shown}); each query must return exactly one row']
        )
    return [rows[0][0]], None


def _side_parameter_errors(query, other_query, other_dst, view, other_view) -> list[str]:
    """Problems with the two sides of values_compare (after the defaults were filled in)."""
    problems = view_parameter_errors(view, STATE_VIEWS) + view_parameter_errors(other_view, STATE_VIEWS, 'other_view')
    for name, value in (('query', query), ('other_query', other_query)):
        if not isinstance(value, str) or not value.strip():
            problems.append(f'{name} must be a non-empty SQL string, got {value!r}')
    if other_dst is not None and (not isinstance(other_dst, str) or not other_dst):
        problems.append(f'other_dst must be a path, got {other_dst!r}')
    return problems


@testfunction(
    name='values_compare',
    description='compares the values two SQL queries return on SQLite databases or views of one (earlier/later, within a tolerance, A = B + offset)',
    category=HostModeCategory.FILE_CONTENT,
)
def values_compare(
    ctx: TestContext,
    dst: str,
    query: str,
    other_query: str | None = None,
    other_dst: str | None = None,
    view: str = 'current',
    other_view: str | None = None,
    comparison_type: str = 'equals',
    value_type: str = 'auto',
    tolerance: int | float | None = None,
    offset: int | float | None = None,
    time_format: str | None = None,
    timestamp_epoch: int | None = None,
    timestamp_unit: str | None = None,
    utc_offset: str | None = None,
):
    """Pass when the value ``query`` returns compares to the value ``other_query`` returns (+ ``offset``).

    Use for: one check for "the write-ahead log adds exactly one row": ``SELECT count(*)`` on
    ``view: current`` equal to ``other_view: main_file`` with ``offset: 1``; how a value
    changed between two transactions in the WAL (``view: commit:2``, ``other_view:
    commit:1``); two timestamps of one record in order (``other_query`` on another column);
    the same value in two databases (``other_dst``). Each side is the first column of the
    single row its query returns. With one database both sides come from one snapshot (the
    files are copied once, as in sqlite.query_result), so they show the same moment; the
    evidence is never opened. To compare one value with a constant use sqlite.query_result.

    Args:
        dst: Guest path to the database; a glob must match exactly one file (otherwise an
            error). A missing file is an error.
        query: SQL returning the first value, e.g. ``SELECT count(*) FROM items``. It must
            return exactly one row (its first column is compared): no row fails, more rows
            are an error. A SQL error is an error.
        other_query: SQL returning the second value; ``None`` (default) runs ``query`` again
            (on ``other_dst`` / ``other_view``). Same rules.
        other_dst: Database of the second value; ``None`` (default) = ``dst``. Same rules as
            ``dst``; it gets its own snapshot.
        view: State of ``dst`` the first query sees: ``current`` (default, the ``-wal``
            replayed), ``main_file`` (the ``-wal`` left out) or ``commit:N`` (the ``-wal``
            replayed through its N-th transaction; ``commit:-1`` the last, ``commit:0`` =
            ``main_file``), as in sqlite.query_result. An N out of range is an error.
        other_view: State the second query sees; ``None`` (default) = ``view``.
        comparison_type: How the first value relates to the second: ``equals`` (default),
            ``not_equals``, ``greater``, ``less``, ``greater_equal`` or ``less_equal``
            (``less`` = earlier for timestamps). Other values are an error.
        value_type: ``auto`` (default; numbers if both are numbers, else timestamps),
            ``number`` or ``timestamp``. A value that is no number or timestamp (NULL, a
            BLOB) is an error.
        tolerance: Allowed difference for ``equals``/``not_equals`` (seconds for timestamps).
        offset: Added to the second value before comparing (seconds for timestamps, may be
            negative): ``first <comparison_type> second + offset``.
        time_format: ``strptime`` format of text timestamps on both sides; default ISO 8601 or RFC 2822.
        timestamp_epoch: Read numbers as a count since 1 January of ``1970``, ``1601`` or ``2001``.
        timestamp_unit: Unit of that count: ``s`` (default), ``ms``, ``us``, ``ns`` or ``100ns``.
        utc_offset: Zone of timestamps without one (``+02:00``); default UTC.

    Example:
        function: sqlite.values_compare
        parameter:
          dst: /data/app/state.db
          query: SELECT count(*) FROM items
          view: current
          other_view: main_file
          offset: 1
    """
    other_query = query if other_query is None else other_query
    other_view = view if other_view is None else other_view
    problems = _side_parameter_errors(query, other_query, other_dst, view, other_view)
    try:
        ordered = build_comparison(
            comparison_type, value_type, tolerance, time_format, timestamp_epoch, timestamp_unit, utc_offset, offset
        )
    except OrderingError as e:
        problems.append(str(e))
    if problems:
        return TestResult.error(problems)

    dst_resolved, status = ctx.resolve_globfilepath(dst)
    error = _checked_db(dst, dst_resolved, status)
    if error is not None:
        return error
    other_resolved = dst_resolved
    if other_dst is not None:
        other_resolved, status = ctx.resolve_globfilepath(other_dst)
        error = _checked_db(other_dst, other_resolved, status, 'other_dst database file')
        if error is not None:
            return error

    same_db = os.path.realpath(other_resolved) == os.path.realpath(dst_resolved)
    sides = [
        ('query', f'query {query!r} ({view})', dst_resolved, query, view),
        ('other_query', f'other_query {other_query!r} ({other_view})', other_resolved, other_query, other_view),
    ]
    with tempfile.TemporaryDirectory(prefix='adare_sqlite_') as workdir:
        snapshots: list[Snapshot] = []
        details: list[str] = []
        try:
            for i, path in enumerate([dst_resolved] if same_db else [dst_resolved, other_resolved]):
                os.mkdir(os.path.join(workdir, str(i)))
                snapshots.append(take_snapshot(path, os.path.join(workdir, str(i))))
                details += snapshots[-1].details('queried snapshot' if i == 0 else 'queried snapshot (other_dst)')
            # every copy is made before any is opened (closing current checkpoints its -wal)
            copies = [snapshots[0 if same_db else i].view_path(side[4]) for i, side in enumerate(sides)]
        except ViewError as e:
            return TestResult.error([str(e)] + details)
        except OSError as e:
            return TestResult.error([f'could not copy the database: {e}'] + details)
        view_details = [f'{side[0]}: {line}' for side, (_, lines) in zip(sides, copies, strict=True) for line in lines]
        values, problems_found = [], []
        for side, (copy, _) in zip(sides, copies, strict=True):
            try:
                rows = fetch(copy, side[3])
            except sqlite3.Error as e:
                return TestResult.error([f'SQLite error executing {side[0]}: {side[3]} - {e}'] + view_details + details)
            value, problem = _single_value(side[1], rows)
            values.append(value)
            if problem is not None:
                problems_found.append(problem)

    context = view_details + details
    if problems_found:
        # an ERROR (several rows) outranks a FAILED (no row), as in compare_pair
        errors = [p for p in problems_found if p.status == StatusEnum.ERROR]
        first = (errors or problems_found)[0]
        return TestResult(status=first.status, details=first.details + context)
    result = compare_pair(sides[0][1], values[0], sides[1][1], values[1], ordered)
    return TestResult(status=result.status, details=list(result.details) + context)


def _free_space_details(space: FreeSpace, matches: list[tuple]) -> list[str]:
    shown = [f'page {r.page} {r.kind} [{r.start}, {r.end}): {n}' for r, n in matches[:MAX_MATCH_DETAILS]]
    if len(matches) > MAX_MATCH_DETAILS:
        shown.append(f'... and {len(matches) - MAX_MATCH_DETAILS} more region(s)')
    freeblocks = space.of_kind('freeblock')
    summary = (
        f'free space: freelist {space.freelist_pages} page(s) ({space.total("freelist")} bytes), '
        f'{len(freeblocks)} freeblock(s) ({space.total("freeblock")} bytes), '
        f'unallocated {space.total("unallocated")} bytes; {space.page_count} page(s) of {space.page_size} bytes'
    )
    return [f"matches: {'; '.join(shown) if shown else 'none'}", summary]


@testfunction(
    name='free_space_pattern_count',
    description='tests how often a text, byte pattern or regex occurs in the free space of an SQLite database (deleted, recoverable data)',
    category=HostModeCategory.FILE_CONTENT,
)
def free_space_pattern_count(
    ctx: TestContext,
    dst: str,
    pattern: str,
    pattern_type: str = 'text',
    encoding: str = 'utf-8',
    region: str = 'all',
    view: str = 'main_file',
    expected_count: int = 1,
    comparison_type: str = 'equals',
):
    r"""Pass when the occurrences of ``pattern`` in the free space of the SQLite database satisfy ``comparison_type``.

    Use for: asserting that a deleted record is still recoverable from the database file
    (``comparison_type: greater_equal``, ``expected_count: 1``) while a query no longer
    returns it (sqlite.row_count with ``expected_count: 0``), or that a delete really erased
    it (``expected_count: 0``, as with ``PRAGMA secure_delete``). The file is parsed per the
    SQLite file format, without SQLite: freelist pages (pages no longer in use, including the
    overflow pages of a deleted large row), freeblocks (freed cells inside a b-tree page)
    and the unallocated space of each b-tree page. Regions never overlap and occurrences
    are counted per region, so a match never spans two regions. SQLite can leave a record in the file twice (the old cell in a
    page it rewrote and a copy in the page that took over the rows), which is then counted
    twice; and it overwrites freed data when it rewrites or merges pages, so a deleted record
    is not always recoverable. Details list which pages and regions matched (absolute
    file offsets) and the size of each kind of free space. To search the whole file use
    binary.pattern_count; live rows are counted there too.

    Free space is not "all stale bytes": a count of 0 here does not prove a deleted value is
    gone from the file. Not covered: the sampled keys in ``sqlite_stat4`` (until the next
    ANALYZE) and the segments of a full-text index (``<name>_data`` of FTS5, ``_segments`` of
    FTS3/4; until a merge or optimize), live rows of ordinary b-trees that a query can read
    (``SELECT ... FROM sqlite_stat4``); the unused tail of an overflow page in use, which
    keeps the old bytes of a page SQLite freed and reused within one transaction (even
    ``secure_delete`` wipes it); the reserved bytes of each page, fragments of fewer than 4
    bytes and bytes after the last complete page; and the ``-wal`` (``view: current`` folds
    it in). Deleted index keys are covered: an index is a b-tree whose interior cells are
    index entries, and deleting one replaces it, so the old cell is free space. Table
    interior pages keep the rowids of deleted rows as dividers (no text; ``secure_delete``
    does not remove them). To assert "gone from the whole file" use text.occurrence_count
    on dst with ``expected_count: 0`` (and on ``<dst>-wal`` when it exists).

    A corrupt header or a broken freelist / freeblock chain (a pointer out of range, a
    cycle, a freelist count that does not match the header) is an error: the free space
    could not be located.

    Args:
        dst: Guest path to the database; a glob must match exactly one file (otherwise an
            error). A missing file is an error. It and any ``-wal``/``-journal`` sidecar are
            copied to a temp dir first; only the copy is read.
        pattern: What to count; must not be empty. Its meaning depends on ``pattern_type``.
        pattern_type: ``text`` (default): ``pattern`` encoded in ``encoding``. ``bytes``:
            ASCII characters stand for their byte, Python escapes (``\x00``) are decoded.
            ``hex``: hex digits, whitespace allowed. ``regex``: an ASCII regular expression
            over the raw bytes (empty matches are not counted). Invalid escapes, hex or
            regexes are an error.
        encoding: Encoding for ``text`` (default ``utf-8``; ``utf-16-le``, ``utf-16-be`` for
            databases with a UTF-16 text encoding).
        region: Which free space is searched: ``all`` (default), ``freelist``, ``freeblocks``
            or ``unallocated``. Other values are an error.
        view: ``main_file`` (default): the main database file as it is, the ``-wal`` left
            out. ``current``: the copy after ``PRAGMA wal_checkpoint(TRUNCATE)``, i.e. with the
            ``-wal`` folded in as SQLite would on a checkpoint. Other values are an error.
        expected_count: Non-negative integer to compare with (default 1); ``0`` asserts
            absence.
        comparison_type: ``equals`` (default), ``greater``, ``less``, ``greater_equal`` or
            ``less_equal``. Use ``greater_equal`` with ``expected_count: 1`` for "at least once".

    Example:
        function: sqlite.free_space_pattern_count
        parameter:
          dst: /data/app/state.db
          pattern: deleted-note-title
          expected_count: 1
          comparison_type: greater_equal
    """
    problems = count_parameter_errors(expected_count, comparison_type)
    if region not in FREE_SPACE_REGIONS:
        problems.append(f"invalid region {region!r} (allowed: {', '.join(FREE_SPACE_REGIONS)})")
    if view not in FREE_SPACE_VIEWS:
        problems.append(f"invalid view {view!r} (allowed: {', '.join(FREE_SPACE_VIEWS)})")
    if isinstance(pattern, str) and ctx.has_placeholders(pattern):
        problems.append(f'pattern {pattern!r} holds a !re or !timestamp placeholder; use pattern_type regex')
    if problems:
        return TestResult.error(problems)
    try:
        compiled = binary.compile_pattern(pattern, pattern_type, encoding)
    except (binary.BinaryParameterError, LookupError, TypeError) as e:
        return TestResult.error([str(e)])

    dst_resolved, status = ctx.resolve_globfilepath(dst)
    error = _checked_db(dst, dst_resolved, status)
    if error is not None:
        return error
    name = os.path.basename(dst_resolved)
    kinds = FREE_SPACE_REGIONS[region]

    with tempfile.TemporaryDirectory(prefix='adare_sqlite_free_') as workdir:
        try:
            snapshot = take_snapshot(dst_resolved, workdir)
        except OSError as e:
            return TestResult.error([f'could not copy the database {dst_resolved}: {e}'])
        snapshot_details = snapshot.details('read snapshot')
        if view == 'current':
            try:
                checkpoint(snapshot.db_copy)
            except sqlite3.Error as e:
                return TestResult.error([f'{name}: SQLite could not checkpoint the copy: {e}'] + snapshot_details)
            view_details = [
                f'view: current (the copy after PRAGMA wal_checkpoint(TRUNCATE), '
                f'parsed {name} sha256={sha256(snapshot.db_copy)})'
            ]
        else:
            view_details = ['view: main_file (the main database file alone, the -wal left out)']
        try:
            with open(snapshot.db_copy, 'rb') as handle:
                space = read_free_space(handle, os.fstat(handle.fileno()).st_size)
                matches = []
                for found in space.of_kind(*kinds):
                    handle.seek(found.start)
                    n = binary.count_pattern(handle.read(found.size), compiled)
                    if n:
                        matches.append((found, n))
        except SqliteFreeSpaceError as e:
            return TestResult.error([f'{name}: {e}'] + view_details + snapshot_details)
        except OSError as e:
            return TestResult.error([f'{name} could not be read: {e}'] + snapshot_details)

    actual = sum(n for _, n in matches)
    ok, message = compare_count(actual, expected_count, comparison_type)
    searched = space.of_kind(*kinds)
    details = [
        f'{actual} occurrence(s) of {pattern_type} {pattern!r} in {len(searched)} free region(s) '
        f'({sum(r.size for r in searched)} bytes; region {region})',
        message,
        *_free_space_details(space, matches),
        *view_details,
        *snapshot_details,
    ]
    return TestResult.success(details) if ok else TestResult.failed(details)


# Host mode pulls these next to dst. Set on the class rather than via a decorator
# argument so this module still loads with older adarelib versions preinstalled in
# guest images (testfunctions are uploaded fresh each run, adarelib is not).
query_result._test_class.host_mode_sidecars = SIDECAR_SUFFIXES
row_count._test_class.host_mode_sidecars = SIDECAR_SUFFIXES
# wal_frame_count reads only the -wal; with dst naming the -wal itself the pull of
# '<dst>-wal' finds nothing, which is harmless.
wal_frame_count._test_class.host_mode_sidecars = (WAL_SUFFIX,)
# values_compare may read a second database: host mode pulls other_dst (and its sidecars) too.
values_compare._test_class.host_mode_sidecars = SIDECAR_SUFFIXES
values_compare._test_class.host_mode_path_params = ('other_dst',)
free_space_pattern_count._test_class.host_mode_sidecars = SIDECAR_SUFFIXES
