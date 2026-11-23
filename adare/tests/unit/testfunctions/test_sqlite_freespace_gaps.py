"""What ``sqlite.free_space_pattern_count`` does not see, and what shows it.

``expected_count: 0`` on the free space passes for text that is still in the file: the tail
of an overflow page in use, a ``sqlite_stat4`` sample and a full-text index segment are not
free space. ``text.occurrence_count`` over the whole file finds the text, and a query finds
what is a live row. Databases are built with the stdlib sqlite3 module (``secure_delete``
set explicitly).
Runs on the guests' Python 3.10 too (``make test-testfunctions-guest``).
"""

import sqlite3
from pathlib import Path

import pytest

from adarelib.constants import StatusEnum
from adarelib.helper.module import import_module_from_pyfile
from adarelib.testset.sqlite_freespace import parse_free_space

pytestmark = pytest.mark.unit

COLLECTIONS = Path(__file__).resolve().parents[3] / 'appdata' / 'testfunctions'
sqlite_module = import_module_from_pyfile(COLLECTIONS / 'sqlite' / 'sqlite.py')
text_module = import_module_from_pyfile(COLLECTIONS / 'text' / 'text.py')
FreeSpaceCount = sqlite_module.free_space_pattern_count._test_class
FreeSpaceCountParameter = sqlite_module.free_space_pattern_count._parameter_class
RowCount = sqlite_module.row_count._test_class
RowCountParameter = sqlite_module.row_count._parameter_class
OccurrenceCount = text_module.occurrence_count._test_class
OccurrenceCountParameter = text_module.occurrence_count._parameter_class

PAGE = 1024


def _free(dst, **params):
    return FreeSpaceCount(name='t', parameter=FreeSpaceCountParameter(dst=str(dst), **params)).test()


def _whole_file(dst, **params):
    return OccurrenceCount(name='t', parameter=OccurrenceCountParameter(dst=str(dst), **params)).test()


def _query(dst, **params):
    return RowCount(name='t', parameter=RowCountParameter(dst=str(dst), **params)).test()


def _connect(path, secure_delete):
    conn = sqlite3.connect(str(path), isolation_level=None)
    conn.execute(f'PRAGMA page_size={PAGE}')
    conn.execute('PRAGMA auto_vacuum=NONE')
    conn.execute(f'PRAGMA secure_delete={secure_delete}')
    return conn


def _options():
    conn = sqlite3.connect(':memory:')
    try:
        return {row[0] for row in conn.execute('PRAGMA compile_options')}
    finally:
        conn.close()


def test_overflow_page_tail_passes_as_deleted_but_the_whole_file_finds_it(tmp_path):
    db = tmp_path / 'state.db'
    conn = _connect(db, 'OFF')
    conn.execute('CREATE TABLE notes (id INTEGER PRIMARY KEY, body TEXT)')
    conn.execute('CREATE TABLE keys (k TEXT PRIMARY KEY) WITHOUT ROWID')
    conn.execute('BEGIN')
    for i in range(1, 200):
        conn.execute('INSERT INTO notes VALUES (?, ?)', (i, f'SECRET-{i:04d}-' + 'q' * 30))
    conn.execute('COMMIT')
    conn.execute('BEGIN')
    conn.execute('DELETE FROM notes')
    conn.execute('INSERT INTO keys VALUES (?)', ('Z' * 600,))
    conn.execute('COMMIT')
    conn.close()
    # some rows sit only in the page SQLite reused as the tail of the overflow chain (page 5)
    data = db.read_bytes()
    regions = parse_free_space(data).regions

    def only_outside(secret):
        offsets = [at for at in range(len(data)) if data.startswith(secret, at)]
        return bool(offsets) and not any(r.start <= at < r.end for at in offsets for r in regions)

    secret = next(f'SECRET-{i:04d}-' for i in range(1, 200) if only_outside(f'SECRET-{i:04d}-'.encode()))
    gone = _free(db, pattern=secret, expected_count=0)
    anywhere = _whole_file(db, content=secret, expected_count=1)
    queryable = _query(db, query=f"SELECT id FROM notes WHERE body LIKE '{secret}%'", expected_count=0)

    assert gone.status == StatusEnum.SUCCESS, gone.details  # "not in the free space"
    assert anywhere.status == StatusEnum.SUCCESS, anywhere.details  # still in the file
    assert queryable.status == StatusEnum.SUCCESS, queryable.details  # and no query returns it


@pytest.mark.skipif('ENABLE_STAT4' not in _options(), reason='SQLite built without STAT4')
def test_stat4_sample_passes_as_deleted_but_a_query_finds_it(tmp_path):
    db = tmp_path / 'state.db'
    conn = _connect(db, 'ON')
    conn.execute('CREATE TABLE notes (id INTEGER PRIMARY KEY, title TEXT)')
    conn.execute('CREATE INDEX notes_title ON notes (title)')
    conn.execute('BEGIN')
    for i in range(1, 401):
        conn.execute('INSERT INTO notes VALUES (?, ?)', (i, f'title-{i:04d}-secret'))
    conn.execute('COMMIT')
    conn.execute('ANALYZE')
    sample = bytes(conn.execute('SELECT sample FROM sqlite_stat4 LIMIT 1 OFFSET 3').fetchone()[0])
    key = sample[sample.index(b'title-') :][:17].decode()
    conn.execute('DELETE FROM notes WHERE title = ?', (key,))
    conn.close()

    gone = _free(db, pattern=key, expected_count=0)
    anywhere = _whole_file(db, content=key, expected_count=1)
    in_statistics = _query(
        db, query=f"SELECT 1 FROM sqlite_stat4 WHERE instr(sample, CAST('{key}' AS BLOB)) > 0", expected_count=1
    )

    assert gone.status == StatusEnum.SUCCESS, gone.details
    assert anywhere.status == StatusEnum.SUCCESS, anywhere.details
    assert in_statistics.status == StatusEnum.SUCCESS, in_statistics.details


@pytest.mark.skipif('ENABLE_FTS5' not in _options(), reason='SQLite built without FTS5')
def test_fts5_segment_passes_as_deleted_but_the_whole_file_finds_it(tmp_path):
    db = tmp_path / 'state.db'
    conn = _connect(db, 'ON')
    conn.execute('CREATE VIRTUAL TABLE f USING fts5(body)')
    conn.execute('BEGIN')
    for i in range(1, 301):
        conn.execute('INSERT INTO f(rowid, body) VALUES (?, ?)', (i, f'common words doc{i} filler text'))
    conn.execute("INSERT INTO f(rowid, body) VALUES (1000, 'the zebrafishsecret appears here')")
    conn.execute('COMMIT')
    conn.execute('DELETE FROM f WHERE rowid = 1000')
    conn.close()

    gone = _free(db, pattern='zebrafishsecret', expected_count=0)
    anywhere = _whole_file(db, content='zebrafishsecret', expected_count=1, comparison_type='greater_equal')
    matching = _query(db, query="SELECT rowid FROM f WHERE f MATCH 'zebrafishsecret'", expected_count=0)

    assert gone.status == StatusEnum.SUCCESS, gone.details
    assert anywhere.status == StatusEnum.SUCCESS, anywhere.details
    assert matching.status == StatusEnum.SUCCESS, matching.details


def test_default_delete_is_found_in_free_space_and_in_the_whole_file(tmp_path):
    """The usual case needs no second test: a delete without secure_delete is free space."""
    db = tmp_path / 'state.db'
    conn = _connect(db, 'OFF')
    conn.execute('CREATE TABLE notes (id INTEGER PRIMARY KEY, title TEXT)')
    conn.execute('CREATE INDEX notes_title ON notes (title)')
    conn.execute('BEGIN')
    for i in range(1, 401):
        conn.execute('INSERT INTO notes VALUES (?, ?)', (i, f'title-{i:04d}-secret'))
    conn.execute('COMMIT')
    conn.execute('DELETE FROM notes WHERE id BETWEEN 100 AND 300')
    conn.close()

    in_free = _free(db, pattern='title-0152-secret', comparison_type='greater_equal')
    in_file = _whole_file(db, content='title-0152-secret', expected_count=1, comparison_type='greater_equal')

    assert in_free.status == StatusEnum.SUCCESS, in_free.details
    assert in_file.status == StatusEnum.SUCCESS, in_file.details
