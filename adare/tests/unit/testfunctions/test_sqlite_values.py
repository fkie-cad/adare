"""Unit tests for ``view: commit:N`` (sqlite.query_result / row_count / values_compare) and
sqlite.values_compare.

Databases are built in the test with the stdlib sqlite3 module; WAL evidence is copied while
the writer connection is still open (auto-checkpoint off), as a pull from a running guest
yields it. Runs on the guests' Python 3.10 too (``make test-testfunctions-guest``).
"""

import contextlib
import hashlib
import shutil
import sqlite3
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
ValuesCompare = sqlite_module.values_compare._test_class
ValuesCompareParameter = sqlite_module.values_compare._parameter_class

ALL_ITEMS = 'SELECT id FROM items'
COUNT = 'SELECT count(*) FROM items'


def _count(dst, **params):
    return RowCount(name='t', parameter=RowCountParameter(dst=str(dst), **params)).test()


def _query(dst, **params):
    return QueryResult(name='t', parameter=QueryResultParameter(dst=str(dst), **params)).test()


def _compare(dst, **params):
    return ValuesCompare(name='t', parameter=ValuesCompareParameter(dst=str(dst), **params)).test()


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@contextlib.contextmanager
def _writer(db):
    """A WAL-mode database with auto-checkpoint off; the table is checkpointed, rows are not."""
    conn = sqlite3.connect(str(db))
    try:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA wal_autocheckpoint=0')
        conn.execute('CREATE TABLE items (id INTEGER, name TEXT, created INTEGER)')
        conn.commit()
        conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        yield conn
    finally:
        conn.close()


def _seize(db, evidence, with_wal=True):
    evidence.mkdir(exist_ok=True)
    shutil.copyfile(db, evidence / db.name)
    if with_wal:
        shutil.copyfile(f'{db}-wal', evidence / f'{db.name}-wal')
    return evidence / db.name


@pytest.fixture
def three_commits(tmp_path):
    """state.db with row 1 checkpointed and three transactions only in the -wal:
    insert 2, insert 3, rename 1."""
    db = tmp_path / 'live' / 'state.db'
    db.parent.mkdir()
    with _writer(db) as conn:
        conn.execute("INSERT INTO items VALUES (1, 'alpha', 1700000000)")
        conn.commit()
        conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        conn.execute("INSERT INTO items VALUES (2, 'beta', 1700000060)")
        conn.commit()
        conn.execute("INSERT INTO items VALUES (3, 'gamma', 1700000120)")
        conn.commit()
        conn.execute("UPDATE items SET name = 'alpha2' WHERE id = 1")
        conn.commit()
        return _seize(db, tmp_path / 'evidence')


# ---------------------------------------------------------------------------
# view: commit:N
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ('view', 'expected'),
    [('commit:0', 1), ('commit:1', 2), ('commit:2', 3), ('commit:3', 3), ('commit:-1', 3), ('commit:-3', 2)],
)
def test_commit_view_counts_rows_after_that_transaction(three_commits, view, expected):
    result = _count(three_commits, query=ALL_ITEMS, expected_count=expected, view=view)

    assert result.status == StatusEnum.SUCCESS, result.details


def test_commit_views_differ_from_current(three_commits):
    first = _query(three_commits, query='SELECT id, name FROM items ORDER BY id', view='commit:1')
    second = _query(three_commits, query='SELECT id, name FROM items ORDER BY id', view='commit:2')
    third = _query(three_commits, query="SELECT id FROM items WHERE name = 'alpha2'", view='commit:3')
    current = _query(three_commits, query="SELECT id FROM items WHERE name = 'alpha2'", expected_count=1)

    assert "query result: [{'id': 1, 'name': 'alpha'}, {'id': 2, 'name': 'beta'}]" in first.details
    assert any("{'id': 3, 'name': 'gamma'}" in d for d in second.details)
    assert "query result: [{'id': 1}]" in third.details
    assert current.status == StatusEnum.SUCCESS, current.details


def test_commit_view_details_name_the_frame_and_wal(three_commits):
    result = _count(three_commits, query=ALL_ITEMS, expected_count=3, view='commit:2')

    wal_hash = _sha256(f'{three_commits}-wal')
    assert result.status == StatusEnum.SUCCESS, result.details
    view_line = next(d for d in result.details if d.startswith('view: commit:2'))
    assert 'replayed through commit 2 of 3, WAL frame ' in view_line
    assert any(d.startswith(f'wal: state.db-wal sha256={wal_hash} (truncated after frame ') for d in result.details)


def test_commit_0_is_the_main_file(three_commits):
    result = _query(three_commits, query=ALL_ITEMS, view='commit:0')

    assert "query result: [{'id': 1}]" in result.details
    assert 'view: commit:0 (the main database file alone, the -wal left out)' in result.details


@pytest.mark.parametrize('view', ['commit:4', 'commit:-4', 'commit:99'])
def test_commit_out_of_range_is_an_error(three_commits, view):
    result = _count(three_commits, query=ALL_ITEMS, expected_count=0, comparison_type='greater_equal', view=view)

    assert result.status == StatusEnum.ERROR, result.details
    assert 'holds 3 commit(s)' in result.details[0]


@pytest.mark.parametrize('view', ['commit:', 'commit:x', 'commit:1.5', 'commits:1'])
def test_malformed_commit_view_is_an_error(three_commits, view):
    result = _count(three_commits, query=ALL_ITEMS, expected_count=1, view=view)

    assert result.status == StatusEnum.ERROR, result.details
    assert 'invalid view' in result.details[0]


def test_without_a_wal_only_commit_0_exists(tmp_path):
    db = tmp_path / 'live' / 'state.db'
    db.parent.mkdir()
    with _writer(db) as conn:
        conn.execute("INSERT INTO items VALUES (1, 'alpha', 0)")
        conn.commit()
        conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        evidence = _seize(db, tmp_path / 'evidence', with_wal=False)

    zero = _count(evidence, query=ALL_ITEMS, expected_count=1, view='commit:0')
    one = _count(evidence, query=ALL_ITEMS, expected_count=1, view='commit:1')
    last = _count(evidence, query=ALL_ITEMS, expected_count=1, view='commit:-1')

    assert zero.status == StatusEnum.SUCCESS, zero.details
    assert one.status == StatusEnum.ERROR, one.details
    assert last.status == StatusEnum.ERROR, last.details
    assert 'no state.db-wal next to the database' in one.details[0]


def test_empty_wal_has_no_commits(tmp_path):
    db = tmp_path / 'live' / 'state.db'
    db.parent.mkdir()
    with _writer(db) as conn:
        conn.execute("INSERT INTO items VALUES (1, 'alpha', 0)")
        conn.commit()
        conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        evidence = _seize(db, tmp_path / 'evidence')
    assert Path(f'{evidence}-wal').stat().st_size == 0

    result = _count(evidence, query=ALL_ITEMS, expected_count=1, view='commit:1')

    assert result.status == StatusEnum.ERROR, result.details
    assert 'holds 0 commit(s)' in result.details[0]


def test_corrupt_wal_is_an_error_for_commit_views(three_commits):
    Path(f'{three_commits}-wal').write_bytes(b'\x00' * 64)

    result = _count(three_commits, query=ALL_ITEMS, expected_count=1, view='commit:1')

    assert result.status == StatusEnum.ERROR, result.details
    assert 'not an SQLite WAL' in result.details[0]


def test_commit_views_leave_the_evidence_untouched(three_commits):
    before = {p.name: _sha256(p) for p in three_commits.parent.iterdir()}

    for view in ('commit:0', 'commit:1', 'commit:-1'):
        _count(three_commits, query=ALL_ITEMS, expected_count=0, comparison_type='greater_equal', view=view)

    assert {p.name: _sha256(p) for p in three_commits.parent.iterdir()} == before


# ---------------------------------------------------------------------------
# sqlite.values_compare
# ---------------------------------------------------------------------------


def test_wal_adds_two_rows_in_one_check(three_commits):
    result = _compare(three_commits, query=COUNT, view='current', other_view='main_file', offset=2)

    assert result.status == StatusEnum.SUCCESS, result.details
    assert result.details[0] == "query 'SELECT count(*) FROM items' (current) = '3', " + (
        "other_query 'SELECT count(*) FROM items' (main_file) = '1'"
    )
    assert any(d.startswith('other_query: wal: state.db-wal sha256=') for d in result.details)


def test_values_compare_mismatch_fails(three_commits):
    result = _compare(three_commits, query=COUNT, view='current', other_view='main_file', offset=1)

    assert result.status == StatusEnum.FAILED, result.details


def test_one_snapshot_for_both_sides(three_commits, monkeypatch):
    copied = []
    original_copyfile = shutil.copyfile

    def counting_copyfile(src, dst, *args, **kwargs):
        copied.append(Path(src).resolve())
        return original_copyfile(src, dst, *args, **kwargs)

    monkeypatch.setattr(shutil, 'copyfile', counting_copyfile)

    result = _compare(three_commits, query=COUNT, view='commit:2', other_view='commit:1', offset=1)

    assert result.status == StatusEnum.SUCCESS, result.details
    evidence = three_commits.resolve().parent
    assert sorted(p.name for p in copied if p.parent == evidence) == ['state.db', 'state.db-wal']


def test_other_query_compares_timestamps(three_commits):
    result = _compare(
        three_commits,
        query='SELECT created FROM items WHERE id = 3',
        other_query='SELECT created FROM items WHERE id = 2',
        comparison_type='greater',
        timestamp_epoch=1970,
    )

    assert result.status == StatusEnum.SUCCESS, result.details


def test_other_dst(three_commits, tmp_path):
    other = tmp_path / 'other' / 'state.db'
    other.parent.mkdir()
    with contextlib.closing(sqlite3.connect(str(other))) as conn:
        conn.execute('CREATE TABLE items (id INTEGER, name TEXT, created INTEGER)')
        conn.executemany('INSERT INTO items VALUES (?, ?, 0)', [(1, 'a'), (2, 'b')])
        conn.commit()

    result = _compare(three_commits, query=COUNT, other_dst=str(other), offset=1)

    assert result.status == StatusEnum.SUCCESS, result.details
    assert any(d.startswith('queried snapshot: state.db-wal sha256=') for d in result.details)
    assert any(d.startswith('queried snapshot (other_dst): state.db sha256=') for d in result.details)


def test_no_row_fails(three_commits):
    result = _compare(three_commits, query='SELECT id FROM items WHERE id = 42', other_query=COUNT)

    assert result.status == StatusEnum.FAILED, result.details
    assert result.details[0] == "query 'SELECT id FROM items WHERE id = 42' (current) returned no row"


def test_two_rows_are_an_error(three_commits):
    result = _compare(three_commits, query=ALL_ITEMS, other_query=COUNT)

    assert result.status == StatusEnum.ERROR, result.details
    assert 'returned 3 rows' in result.details[0]


def test_two_rows_outrank_no_row(three_commits):
    result = _compare(three_commits, query='SELECT id FROM items WHERE id = 42', other_query=ALL_ITEMS)

    assert result.status == StatusEnum.ERROR, result.details


def test_bad_sql_is_an_error(three_commits):
    result = _compare(three_commits, query=COUNT, other_query='SELECT nope FROM missing')

    assert result.status == StatusEnum.ERROR, result.details
    assert result.details[0].startswith('SQLite error executing other_query')


def test_null_value_is_an_error(three_commits):
    result = _compare(three_commits, query='SELECT NULL', other_query=COUNT)

    assert result.status == StatusEnum.ERROR, result.details


def test_commit_out_of_range_is_an_error_in_values_compare(three_commits):
    result = _compare(three_commits, query=COUNT, other_view='commit:7')

    assert result.status == StatusEnum.ERROR, result.details
    assert 'holds 3 commit(s)' in result.details[0]


@pytest.mark.parametrize(
    'params',
    [
        {'view': 'wal_added'},
        {'other_view': 'wal_removed'},
        {'other_view': 'latest'},
        {'query': ''},
        {'other_query': '  '},
        {'other_dst': ''},
        {'comparison_type': 'roughly'},
        {'value_type': 'text'},
        {'timestamp_unit': 'ms'},
    ],
)
def test_invalid_parameters_are_an_error(three_commits, params):
    result = _compare(three_commits, **{'query': COUNT, **params})

    assert result.status == StatusEnum.ERROR, result.details


def test_missing_other_dst_is_an_error(three_commits, tmp_path):
    result = _compare(three_commits, query=COUNT, other_dst=str(tmp_path / 'missing.db'))

    assert result.status == StatusEnum.ERROR, result.details
    assert result.details[0] == f'other_dst database file {tmp_path / "missing.db"} does not exist'


def test_values_compare_leaves_the_evidence_untouched(three_commits):
    before = {p.name: _sha256(p) for p in three_commits.parent.iterdir()}

    _compare(three_commits, query=COUNT, view='current', other_view='main_file', offset=2)

    assert {p.name: _sha256(p) for p in three_commits.parent.iterdir()} == before


def test_host_mode_pulls_other_dst_and_sidecars():
    assert ValuesCompare.host_mode_sidecars == ('-wal', '-journal')
    assert ValuesCompare.host_mode_path_params == ('other_dst',)
