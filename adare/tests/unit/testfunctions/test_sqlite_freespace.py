"""Unit tests for sqlite.free_space_pattern_count: deleted but recoverable data.

Databases are built in the test with the stdlib sqlite3 module (``secure_delete`` set
explicitly); corrupt files are made by patching their bytes.
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
FreeSpaceCount = sqlite_module.free_space_pattern_count._test_class
FreeSpaceCountParameter = sqlite_module.free_space_pattern_count._parameter_class
RowCount = sqlite_module.row_count._test_class
RowCountParameter = sqlite_module.row_count._parameter_class

PAGE = 1024
SECRET = 'note-008-'


def _free(dst, **params):
    return FreeSpaceCount(name='t', parameter=FreeSpaceCountParameter(dst=str(dst), **params)).test()


def _count(dst, **params):
    return RowCount(name='t', parameter=RowCountParameter(dst=str(dst), **params)).test()


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@contextlib.contextmanager
def _connect(path, secure_delete='OFF'):
    conn = sqlite3.connect(str(path), isolation_level=None)
    try:
        conn.execute('PRAGMA auto_vacuum=NONE')
        conn.execute(f'PRAGMA page_size={PAGE}')
        conn.execute(f'PRAGMA secure_delete={secure_delete}')
        yield conn
    finally:
        conn.close()


def _fill(conn, rows=20, big_row=False):
    conn.execute('CREATE TABLE notes (id INTEGER PRIMARY KEY, body TEXT)')
    for i in range(1, rows + 1):
        conn.execute('INSERT INTO notes VALUES (?, ?)', (i, f'note-{i:03d}-' + 'z' * 30))
    if big_row:
        conn.execute('INSERT INTO notes VALUES (?, ?)', (1000, 'LARGE-ROW-' * 600))


def _db(path, secure_delete='OFF', delete='id = 8', big_row=False):
    with _connect(path, secure_delete) as conn:
        _fill(conn, big_row=big_row)
        conn.execute(f'DELETE FROM notes WHERE {delete}')
    return path


def _patched(path, offset, raw):
    data = bytearray(path.read_bytes())
    data[offset : offset + len(raw)] = raw
    path.write_bytes(bytes(data))
    return path


def test_deleted_row_is_recoverable_but_not_queryable(tmp_path):
    db = _db(tmp_path / 'state.db')

    found = _free(db, pattern=SECRET, comparison_type='greater_equal')
    live = _count(db, query=f"SELECT id FROM notes WHERE body LIKE '{SECRET}%'", expected_count=0)

    assert found.status == StatusEnum.SUCCESS, found.details
    assert live.status == StatusEnum.SUCCESS, live.details
    assert found.details[0].startswith(f"1 occurrence(s) of text '{SECRET}' in ")
    assert any(d.startswith('matches: page 2 freeblock [') and d.endswith('): 1') for d in found.details)
    assert any(d.startswith('free space: freelist 0 page(s)') for d in found.details)
    assert any(d.startswith('read snapshot: state.db sha256=') for d in found.details)


def test_live_rows_are_not_counted(tmp_path):
    db = _db(tmp_path / 'state.db')

    result = _free(db, pattern='note-009-', expected_count=0)

    assert result.status == StatusEnum.SUCCESS, result.details
    assert 'matches: none' in result.details


def test_secure_delete_leaves_nothing_to_find(tmp_path):
    db = _db(tmp_path / 'state.db', secure_delete='ON')

    result = _free(db, pattern=SECRET, expected_count=0)
    expect_found = _free(db, pattern=SECRET, comparison_type='greater_equal')

    assert result.status == StatusEnum.SUCCESS, result.details
    assert expect_found.status == StatusEnum.FAILED, expect_found.details


def test_overflow_pages_of_a_deleted_large_row_are_on_the_freelist(tmp_path):
    db = _db(tmp_path / 'state.db', delete='id = 1000', big_row=True)

    on_freelist = _free(db, pattern='LARGE-ROW-', region='freelist', expected_count=100, comparison_type='greater')
    in_freeblocks = _free(db, pattern='LARGE-ROW-', region='freeblocks', expected_count=0)

    assert on_freelist.status == StatusEnum.SUCCESS, on_freelist.details
    assert in_freeblocks.status == StatusEnum.SUCCESS, in_freeblocks.details
    assert any(d.startswith('matches: page ') and ' freelist [' in d for d in on_freelist.details)


@pytest.mark.parametrize(
    ('pattern', 'pattern_type'),
    [('6e6f74652d3030382d', 'hex'), ('note-00[8]-', 'regex'), ('note\\x2d008-', 'bytes')],
)
def test_pattern_types(tmp_path, pattern, pattern_type):
    db = _db(tmp_path / 'state.db')

    result = _free(db, pattern=pattern, pattern_type=pattern_type)

    assert result.status == StatusEnum.SUCCESS, result.details


def test_utf16_text(tmp_path):
    """The deleted row is in the file twice, and both copies are free space.

    20 rows of about 82 bytes (UTF-16) do not fit on one 1024-byte page, so SQLite splits the
    root leaf: its cells move to new leaf pages, but the old cells stay behind in the unallocated
    space of the root, which is now an interior page. The deleted row is a freeblock on the leaf
    that took it over and a stale cell in the root's unallocated space. (The UTF-8 rows of the
    other tests fit on one page, hence a single copy there.)
    """
    db = tmp_path / 'state.db'
    with _connect(db) as conn:
        conn.execute("PRAGMA encoding='UTF-16le'")
        _fill(conn)
        conn.execute('DELETE FROM notes WHERE id = 8')
    needle = SECRET.encode('utf-16-le')

    utf8 = _free(db, pattern=SECRET, expected_count=0)
    utf16 = _free(db, pattern=SECRET, encoding='utf-16-le', expected_count=2)
    in_freeblock = _free(db, pattern=SECRET, encoding='utf-16-le', region='freeblocks', expected_count=1)
    in_unallocated = _free(db, pattern=SECRET, encoding='utf-16-le', region='unallocated', expected_count=1)

    assert utf8.status == StatusEnum.SUCCESS, utf8.details
    assert utf16.status == StatusEnum.SUCCESS, utf16.details
    assert in_freeblock.status == StatusEnum.SUCCESS, in_freeblock.details
    assert in_unallocated.status == StatusEnum.SUCCESS, in_unallocated.details
    assert db.read_bytes().count(needle) == 2  # no third copy anywhere: both are the free ones


def test_view_current_checkpoints_a_copy(tmp_path):
    """Deleted only in the -wal: the main file still holds the row live, current frees it."""
    live = tmp_path / 'live' / 'state.db'
    live.parent.mkdir()
    evidence = tmp_path / 'evidence'
    evidence.mkdir()
    with _connect(live) as conn:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA wal_autocheckpoint=0')
        _fill(conn)
        conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        conn.execute('DELETE FROM notes WHERE id = 8')
        for name in ('state.db', 'state.db-wal'):
            shutil.copyfile(live.parent / name, evidence / name)
    db = evidence / 'state.db'
    before = {p.name: _sha256(p) for p in evidence.iterdir()}

    main_file = _free(db, pattern=SECRET, expected_count=0)
    current = _free(db, pattern=SECRET, view='current')

    assert main_file.status == StatusEnum.SUCCESS, main_file.details
    assert current.status == StatusEnum.SUCCESS, current.details
    assert any(d.startswith('view: current (the copy after PRAGMA wal_checkpoint(TRUNCATE)') for d in current.details)
    assert any(d.startswith('read snapshot: state.db-wal sha256=') for d in current.details)
    assert {p.name: _sha256(p) for p in evidence.iterdir()} == before


# ---------------------------------------------------------------------------
# errors
# ---------------------------------------------------------------------------


def test_corrupt_freelist_pointer_is_an_error(tmp_path):
    db = _db(tmp_path / 'state.db', delete='id = 1000', big_row=True)
    _patched(db, 32, struct.pack('>I', 9999))

    result = _free(db, pattern=SECRET, expected_count=0)

    assert result.status == StatusEnum.ERROR, result.details
    assert 'broken freelist' in result.details[0]


def test_freelist_count_mismatch_is_an_error(tmp_path):
    db = _db(tmp_path / 'state.db')
    _patched(db, 36, struct.pack('>I', 2))

    result = _free(db, pattern=SECRET, expected_count=0)

    assert result.status == StatusEnum.ERROR, result.details
    assert 'counts 2 freelist pages' in result.details[0]


def test_corrupt_header_is_an_error(tmp_path):
    db = _patched(_db(tmp_path / 'state.db'), 16, b'\x03\x00')

    result = _free(db, pattern=SECRET, expected_count=0)

    assert result.status == StatusEnum.ERROR, result.details
    assert 'invalid page size' in result.details[0]


def test_not_a_database_is_an_error(tmp_path):
    db = tmp_path / 'state.db'
    db.write_bytes(b'plain text, ' * 100)

    result = _free(db, pattern=SECRET, expected_count=0)

    assert result.status == StatusEnum.ERROR, result.details
    assert 'not an SQLite database' in result.details[0]


def test_uncheckpointable_copy_is_an_error_in_view_current(tmp_path):
    db = tmp_path / 'state.db'
    db.write_bytes(b'SQLite format 3\x00' + b'\xff' * 200)

    result = _free(db, pattern=SECRET, expected_count=0, view='current')

    assert result.status == StatusEnum.ERROR, result.details
    assert 'could not checkpoint' in result.details[0]


@pytest.mark.parametrize(
    'params',
    [
        {'region': 'pages'},
        {'view': 'wal_added'},
        {'view': 'commit:1'},
        {'pattern_type': 'glob'},
        {'pattern': ''},
        {'pattern': 'zz', 'pattern_type': 'hex'},
        {'pattern': '(', 'pattern_type': 'regex'},
        {'encoding': 'no-such-encoding'},
        {'expected_count': -1},
        {'comparison_type': 'roughly'},
        {'pattern': '{{ts}}'},
    ],
)
def test_invalid_parameters_are_an_error(tmp_path, params):
    db = _db(tmp_path / 'state.db')
    params = {'pattern': SECRET, **params}

    result = _free(db, **params)

    assert result.status == StatusEnum.ERROR, result.details


def test_missing_database_is_an_error(tmp_path):
    result = _free(tmp_path / 'missing.db', pattern=SECRET)

    assert result.status == StatusEnum.ERROR, result.details
    assert 'does not exist' in result.details[0]


def test_host_mode_pulls_the_sidecars():
    assert FreeSpaceCount.host_mode_sidecars == ('-wal', '-journal')
