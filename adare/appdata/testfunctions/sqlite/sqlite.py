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

# configure logging
import logging
log = logging.getLogger(__name__)

# SQLite keeps committed-but-uncheckpointed changes (WAL mode) or an interrupted
# transaction (rollback journal) in files next to the database; a query without
# them sees stale data. -shm is not copied: it is a derived index that SQLite
# rebuilds from the WAL when the copy is opened.
SIDECAR_SUFFIXES = ('-wal', '-journal')


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
        dst = db_copy + src[len(db_path):]
        try:
            shutil.copyfile(src, dst)
        except FileNotFoundError:
            # a sidecar vanished (e.g. the app checkpointed on close); the stat
            # comparison below reports the snapshot as changed
            continue
        hashes.append(f'{os.path.basename(src)} sha256={_sha256(dst)}')

    after = {suffix: _stat_key(db_path + suffix) for suffix in ('',) + SIDECAR_SUFFIXES}
    return db_copy, hashes, before != after


@testfunction(
    name='query_result',
    description='executes SQL query against SQLite database and validates result',
    category=HostModeCategory.FILE_CONTENT,
)
def query_result(ctx: TestContext, dst: str, query: str, expected_rows: int = None, expected_result: list = None):
    dst_resolved, status = ctx.resolve_globfilepath(dst)
    if not dst_resolved:
        return TestResult.error([f'database file {dst} can\'t be used, because no unambiguous file could be identified (because {status})'])
    if not os.path.isfile(dst_resolved):
        return TestResult.failed([f'database file {dst_resolved} does not exist'])

    log.debug(f'dst database {dst_resolved} will be used for test query_result')

    with tempfile.TemporaryDirectory(prefix='adare_sqlite_') as workdir:
        db_copy, hashes, changed = _snapshot(dst_resolved, workdir)
        snapshot_details = [f'queried snapshot: {h}' for h in hashes]
        if changed:
            snapshot_details.append('warning: database files changed while being copied; the snapshot may be inconsistent')

        try:
            with contextlib.closing(sqlite3.connect(db_copy)) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(query).fetchall()
        except sqlite3.Error as e:
            return TestResult.failed([f"SQLite error executing query: {query} - {e}"] + snapshot_details)

    # Convert to list of dicts for easier comparison
    result = [dict(row) for row in rows]

    # Check expected row count
    if expected_rows is not None and len(result) != expected_rows:
        return TestResult.failed([f'expected {expected_rows} rows, got {len(result)}'] + snapshot_details)

    # Check expected result content
    if expected_result is not None:
        # Check if expected_result has placeholders
        expected_str = str(expected_result)
        if ctx.has_placeholders(expected_str):
            # For complex result comparison with placeholders, convert to string and use placeholder system
            success, message = ctx.handle_placeholders_comparison(str(result), expected_str)
            if not success:
                return TestResult.failed([f'query result placeholder comparison failed: {message}'] + snapshot_details)
        elif result != expected_result:
            return TestResult.failed([f'query result does not match expected result. Got: {result}'] + snapshot_details)

    return TestResult.success([f'query returned {len(result)} rows'] + snapshot_details)


# Host mode pulls these next to dst. Set on the class rather than via a decorator
# argument so this module still loads with older adarelib versions preinstalled in
# guest images (testfunctions are uploaded fresh each run, adarelib is not).
query_result._test_class.host_mode_sidecars = SIDECAR_SUFFIXES
