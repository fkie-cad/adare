# external imports
import contextlib
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

# wal parameter of query_result / row_count: 'apply' queries the database as SQLite sees it
# (the WAL replayed), 'ignore' the main database file alone. 'ignore' only leaves out the
# -wal: a -journal is still copied, so a hot rollback journal is rolled back and the query
# sees the last committed state, never the half-written pages of an interrupted transaction.
WAL_MODES = ('apply', 'ignore')

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


def _snapshot(db_path: str, workdir: str, suffixes: tuple[str, ...] = SIDECAR_SUFFIXES) -> tuple[str, list[str], bool]:
    """Copy the database and those of its sidecars ``suffixes`` names that exist into workdir.

    The original files are only ever read, never opened by SQLite, so querying
    cannot checkpoint, roll back or otherwise modify them. A sidecar left out is not
    in workdir either, so SQLite opening the copy cannot pick it up.

    :return: (path of the copied database, one 'name sha256=...' entry per copied
             file, whether the source files changed while being copied)
    """
    sources = [db_path] + [db_path + s for s in suffixes if os.path.isfile(db_path + s)]
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


def _wal_parameter_errors(wal) -> list[str]:
    if wal not in WAL_MODES:
        return [f"invalid wal {wal!r} (allowed: {', '.join(WAL_MODES)})"]
    return []


def _ignored_wal_detail(db_path: str) -> str:
    """What wal=ignore left out, for the result details."""
    name = os.path.basename(db_path) + WAL_SUFFIX
    try:
        return f'wal ignore: not applied: {name} sha256={_sha256(db_path + WAL_SUFFIX)}'
    except FileNotFoundError:
        return f'wal ignore: no {name} next to the database'
    except OSError as e:
        return f'wal ignore: not applied: {name} (not hashed: {e})'


def _run_query(
    ctx: TestContext, dst: str, query: str, wal: str = 'apply'
) -> tuple[list[dict], list[str], TestResult | None]:
    """Run ``query`` on a snapshot of the database ``dst`` (see :func:`_snapshot`).

    ``wal='ignore'`` leaves the -wal out of the snapshot: the copy of a database whose
    header says WAL mode then opens with an empty WAL, i.e. as the main file alone.

    :return: (rows as ``{column: value}`` dicts, ``queried snapshot`` details, an ERROR
             result when the database cannot be found or the query fails, else None)
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

    log.debug(f'dst database {dst_resolved} will be used for query {query!r}')

    suffixes = SIDECAR_SUFFIXES if wal == 'apply' else tuple(s for s in SIDECAR_SUFFIXES if s != WAL_SUFFIX)
    with tempfile.TemporaryDirectory(prefix='adare_sqlite_') as workdir:
        db_copy, hashes, changed = _snapshot(dst_resolved, workdir, suffixes)
        snapshot_details = [f'queried snapshot: {h}' for h in hashes]
        if wal == 'ignore':
            snapshot_details.append(_ignored_wal_detail(dst_resolved))
        if changed:
            snapshot_details.append(
                'warning: database files changed while being copied; the snapshot may be inconsistent'
            )
        try:
            with contextlib.closing(sqlite3.connect(db_copy)) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(query).fetchall()
        except sqlite3.Error as e:
            return (
                [],
                snapshot_details,
                TestResult.error([f"SQLite error executing query: {query} - {e}"] + snapshot_details),
            )
    return [dict(row) for row in rows], snapshot_details, None


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
    wal: str = 'apply',
):
    """Pass when ``query`` runs on the SQLite database and its result matches the expectations.

    Use for: asserting that a row was written, changed or removed; with ``wal: ignore``,
    what the main database file alone holds (a row only in the write-ahead log, not yet
    checkpointed: one test with ``wal: apply`` finds it, a second with ``wal: ignore`` does
    not). The original file is never opened: ``dst`` and any ``-wal``/``-journal``
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
        wal: ``apply`` (default) queries the database as SQLite sees it, the ``-wal``
            replayed; ``ignore`` leaves the ``-wal`` out of the copy and queries the main
            file alone (details: ``wal ignore: not applied: <file> sha256=...``). A
            ``-journal`` is copied either way, so a hot rollback journal is rolled back and
            an interrupted transaction is never seen. Other values are an error.

    Example:
        function: sqlite.query_result
        parameter:
          dst: /home/user/data/app.db
          query: SELECT name FROM items WHERE name LIKE '%example%'
          expected_count: 0
    """
    problems = _wal_parameter_errors(wal)
    if expected_count is not None or comparison_type != 'equals':
        problems += count_parameter_errors(expected_count, comparison_type)
    if problems:
        return TestResult.error(problems)

    result, snapshot_details, error = _run_query(ctx, dst, query, wal)
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
    wal: str = 'apply',
):
    """Pass when the number of rows ``query`` returns on the SQLite database satisfies ``comparison_type``.

    Use for: asserting how many records an action left behind (exactly one history entry
    for a URL); asserting a record is gone: ``expected_count: 0``; asserting a row is only in
    the write-ahead log, not yet checkpointed into the main file: two tests, ``wal: apply``
    with ``expected_count: 1`` and ``comparison_type: greater_equal``, and ``wal: ignore``
    with ``expected_count: 0``. Queried like
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
        wal: ``apply`` (default) counts in the database as SQLite sees it, the ``-wal``
            replayed; ``ignore`` counts in the main file alone (the ``-wal`` is not copied, a
            ``-journal`` still is, so a hot rollback journal is rolled back). Other values
            are an error.

    Example:
        function: sqlite.row_count
        parameter:
          dst: /home/user/data/app.db
          query: SELECT id FROM items WHERE name LIKE '%example%'
          expected_count: 1
    """
    problems = count_parameter_errors(expected_count, comparison_type) + _wal_parameter_errors(wal)
    if not isinstance(query, str) or not query.strip():
        problems.append(f'query must be a non-empty SQL string, got {query!r}')
    if problems:
        return TestResult.error(problems)

    result, snapshot_details, error = _run_query(ctx, dst, query, wal)
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
    To find which rows live only in the WAL use sqlite.row_count with ``wal: ignore``.

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
