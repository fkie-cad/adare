"""Pure-Python Snappy decoder: raw blocks, framing format, CRC-32C, size cap.

Fixtures were made once with the python-snappy package (``snappy.compress`` for raw
blocks, ``snappy.stream_compress`` for the framing format) and are kept as literals, so
the tests need no Snappy package. Blocks with 4-byte copy offsets are built by hand (the
reference compressor never emits them for chunks of at most 64 KiB) and were checked
against ``snappy.uncompress``.
"""

import struct

import pytest

from adarelib.testset import snappy

pytestmark = pytest.mark.unit

JSON_TEXT = b'{"items": [' + b', '.join(b'{"id": %d, "name": "entry"}' % i for i in range(8)) + b']}'
# snappy.compress(JSON_TEXT): literals, 1-byte and 2-byte offset copies
JSON_RAW = bytes.fromhex(
    'eb01987b226974656d73223a205b7b226964223a20302c20226e616d65223a2022656e747279227d2c200d1c0031'
    '6a1c0000326a1c0000336a1c0000346a1c0000356a1c0000366a1c000037461c00045d7d'
)
# snappy.stream_compress(JSON_TEXT): stream identifier + one compressed chunk
JSON_FRAMED = bytes.fromhex('ff060000734e61507059005600009dc49355') + JSON_RAW

REPEATED_TEXT = b''.join(b'record %d of the sample\n' % (i % 7) for i in range(4000))  # 92000 bytes
# snappy.stream_compress(REPEATED_TEXT): two compressed chunks (65536 + 26464 bytes)
_RUN = bytes.fromhex('fea100')  # a 2-byte offset copy (offset 161, 64 bytes), repeated
REPEATED_FRAMED = (
    bytes.fromhex(
        'ff060000734e6150705900390c007cb415ee808004587265636f72642030206f66207468652073616d706c650a0d17'
        '003156170000325617000033561700003456170000355617000036561700'
    )
    + _RUN * 1021
    + bytes.fromhex(
        '5ea10000110500a25feca3e0ce01586f66207468652073616d706c650a7265636f72642031205217000032561700'
        '00335617000034561700003556170000365617000030561700'
    )
    + _RUN * 410
    + bytes.fromhex('a6a100')
)

NOISE = bytes((i * 7919 + 13) * 2654435761 % 256 for i in range(40))
# snappy.stream_compress(NOISE): incompressible, so stored as an uncompressed chunk
NOISE_FRAMED = bytes.fromhex(
    'ff060000734e61507059012c00005ac23208fd3c7bbaf93877b6f53473b2f1306faeed2c6baae92867a6e52463a2e1'
    '205f9edd1c5b9ad9185796'
)

CAP = 1 << 30


def _varint(n: int) -> bytes:
    out = b''
    while n >= 0x80:
        out += bytes([n & 0x7F | 0x80])
        n >>= 7
    return out + bytes([n])


def _literal(data: bytes) -> bytes:
    n = len(data) - 1
    if n < 60:
        return bytes([n << 2]) + data
    extra = (n.bit_length() + 7) // 8
    return bytes([(59 + extra) << 2]) + n.to_bytes(extra, 'little') + data


def _copy4(offset: int, length: int) -> bytes:
    return bytes([(length - 1) << 2 | 3]) + struct.pack('<I', offset)


def _chunk(chunk_type: int, body: bytes) -> bytes:
    return bytes([chunk_type]) + len(body).to_bytes(3, 'little') + body


def _data_chunk(chunk_type: int, payload: bytes, data: bytes) -> bytes:
    """A compressed (0x00) or uncompressed (0x01) chunk with the checksum of ``data``."""
    return _chunk(chunk_type, struct.pack('<I', snappy.masked_crc32c(data)) + payload)


# --- CRC-32C -------------------------------------------------------------------


@pytest.mark.parametrize(
    ('data', 'expected'),
    [
        (b'', 0x00000000),
        (b'123456789', 0xE3069283),
        (bytes(32), 0x8A9136AA),  # RFC 3720 test vectors
        (b'\xff' * 32, 0x62A8AB43),
        (bytes(range(32)), 0x46DD794E),
    ],
)
def test_crc32c_reference_values(data, expected):
    assert snappy.crc32c(data) == expected
    assert snappy.crc32c(memoryview(data)) == expected


def test_crc32c_continues():
    assert snappy.crc32c(b'56789', snappy.crc32c(b'1234')) == 0xE3069283


def test_masked_crc_matches_the_reference_stream():
    (stored,) = struct.unpack_from('<I', JSON_FRAMED, 14)
    assert snappy.masked_crc32c(JSON_TEXT) == stored


# --- raw blocks ----------------------------------------------------------------


def test_raw_block_from_the_reference_tool():
    assert snappy.decompress_raw(JSON_RAW, CAP) == JSON_TEXT


def test_literal_only():
    assert snappy.decompress_raw(_varint(5) + _literal(b'hello'), CAP) == b'hello'


def test_long_literals():
    for size in (60, 61, 300, 70000):
        data = bytes(i % 251 for i in range(size))
        assert snappy.decompress_raw(_varint(size) + _literal(data), CAP) == data


def test_overlapping_one_byte_offset_copy():
    # 'ab', then copy offset 2 length 10 (1-byte offset: length 4 + 6), then '!'
    block = _varint(13) + _literal(b'ab') + bytes([(6 << 2) | 1, 2]) + _literal(b'!')
    assert snappy.decompress_raw(block, CAP) == b'ab' + b'ababababab' + b'!'


def test_two_byte_offset_copy():
    block = _varint(8) + _literal(b'abcd') + bytes([(3 << 2) | 2, 4, 0])
    assert snappy.decompress_raw(block, CAP) == b'abcdabcd'


def test_four_byte_offset_copies():
    block = _varint(14) + _literal(b'abcd') + _copy4(4, 8) + _copy4(2, 2)
    assert snappy.decompress_raw(block, CAP) == b'abcd' + b'abcdabcd' + b'cd'


def test_four_byte_offset_beyond_64k():
    data = bytes((i * 31 + i // 256) % 256 for i in range(65540))
    block = _varint(65540 + 4) + _literal(data) + _copy4(65540, 4)
    assert snappy.decompress_raw(block, CAP) == data + data[:4]


@pytest.mark.parametrize(
    ('block', 'message'),
    [
        (b'', 'length header'),
        (b'\x80\x80', 'length header'),
        (b'\xff\xff\xff\xff\xff\x01', 'longer than 32 bits'),
        (b'\x80\x80\x80\x80\x10', 'longer than 32 bits'),
        (_varint(5) + bytes([1 << 2 | 1, 1]), 'before the start'),  # copy as first element
        (_varint(4) + _literal(b'ab') + bytes([1, 0]), 'offset 0'),
        (_varint(6) + _literal(b'ab') + bytes([1, 3]), 'before the start'),
        (_varint(6) + _literal(b'ab') + _copy4(9, 4), 'before the start'),
        (_varint(5) + b'\x10hel', 'literal past the end'),
        (_varint(70) + b'\xf0', 'literal length past the end'),
        (_varint(6) + _literal(b'ab') + b'\x02\x02', 'copy offset past the end'),
        (_varint(6) + _literal(b'ab') + b'\x03\x02\x00', 'copy offset past the end'),
        (_varint(6) + _literal(b'hello'), 'decoded to 5 bytes, header announces 6'),
        (_varint(4) + _literal(b'hello'), 'more data than'),
        (_varint(4) + _literal(b'ab') + bytes([1 << 2 | 1, 2]), 'more data than'),
    ],
)
def test_corrupt_raw_blocks(block, message):
    with pytest.raises(snappy.SnappyError, match=message):
        snappy.decompress_raw(block, CAP)


def test_raw_size_cap_checked_before_decoding():
    with pytest.raises(snappy.SnappySizeError, match='announces'):
        snappy.decompress_raw(_varint(5000) + _literal(b'x'), 1000)


def test_size_error_is_a_snappy_error():
    assert issubclass(snappy.SnappySizeError, snappy.SnappyError)


# --- framing format ------------------------------------------------------------


def test_framed_stream_from_the_reference_tool():
    assert snappy.decompress_framed(JSON_FRAMED, CAP) == JSON_TEXT


def test_multi_chunk_stream():
    assert snappy.decompress_framed(REPEATED_FRAMED, CAP) == REPEATED_TEXT


def test_uncompressed_chunk():
    assert snappy.decompress_framed(NOISE_FRAMED, CAP) == NOISE


def test_padding_skippable_and_repeated_stream_identifiers():
    stream = (
        JSON_FRAMED
        + _chunk(0xFE, bytes(7))
        + _chunk(0x80, b'skip me')
        + _chunk(0xFD, b'')
        + NOISE_FRAMED  # starts with another stream identifier
    )
    assert snappy.decompress_framed(stream, CAP) == JSON_TEXT + NOISE


def test_concatenated_streams():
    assert snappy.decompress_framed(JSON_FRAMED + JSON_FRAMED, CAP) == JSON_TEXT * 2


@pytest.mark.parametrize('stream', [JSON_FRAMED, NOISE_FRAMED])
def test_checksum_mismatch(stream):
    bad = stream[:14] + bytes([stream[14] ^ 1]) + stream[15:]
    with pytest.raises(snappy.SnappyError, match='checksum mismatch'):
        snappy.decompress_framed(bad, CAP)


def test_corrupt_data_with_a_valid_header_fails_the_checksum():
    # flip a literal byte: the block still decodes, the checksum catches it
    pos = len(JSON_FRAMED) - 1
    bad = JSON_FRAMED[:pos] + b'X' + JSON_FRAMED[pos + 1 :]
    with pytest.raises(snappy.SnappyError, match='checksum mismatch'):
        snappy.decompress_framed(bad, CAP)


def test_missing_stream_identifier():
    with pytest.raises(snappy.SnappyError, match='missing stream identifier'):
        snappy.decompress_framed(JSON_FRAMED[len(snappy.STREAM_IDENTIFIER) :], CAP)


def test_bad_repeated_stream_identifier():
    with pytest.raises(snappy.SnappyError, match='bad stream identifier'):
        snappy.decompress_framed(JSON_FRAMED + _chunk(0xFF, b'sNaPpX'), CAP)


@pytest.mark.parametrize('chunk_type', [0x02, 0x42, 0x7F])
def test_reserved_unskippable_chunk_type(chunk_type):
    with pytest.raises(snappy.SnappyError, match=f'reserved chunk type 0x{chunk_type:02x}'):
        snappy.decompress_framed(JSON_FRAMED + _chunk(chunk_type, b'xx'), CAP)


@pytest.mark.parametrize('cut', [12, 14, 16, 30, len(JSON_FRAMED) - 1])
def test_truncated_stream(cut):
    with pytest.raises(snappy.SnappyError, match='truncated'):
        snappy.decompress_framed(JSON_FRAMED[:cut], CAP)


def test_chunk_too_short_for_its_checksum():
    with pytest.raises(snappy.SnappyError, match='too short'):
        snappy.decompress_framed(snappy.STREAM_IDENTIFIER + _chunk(0x00, b'\x01\x02'), CAP)


def test_compressed_chunk_over_64k_is_corrupt():
    data = b'x' * 65537
    block = _varint(len(data)) + _literal(b'x') + _copy4(1, 64) * 1024
    stream = snappy.STREAM_IDENTIFIER + _data_chunk(0x00, block, data)
    with pytest.raises(snappy.SnappyError, match='maximum 65536'):
        snappy.decompress_framed(stream, CAP)


def test_uncompressed_chunk_over_64k_is_corrupt():
    data = b'x' * 65537
    stream = snappy.STREAM_IDENTIFIER + _data_chunk(0x01, data, data)
    with pytest.raises(snappy.SnappyError, match='maximum 65536'):
        snappy.decompress_framed(stream, CAP)


def test_hand_built_chunks():
    data = b'abcd' * 3
    block = _varint(len(data)) + _literal(b'abcd') + _copy4(4, 8)
    stream = snappy.STREAM_IDENTIFIER + _data_chunk(0x00, block, data) + _data_chunk(0x01, b'!', b'!')
    assert snappy.decompress_framed(stream, CAP) == data + b'!'


@pytest.mark.parametrize('stream', [REPEATED_FRAMED, snappy.STREAM_IDENTIFIER + _data_chunk(0x01, NOISE, NOISE) * 3])
def test_framed_size_cap(stream):
    with pytest.raises(snappy.SnappySizeError, match='size cap'):
        snappy.decompress_framed(stream, 100)


def test_stop_at_returns_the_head():
    head = snappy.decompress_framed(REPEATED_FRAMED, CAP, stop_at=512)
    assert len(head) >= 512
    assert REPEATED_TEXT.startswith(head)
    assert len(head) < len(REPEATED_TEXT)


def test_empty_stream():
    with pytest.raises(snappy.SnappyError, match='empty'):
        snappy.decompress_framed(b'', CAP)


def test_stream_identifier_only_is_empty_content():
    assert snappy.decompress_framed(snappy.STREAM_IDENTIFIER, CAP) == b''
