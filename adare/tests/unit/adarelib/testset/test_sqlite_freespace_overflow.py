"""SQLite free-space parser: the unused tail of overflow pages and the checks on overflow chains.

A value too large for its b-tree cell continues on a chain of overflow pages; the last page
of the chain keeps the old bytes of the page after the value (the ``overflow_tail`` region).
Databases are written by the stdlib sqlite3 module and, where it can, checked against SQLite's
own ``dbstat`` table; corrupt chains are made by patching those bytes.
Runs on the guests' Python 3.10 too (``make test-adarelib-guest``).
"""

import random
import sqlite3
import struct

import pytest

from adarelib.testset import sqlite_freespace
from adarelib.testset.sqlite_freespace import SqliteFreeSpaceError, parse_free_space

pytestmark = pytest.mark.unit

PAGE = 1024
# 1024-byte pages: 103 bytes of a big value stay in the cell, the rest goes 1020 bytes per page
BODY = 3100  # + 4 bytes of record header (the rowid column is stored as NULL): 3001 bytes on overflow pages 3, 4, 5
LAST_PAGE_BYTES = 961  # 1020 + 1020 + 961


def _has_dbstat():
    conn = sqlite3.connect(':memory:')
    try:
        return any(row[0] == 'ENABLE_DBSTAT_VTAB' for row in conn.execute('PRAGMA compile_options'))
    finally:
        conn.close()


def _connect(path, page_size=PAGE, auto_vacuum='NONE', secure_delete='OFF'):
    conn = sqlite3.connect(str(path), isolation_level=None)
    conn.execute(f'PRAGMA page_size={page_size}')
    conn.execute(f'PRAGMA auto_vacuum={auto_vacuum}')
    conn.execute(f'PRAGMA secure_delete={secure_delete}')
    return conn


def _one_big_row(path, body=None):
    """notes(id, body) with a single row: page 2 is the table, pages 3, 4, 5 its overflow chain."""
    conn = _connect(path)
    try:
        conn.execute('CREATE TABLE notes (id INTEGER PRIMARY KEY, body BLOB)')
        conn.execute('INSERT INTO notes VALUES (1, ?)', (body if body is not None else b'A' * BODY,))
    finally:
        conn.close()
    return bytearray(path.read_bytes())


def _next_page(data, page):
    return struct.unpack('>I', data[(page - 1) * PAGE : (page - 1) * PAGE + 4])[0]


def _set_next(data, page, value):
    data[(page - 1) * PAGE : (page - 1) * PAGE + 4] = struct.pack('>I', value)


def _cell_overflow_pointer(data, page=2):
    """The offset of the first-overflow-page number of the only cell of table leaf ``page``."""
    base = (page - 1) * PAGE
    cell = struct.unpack('>H', data[base + 8 : base + 10])[0]
    return base + cell + 2 + 1 + 103  # payload size (2 bytes), rowid (1), 103 local bytes


# ---------------------------------------------------------------------------
# what SQLite writes
# ---------------------------------------------------------------------------


def test_the_last_overflow_page_has_a_tail_region(tmp_path):
    data = _one_big_row(tmp_path / 'a.db')
    assert [_next_page(data, p) for p in (3, 4, 5)] == [4, 5, 0]  # the layout the tests below patch

    space = parse_free_space(bytes(data))

    tails = space.of_kind('overflow_tail')
    assert space.overflow_pages == 3
    assert [(r.page, r.start, r.end) for r in tails] == [(5, 4 * PAGE + 4 + LAST_PAGE_BYTES, 5 * PAGE)]
    assert tails[0].size == 59


def test_a_value_that_fills_its_last_overflow_page_has_no_tail(tmp_path):
    data = _one_big_row(tmp_path / 'a.db', b'A' * (BODY - LAST_PAGE_BYTES + 1020))  # last page full

    space = parse_free_space(bytes(data))

    assert space.overflow_pages == 3
    assert not space.of_kind('overflow_tail')


def test_overflow_pages_are_not_in_the_other_kinds(tmp_path):
    data = _one_big_row(tmp_path / 'a.db')

    space = parse_free_space(bytes(data))

    assert {r.page for r in space.regions if r.page in (3, 4, 5)} == {5}
    assert {r.kind for r in space.regions if r.page == 5} == {'overflow_tail'}


@pytest.mark.skipif(not _has_dbstat(), reason='SQLite built without the dbstat table')
@pytest.mark.parametrize('seed', range(8))
@pytest.mark.parametrize('auto_vacuum', ['NONE', 'FULL'])
@pytest.mark.parametrize('page_size', [512, 1024, 4096])
def test_overflow_pages_and_tails_agree_with_dbstat(tmp_path, page_size, auto_vacuum, seed):
    """Table leaves, index leaves and index interior pages with big values, some deleted again."""
    rnd = random.Random(f'{page_size}-{auto_vacuum}-{seed}')
    db = tmp_path / 'a.db'
    conn = _connect(db, page_size, auto_vacuum)
    try:
        conn.execute('CREATE TABLE blobs (id INTEGER PRIMARY KEY, body BLOB)')
        conn.execute('CREATE TABLE keys (k TEXT PRIMARY KEY, v BLOB) WITHOUT ROWID')
        conn.execute('CREATE INDEX blobs_body ON blobs (body)')
        conn.execute('BEGIN')
        for i in range(rnd.randint(30, 80)):
            big = rnd.random() < 0.5
            size = rnd.randint(page_size // 2, 4 * page_size) if big else rnd.randint(1, 40)
            conn.execute('INSERT INTO blobs VALUES (?, ?)', (i, bytes([65 + i % 26]) * size + bytes([i % 251])))
            key = f'K{i:04d}-' + 'k' * (rnd.randint(page_size // 2, 3 * page_size) if big else rnd.randint(1, 20))
            conn.execute('INSERT INTO keys VALUES (?, ?)', (key, b'v' * rnd.randint(1, 3 * page_size)))
        conn.execute('COMMIT')
        for round_ in range(2):
            conn.execute('BEGIN')
            for i in rnd.sample(range(30), 10):
                conn.execute('DELETE FROM blobs WHERE id = ?', (i,))
                conn.execute('DELETE FROM keys WHERE k LIKE ?', (f'K{i:04d}-%',))
            conn.execute('INSERT INTO keys VALUES (?, ?)', (f'N{round_}-' + 'n' * 2 * page_size, b'w'))
            conn.execute('COMMIT')
        pages = conn.execute("SELECT pageno, unused FROM dbstat WHERE pagetype = 'overflow' ORDER BY pageno").fetchall()
    finally:
        conn.close()

    space = parse_free_space(db.read_bytes())

    assert space.overflow_pages == len(pages)
    assert [(r.page, r.size) for r in space.of_kind('overflow_tail')] == [(p, unused) for p, unused in pages if unused]


@pytest.mark.parametrize('seed', range(5))
def test_overflow_tail_regions_stay_sorted_disjoint_and_inside_their_page(tmp_path, seed):
    rnd = random.Random(seed)
    db = tmp_path / 'a.db'
    conn = _connect(db)
    try:
        conn.execute('CREATE TABLE notes (id INTEGER PRIMARY KEY, body TEXT)')
        conn.execute('CREATE TABLE keys (k TEXT PRIMARY KEY) WITHOUT ROWID')
        conn.execute('BEGIN')
        for i in range(120):
            conn.execute('INSERT INTO notes VALUES (?, ?)', (i, f'row-{i:04d}-' + 'x' * rnd.randint(10, 3000)))
        conn.execute('COMMIT')
        conn.execute('BEGIN')
        conn.execute('DELETE FROM notes WHERE id % 2 = 0')
        for i in range(rnd.randint(1, 4)):
            conn.execute('INSERT INTO keys VALUES (?)', (f'key{i}' + 'Z' * rnd.randint(300, 2500),))
        conn.execute('COMMIT')
    finally:
        conn.close()
    data = db.read_bytes()

    space = parse_free_space(data)

    assert space.of_kind('overflow_tail')
    for r in space.regions:
        assert (r.page - 1) * PAGE <= r.start < r.end <= (r.page - 1) * PAGE + space.usable_size <= len(data)
    for before, after in zip(space.regions, space.regions[1:], strict=False):
        assert before.end <= after.start, f'{before} overlaps {after}'


def test_reserved_bytes_are_not_part_of_the_tail():
    # hand-made: 512-byte pages with 32 reserved bytes (usable size 480). Page 1 is a table leaf
    # holding one cell with a 500-byte value: 35 bytes in the cell, 465 on overflow page 2
    page_size, usable = 512, 480
    page1 = bytearray(page_size)
    page1[:16] = b'SQLite format 3\x00'
    struct.pack_into('>H', page1, 16, page_size)
    page1[20] = 32
    page1[100] = 0x0D
    struct.pack_into('>H', page1, 103, 1)  # one cell
    cell = b'\x83\x74' + b'\x01' + b'L' * 35 + struct.pack('>I', 2)  # 500 = 0x83 0x74, rowid 1
    struct.pack_into('>H', page1, 105, usable - len(cell))
    struct.pack_into('>H', page1, 108, usable - len(cell))
    page1[usable - len(cell) : usable] = cell
    page2 = bytearray(b'\xee' * page_size)
    page2[:4] = b'\x00\x00\x00\x00'

    space = parse_free_space(bytes(page1 + page2))

    assert space.usable_size == usable
    assert [(r.page, r.start, r.end, r.kind) for r in space.of_kind('overflow_tail')] == [
        (2, page_size + 4 + 465, page_size + usable, 'overflow_tail')  # 11 bytes; the reserved 32 are left out
    ]


# ---------------------------------------------------------------------------
# broken chains
# ---------------------------------------------------------------------------


def _error(data):
    with pytest.raises(SqliteFreeSpaceError) as info:
        parse_free_space(bytes(data))
    return str(info.value)


def test_a_chain_that_loops_back_is_an_error(tmp_path):
    data = _one_big_row(tmp_path / 'a.db')
    _set_next(data, 4, 3)

    assert 'claimed twice' in _error(data)


def test_a_chain_pointing_at_itself_is_an_error(tmp_path):
    data = _one_big_row(tmp_path / 'a.db')
    _set_next(data, 4, 4)

    assert 'claimed twice' in _error(data)


@pytest.mark.parametrize('target', [1, 6, 9999, 0xFFFFFFFF], ids=['page-1', 'past-the-end', 'far', 'max'])
def test_a_chain_pointing_out_of_range_is_an_error(tmp_path, target):
    data = _one_big_row(tmp_path / 'a.db')
    _set_next(data, 4, target)

    assert 'no page that can hold overflow data' in _error(data)


def test_the_first_overflow_page_of_a_cell_out_of_range_is_an_error(tmp_path):
    data = _one_big_row(tmp_path / 'a.db')
    at = _cell_overflow_pointer(data)
    assert struct.unpack('>I', data[at : at + 4])[0] == 3  # the offset arithmetic is right
    data[at : at + 4] = struct.pack('>I', 77)

    assert 'no page that can hold overflow data' in _error(data)


def test_a_chain_that_ends_early_is_an_error(tmp_path):
    data = _one_big_row(tmp_path / 'a.db')
    _set_next(data, 4, 0)

    assert 'ends with' in _error(data)
    assert 'bytes of the value missing' in _error(data)


def test_a_chain_that_goes_on_is_an_error(tmp_path):
    data = _one_big_row(tmp_path / 'a.db')
    _set_next(data, 5, 2)

    assert 'names page 2 next' in _error(data)


def test_a_cell_that_names_no_overflow_page_is_an_error(tmp_path):
    data = _one_big_row(tmp_path / 'a.db')
    at = _cell_overflow_pointer(data)
    data[at : at + 4] = b'\x00\x00\x00\x00'

    assert 'ends with 3001 bytes of the value missing' in _error(data)


def test_two_cells_sharing_a_chain_is_an_error(tmp_path):
    db = tmp_path / 'a.db'
    conn = _connect(db)
    conn.execute('CREATE TABLE notes (id INTEGER PRIMARY KEY, body BLOB)')
    conn.execute('INSERT INTO notes VALUES (1, ?)', (b'A' * BODY,))
    conn.execute('INSERT INTO notes VALUES (2, ?)', (b'B' * BODY,))
    conn.close()
    data = bytearray(db.read_bytes())
    base = PAGE  # page 2, the table's only page, two cells; the cell at the lower address is row 2
    pointers = [struct.unpack('>H', data[base + 8 + 2 * i : base + 10 + 2 * i])[0] for i in range(2)]
    first, second = (base + p + 2 + 1 + 103 for p in pointers)
    data[first : first + 4] = data[second : second + 4]

    assert 'claimed twice' in _error(data)


def test_a_chain_into_the_freelist_is_an_error(tmp_path):
    db = tmp_path / 'a.db'
    conn = _connect(db)
    conn.execute('CREATE TABLE notes (id INTEGER PRIMARY KEY, body BLOB)')
    conn.execute('INSERT INTO notes VALUES (1, ?)', (b'A' * BODY,))
    conn.execute('INSERT INTO notes VALUES (2, ?)', (b'B' * BODY,))
    conn.execute('DELETE FROM notes WHERE id = 2')  # pages 6, 7, 8 are on the freelist
    conn.close()
    data = bytearray(db.read_bytes())
    assert struct.unpack('>I', data[36:40])[0] == 3
    _set_next(data, 4, 7)

    assert 'no page that can hold overflow data' in _error(data)


def test_a_cell_claiming_its_own_page_is_an_error(tmp_path):
    data = _one_big_row(tmp_path / 'a.db')
    at = _cell_overflow_pointer(data)
    data[at : at + 4] = struct.pack('>I', 2)  # the table's own page

    assert 'claimed as an overflow page by no b-tree page in use' in _error(data)


def test_a_cell_that_runs_off_the_page_is_an_error(tmp_path):
    data = _one_big_row(tmp_path / 'a.db')
    base = PAGE
    data[base + 8 : base + 10] = struct.pack('>H', PAGE - 3)  # a cell of three bytes that all continue a varint
    data[base + 5 : base + 7] = struct.pack('>H', PAGE - 3)
    data[base + PAGE - 3 : base + PAGE] = b'\x80\x80\x80'

    assert 'cell 0 of page 2' in _error(data)


# ---------------------------------------------------------------------------
# a page that a chain claims is an overflow page, whatever its first byte says
# ---------------------------------------------------------------------------


def test_an_overflow_page_that_looks_like_a_btree_page_is_not_parsed_as_one(tmp_path, monkeypatch):
    """The first byte of an overflow page is 0 below 2**24 pages (the next-page number), so a page
    that looks like a b-tree page is not made here by a real database. It is simulated: byte 0 is
    declared a b-tree page type, and the last overflow page starts with bytes that make it a
    valid, empty leaf page (``unallocated`` from 8 to 1024) that would overlap the real tail.
    """
    body = bytearray(b'A' * BODY)
    body[2139:2142] = b'\x00\x04\x00'  # payload offset 4 + 2139 = 2143 = 103 + 2040: byte 4 of page 5
    data = _one_big_row(tmp_path / 'a.db', bytes(body))
    assert data[4 * PAGE : 4 * PAGE + 8] == b'\x00\x00\x00\x00\x00\x04\x00A'
    honest = parse_free_space(bytes(data))
    monkeypatch.setattr(sqlite_freespace, 'BTREE_PAGE_TYPES', sqlite_freespace.BTREE_PAGE_TYPES + (0x00,))

    simulated = parse_free_space(bytes(data))

    assert simulated.regions == honest.regions
    assert {r.kind for r in simulated.regions if r.page == 5} == {'overflow_tail'}
    assert simulated.overflow_pages == 3
