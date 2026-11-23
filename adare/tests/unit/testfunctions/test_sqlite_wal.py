"""Unit tests for the write-ahead log side of the sqlite collection: the ``wal`` parameter of
sqlite.query_result / sqlite.row_count and sqlite.wal_frame_count.

Databases are built in the test with the stdlib sqlite3 module; evidence files are copied
while the writer connection is still open, as a pull from a running guest yields them.
Runs on the guests' Python 3.10 too (``make test-testfunctions-guest``).
"""

import contextlib
import hashlib
import shutil
import sqlite3
import struct
from pathlib import Path

import pytest

from adarelib.constants import StatusEnum
from adarelib.helper.module import import_module_from_pyfile

pytestmark = pytest.mark.unit

COLLECTIONS = Path(__file__).resolve().parents[3] / 'appdata' / 'testfunctions'
sqlite_module = import_module_from_pyfile(COLLECTIONS / 'sqlite' / 'sqlite.py')
QueryResult = sqlite_module.query_result._test_class
QueryResultParameter = sqlite_module.query_result._parameter_class
RowCount = sqlite_module.row_count._test_class
RowCountParameter = sqlite_module.row_count._parameter_class
WalFrameCount = sqlite_module.wal_frame_count._test_class
WalFrameCountParameter = sqlite_module.wal_frame_count._parameter_class

ALL_ITEMS = 'SELECT id FROM items'


def _count(dst, **params):
    return RowCount(name='t', parameter=RowCountParameter(dst=str(dst), **params)).test()


def _query(dst, **params):
    return QueryResult(name='t', parameter=QueryResultParameter(dst=str(dst), **params)).test()


def _frames(dst, **params):
    return WalFrameCount(name='t', parameter=WalFrameCountParameter(dst=str(dst), **params)).test()


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@contextlib.contextmanager
def _writer(db):
    """A WAL-mode database with auto-checkpoint off; the table is checkpointed, rows are not."""
    conn = sqlite3.connect(str(db))
    try:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA wal_autocheckpoint=0')
        conn.execute('CREATE TABLE items (id INTEGER, name TEXT)')
        conn.commit()
        conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        yield conn
    finally:
        conn.close()


def _insert(conn, *ids, size=10):
    for i in ids:  # one transaction each
        conn.execute('INSERT INTO items VALUES (?, ?)', (i, 'x' * size))
        conn.commit()


def _seize(db, evidence, with_wal=True):
    """Copy the database (and its -wal) into ``evidence`` while the writer is open."""
    evidence.mkdir(exist_ok=True)
    shutil.copyfile(db, evidence / db.name)
    if with_wal:
        shutil.copyfile(f'{db}-wal', evidence / f'{db.name}-wal')
    return evidence / db.name


@pytest.fixture
def wal_only(tmp_path):
    """data.db with one checkpointed row (id 1) and two transactions (ids 2, 3) only in the -wal."""
    db = tmp_path / 'live' / 'data.db'
    db.parent.mkdir()
    with _writer(db) as conn:
        _insert(conn, 1)
        conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        _insert(conn, 2, 3)
        return _seize(db, tmp_path / 'evidence')


# ---------------------------------------------------------------------------
# wal parameter of row_count / query_result
# ---------------------------------------------------------------------------


def test_apply_sees_rows_only_in_the_wal(wal_only):
    result = _count(wal_only, query=ALL_ITEMS, expected_count=3)

    assert result.status == StatusEnum.SUCCESS, result.details
    assert any(d.startswith('queried snapshot: data.db-wal sha256=') for d in result.details)


def test_ignore_queries_the_main_file_alone(wal_only):
    result = _count(wal_only, query=ALL_ITEMS, expected_count=1, wal='ignore')

    assert result.status == StatusEnum.SUCCESS, result.details
    assert "query result: [{'id': 1}]" in result.details
    assert f'wal ignore: not applied: data.db-wal sha256={_sha256(f"{wal_only}-wal")}' in result.details
    assert not any(d.startswith('queried snapshot: data.db-wal') for d in result.details)


def test_row_only_in_wal_is_two_checks(wal_only):
    """The recipe in the docstring: wal=apply finds the row, wal=ignore does not."""
    row = 'SELECT id FROM items WHERE id = 3'

    in_db = _count(wal_only, query=row, expected_count=1, comparison_type='greater_equal')
    in_main_file = _count(wal_only, query=row, expected_count=0, wal='ignore')
    checkpointed = _count(wal_only, query='SELECT id FROM items WHERE id = 1', expected_count=0, wal='ignore')

    assert in_db.status == StatusEnum.SUCCESS, in_db.details
    assert in_main_file.status == StatusEnum.SUCCESS, in_main_file.details
    assert checkpointed.status == StatusEnum.FAILED, checkpointed.details  # row 1 is in the main file


def test_query_result_ignore(wal_only):
    result = _query(wal_only, query='SELECT id FROM items ORDER BY id', expected_result=[{'id': 1}], wal='ignore')
    applied = _query(wal_only, query='SELECT id FROM items ORDER BY id', expected_count=3)

    assert result.status == StatusEnum.SUCCESS, result.details
    assert applied.status == StatusEnum.SUCCESS, applied.details


def test_ignore_leaves_the_evidence_untouched(wal_only):
    before = {p.name: _sha256(p) for p in wal_only.parent.iterdir()}

    _count(wal_only, query=ALL_ITEMS, expected_count=1, wal='ignore')
    _count(wal_only, query=ALL_ITEMS, expected_count=3)

    assert {p.name: _sha256(p) for p in wal_only.parent.iterdir()} == before


def test_ignore_without_a_wal_file(tmp_path):
    db = tmp_path / 'live' / 'data.db'
    db.parent.mkdir()
    with _writer(db) as conn:
        _insert(conn, 1)
        conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        evidence = _seize(db, tmp_path / 'evidence', with_wal=False)

    result = _count(evidence, query=ALL_ITEMS, expected_count=1, wal='ignore')

    assert result.status == StatusEnum.SUCCESS, result.details
    assert 'wal ignore: no data.db-wal next to the database' in result.details


def test_ignore_still_rolls_back_a_hot_journal(tmp_path):
    """wal=ignore only leaves out the -wal: an interrupted transaction is never seen."""
    db = tmp_path / 'live' / 'data.db'
    db.parent.mkdir()
    conn = sqlite3.connect(str(db), isolation_level=None)
    try:
        conn.execute('PRAGMA journal_mode=DELETE')
        conn.execute('CREATE TABLE items (id INTEGER, name TEXT)')
        conn.executemany('INSERT INTO items VALUES (?, ?)', [(i, 'kept' + 'x' * 1000) for i in range(200)])
        conn.execute('PRAGMA cache_size=1')  # spill the uncommitted pages into the database file
        conn.execute('BEGIN')
        conn.execute("UPDATE items SET name = 'changed'")
        evidence = _seize(db, tmp_path / 'evidence', with_wal=False)
        shutil.copyfile(f'{db}-journal', f'{evidence}-journal')
        conn.execute('ROLLBACK')
    finally:
        conn.close()
    changed = "SELECT id FROM items WHERE name = 'changed'"
    main_only = tmp_path / 'main_only.db'
    shutil.copyfile(evidence, main_only)
    # sanity check: without its journal the file shows the uncommitted update
    assert _count(main_only, query=changed, expected_count=1, comparison_type='greater_equal').status == (
        StatusEnum.SUCCESS
    )

    for wal in ('apply', 'ignore'):
        result = _count(evidence, query=changed, expected_count=0, wal=wal)

        assert result.status == StatusEnum.SUCCESS, (wal, result.details)
        assert any(d.startswith('queried snapshot: data.db-journal sha256=') for d in result.details)
    assert Path(f'{evidence}-journal').exists()  # the original journal was not rolled back


@pytest.mark.parametrize('wal', ['skip', 'APPLY', '', None, True])
def test_invalid_wal_is_an_error(wal_only, wal):
    counted = _count(wal_only, query=ALL_ITEMS, expected_count=3, wal=wal)
    queried = _query(wal_only, query=ALL_ITEMS, wal=wal)

    for result in (counted, queried):
        assert result.status == StatusEnum.ERROR, result.details
        assert 'invalid wal' in result.details[0]


def test_ignore_on_missing_database_is_an_error(tmp_path):
    result = _count(tmp_path / 'absent.db', query=ALL_ITEMS, expected_count=0, wal='ignore')

    assert result.status == StatusEnum.ERROR, result.details


# ---------------------------------------------------------------------------
# wal_frame_count
# ---------------------------------------------------------------------------


def test_counts_valid_and_commit_frames(wal_only):
    commits = _frames(wal_only, expected_count=2, frames='commits')
    valid = _frames(wal_only, expected_count=2, frames='valid', comparison_type='greater_equal')
    stale = _frames(wal_only, expected_count=0, frames='stale')

    for result in (commits, valid, stale):
        assert result.status == StatusEnum.SUCCESS, result.details
    assert commits.details[0] == 'commits frames: 2'
    assert any(d.startswith('frames: all=') and d.endswith('commits=2 stale=0') for d in commits.details)
    assert any('little-endian checksums, page size ' in d for d in commits.details)
    assert f'read snapshot: data.db-wal sha256={_sha256(f"{wal_only}-wal")}' in commits.details


def test_default_counts_valid_frames(wal_only):
    result = _frames(wal_only, expected_count=0)

    assert result.status == StatusEnum.FAILED, result.details
    assert result.details[0].startswith('valid frames: ')
    assert 'does not hold' in result.details[1]


@pytest.mark.parametrize(
    ('expected_count', 'comparison_type', 'status'),
    [
        (2, 'equals', StatusEnum.SUCCESS),
        (1, 'greater', StatusEnum.SUCCESS),
        (2, 'greater', StatusEnum.FAILED),
        (3, 'less', StatusEnum.SUCCESS),
        (2, 'less_equal', StatusEnum.SUCCESS),
        (3, 'greater_equal', StatusEnum.FAILED),
    ],
)
def test_comparison_types(wal_only, expected_count, comparison_type, status):
    result = _frames(wal_only, expected_count=expected_count, comparison_type=comparison_type, frames='commits')

    assert result.status == status, result.details


def test_dst_may_name_the_wal_itself(wal_only):
    result = _frames(f'{wal_only}-wal', expected_count=2, frames='commits')

    assert result.status == StatusEnum.SUCCESS, result.details


def test_glob_dst(wal_only):
    result = _frames(wal_only.parent / 'data.d?', expected_count=2, frames='commits')

    assert result.status == StatusEnum.SUCCESS, result.details


def test_stale_frames_after_a_wal_reset(tmp_path):
    db = tmp_path / 'live' / 'data.db'
    db.parent.mkdir()
    with _writer(db) as conn:
        _insert(conn, 1, 2, 3, 4, size=3000)
        assert conn.execute('PRAGMA wal_checkpoint(RESTART)').fetchone()[0] == 0
        _insert(conn, 5)  # restarts the WAL from its start; older frames stay behind it
        evidence = _seize(db, tmp_path / 'evidence')

    commits = _frames(evidence, expected_count=1, frames='commits')
    stale = _frames(evidence, expected_count=1, frames='stale', comparison_type='greater_equal')
    everything = _frames(evidence, expected_count=4, frames='all', comparison_type='greater_equal')

    for result in (commits, stale, everything):
        assert result.status == StatusEnum.SUCCESS, result.details
    # rows 1-4 were checkpointed, row 5 is the only one that is in the WAL alone
    assert _count(evidence, query=ALL_ITEMS, expected_count=4, wal='ignore').status == StatusEnum.SUCCESS


def test_truncated_wal_has_no_frames(wal_only, tmp_path):
    Path(f'{wal_only}-wal').write_bytes(b'')

    for frames in ('valid', 'commits', 'all', 'stale'):
        result = _frames(wal_only, expected_count=0, frames=frames)

        assert result.status == StatusEnum.SUCCESS, result.details
    assert 'WAL is empty (0 bytes)' in result.details


def test_missing_wal_is_zero_frames(wal_only):
    Path(f'{wal_only}-wal').unlink()

    zero = _frames(wal_only, expected_count=0)
    some = _frames(wal_only, expected_count=1, comparison_type='greater_equal', frames='commits')

    assert zero.status == StatusEnum.SUCCESS, zero.details
    assert zero.details[0] == 'valid frames: 0 (no data.db-wal next to the database)'
    assert some.status == StatusEnum.FAILED, some.details


def test_missing_database_is_an_error(tmp_path):
    result = _frames(tmp_path / 'absent.db', expected_count=0)

    assert result.status == StatusEnum.ERROR, result.details
    assert 'does not exist' in result.details[0]


def test_missing_wal_named_as_dst_is_an_error(wal_only):
    Path(f'{wal_only}-wal').unlink()

    result = _frames(f'{wal_only}-wal', expected_count=0)

    assert result.status == StatusEnum.ERROR, result.details


@pytest.mark.parametrize(
    ('header', 'message'),
    [
        (b'\x37\x7f\x06', 'truncated'),
        (b'\0' * 32, 'not an SQLite WAL'),
        (struct.pack('>8I', 0x377F0682, 3007000, 4096, 0, 1, 2, 0, 0), 'header checksum mismatch'),
    ],
    ids=['short', 'magic', 'checksum'],
)
def test_corrupt_header_is_an_error(wal_only, header, message):
    Path(f'{wal_only}-wal').write_bytes(header)

    result = _frames(wal_only, expected_count=0)

    assert result.status == StatusEnum.ERROR, result.details
    assert message in result.details[0]
    assert any(d.startswith('read snapshot: data.db-wal sha256=') for d in result.details)


@pytest.mark.parametrize(
    ('params', 'message'),
    [
        ({'expected_count': -1}, 'expected_count'),
        ({'expected_count': '2'}, 'expected_count'),
        ({'expected_count': 1, 'comparison_type': 'about'}, 'comparison_type'),
        ({'expected_count': 1, 'frames': 'pages'}, 'invalid frames'),
    ],
)
def test_invalid_parameters_are_errors(wal_only, params, message):
    result = _frames(wal_only, **params)

    assert result.status == StatusEnum.ERROR, result.details
    assert message in result.details[0]


def test_wal_is_not_modified(wal_only):
    before = {p.name: _sha256(p) for p in wal_only.parent.iterdir()}

    _frames(wal_only, expected_count=2, frames='commits')

    assert {p.name: _sha256(p) for p in wal_only.parent.iterdir()} == before


def test_declares_wal_sidecar_for_host_mode():
    assert WalFrameCount.host_mode_sidecars == ('-wal',)
    assert QueryResult.host_mode_sidecars == RowCount.host_mode_sidecars == ('-wal', '-journal')
