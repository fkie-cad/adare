"""LZ4 decompression in pure Python, for reading LZ4-compressed files in file testfunctions.

Two container formats are supported:

* the LZ4 frame format (magic ``04 22 4D 18``): block and content checksums are verified,
  linked and independent blocks, uncompressed blocks, concatenated and skippable frames.
  Frames that need a dictionary and the legacy frame format are not supported.
* an LZ4 block with an 8-byte magic and size header (the magic, then the decompressed
  size as u32 little-endian, then one LZ4 block), a format some applications use for JSON
  stores (file suffix ``.jsonlz4``).

Standard library only (the guest agent runs on Python 3.10); no ``lz4`` package needed.
Every decoder takes ``max_bytes`` and raises :class:`Lz4SizeError` before producing more
output than that, so a small file cannot expand into an unbounded allocation.
"""

import struct
from dataclasses import dataclass

FRAME_MAGIC = b'\x04\x22\x4d\x18'
LEGACY_FRAME_MAGIC = b'\x02\x21\x4c\x18'
BLOCK_HEADER_MAGIC = b'mozLz40\x00'
# skippable frames: magic 0x184D2A50 .. 0x184D2A5F (little-endian)
SKIPPABLE_MAGICS = tuple(bytes([0x50 + i, 0x2A, 0x4D, 0x18]) for i in range(16))

_BLOCK_MAX_SIZES = {4: 64 << 10, 5: 256 << 10, 6: 1 << 20, 7: 4 << 20}
_MIN_MATCH = 4


class Lz4Error(Exception):
    """The data is not valid LZ4 (truncated, corrupt, bad checksum) or uses an unsupported feature."""


class Lz4SizeError(Lz4Error):
    """The decompressed data would exceed the size cap."""


# ---------------------------------------------------------------------------
# xxHash32 (frame checksums)
# ---------------------------------------------------------------------------

_P1 = 2654435761
_P2 = 2246822519
_P3 = 3266489917
_P4 = 668265263
_P5 = 374761393
_M32 = 0xFFFFFFFF
_STRIPES_PER_CHUNK = 1 << 14  # 256 KiB of input per unpack


def _rotl(x: int, r: int) -> int:
    return ((x << r) | (x >> (32 - r))) & _M32


def xxh32(data: bytes | memoryview, seed: int = 0) -> int:
    """xxHash32 of ``data`` (the checksum the LZ4 frame format uses)."""
    length = len(data)
    pos = 0
    if length >= 16:
        v1 = (seed + _P1 + _P2) & _M32
        v2 = (seed + _P2) & _M32
        v3 = seed & _M32
        v4 = (seed - _P1) & _M32
        stripes = length // 16
        # unpack in bounded chunks: a tuple of ints costs ~10x the bytes it holds
        for first in range(0, stripes, _STRIPES_PER_CHUNK):
            count = min(_STRIPES_PER_CHUNK, stripes - first)
            lanes = struct.unpack_from(f'<{count * 4}I', data, first * 16)
            for i in range(0, count * 4, 4):
                v1 = (_rotl((v1 + lanes[i] * _P2) & _M32, 13) * _P1) & _M32
                v2 = (_rotl((v2 + lanes[i + 1] * _P2) & _M32, 13) * _P1) & _M32
                v3 = (_rotl((v3 + lanes[i + 2] * _P2) & _M32, 13) * _P1) & _M32
                v4 = (_rotl((v4 + lanes[i + 3] * _P2) & _M32, 13) * _P1) & _M32
        h = (_rotl(v1, 1) + _rotl(v2, 7) + _rotl(v3, 12) + _rotl(v4, 18)) & _M32
        pos = stripes * 16
    else:
        h = (seed + _P5) & _M32
    h = (h + length) & _M32
    while pos + 4 <= length:
        (lane,) = struct.unpack_from('<I', data, pos)
        h = (_rotl((h + lane * _P3) & _M32, 17) * _P4) & _M32
        pos += 4
    while pos < length:
        h = (_rotl((h + data[pos] * _P5) & _M32, 11) * _P1) & _M32
        pos += 1
    h ^= h >> 15
    h = (h * _P2) & _M32
    h ^= h >> 13
    h = (h * _P3) & _M32
    h ^= h >> 16
    return h


# ---------------------------------------------------------------------------
# Block format
# ---------------------------------------------------------------------------


def _read_length(src: bytes, pos: int, base: int) -> tuple[int, int]:
    """Extend a 4-bit length of 15 with the following bytes (255 = continue)."""
    length = base
    if base == 15:
        while True:
            if pos >= len(src):
                raise Lz4Error('truncated LZ4 block (length extension past the end)')
            byte = src[pos]
            pos += 1
            length += byte
            if byte != 255:
                break
    return length, pos


def decode_block(src: bytes, out: bytearray, max_bytes: int, window_start: int = 0, stop_at: int | None = None) -> None:
    """Decode one LZ4 block from ``src``, appending to ``out``.

    Matches may reach back to ``window_start`` in ``out`` (0 for linked blocks, where the
    previous blocks are the dictionary; ``len(out)`` before the call for independent ones).
    Decoding stops early once ``out`` holds ``stop_at`` bytes.

    :raises Lz4Error: corrupt or truncated block
    :raises Lz4SizeError: ``out`` would grow beyond ``max_bytes``
    """
    pos = 0
    end = len(src)
    if end == 0:
        raise Lz4Error('empty LZ4 block')
    while True:
        if pos >= end:
            raise Lz4Error('truncated LZ4 block (missing token)')
        token = src[pos]
        pos += 1
        literal_len, pos = _read_length(src, pos, token >> 4)
        if literal_len:
            if pos + literal_len > end:
                raise Lz4Error('truncated LZ4 block (literals past the end)')
            if len(out) + literal_len > max_bytes:
                raise Lz4SizeError(f'decompressed LZ4 data is larger than the size cap of {max_bytes} bytes')
            out += src[pos : pos + literal_len]
            pos += literal_len
        if pos == end:  # the last sequence has literals only
            return
        if stop_at is not None and len(out) >= stop_at:
            return
        if pos + 2 > end:
            raise Lz4Error('truncated LZ4 block (missing match offset)')
        offset = src[pos] | (src[pos + 1] << 8)
        pos += 2
        if offset == 0:
            raise Lz4Error('corrupt LZ4 block (match offset 0)')
        match_len, pos = _read_length(src, pos, token & 0x0F)
        match_len += _MIN_MATCH
        start = len(out) - offset
        if start < window_start:
            raise Lz4Error('corrupt LZ4 block (match offset before the start of the data)')
        if len(out) + match_len > max_bytes:
            raise Lz4SizeError(f'decompressed LZ4 data is larger than the size cap of {max_bytes} bytes')
        if offset >= match_len:
            out += out[start : start + match_len]
        else:
            # overlapping match: the last `offset` bytes repeat
            pattern = bytes(out[start:])
            repeats = match_len // offset + 1
            out += (pattern * repeats)[:match_len]
        if stop_at is not None and len(out) >= stop_at:
            return


def decompress_block_with_header(data: bytes, max_bytes: int, stop_at: int | None = None) -> bytes:
    """Decode an LZ4 block with an 8-byte magic and size header (magic + u32 LE size + block)."""
    if not data.startswith(BLOCK_HEADER_MAGIC):
        raise Lz4Error('not an LZ4 block with header (wrong magic)')
    if len(data) < 12:
        raise Lz4Error('truncated LZ4 block header')
    (size,) = struct.unpack_from('<I', data, 8)
    if size > max_bytes:
        raise Lz4SizeError(f'LZ4 header announces {size} decompressed bytes, over the size cap of {max_bytes} bytes')
    out = bytearray()
    if size == 0 and len(data) == 12:
        return b''
    try:
        decode_block(data[12:], out, size, stop_at=stop_at)
    except Lz4SizeError as e:
        # the limit here is the header's size (already within the cap): the block is corrupt
        raise Lz4Error(f'LZ4 block is larger than its header announces {size} bytes') from e
    if stop_at is None and len(out) != size:
        raise Lz4Error(f'LZ4 block decoded to {len(out)} bytes, header announces {size}')
    return bytes(out)


# ---------------------------------------------------------------------------
# Frame format
# ---------------------------------------------------------------------------


def _need(data: bytes, pos: int, count: int, what: str) -> None:
    if pos + count > len(data):
        raise Lz4Error(f'truncated LZ4 frame ({what})')


@dataclass(frozen=True)
class _FrameHeader:
    independent: bool
    block_checksum: bool
    content_checksum: bool
    block_max: int
    content_size: int | None


def _read_frame_header(data: bytes, pos: int, already: int, max_bytes: int) -> tuple[_FrameHeader, int]:
    """Parse and verify the frame descriptor at ``pos``; return it and the position after it."""
    _need(data, pos, 3, 'frame descriptor')
    descriptor_start = pos
    flg, bd = data[pos], data[pos + 1]
    pos += 2
    if flg >> 6 != 1:
        raise Lz4Error(f'unsupported LZ4 frame version {flg >> 6}')
    if flg & 0x02 or bd & 0x8F:
        raise Lz4Error('corrupt LZ4 frame descriptor (reserved bits set)')
    if flg & 0x01:
        raise Lz4Error('LZ4 frames that need a dictionary are not supported')
    block_max = _BLOCK_MAX_SIZES.get((bd >> 4) & 0x07)
    if block_max is None:
        raise Lz4Error(f'corrupt LZ4 frame descriptor (block size code {(bd >> 4) & 0x07})')
    content_size = None
    if flg & 0x08:
        _need(data, pos, 8, 'content size')
        (content_size,) = struct.unpack_from('<Q', data, pos)
        pos += 8
        if already + content_size > max_bytes:
            raise Lz4SizeError(
                f'LZ4 frame announces {content_size} decompressed bytes, over the size cap of {max_bytes} bytes'
            )
    _need(data, pos, 1, 'header checksum')
    if data[pos] != (xxh32(bytes(data[descriptor_start:pos])) >> 8) & 0xFF:
        raise Lz4Error('corrupt LZ4 frame (header checksum mismatch)')
    header = _FrameHeader(
        independent=bool(flg & 0x20),
        block_checksum=bool(flg & 0x10),
        content_checksum=bool(flg & 0x04),
        block_max=block_max,
        content_size=content_size,
    )
    return header, pos + 1


def _read_checksum(data: bytes, pos: int, covered: bytes | memoryview, what: str) -> int:
    """Verify the u32 xxh32 checksum of ``covered`` stored at ``pos``; return the position after it."""
    _need(data, pos, 4, what)
    (stored,) = struct.unpack_from('<I', data, pos)
    if xxh32(covered) != stored:
        raise Lz4Error(f'corrupt LZ4 frame ({what} mismatch)')
    return pos + 4


def _decode_frame(data: bytes, pos: int, out: bytearray, max_bytes: int, stop_at: int | None) -> int:
    """Decode the frame starting after its magic at ``pos``; return the position after it."""
    header, pos = _read_frame_header(data, pos, len(out), max_bytes)
    frame_start = len(out)
    while True:
        _need(data, pos, 4, 'block size')
        (raw_size,) = struct.unpack_from('<I', data, pos)
        pos += 4
        if raw_size == 0:  # end mark
            break
        size = raw_size & 0x7FFFFFFF
        if size > header.block_max:
            raise Lz4Error(f'corrupt LZ4 frame (block of {size} bytes, maximum {header.block_max})')
        _need(data, pos, size, 'block data')
        block = bytes(data[pos : pos + size])
        pos += size
        if header.block_checksum:
            pos = _read_checksum(data, pos, block, 'block checksum')
        if raw_size & 0x80000000:  # stored uncompressed
            if len(out) + size > max_bytes:
                raise Lz4SizeError(f'decompressed LZ4 data is larger than the size cap of {max_bytes} bytes')
            out += block
        else:
            window = len(out) if header.independent else frame_start
            decode_block(block, out, max_bytes, window_start=window, stop_at=stop_at)
        if stop_at is not None and len(out) >= stop_at:
            return len(data)

    if header.content_checksum:
        pos = _read_checksum(data, pos, memoryview(out)[frame_start:], 'content checksum')
    decoded = len(out) - frame_start
    if header.content_size is not None and decoded != header.content_size:
        raise Lz4Error(f'LZ4 frame decoded to {decoded} bytes, header announces {header.content_size}')
    return pos


def decompress_frames(data: bytes, max_bytes: int, stop_at: int | None = None) -> bytes:
    """Decode one or more concatenated LZ4 frames (skippable frames are skipped)."""
    out = bytearray()
    pos = 0
    if not data:
        raise Lz4Error('empty LZ4 frame data')
    while pos < len(data):
        _need(data, pos, 4, 'magic')
        magic = bytes(data[pos : pos + 4])
        pos += 4
        if magic == FRAME_MAGIC:
            pos = _decode_frame(data, pos, out, max_bytes, stop_at)
        elif magic in SKIPPABLE_MAGICS:
            _need(data, pos, 4, 'skippable frame size')
            (size,) = struct.unpack_from('<I', data, pos)
            pos += 4
            _need(data, pos, size, 'skippable frame data')
            pos += size
        elif magic == LEGACY_FRAME_MAGIC:
            raise Lz4Error('the legacy LZ4 frame format is not supported')
        else:
            raise Lz4Error(f'unexpected data after LZ4 frame at offset {pos - 4} (magic {magic.hex()})')
        if stop_at is not None and len(out) >= stop_at:
            break
    return bytes(out)


def decompress(data: bytes, max_bytes: int, stop_at: int | None = None) -> bytes:
    """Decode LZ4 data in either supported container format, chosen by its magic bytes.

    :param max_bytes: size cap for the decompressed data
    :param stop_at: stop once this many bytes are decoded (to sniff the content); checksums
                    of unfinished frames are then not verified
    :raises Lz4Error: not LZ4, corrupt, truncated, bad checksum or unsupported feature
    :raises Lz4SizeError: the decompressed data would exceed ``max_bytes``
    """
    if data.startswith(BLOCK_HEADER_MAGIC):
        return decompress_block_with_header(data, max_bytes, stop_at)
    if data[:4] in (FRAME_MAGIC, LEGACY_FRAME_MAGIC, *SKIPPABLE_MAGICS):
        return decompress_frames(data, max_bytes, stop_at)
    raise Lz4Error('not LZ4 data (unknown magic)')
