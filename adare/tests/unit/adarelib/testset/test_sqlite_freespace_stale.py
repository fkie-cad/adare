"""Where text of deleted rows is, and is not, found by the free-space parser.

Pins what SQLite writes (databases built with the stdlib sqlite3 module) for deleted values:

* an **index** b-tree is a Knuth tree: its interior cells are real index entries. Deleting
  one replaces it with the entry before it, so the deleted key does NOT stay behind as a live
  divider; its old bytes are free space (a freeblock or unallocated space);
* a **table** b-tree interior page keeps only rowids as dividers, and those survive the
  deletion of their rows (even with ``secure_delete``). There is no text in them;
* the tail of an **overflow page** in use keeps the old bytes of the page when SQLite reuses
  a page freed in the same transaction, so text of a deleted row can sit there; the parser
  reports it as an ``overflow_tail`` region;
* ``sqlite_stat4`` samples and the segments of a full-text index (FTS5) are live rows of
  b-trees, with the values of deleted rows, until the next ANALYZE or merge.

Runs on the guests' Python 3.10 too (``make test-adarelib-guest``).
"""

import re
import sqlite3
import struct

import pytest

from adarelib.testset.sqlite_freespace import parse_free_space

pytestmark = pytest.mark.unit

PAGE = 1024
INDEX_INTERIOR, TABLE_INTERIOR = 0x02, 0x05


def _connect(path, secure_delete='OFF'):
    conn = sqlite3.connect(str(path), isolation_level=None)
    conn.execute(f'PRAGMA page_size={PAGE}')  # first: it only takes effect before the file exists
    conn.execute('PRAGMA auto_vacuum=NONE')
    conn.execute(f'PRAGMA secure_delete={secure_delete}')
    return conn


def _compile_options():
    conn = sqlite3.connect(':memory:')
    try:
        return {row[0] for row in conn.execute('PRAGMA compile_options')}
    finally:
        conn.close()


def _classify(data, offset):
    """``'free:<kind>'`` when ``offset`` is in a free region, else ``'outside'``."""
    for region in parse_free_space(data).regions:
        if region.start <= offset < region.end:
            return f'free:{region.kind}'
    return 'outside'


def _occurrences(data, needle):
    found, at = [], data.find(needle)
    while at >= 0:
        found.append(at)
        at = data.find(needle, at + 1)
    return found


def _outside_free_space(data, needle):
    return [at for at in _occurrences(data, needle) if _classify(data, at) == 'outside']


def _page(data, offset):
    return offset // PAGE + 1


def _root_cell_keys(data, page, pattern):
    """The matches of ``pattern`` (bytes regex) inside the live cells of the b-tree page ``page``."""
    base = (page - 1) * PAGE
    count = struct.unpack('>H', data[base + 3 : base + 5])[0]
    header = 12 if data[base] in (INDEX_INTERIOR, TABLE_INTERIOR) else 8
    keys = []
    for i in range(count):
        cell = struct.unpack('>H', data[base + header + 2 * i : base + header + 2 * i + 2])[0]
        match = re.search(pattern, data[base + cell : base + cell + 64])
        keys.append(match.group() if match else None)
    return keys


def _rowid_dividers(data, page):
    """The rowids of the cells of the table interior page ``page`` (a varint after the 4-byte child pointer)."""
    base = (page - 1) * PAGE
    count = struct.unpack('>H', data[base + 3 : base + 5])[0]
    rowids = []
    for i in range(count):
        at = base + struct.unpack('>H', data[base + 12 + 2 * i : base + 12 + 2 * i + 2])[0] + 4
        value = 0
        while data[at] & 0x80:  # these rowids need at most 3 bytes
            value = (value << 7) | (data[at] & 0x7F)
            at += 1
        rowids.append((value << 7) | data[at])
    return rowids


def _fill_notes(conn, rows=400):
    conn.execute('CREATE TABLE notes (id INTEGER PRIMARY KEY, title TEXT, body TEXT)')
    conn.execute('CREATE INDEX notes_title ON notes (title)')
    conn.execute('BEGIN')
    for i in range(1, rows + 1):
        conn.execute('INSERT INTO notes VALUES (?, ?, ?)', (i, f'title-{i:04d}-secret', f'body {i} ' + 'x' * 20))
    conn.execute('COMMIT')


def test_deleted_index_key_does_not_survive_as_an_interior_divider(tmp_path):
    db = tmp_path / 'a.db'
    conn = _connect(db)
    _fill_notes(conn)
    before = db.read_bytes()
    assert before[2 * PAGE : 2 * PAGE + 1][0] == INDEX_INTERIOR  # page 3: root of notes_title
    dividers = _root_cell_keys(before, 3, rb'title-\d{4}-secret')
    victim = dividers[2]  # a key held by an interior cell, in no leaf
    assert victim is not None
    victim_at = before.find(victim, 2 * PAGE)
    assert _page(before, victim_at) == 3 and _classify(before, victim_at) == 'outside'  # live

    conn.execute('DELETE FROM notes WHERE title = ?', (victim.decode(),))
    conn.close()
    after = db.read_bytes()

    assert _root_cell_keys(after, 3, rb'title-\d{4}-secret')[2] != victim  # replaced by the entry before it
    assert after[2 * PAGE] == INDEX_INTERIOR
    assert _outside_free_space(after, victim) == []
    assert after.count(victim) >= 1  # the old cell, now free space: a freeblock or unallocated
    assert {_classify(after, at) for at in _occurrences(after, victim)} <= {'free:freeblock', 'free:unallocated'}


@pytest.mark.parametrize('secure_delete', ['OFF', 'ON'])
def test_deleted_table_rowids_stay_as_interior_dividers(tmp_path, secure_delete):
    db = tmp_path / 'a.db'
    conn = _connect(db, secure_delete)
    conn.execute('CREATE TABLE notes (id INTEGER PRIMARY KEY, title TEXT)')
    conn.execute('BEGIN')
    for i in range(1, 401):
        conn.execute('INSERT INTO notes VALUES (?, ?)', (i, f'title-{i:04d}-secret'))
    conn.execute('COMMIT')
    before = db.read_bytes()
    assert before[PAGE] == TABLE_INTERIOR  # page 2: root of notes
    dividers = _rowid_dividers(before, 2)
    assert dividers == [42, 84, 126, 166, 206, 246, 286, 326, 366]

    id_list = ','.join(map(str, dividers))
    conn.execute(f'DELETE FROM notes WHERE id IN ({id_list})')
    check = conn.execute(f'SELECT count(*) FROM notes WHERE id IN ({id_list})').fetchone()
    conn.close()
    after = db.read_bytes()

    assert check == (0,)
    assert after[PAGE] == TABLE_INTERIOR
    assert _rowid_dividers(after, 2) == dividers  # the same nine dividers, rows deleted


def _overflow_slack_database(path, secure_delete):
    """notes rows freed and a page of them reused as the last overflow page of a big key, one transaction."""
    conn = _connect(path, secure_delete)
    conn.execute('CREATE TABLE notes (id INTEGER PRIMARY KEY, body TEXT)')
    conn.execute('CREATE TABLE keys (k TEXT PRIMARY KEY) WITHOUT ROWID')
    conn.execute('BEGIN')
    for i in range(1, 200):
        conn.execute('INSERT INTO notes VALUES (?, ?)', (i, f'SECRET-{i:04d}-' + 'q' * 30))
    conn.execute('COMMIT')
    before = path.read_bytes()
    conn.execute('BEGIN')
    conn.execute('DELETE FROM notes')
    conn.execute('INSERT INTO keys VALUES (?)', ('Z' * 600,))  # 103 bytes local, the rest on one overflow page
    conn.execute('COMMIT')
    conn.close()
    return before, path.read_bytes()


def test_overflow_page_tail_keeps_deleted_text_and_is_a_region(tmp_path):
    before, after = _overflow_slack_database(tmp_path / 'a.db', 'OFF')
    space = parse_free_space(after)

    # page 5 was a leaf of notes, was freed by the delete and taken again as the overflow page
    assert after[4 * PAGE : 4 * PAGE + 4] == b'\x00\x00\x00\x00'  # last page of the chain: no next page
    assert after[4 * PAGE + 4 : 4 * PAGE + 8] == b'ZZZZ'
    assert space.overflow_pages == 1
    page5 = [r for r in space.regions if r.page == 5]
    assert [(r.kind, r.start, r.end) for r in page5] == [
        ('overflow_tail', 4 * PAGE + 4 + 603 - 103, 5 * PAGE)
    ]  # 603 payload bytes, 103 in the cell
    # every copy of the deleted text on that page is in the tail region, none outside any region
    assert not _outside_free_space(after, b'SECRET-')
    stale = [
        at for i in range(1, 200) for at in _occurrences(after, f'SECRET-{i:04d}-'.encode()) if _page(after, at) == 5
    ]
    assert stale  # deleted rows, sitting on the overflow page
    assert all(page5[0].start <= at < page5[0].end for at in stale)
    # the text never moved: each copy is at the offset it had while the row was live
    assert all(after[at : at + 12] == before[at : at + 12] for at in stale)
    assert after[page5[0].start : page5[0].end].count(b'SECRET-') == len(stale)


def test_secure_delete_leaves_no_text_in_an_overflow_page_tail(tmp_path):
    _, after = _overflow_slack_database(tmp_path / 'a.db', 'ON')

    assert after.count(b'SECRET-') == 0


@pytest.mark.skipif('ENABLE_STAT4' not in _compile_options(), reason='SQLite built without STAT4')
def test_sqlite_stat4_sample_keeps_a_deleted_key_as_a_live_row(tmp_path):
    db = tmp_path / 'a.db'
    conn = _connect(db, 'ON')
    _fill_notes(conn)
    conn.execute('ANALYZE')
    sampled = [bytes(row[0]) for row in conn.execute('SELECT sample FROM sqlite_stat4')]
    key = sampled[3][sampled[3].index(b'title-') :][:17]
    assert len(key) == 17

    conn.execute('DELETE FROM notes WHERE title = ?', (key.decode(),))
    still = conn.execute('SELECT count(*) FROM sqlite_stat4 WHERE instr(sample, ?) > 0', (key,)).fetchone()
    live_rows = conn.execute('SELECT count(*) FROM notes WHERE title = ?', (key.decode(),)).fetchone()
    conn.close()
    data = db.read_bytes()

    assert live_rows == (0,)
    assert still == (1,)  # a query on the statistics table finds it
    assert len(_outside_free_space(data, key)) == 1  # one live copy (the sample), no free-space copy
    assert data.count(key) == 1  # secure_delete wiped the table row and the index entry


@pytest.mark.skipif(not _compile_options() & {'ENABLE_FTS5'}, reason='SQLite built without FTS5')
def test_fts5_segment_keeps_a_deleted_token_as_a_live_row(tmp_path):
    db = tmp_path / 'a.db'
    conn = _connect(db, 'ON')
    conn.execute('CREATE VIRTUAL TABLE f USING fts5(body)')
    conn.execute('BEGIN')
    for i in range(1, 301):
        conn.execute('INSERT INTO f(rowid, body) VALUES (?, ?)', (i, f'common words doc{i} filler text'))
    conn.execute("INSERT INTO f(rowid, body) VALUES (1000, 'the zebrafishsecret appears here')")
    conn.execute('COMMIT')
    conn.execute('DELETE FROM f WHERE rowid = 1000')
    matching = conn.execute("SELECT count(*) FROM f WHERE f MATCH 'zebrafishsecret'").fetchone()
    in_segments = conn.execute("SELECT count(*) FROM f_data WHERE instr(block, CAST('zebrafishsecret' AS BLOB)) > 0")
    segments = in_segments.fetchone()
    conn.close()
    data = db.read_bytes()

    assert matching == (0,)  # gone for the full-text query
    assert segments[0] >= 1  # but the segment blob of the index still holds the token (live row of f_data)
    assert data.count(b'zebrafishsecret') >= 1
    assert len(_outside_free_space(data, b'zebrafishsecret')) == data.count(
        b'zebrafishsecret'
    )  # secure_delete: none free


def test_vacuum_removes_the_stale_copies(tmp_path):
    db = tmp_path / 'a.db'
    conn = _connect(db)
    _fill_notes(conn)
    conn.execute('DELETE FROM notes WHERE id BETWEEN 100 AND 300')
    assert db.read_bytes().count(b'title-0152-secret') >= 1
    conn.execute('VACUUM')
    conn.close()

    assert db.read_bytes().count(b'title-0152-secret') == 0
