"""Parsing an SQLite write-ahead log (``<database>-wal``) without SQLite.

Follows the WAL file format of https://www.sqlite.org/fileformat2.html#walformat:

* a 32-byte header (big-endian fields): magic ``0x377f0682`` / ``0x377f0683`` (the low bit
  selects the byte order of the checksums: 1 = big-endian), format version ``3007000``, page
  size, checkpoint sequence number, salt-1, salt-2 and a checksum over the first 24 bytes;
* then frames of a 24-byte frame header (page number, database size in pages after a commit,
  nonzero only in the last frame of a transaction, salt-1, salt-2, cumulative checksum) plus one
  page of data.

A frame is valid when its salts equal the header's and its checksum, computed over the frame
header's first 8 bytes and the page data and seeded with the previous frame's checksum (the
header's for the first frame), matches. SQLite replays the valid frames from the start of the
file up to the last commit frame among them; everything else in the file (frames left over from
before a WAL reset, an unfinished transaction) is stale and never read by SQLite.

Ships with the agent's adarelib wheel. Standard library only, importable on Python 3.10.
"""

import struct
from dataclasses import dataclass

WAL_MAGIC_LITTLE_ENDIAN = 0x377F0682
WAL_MAGIC_BIG_ENDIAN = 0x377F0683
WAL_FORMAT_VERSION = 3007000
WAL_HEADER_SIZE = 32
WAL_FRAME_HEADER_SIZE = 24
MIN_PAGE_SIZE = 512
MAX_PAGE_SIZE = 65536

# What wal_frame_count can count (see WalInfo.count).
FRAME_KINDS = ('valid', 'commits', 'all', 'stale')

_MASK = 0xFFFFFFFF


class WalFormatError(ValueError):
    """The file is not a usable SQLite WAL (short, wrong magic or version, bad header checksum)."""


@dataclass(frozen=True)
class WalInfo:
    """Header fields and frame counts of one WAL file."""

    big_endian_checksums: bool
    page_size: int
    checkpoint_sequence: int
    salt1: int
    salt2: int
    total_frames: int  # every complete frame in the file
    valid_frames: int  # frames SQLite replays: valid prefix up to the last commit frame
    commit_frames: int  # commit frames among the valid frames (= transactions)
    trailing_bytes: int  # bytes after the last complete frame (an incompletely written frame)

    @property
    def stale_frames(self) -> int:
        """Frames in the file that SQLite does not replay."""
        return self.total_frames - self.valid_frames

    def count(self, kind: str) -> int:
        """The count for one of :data:`FRAME_KINDS`.

        :raises ValueError: unknown ``kind``
        """
        counts = {
            'valid': self.valid_frames,
            'commits': self.commit_frames,
            'all': self.total_frames,
            'stale': self.stale_frames,
        }
        if kind not in counts:
            raise ValueError(f"invalid frames {kind!r} (allowed: {', '.join(FRAME_KINDS)})")
        return counts[kind]


EMPTY_WAL = WalInfo(
    big_endian_checksums=False,
    page_size=0,
    checkpoint_sequence=0,
    salt1=0,
    salt2=0,
    total_frames=0,
    valid_frames=0,
    commit_frames=0,
    trailing_bytes=0,
)


def wal_checksum(data: bytes, s0: int = 0, s1: int = 0, big_endian: bool = False) -> tuple[int, int]:
    """The WAL checksum of ``data`` (length a multiple of 8), continuing from ``(s0, s1)``.

    Per the file format: ``data`` is read as 32-bit unsigned integers ``x`` in the byte order
    the magic selects, and for each pair ``s0 += x[i] + s1; s1 += x[i+1] + s0`` modulo 2**32.
    """
    if len(data) % 8:
        raise ValueError(f'checksummed data must be a multiple of 8 bytes, got {len(data)}')
    words = struct.unpack(f"{'>' if big_endian else '<'}{len(data) // 4}I", data)
    for i in range(0, len(words), 2):
        s0 = (s0 + words[i] + s1) & _MASK
        s1 = (s1 + words[i + 1] + s0) & _MASK
    return s0, s1


def _parse_header(header: bytes) -> tuple[bool, int, int, int, int, tuple[int, int]]:
    """Check the 32-byte header; return (big-endian, page size, checkpoint seq, salt-1, salt-2, checksum)."""
    magic, version, page_size, checkpoint_seq, salt1, salt2, c0, c1 = struct.unpack('>8I', header)
    if magic not in (WAL_MAGIC_LITTLE_ENDIAN, WAL_MAGIC_BIG_ENDIAN):
        raise WalFormatError(f'not an SQLite WAL: magic 0x{magic:08x} (expected 0x377f0682 or 0x377f0683)')
    if version != WAL_FORMAT_VERSION:
        raise WalFormatError(f'unsupported WAL format version {version} (expected {WAL_FORMAT_VERSION})')
    if page_size < MIN_PAGE_SIZE or page_size > MAX_PAGE_SIZE or page_size & (page_size - 1):
        raise WalFormatError(f'invalid WAL page size {page_size} (a power of two from 512 to 65536)')
    big_endian = bool(magic & 1)
    if wal_checksum(header[:24], big_endian=big_endian) != (c0, c1):
        raise WalFormatError('WAL header checksum mismatch (SQLite would ignore this WAL)')
    return big_endian, page_size, checkpoint_seq, salt1, salt2, (c0, c1)


def parse_wal(path: str) -> WalInfo:
    """Parse the WAL file at ``path``; an empty (0-byte) file is a WAL with no frames.

    :raises WalFormatError: the header is short or invalid
    :raises OSError: the file cannot be read
    """
    with open(path, 'rb') as f:
        header = f.read(WAL_HEADER_SIZE)
        if not header:
            return EMPTY_WAL
        if len(header) < WAL_HEADER_SIZE:
            raise WalFormatError(f'WAL header is truncated: {len(header)} of {WAL_HEADER_SIZE} bytes')
        big_endian, page_size, checkpoint_seq, salt1, salt2, checksum = _parse_header(header)

        frame_size = WAL_FRAME_HEADER_SIZE + page_size
        total = valid = commits = valid_through_commit = 0
        in_valid_prefix = True
        trailing = 0
        while True:
            frame = f.read(frame_size)
            if len(frame) < frame_size:
                trailing = len(frame)
                break
            total += 1
            if not in_valid_prefix:
                continue
            page_number, db_size, f_salt1, f_salt2, f_c0, f_c1 = struct.unpack('>6I', frame[:WAL_FRAME_HEADER_SIZE])
            if page_number == 0 or (f_salt1, f_salt2) != (salt1, salt2):
                in_valid_prefix = False
                continue
            checksum = wal_checksum(frame[:8], *checksum, big_endian=big_endian)
            checksum = wal_checksum(frame[WAL_FRAME_HEADER_SIZE:], *checksum, big_endian=big_endian)
            if checksum != (f_c0, f_c1):
                in_valid_prefix = False
                continue
            valid += 1
            if db_size:
                commits += 1
                valid_through_commit = valid

    return WalInfo(
        big_endian_checksums=big_endian,
        page_size=page_size,
        checkpoint_sequence=checkpoint_seq,
        salt1=salt1,
        salt2=salt2,
        total_frames=total,
        valid_frames=valid_through_commit,
        commit_frames=commits,
        trailing_bytes=trailing,
    )
