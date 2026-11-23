"""SQLite WAL parser: header checks, checksum chain, valid/commit/all/stale frame counts.

WAL files are written by the stdlib sqlite3 module in the test, so the parser is checked
against what SQLite itself writes (and, for the big-endian variant, what SQLite replays).
Runs on the guests' Python 3.10 too (``make test-adarelib-guest``).
"""

import contextlib
import shutil
import sqlite3
import struct

import pytest

from adarelib.testset import sqlite_wal
from adarelib.testset.sqlite_wal import WalFormatError, parse_wal, wal_checksum

pytestmark = pytest.mark.unit

PAGE = 4096


@contextlib.contextmanager
def wal_db(path):
    """A WAL-mode database without auto-checkpoint; the connection stays open."""
    conn = sqlite3.connect(str(path))
    try:
        conn.execute('PRAGMA page_size=4096')
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA wal_autocheckpoint=0')
        conn.execute('CREATE TABLE items (id INTEGER, name TEXT)')
        conn.commit()
        conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        yield conn
    finally:
        conn.close()


def _insert(conn, *ids, size=10):
    for i in ids:
        conn.execute('INSERT INTO items VALUES (?, ?)', (i, 'x' * size))
        conn.commit()


def _copy_wal(db, dst):
    shutil.copyfile(f'{db}-wal', dst)
    return dst


def _rows(db):
    with contextlib.closing(sqlite3.connect(str(db))) as conn:
        return conn.execute('SELECT id FROM items ORDER BY id').fetchall()


def _reencode_big_endian(data: bytes) -> bytes:
    """The same WAL with magic 0x377f0683 and its checksums recomputed big-endian."""
    page_size = struct.unpack('>I', data[8:12])[0]
    header = struct.pack('>I', sqlite_wal.WAL_MAGIC_BIG_ENDIAN) + data[4:24]
    checksum = wal_checksum(header, big_endian=True)
    out = [header + struct.pack('>2I', *checksum)]
    frame_size = 24 + page_size
    for offset in range(32, len(data) - frame_size + 1, frame_size):
        frame = data[offset : offset + frame_size]
        checksum = wal_checksum(frame[:8], *checksum, big_endian=True)
        checksum = wal_checksum(frame[24:], *checksum, big_endian=True)
        out.append(frame[:16] + struct.pack('>2I', *checksum) + frame[24:])
    return b''.join(out)


def test_checksum_reference_values():
    # s0 += x0 + s1; s1 += x1 + s0 over 32-bit words
    assert wal_checksum(struct.pack('<2I', 1, 2)) == (1, 3)
    assert wal_checksum(struct.pack('<4I', 1, 2, 3, 4)) == (7, 14)
    assert wal_checksum(struct.pack('>2I', 1, 2), big_endian=True) == (1, 3)
    # wraps modulo 2**32
    assert wal_checksum(struct.pack('<2I', 0xFFFFFFFF, 1)) == (0xFFFFFFFF, 0)


def test_checksum_rejects_unaligned_data():
    with pytest.raises(ValueError, match='multiple of 8'):
        wal_checksum(b'\0' * 12)


def test_counts_transactions_in_wal(tmp_path):
    db = tmp_path / 'data.db'
    with wal_db(db) as conn:
        _insert(conn, 1, 2, 3)
        info = parse_wal(_copy_wal(db, tmp_path / 'copy-wal'))

    assert info.page_size == PAGE
    assert not info.big_endian_checksums  # SQLite writes native order; tests run on little-endian hosts
    assert info.commit_frames == 3
    assert info.valid_frames == info.total_frames >= 3
    assert info.stale_frames == 0
    assert info.trailing_bytes == 0
    assert {k: info.count(k) for k in sqlite_wal.FRAME_KINDS} == {
        'valid': info.valid_frames,
        'commits': 3,
        'all': info.total_frames,
        'stale': 0,
    }


def test_frames_left_from_before_a_wal_reset_are_stale(tmp_path):
    db = tmp_path / 'data.db'
    with wal_db(db) as conn:
        _insert(conn, 1, 2, 3, 4, size=3000)  # several pages
        before = parse_wal(_copy_wal(db, tmp_path / 'before-wal'))
        assert conn.execute('PRAGMA wal_checkpoint(RESTART)').fetchone()[0] == 0
        _insert(conn, 5)  # the next writer restarts the WAL from its start
        info = parse_wal(_copy_wal(db, tmp_path / 'after-wal'))

    assert info.salt1 == (before.salt1 + 1) & 0xFFFFFFFF
    assert info.checkpoint_sequence == before.checkpoint_sequence + 1
    assert info.total_frames == before.total_frames  # the file was overwritten, not truncated
    assert info.commit_frames == 1
    assert 1 <= info.valid_frames < info.total_frames
    assert info.stale_frames == info.total_frames - info.valid_frames


def test_truncate_checkpoint_leaves_an_empty_wal(tmp_path):
    db = tmp_path / 'data.db'
    with wal_db(db) as conn:
        _insert(conn, 1)
        conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        info = parse_wal(_copy_wal(db, tmp_path / 'copy-wal'))

    assert info == sqlite_wal.EMPTY_WAL
    assert {k: info.count(k) for k in sqlite_wal.FRAME_KINDS} == {'valid': 0, 'commits': 0, 'all': 0, 'stale': 0}


def test_uncommitted_tail_and_partial_frame_are_not_valid(tmp_path):
    db = tmp_path / 'data.db'
    with wal_db(db) as conn:
        _insert(conn, 1)
        _insert(conn, 2)
        data = (tmp_path / 'data.db-wal').read_bytes()
        complete = parse_wal(_copy_wal(db, tmp_path / 'full-wal'))
    frame_size = 24 + PAGE
    head, last = data[:-frame_size], data[-frame_size:]
    # rewrite the last (commit) frame as a non-commit frame with an intact checksum chain:
    # a transaction whose commit frame was never written
    previous = struct.unpack('>2I', head[-frame_size + 16 : -frame_size + 24])
    frame_start = last[:4] + b'\0\0\0\0'
    checksum = wal_checksum(last[24:], *wal_checksum(frame_start, *previous))
    tail = frame_start + last[8:16] + struct.pack('>2I', *checksum) + last[24:]
    path = tmp_path / 'tail-wal'
    path.write_bytes(head + tail + b'\0' * 100)  # plus a partially written frame

    info = parse_wal(path)

    assert complete.commit_frames == 2
    assert info.total_frames == complete.total_frames
    assert info.trailing_bytes == 100
    assert info.commit_frames == 1
    assert info.valid_frames < complete.valid_frames  # frames after the last commit are not replayed
    assert info.stale_frames == info.total_frames - info.valid_frames


def test_broken_checksum_ends_the_valid_prefix(tmp_path):
    db = tmp_path / 'data.db'
    with wal_db(db) as conn:
        _insert(conn, 1)
        first_txn = parse_wal(_copy_wal(db, tmp_path / 'one-wal')).total_frames
        _insert(conn, 2)
        data = bytearray((tmp_path / 'data.db-wal').read_bytes())
        complete = parse_wal(_copy_wal(db, tmp_path / 'two-wal'))
    # flip a byte in the page data of the first frame of the second transaction
    data[32 + first_txn * (24 + PAGE) + 24 + 100] ^= 0xFF
    path = tmp_path / 'broken-wal'
    path.write_bytes(bytes(data))

    info = parse_wal(path)

    assert complete.commit_frames == 2
    assert info.commit_frames == 1
    assert info.valid_frames == first_txn
    assert info.total_frames == complete.total_frames


def test_big_endian_variant_matches_what_sqlite_replays(tmp_path):
    live = tmp_path / 'live'
    evidence = tmp_path / 'evidence'
    live.mkdir()
    evidence.mkdir()
    db = live / 'data.db'
    with wal_db(db) as conn:
        _insert(conn, 1, 2)
        shutil.copyfile(db, evidence / 'data.db')
        little = (live / 'data.db-wal').read_bytes()
    (evidence / 'data.db-wal').write_bytes(_reencode_big_endian(little))
    big_info = parse_wal(evidence / 'data.db-wal')
    little_path = tmp_path / 'little-wal'
    little_path.write_bytes(little)
    little_info = parse_wal(little_path)

    assert struct.unpack('>I', (evidence / 'data.db-wal').read_bytes()[:4])[0] == 0x377F0683
    assert big_info.big_endian_checksums
    assert (big_info.total_frames, big_info.valid_frames, big_info.commit_frames) == (
        little_info.total_frames,
        little_info.valid_frames,
        2,
    )
    # SQLite accepts the re-encoded WAL: both rows are replayed
    assert _rows(evidence / 'data.db') == [(1,), (2,)]


@pytest.mark.parametrize(
    ('mutate', 'message'),
    [
        (lambda h: h[:10], 'truncated: 10 of 32'),
        (lambda h: b'\0\0\0\0' + h[4:], 'not an SQLite WAL'),
        (lambda h: h[:4] + struct.pack('>I', 3007001) + h[8:], 'unsupported WAL format version 3007001'),
        (lambda h: h[:8] + struct.pack('>I', 1000) + h[12:], 'invalid WAL page size 1000'),
        (lambda h: h[:8] + struct.pack('>I', 256) + h[12:], 'invalid WAL page size 256'),
        (lambda h: h[:16] + bytes([h[16] ^ 1]) + h[17:], 'header checksum mismatch'),
    ],
    ids=['short', 'magic', 'version', 'page-size', 'small-page', 'checksum'],
)
def test_invalid_header_is_an_error(tmp_path, mutate, message):
    db = tmp_path / 'data.db'
    with wal_db(db) as conn:
        _insert(conn, 1)
        data = (tmp_path / 'data.db-wal').read_bytes()
    path = tmp_path / 'bad-wal'
    path.write_bytes(mutate(data[:32]) + (data[32:] if len(mutate(data[:32])) == 32 else b''))

    with pytest.raises(WalFormatError, match=message):
        parse_wal(path)


def test_empty_file_has_no_frames(tmp_path):
    path = tmp_path / 'empty-wal'
    path.write_bytes(b'')

    assert parse_wal(path).count('all') == 0


def test_header_only_has_no_frames(tmp_path):
    db = tmp_path / 'data.db'
    with wal_db(db) as conn:
        _insert(conn, 1)
        header = (tmp_path / 'data.db-wal').read_bytes()[:32]
    path = tmp_path / 'header-wal'
    path.write_bytes(header)

    info = parse_wal(path)

    assert (info.total_frames, info.valid_frames, info.page_size) == (0, 0, PAGE)


def test_missing_file_raises_oserror(tmp_path):
    with pytest.raises(FileNotFoundError):
        parse_wal(tmp_path / 'absent-wal')


def test_unknown_kind_is_rejected():
    with pytest.raises(ValueError, match='invalid frames'):
        sqlite_wal.EMPTY_WAL.count('pages')
