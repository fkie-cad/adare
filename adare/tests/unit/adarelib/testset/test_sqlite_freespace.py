"""SQLite free-space parser: freelist, freeblocks, unallocated space and the corruption checks.

Databases are written by the stdlib sqlite3 module in the test, so the parser is checked
against what SQLite itself writes; corrupt files are made by patching those bytes.
Runs on the guests' Python 3.10 too (``make test-adarelib-guest``).
"""

import io
import random
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
        conn.execute(f'PRAGMA page_size={page_size}')  # before auto_vacuum: that creates the file at the default size
        conn.execute(f'PRAGMA auto_vacuum={auto_vacuum}')
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
# what SQLite leaves in the file: copies, overwritten cells


def _occurrences(data, needle):
    offsets, at = [], data.find(needle)
    while at != -1:
        offsets.append(at)
        at = data.find(needle, at + 1)
    return offsets


def _region_at(space, offset, length):
    return next((r for r in space.regions if r.start <= offset and offset + length <= r.end), None)


def test_utf16_row_deleted_after_a_page_split_is_in_the_file_twice(tmp_path):
    """20 rows of 82 bytes do not fit on one 1024-byte page, so the root leaf is split.

    The root page becomes an interior page, but SQLite does not erase the leaf cells it
    moved out: the old cells stay in its unallocated space. The deleted row is therefore
    in the file twice, as a freeblock on the leaf that took it over and as a stale cell in
    the root's unallocated space. Both are free space; the parser finds each copy once.
    """
    db = tmp_path / 'a.db'
    conn = sqlite3.connect(str(db), isolation_level=None)
    conn.execute(f'PRAGMA page_size={PAGE}')
    conn.execute("PRAGMA encoding='UTF-16le'")
    conn.execute('CREATE TABLE notes (id INTEGER PRIMARY KEY, body TEXT)')
    for i in range(1, 21):
        conn.execute('INSERT INTO notes VALUES (?, ?)', (i, f'note-{i:03d}-' + 'z' * 30))
    conn.execute('DELETE FROM notes WHERE id = 8')
    conn.close()
    needle = 'note-008-'.encode('utf-16-le')
    data = db.read_bytes()

    space = parse_free_space(data)

    offsets = _occurrences(data, needle)
    assert len(offsets) == 2
    kinds = sorted(_region_at(space, o, len(needle)).kind for o in offsets)
    assert kinds == ['freeblock', 'unallocated']
    stale = next(o for o in offsets if _region_at(space, o, len(needle)).kind == 'unallocated')
    assert data[(stale // PAGE) * PAGE] == 0x05  # in the page that is now the interior root
    assert _found(db, needle) == 2
    # the unmoved live neighbour has the stale copy too: free space also holds live data's old copies
    assert _found(db, 'note-009-'.encode('utf-16-le')) == 1


def test_a_large_delete_can_overwrite_the_stale_copy_of_an_earlier_delete(tmp_path):
    """Deleting the large row empties its leaf, SQLite merges the tree back into the root page.

    Rewriting the root overwrites the stale cells an earlier delete had left there: the
    count drops from 2 to 1. The freeblock copy on the leaf, which is now a freelist page,
    survives, and everything still in the file is still reported.
    """
    db = _db(tmp_path / 'a.db', big_row=True)
    _delete(db, 'id = 8')
    before = _found(db, b'note-008-')
    _delete(db, 'id = 1000')
    data = db.read_bytes()
    space = parse_free_space(data)

    after = _found(db, b'note-008-')

    assert before == 2
    assert after == 1
    assert len(_occurrences(data, b'note-008-')) == after
    assert _region_at(space, _occurrences(data, b'note-008-')[0], 9).kind == 'freelist'


def _marker_db(path, rnd, page_size, encoding, auto_vacuum):
    """Rows with unique markers, some spilling to overflow pages, deleted in two transactions.

    Returns the markers (in the file's encoding) of the deleted rows; they occur nowhere else.
    There is no index: an index's interior pages keep the divider keys of deleted rows as live
    cells, which are not free space.
    """
    codec = {'UTF-8': 'utf-8', 'UTF-16le': 'utf-16-le', 'UTF-16be': 'utf-16-be'}[encoding]
    conn = sqlite3.connect(str(path), isolation_level=None)
    try:
        conn.execute(f'PRAGMA page_size={page_size}')
        conn.execute(f'PRAGMA auto_vacuum={auto_vacuum}')
        conn.execute(f"PRAGMA encoding='{encoding}'")
        conn.execute('PRAGMA secure_delete=OFF')
        conn.execute('CREATE TABLE t (id INTEGER PRIMARY KEY, body TEXT)')
        # an index b-tree whose big keys overflow in leaf and interior cells (no marker in them)
        conn.execute('CREATE TABLE k (key TEXT PRIMARY KEY) WITHOUT ROWID')
        conn.execute('BEGIN')
        for i in range(rnd.randint(20, 60)):
            fill = 'Q' * rnd.randint(page_size, 3 * page_size) if rnd.random() < 0.15 else 'q' * rnd.randint(5, 60)
            conn.execute('INSERT INTO t VALUES (?, ?)', (i, f'MK{i:04d}-{fill}'))
            kfill = 'K' * rnd.randint(page_size // 2, 2 * page_size) if rnd.random() < 0.4 else 'k' * rnd.randint(1, 30)
            conn.execute('INSERT INTO k VALUES (?)', (f'{i:04d}-{kfill}',))
        conn.execute('COMMIT')
        ids = [row[0] for row in conn.execute('SELECT id FROM t')]
        deleted = set()
        for _ in range(rnd.randint(1, 3)):
            conn.execute('BEGIN')
            for i in rnd.sample(ids, rnd.randint(1, len(ids) // 2)):
                conn.execute('DELETE FROM t WHERE id = ?', (i,))
                conn.execute('DELETE FROM k WHERE key LIKE ?', (f'{i:04d}-%',))
                deleted.add(i)
            conn.execute('COMMIT')
    finally:
        conn.close()
    return [f'MK{i:04d}-'.encode(codec) for i in sorted(deleted)]


@pytest.mark.parametrize('seed', range(6))
@pytest.mark.parametrize('auto_vacuum', ['NONE', 'INCREMENTAL', 'FULL'])
@pytest.mark.parametrize('encoding', ['UTF-8', 'UTF-16le', 'UTF-16be'])
@pytest.mark.parametrize('page_size', [512, 1024, 4096])
def test_regions_are_sorted_disjoint_inside_their_page_and_miss_no_deleted_data(
    tmp_path, page_size, encoding, auto_vacuum, seed
):
    db = tmp_path / 'a.db'
    markers = _marker_db(
        db, random.Random(f'{page_size}-{encoding}-{auto_vacuum}-{seed}'), page_size, encoding, auto_vacuum
    )
    data = db.read_bytes()

    space = parse_free_space(data)

    assert space.page_size == page_size
    assert space.regions
    assert set(space.of_kind('overflow_tail')) <= set(space.regions)
    for r in space.regions:
        assert 0 <= (r.page - 1) * page_size <= r.start < r.end <= r.page * page_size <= len(data)
        assert r.end <= (r.page - 1) * page_size + space.usable_size
        assert r.kind in REGION_KINDS
    for before, after in zip(space.regions, space.regions[1:], strict=False):
        assert before.start < after.start
        assert before.end <= after.start, f'{before} overlaps {after}'
    # whatever SQLite left of a deleted row is in a region: the parser misses no recoverable bytes
    for marker in markers:
        for offset in _occurrences(data, marker):
            assert _region_at(space, offset, len(marker)) is not None, f'{marker!r} at {offset} is in no region'


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
