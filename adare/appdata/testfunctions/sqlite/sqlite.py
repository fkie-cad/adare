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
from adarelib.testset.structured import compare_count, count_parameter_errors

# configure logging
import logging

log = logging.getLogger(__name__)

# SQLite keeps committed-but-uncheckpointed changes (WAL mode) or an interrupted
# transaction (rollback journal) in files next to the database; a query without
# them sees stale data. -shm is not copied: it is a derived index that SQLite
# rebuilds from the WAL when the copy is opened.
SIDECAR_SUFFIXES = ('-wal', '-journal')

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


def _run_query(ctx: TestContext, dst: str, query: str) -> tuple[list[dict], list[str], TestResult | None]:
    """Run ``query`` on a snapshot of the database ``dst`` (see :func:`_snapshot`).

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

    with tempfile.TemporaryDirectory(prefix='adare_sqlite_') as workdir:
        db_copy, hashes, changed = _snapshot(dst_resolved, workdir)
        snapshot_details = [f'queried snapshot: {h}' for h in hashes]
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
):
    """Pass when ``query`` runs on the SQLite database and its result matches the expectations.

    Use for: asserting that a row was written, changed or removed. The original file is never opened: ``dst`` and any ``-wal``/``-journal``
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

    Example:
        function: sqlite.query_result
        parameter:
          dst: /home/user/data/app.db
          query: SELECT name FROM items WHERE name LIKE '%example%'
          expected_count: 0
    """
    if expected_count is not None or comparison_type != 'equals':
        problems = count_parameter_errors(expected_count, comparison_type)
        if problems:
            return TestResult.error(problems)

    result, snapshot_details, error = _run_query(ctx, dst, query)
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


# Host mode pulls these next to dst. Set on the class rather than via a decorator
# argument so this module still loads with older adarelib versions preinstalled in
# guest images (testfunctions are uploaded fresh each run, adarelib is not).
query_result._test_class.host_mode_sidecars = SIDECAR_SUFFIXES
