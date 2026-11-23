"""SQLite free-space parser: freelist, freeblocks, unallocated space and the corruption checks.

Databases are written by the stdlib sqlite3 module in the test, so the parser is checked
against what SQLite itself writes; corrupt files are made by patching those bytes.
Runs on the guests' Python 3.10 too (``make test-adarelib-guest``).
"""

import io
import sqlite3
import struct

import pytest

from adarelib.testset.sqlite_freespace import (
    REGION_KINDS,
    SqliteFreeSpaceError,
    free_space_of_file,
    parse_free_space,
    read_free_space,
    read_region,
)

pytestmark = pytest.mark.unit

PAGE = 1024


def _db(path, secure_delete='OFF', page_size=PAGE, auto_vacuum='NONE', rows=20, big_row=False):
    """notes(id, body) with ``rows`` small rows (and one row spilling to overflow pages)."""
    conn = sqlite3.connect(str(path), isolation_level=None)
    try:
        conn.execute(f'PRAGMA auto_vacuum={auto_vacuum}')
        conn.execute(f'PRAGMA page_size={page_size}')
        conn.execute(f'PRAGMA secure_delete={secure_delete}')
        conn.execute('CREATE TABLE notes (id INTEGER PRIMARY KEY, body TEXT)')
        for i in range(1, rows + 1):
            conn.execute('INSERT INTO notes VALUES (?, ?)', (i, f'note-{i:03d}-' + 'z' * 30))
        if big_row:
            conn.execute('INSERT INTO notes VALUES (?, ?)', (1000, 'LARGE-ROW-' * 600))
    finally:
        conn.close()
    return path


def _delete(path, where, secure_delete='OFF'):
    conn = sqlite3.connect(str(path), isolation_level=None)
    try:
        conn.execute(f'PRAGMA secure_delete={secure_delete}')
        conn.execute(f'DELETE FROM notes WHERE {where}')
    finally:
        conn.close()


def _found(path, needle, *kinds):
    data = path.read_bytes()
    space = parse_free_space(data)
    return sum(data[r.start : r.end].count(needle) for r in space.of_kind(*kinds))


def _patch(path, offset, raw):
    data = bytearray(path.read_bytes())
    data[offset : offset + len(raw)] = raw
    return bytes(data)


def test_empty_file_has_no_free_space():
    space = parse_free_space(b'')

    assert space.regions == ()
    assert space.page_count == 0


def test_fresh_database_has_only_unallocated_space(tmp_path):
    db = _db(tmp_path / 'a.db', rows=0)

    space = free_space_of_file(str(db))

    assert space.page_size == PAGE
    assert space.freelist_pages == 0
    assert {r.kind for r in space.regions} == {'unallocated'}
    page1 = space.regions[0]
    assert page1.page == 1
    assert page1.start == 110  # 100-byte file header, 8-byte leaf page header, one cell pointer (the table)


def test_deleted_row_is_in_a_freeblock(tmp_path):
    db = _db(tmp_path / 'a.db')
    _delete(db, 'id = 8')

    assert _found(db, b'note-008-', 'freeblock') == 1
    assert _found(db, b'note-009-', 'freeblock') == 0
    blocks = parse_free_space(db.read_bytes()).of_kind('freeblock')
    assert blocks and all(r.page == 2 for r in blocks)


def test_secure_delete_erases_the_freed_cell(tmp_path):
    db = _db(tmp_path / 'a.db', secure_delete='ON')
    _delete(db, 'id = 8', secure_delete='ON')

    assert _found(db, b'note-008-') == 0
    assert b'note-008-' not in db.read_bytes()


def test_overflow_pages_of_a_deleted_row_are_on_the_freelist(tmp_path):
    db = _db(tmp_path / 'a.db', big_row=True)
    _delete(db, 'id = 1000')

    space = parse_free_space(db.read_bytes())

    assert space.freelist_pages >= 5  # 6000 bytes on 1024-byte pages
    assert len(space.of_kind('freelist')) == space.freelist_pages
    assert _found(db, b'LARGE-ROW-', 'freelist') > 100


def test_freelist_regions_are_whole_pages_but_the_trunk_list(tmp_path):
    db = _db(tmp_path / 'a.db', big_row=True)
    _delete(db, 'id = 1000')
    data = db.read_bytes()
    first_trunk = struct.unpack('>I', data[32:36])[0]

    space = parse_free_space(data)

    trunk = next(r for r in space.of_kind('freelist') if r.page == first_trunk)
    leaf_count = struct.unpack('>I', data[(first_trunk - 1) * PAGE + 4 : (first_trunk - 1) * PAGE + 8])[0]
    assert trunk.start == (first_trunk - 1) * PAGE + 8 + 4 * leaf_count
    leaves = [r for r in space.of_kind('freelist') if r.page != first_trunk]
    assert all(r.size == PAGE for r in leaves)


def test_regions_are_absolute_offsets_inside_their_page(tmp_path):
    db = _db(tmp_path / 'a.db', rows=200, big_row=True)
    _delete(db, 'id % 3 = 0 OR id = 1000')

    space = parse_free_space(db.read_bytes())

    assert {r.kind for r in space.regions} <= set(REGION_KINDS)
    for r in space.regions:
        assert (r.page - 1) * PAGE <= r.start < r.end <= r.page * PAGE
    assert [r.start for r in space.regions] == sorted(r.start for r in space.regions)


def test_interior_pages_are_parsed(tmp_path):
    db = _db(tmp_path / 'a.db', rows=500)
    data = db.read_bytes()
    root = data[PAGE]  # page 2, the table root, became an interior page

    space = parse_free_space(data)

    assert root == 0x05
    assert any(r.page == 2 and r.kind == 'unallocated' for r in space.regions)


def test_reserved_bytes_are_not_free_space():
    # page 1 alone: 100-byte header, an empty leaf table page, 32 reserved bytes per page
    page = bytearray(PAGE)
    page[:16] = b'SQLite format 3\x00'
    struct.pack_into('>H', page, 16, PAGE)
    page[20] = 32
    page[100] = 0x0D
    struct.pack_into('>H', page, 105, PAGE - 32)

    space = parse_free_space(bytes(page))

    assert space.usable_size == PAGE - 32
    assert [(r.start, r.end) for r in space.regions] == [(108, PAGE - 32)]


def test_page_size_65536_is_read_from_its_marker(tmp_path):
    db = _db(tmp_path / 'a.db', page_size=65536, rows=3)

    space = parse_free_space(db.read_bytes())

    assert struct.unpack('>H', db.read_bytes()[16:18])[0] == 1
    assert space.page_size == 65536


def test_auto_vacuum_pointer_map_pages_are_skipped(tmp_path):
    db = _db(tmp_path / 'a.db', auto_vacuum='FULL', rows=50)
    _delete(db, 'id < 10')

    space = parse_free_space(db.read_bytes())

    assert all(r.page != 2 for r in space.regions)  # page 2 is the first pointer-map page


def test_file_object_and_bytes_agree(tmp_path):
    db = _db(tmp_path / 'a.db', big_row=True)
    _delete(db, 'id IN (3, 1000)')
    data = db.read_bytes()

    with open(db, 'rb') as handle:
        from_file = read_free_space(handle, len(data))
        first = read_region(handle, from_file.regions[0])

    assert from_file == parse_free_space(data)
    assert first == data[from_file.regions[0].start : from_file.regions[0].end]


# ---------------------------------------------------------------------------
# corrupt input -> SqliteFreeSpaceError
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    'data',
    [b'x', b'SQLite format 3\x00' + b'\x00' * 50, b'not a database' + b'\x00' * 200],
    ids=['one-byte', 'short-header', 'wrong-magic'],
)
def test_not_a_database_is_an_error(data):
    with pytest.raises(SqliteFreeSpaceError, match='not an SQLite database'):
        parse_free_space(data)


@pytest.mark.parametrize('raw', [b'\x00\x00', b'\x03\x00', b'\x01\x01', b'\x00\x80'])
def test_invalid_page_size_is_an_error(tmp_path, raw):
    data = _patch(_db(tmp_path / 'a.db'), 16, raw)

    with pytest.raises(SqliteFreeSpaceError, match='invalid page size'):
        parse_free_space(data)


def test_too_many_reserved_bytes_is_an_error(tmp_path):
    db = _db(tmp_path / 'a.db', page_size=512)

    with pytest.raises(SqliteFreeSpaceError, match='reserved bytes'):
        parse_free_space(_patch(db, 20, b'\x40'))


@pytest.fixture
def with_freelist(tmp_path):
    db = _db(tmp_path / 'a.db', big_row=True)
    _delete(db, 'id = 1000')
    return db


def test_trunk_pointer_out_of_range_is_an_error(with_freelist):
    with pytest.raises(SqliteFreeSpaceError, match='outside the database'):
        parse_free_space(_patch(with_freelist, 32, struct.pack('>I', 9999)))


def test_leaf_pointer_out_of_range_is_an_error(with_freelist):
    trunk = struct.unpack('>I', with_freelist.read_bytes()[32:36])[0]

    with pytest.raises(SqliteFreeSpaceError, match='leaf .* outside the database'):
        parse_free_space(_patch(with_freelist, (trunk - 1) * PAGE + 8, struct.pack('>I', 9999)))


def test_trunk_cycle_is_an_error(with_freelist):
    trunk = struct.unpack('>I', with_freelist.read_bytes()[32:36])[0]

    with pytest.raises(SqliteFreeSpaceError, match='listed twice'):
        parse_free_space(_patch(with_freelist, (trunk - 1) * PAGE, struct.pack('>I', trunk)))


def test_trunk_leaf_count_too_large_is_an_error(with_freelist):
    trunk = struct.unpack('>I', with_freelist.read_bytes()[32:36])[0]

    with pytest.raises(SqliteFreeSpaceError, match='leaf pages'):
        parse_free_space(_patch(with_freelist, (trunk - 1) * PAGE + 4, struct.pack('>I', 0xFFFFFFFF)))


@pytest.mark.parametrize('delta', [1, -1])
def test_freelist_count_mismatch_is_an_error(with_freelist, delta):
    count = struct.unpack('>I', with_freelist.read_bytes()[36:40])[0]

    with pytest.raises(SqliteFreeSpaceError, match='counts'):
        parse_free_space(_patch(with_freelist, 36, struct.pack('>I', count + delta)))


def test_count_without_a_trunk_is_an_error(tmp_path):
    db = _db(tmp_path / 'a.db')

    with pytest.raises(SqliteFreeSpaceError, match='counts 3 freelist pages'):
        parse_free_space(_patch(db, 36, struct.pack('>I', 3)))


@pytest.fixture
def with_freeblocks(tmp_path):
    db = _db(tmp_path / 'a.db')
    _delete(db, 'id IN (5, 12)')
    first = struct.unpack('>H', db.read_bytes()[PAGE + 1 : PAGE + 3])[0]
    assert first, 'expected a freeblock chain on page 2'
    return db, PAGE + first


def test_freeblock_pointing_backwards_is_an_error(with_freeblocks):
    db, block = with_freeblocks

    with pytest.raises(SqliteFreeSpaceError, match='ascending order'):
        parse_free_space(_patch(db, block, struct.pack('>H', block - PAGE)))


def test_freeblock_off_the_page_is_an_error(with_freeblocks):
    db, _ = with_freeblocks

    with pytest.raises(SqliteFreeSpaceError, match='off the page'):
        parse_free_space(_patch(db, PAGE + 1, struct.pack('>H', PAGE - 2)))


def test_freeblock_size_past_the_page_is_an_error(with_freeblocks):
    db, block = with_freeblocks

    with pytest.raises(SqliteFreeSpaceError, match='extends past the page'):
        parse_free_space(_patch(db, block + 2, struct.pack('>H', PAGE)))


def test_cell_content_start_before_the_pointer_array_is_an_error(tmp_path):
    db = _db(tmp_path / 'a.db')

    with pytest.raises(SqliteFreeSpaceError, match='corrupt b-tree page 2'):
        parse_free_space(_patch(db, PAGE + 5, struct.pack('>H', 10)))


def test_page_1_that_is_no_btree_page_is_an_error(tmp_path):
    db = _db(tmp_path / 'a.db')

    with pytest.raises(SqliteFreeSpaceError, match='page 1 is not a b-tree page'):
        parse_free_space(_patch(db, 100, b'\x07'))


def test_truncated_file_is_an_error_not_an_index_error(with_freelist):
    data = with_freelist.read_bytes()

    with pytest.raises(SqliteFreeSpaceError):
        parse_free_space(data[: 2 * PAGE])


def test_reads_beyond_a_shrunk_file_are_an_error():
    class Shrinking(io.BytesIO):
        def read(self, size=-1):
            return super().read(size)[:1]

    page = bytearray(PAGE)
    page[:16] = b'SQLite format 3\x00'

    with pytest.raises(SqliteFreeSpaceError, match='could be read'):
        read_free_space(Shrinking(bytes(page)), PAGE)
