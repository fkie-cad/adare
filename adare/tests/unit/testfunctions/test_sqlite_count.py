"""Unit tests for sqlite.row_count (test_sqlite.py covers sqlite.query_result).

Runs on the guests' Python 3.10 too (``make test-testfunctions-guest``).
"""

import sqlite3
from pathlib import Path

import pytest

from adarelib.constants import StatusEnum
from adarelib.helper.module import import_module_from_pyfile

pytestmark = pytest.mark.unit

COLLECTIONS = Path(__file__).resolve().parents[3] / 'appdata' / 'testfunctions'
sqlite_module = import_module_from_pyfile(COLLECTIONS / 'sqlite' / 'sqlite.py')
RowCount = sqlite_module.row_count._test_class
RowCountParameter = sqlite_module.row_count._parameter_class


def _count(dst, **params):
    return RowCount(name='t', parameter=RowCountParameter(dst=str(dst), **params)).test()


@pytest.fixture
def db(create_sqlite_db):
    return create_sqlite_db(
        'items.db',
        'CREATE TABLE test_table (id INTEGER, name TEXT)',
        [(1, 'report.txt'), (2, 'notes.txt'), (3, 'report.txt')],
    )


@pytest.mark.parametrize(
    ('query', 'count'),
    [
        ('SELECT * FROM test_table', 3),
        ("SELECT id FROM test_table WHERE name = 'report.txt'", 2),
        ("SELECT id FROM test_table WHERE name = 'absent.txt'", 0),
        ('SELECT COUNT(*) FROM test_table', 1),  # one row holding the number
    ],
)
def test_counts_returned_rows(db, query, count):
    result = _count(db, query=query, expected_count=count)

    assert result.status == StatusEnum.SUCCESS, result.details
    assert result.details[0] == f'query returned {count} rows'
    assert any(d.startswith('query result: ') for d in result.details)
    assert any(d.startswith('queried snapshot: items.db sha256=') for d in result.details)


def test_mismatch_fails_with_rows_and_snapshot(db):
    result = _count(db, query="SELECT name FROM test_table WHERE name = 'report.txt'", expected_count=1)

    assert result.status == StatusEnum.FAILED, result.details
    assert 'count 2 == 1 does not hold' in result.details[1]
    assert "query result: [{'name': 'report.txt'}, {'name': 'report.txt'}]" in result.details
    assert any(d.startswith('queried snapshot: ') for d in result.details)


@pytest.mark.parametrize(
    ('expected_count', 'comparison_type', 'status'),
    [
        (3, 'equals', StatusEnum.SUCCESS),
        (2, 'equals', StatusEnum.FAILED),
        (2, 'greater', StatusEnum.SUCCESS),
        (3, 'greater', StatusEnum.FAILED),
        (4, 'less', StatusEnum.SUCCESS),
        (3, 'greater_equal', StatusEnum.SUCCESS),
        (2, 'less_equal', StatusEnum.FAILED),
    ],
)
def test_comparison_types(db, expected_count, comparison_type, status):
    result = _count(
        db, query='SELECT * FROM test_table', expected_count=expected_count, comparison_type=comparison_type
    )

    assert result.status == status, result.details


@pytest.mark.parametrize(
    'params',
    [
        {'query': 'SELECT * FROM test_table', 'expected_count': -1},
        {'query': 'SELECT * FROM test_table', 'expected_count': 'two'},
        {'query': 'SELECT * FROM test_table', 'expected_count': True},
        {'query': 'SELECT * FROM test_table', 'expected_count': 1, 'comparison_type': 'roughly'},
        {'query': '', 'expected_count': 1},
        {'query': 'SELEC * FROM test_table', 'expected_count': 1},
        {'query': 'SELECT * FROM no_such_table', 'expected_count': 0},
    ],
)
def test_bad_parameters_and_sql_errors_are_errors(db, params):
    # ERROR, not FAILED: expect_to_fail inverts only SUCCESS/FAILED
    assert _count(db, **params).status == StatusEnum.ERROR


def test_missing_database_is_an_error(tmp_path):
    result = _count(tmp_path / 'missing.db', query='SELECT 1', expected_count=0)

    assert result.status == StatusEnum.ERROR
    assert 'does not exist' in result.details[0]


@pytest.mark.parametrize('pattern', ['nothing*.db', 'a*.db'])
def test_glob_without_unique_match_is_an_error(tmp_path, pattern):
    for name in ('a1.db', 'a2.db'):
        sqlite3.connect(str(tmp_path / name)).close()

    assert _count(tmp_path / pattern, query='SELECT 1', expected_count=1).status == StatusEnum.ERROR


def test_uncheckpointed_wal_rows_are_counted_and_the_original_is_untouched(tmp_path):
    db_path = tmp_path / 'wal.db'
    writer = sqlite3.connect(str(db_path))
    writer.execute('PRAGMA journal_mode=WAL')
    writer.execute('PRAGMA wal_autocheckpoint=0')
    writer.execute('CREATE TABLE items (name TEXT)')
    writer.commit()
    writer.execute("INSERT INTO items VALUES ('in-wal')")
    writer.commit()  # stays in -wal while this connection is open
    try:
        before = db_path.read_bytes()

        result = _count(db_path, query="SELECT * FROM items WHERE name = 'in-wal'", expected_count=1)

        assert result.status == StatusEnum.SUCCESS, result.details
        assert any(d.startswith('queried snapshot: wal.db-wal sha256=') for d in result.details)
        assert db_path.read_bytes() == before
    finally:
        writer.close()


def test_host_mode_pulls_the_sidecars():
    assert RowCount.host_mode_sidecars == ('-wal', '-journal')
