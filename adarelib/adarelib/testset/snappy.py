"""Snappy decompression in pure Python, for reading Snappy-compressed files in file testfunctions.

Two formats are supported:

* the Snappy framing format (stream identifier ``ff 06 00 00 73 4e 61 50 70 59``, file
  suffix ``.sz``): compressed and uncompressed chunks with their masked CRC-32C checksums
  verified, padding and skippable chunks skipped, repeated stream identifiers allowed.
* a raw Snappy block (a varint of the decompressed length, then literal and copy
  elements). It has no magic bytes, so it is never detected from file content; the
  decoder is for formats that embed raw blocks.

Standard library only (the guest agent runs on Python 3.10); no ``snappy`` package needed.
Every decoder takes ``max_bytes`` and raises :class:`SnappySizeError` before producing more
output than that, so a small file cannot expand into an unbounded allocation.
"""

import struct

STREAM_IDENTIFIER = b'\xff\x06\x00\x00sNaPpY'
_STREAM_IDENTIFIER_BODY = b'sNaPpY'
_MAX_CHUNK_UNCOMPRESSED = 65536

_CHUNK_COMPRESSED = 0x00
_CHUNK_UNCOMPRESSED = 0x01
_CHUNK_PADDING = 0xFE
_CHUNK_STREAM_IDENTIFIER = 0xFF


class SnappyError(Exception):
    """The data is not valid Snappy (truncated, corrupt, bad checksum) or uses an unsupported feature."""


class SnappySizeError(SnappyError):
    """The decompressed data would exceed the size cap."""


# ---------------------------------------------------------------------------
# CRC-32C (Castagnoli), used by the framing format
# ---------------------------------------------------------------------------

_M32 = 0xFFFFFFFF


def _make_crc32c_tables() -> tuple[list[int], ...]:
    """Lookup tables for slicing-by-4 (reflected polynomial 0x82F63B78)."""
    base = []
    for n in range(256):
        crc = n
        for _ in range(8):
            crc = (crc >> 1) ^ 0x82F63B78 if crc & 1 else crc >> 1
        base.append(crc)
    tables = [base]
    for _ in range(3):
        prev = tables[-1]
        tables.append([(prev[n] >> 8) ^ base[prev[n] & 0xFF] for n in range(256)])
    return tuple(tables)


_T0, _T1, _T2, _T3 = _make_crc32c_tables()


def crc32c(data: bytes | memoryview, crc: int = 0) -> int:
    """CRC-32C (Castagnoli) of ``data``, continuing from ``crc``."""
    t0, t1, t2, t3 = _T0, _T1, _T2, _T3
    crc ^= _M32
    words = len(data) // 4
    if words:
        for word in struct.unpack_from(f'<{words}I', data):
            crc ^= word
            crc = t3[crc & 0xFF] ^ t2[(crc >> 8) & 0xFF] ^ t1[(crc >> 16) & 0xFF] ^ t0[crc >> 24]
    for byte in bytes(data[words * 4 :]):
        crc = t0[(crc ^ byte) & 0xFF] ^ (crc >> 8)
    return crc ^ _M32


def masked_crc32c(data: bytes | memoryview) -> int:
    """The masked CRC-32C the framing format stores for each chunk."""
    crc = crc32c(data)
    return (((crc >> 15) | (crc << 17)) + 0xA282EAD8) & _M32


# ---------------------------------------------------------------------------
# Raw block format
# ---------------------------------------------------------------------------


def _read_varint(src: bytes, pos: int) -> tuple[int, int]:
    """Decode the little-endian base-128 decompressed length (at most 32 bits)."""
    value = 0
    for shift in range(0, 35, 7):
        if pos >= len(src):
            raise SnappyError('truncated Snappy block (length header)')
        byte = src[pos]
        pos += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            if value > _M32:
                break
            return value, pos
    raise SnappyError('corrupt Snappy block (length header longer than 32 bits)')


def _read_copy(src: bytes, pos: int, tag: int) -> tuple[int, int, int]:
    """Length and offset of the copy element whose tag byte was just read; the position after it."""
    kind = tag & 0x03
    width = (0, 1, 2, 4)[kind]
    if pos + width > len(src):
        raise SnappyError('truncated Snappy block (copy offset past the end)')
    if kind == 1:  # 1-byte offset: length 4..11, offset 11 bits (3 of them in the tag)
        return 4 + ((tag >> 2) & 0x07), ((tag >> 5) << 8) | src[pos], pos + 1
    if kind == 2:
        return 1 + (tag >> 2), src[pos] | (src[pos + 1] << 8), pos + 2
    (offset,) = struct.unpack_from('<I', src, pos)
    return 1 + (tag >> 2), offset, pos + 4


def decode_block(src: bytes, out: bytearray, max_bytes: int, max_length: int | None = None) -> None:
    """Decode one raw Snappy block from ``src``, appending to ``out``.

    Copies may only reach back into this block's own output. ``max_length`` rejects a block
    that announces more decompressed bytes than its container allows (as corrupt, not as
    over the size cap).

    :raises SnappyError: corrupt or truncated block
    :raises SnappySizeError: ``out`` would grow beyond ``max_bytes``
    """
    length, pos = _read_varint(src, 0)
    if max_length is not None and length > max_length:
        raise SnappyError(f'corrupt Snappy data (block of {length} decompressed bytes, maximum {max_length})')
    if len(out) + length > max_bytes:
        raise SnappySizeError(
            f'Snappy block announces {length} decompressed bytes, over the size cap of {max_bytes} bytes'
        )
    start = len(out)
    expected_end = start + length
    end = len(src)
    while pos < end:
        tag = src[pos]
        pos += 1
        if tag & 0x03 == 0:  # literal
            size = tag >> 2
            if size >= 60:  # the length minus one follows in 1..4 bytes
                extra = size - 59
                if pos + extra > end:
                    raise SnappyError('truncated Snappy block (literal length past the end)')
                size = int.from_bytes(src[pos : pos + extra], 'little')
                pos += extra
            size += 1
            if pos + size > end:
                raise SnappyError('truncated Snappy block (literal past the end)')
            if len(out) + size > expected_end:
                raise SnappyError(f'corrupt Snappy block (more data than the {length} bytes the header announces)')
            out += src[pos : pos + size]
            pos += size
            continue
        size, offset, pos = _read_copy(src, pos, tag)
        if offset == 0:
            raise SnappyError('corrupt Snappy block (copy offset 0)')
        if offset > len(out) - start:
            raise SnappyError('corrupt Snappy block (copy offset before the start of the data)')
        if len(out) + size > expected_end:
            raise SnappyError(f'corrupt Snappy block (more data than the {length} bytes the header announces)')
        copy_from = len(out) - offset
        if offset >= size:
            out += out[copy_from : copy_from + size]
        else:
            # overlapping copy: the last `offset` bytes repeat
            pattern = bytes(out[copy_from:])
            out += (pattern * (size // offset + 1))[:size]
    if len(out) != expected_end:
        raise SnappyError(f'Snappy block decoded to {len(out) - start} bytes, header announces {length}')


def decompress_raw(data: bytes, max_bytes: int) -> bytes:
    """Decode one raw Snappy block (no framing).

    :raises SnappyError: corrupt or truncated block
    :raises SnappySizeError: the decompressed data would exceed ``max_bytes``
    """
    out = bytearray()
    decode_block(data, out, max_bytes)
    return bytes(out)


# ---------------------------------------------------------------------------
# Framing format
# ---------------------------------------------------------------------------


def _need(data: bytes, pos: int, count: int, what: str) -> None:
    if pos + count > len(data):
        raise SnappyError(f'truncated Snappy stream ({what})')


def decompress_framed(data: bytes, max_bytes: int, stop_at: int | None = None) -> bytes:
    """Decode a Snappy framed stream.

    :param max_bytes: size cap for the decompressed data
    :param stop_at: stop after the chunk that brings the output to this many bytes (to sniff
                    the content); the rest of the stream is then not checked
    :raises SnappyError: not a Snappy stream, corrupt, truncated, bad checksum or a reserved
                         chunk type
    :raises SnappySizeError: the decompressed data would exceed ``max_bytes``
    """
    if not data:
        raise SnappyError('empty Snappy stream')
    if not data.startswith(STREAM_IDENTIFIER):
        raise SnappyError('not a Snappy framed stream (missing stream identifier)')
    out = bytearray()
    pos = 0
    while pos < len(data):
        _need(data, pos, 4, 'chunk header')
        chunk_type = data[pos]
        size = data[pos + 1] | (data[pos + 2] << 8) | (data[pos + 3] << 16)
        chunk_start = pos
        pos += 4
        _need(data, pos, size, 'chunk data')
        body = data[pos : pos + size]
        pos += size
        if chunk_type == _CHUNK_STREAM_IDENTIFIER:
            if body != _STREAM_IDENTIFIER_BODY:
                raise SnappyError(f'corrupt Snappy stream (bad stream identifier at offset {chunk_start})')
        elif chunk_type in (_CHUNK_COMPRESSED, _CHUNK_UNCOMPRESSED):
            if size < 4:
                raise SnappyError(f'corrupt Snappy stream (chunk at offset {chunk_start} too short for its checksum)')
            (stored,) = struct.unpack_from('<I', body, 0)
            chunk_out = len(out)
            if chunk_type == _CHUNK_COMPRESSED:
                decode_block(body[4:], out, max_bytes, max_length=_MAX_CHUNK_UNCOMPRESSED)
            else:
                if size - 4 > _MAX_CHUNK_UNCOMPRESSED:
                    raise SnappyError(
                        f'corrupt Snappy stream (uncompressed chunk of {size - 4} bytes, '
                        f'maximum {_MAX_CHUNK_UNCOMPRESSED})'
                    )
                if len(out) + size - 4 > max_bytes:
                    raise SnappySizeError(f'decompressed Snappy data is larger than the size cap of {max_bytes} bytes')
                out += body[4:]
            if masked_crc32c(memoryview(out)[chunk_out:]) != stored:
                raise SnappyError(f'corrupt Snappy stream (checksum mismatch in chunk at offset {chunk_start})')
        elif chunk_type == _CHUNK_PADDING or 0x80 <= chunk_type <= 0xFD:
            pass  # padding and skippable chunks
        else:
            raise SnappyError(
                f'unsupported Snappy stream (reserved chunk type 0x{chunk_type:02x} at offset {chunk_start})'
            )
        if stop_at is not None and len(out) >= stop_at:
            break
    return bytes(out)
