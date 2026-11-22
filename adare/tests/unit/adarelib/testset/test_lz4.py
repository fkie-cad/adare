"""Pure-Python LZ4 decoder: block format, block with header, frame format, xxh32, size cap.

Frame fixtures were made once with the ``lz4`` command-line tool (v1.10) and are kept as
literals, so the tests need neither the tool nor an ``lz4`` Python package.
"""

import base64
import struct

import pytest

from adarelib.testset import lz4

pytestmark = pytest.mark.unit

JSON_TEXT = b'{"items": [' + b', '.join(b'{"id": %d, "name": "entry"}' % i for i in range(8)) + b']}'
# lz4 json.txt (defaults: independent blocks, content checksum)
JSON_FRAME = bytes.fromhex(
    '04224d186440a753000000f3187b226974656d73223a205b7b226964223a20302c20226e616d65223a2022656e74'
    '7279227d2c201c001f311c00081f321c00081f331c00081f341c00081f351c00081f361c00081b371c005079227d'
    '5d7d0000000047e18278'
)
# lz4 -BX --content-size json.txt (block checksum, content size)
JSON_FRAME_CHECKED = bytes.fromhex(
    '04224d187c40eb00000000000000bf53000000f3187b226974656d73223a205b7b226964223a20302c20226e616d'
    '65223a2022656e747279227d2c201c001f311c00081f321c00081f331c00081f341c00081f351c00081f361c0008'
    '1b371c005079227d5d7de8f4f57c0000000047e18278'
)

REPEATED_TEXT = b''.join(b'record %d of the sample\n' % (i % 7) for i in range(4000))  # 92000 bytes
# lz4 -B4 -BD -BX --content-size: 64 KiB linked blocks; the second block starts with a match
# into the first one
LINKED_FRAME = base64.b64decode(
    'BCJNGFxAYGcBAAAAAAAjQwEAAPMIcmVjb3JkIDAgb2YgdGhlIHNhbXBsZQoXAB8xFwADHzIXAAMfMxcAAx80FwADHzUX'
    'AAMfNhcAAw+hAP' + '/' * 340 + '9AUHJkIDAguhrjlHEAAAAP9' + '/' * 139 + 'r1BtcGxlCu0OnMIAAAAAr/c52Q=='
)
# lz4 -B4 -BI: 64 KiB independent blocks
INDEPENDENT_FRAME = base64.b64decode(
    'BCJNGGRAp0MBAADzCHJlY29yZCAwIG9mIHRoZSBzYW1wbGUKFwAfMRcAAx8yFwADHzMXAAMfNBcAAx81FwADHzYXAAMP'
    'oQD' + '/' * 341 + 'QFByZCAwIKoAAAD/CG9mIHRoZSBzYW1wbGUKcmVjb3JkIDEgFwACHzIXAAMfMxcAAx80FwADHzUXAAMfNhcAAx8w'
    'FwADD6EA' + '/' * 136 + '+FBtcGxlCgAAAACv9znZ'
)

CAP = 1 << 30


def _decode_block(block: bytes, max_bytes: int = CAP) -> bytes:
    out = bytearray()
    lz4.decode_block(block, out, max_bytes)
    return bytes(out)


def _frame(flg: int, bd: int, body: bytes, extra_descriptor: bytes = b'') -> bytes:
    """A frame with a correct header checksum around ``body`` (blocks + end mark)."""
    descriptor = bytes([flg, bd]) + extra_descriptor
    hc = (lz4.xxh32(descriptor) >> 8) & 0xFF
    return lz4.FRAME_MAGIC + descriptor + bytes([hc]) + body


def _with_new_header_checksum(frame: bytes, flg: int) -> bytes:
    """``frame`` (no dict id) with FLG replaced and the header checksum redone."""
    end = 6 + (8 if frame[4] & 0x08 else 0)
    descriptor = bytes([flg]) + frame[5:end]
    return frame[:4] + descriptor + bytes([(lz4.xxh32(descriptor) >> 8) & 0xFF]) + frame[end + 1 :]


# --- xxh32 -------------------------------------------------------------------


@pytest.mark.parametrize(
    ('data', 'expected'),
    [
        (b'', 0x02CC5D05),
        (b'a', 0x550D7456),
        (b'abc', 0x32D153FF),
        (b'Nobody inspects the spammish repetition', 0xE2293B2F),
    ],
)
def test_xxh32_reference_values(data, expected):
    assert lz4.xxh32(data) == expected


# --- block format --------------------------------------------------------------


def test_literals_only():
    assert _decode_block(b'\x50hello') == b'hello'


def test_overlapping_match_repeats_the_window():
    # literals 'ab', match offset 2 length 10, last literals '!'
    block = b'\x26ab\x02\x00' + b'\x10!'
    assert _decode_block(block) == b'ab' + b'ababababab' + b'!'


def test_long_literal_length():
    data = bytes(range(256)) + bytes(44)  # 300 bytes
    block = b'\xf0' + bytes([255, 30]) + data
    assert _decode_block(block) == data


def test_long_match_length():
    # 'x', then match offset 1 length 1000 (15 + 4 + 255*3 + 216), then 'y'
    block = b'\x1fx\x01\x00' + bytes([255, 255, 255, 216]) + b'\x10y'
    assert _decode_block(block) == b'x' * 1001 + b'y'


def test_non_overlapping_match():
    block = b'\x40abcd\x04\x00' + b'\x10!'
    assert _decode_block(block) == b'abcdabcd!'


@pytest.mark.parametrize(
    ('block', 'message'),
    [
        (b'', 'empty'),
        (b'\x50hel', 'literals past the end'),
        (b'\x26ab\x00\x00\x10!', 'offset 0'),
        (b'\x26ab\x09\x00\x10!', 'before the start'),
        (b'\x26ab\x02', 'missing match offset'),
        (b'\xf0', 'length extension'),
        (b'\x26ab\x02\x00', 'missing token'),
    ],
)
def test_corrupt_blocks(block, message):
    with pytest.raises(lz4.Lz4Error, match=message):
        _decode_block(block)


def test_block_size_cap():
    block = b'\x1fx\x01\x00' + bytes([255, 255, 255, 216]) + b'\x10y'
    with pytest.raises(lz4.Lz4SizeError):
        _decode_block(block, max_bytes=100)


# --- block with header ---------------------------------------------------------


def _with_header(block: bytes, size: int) -> bytes:
    return lz4.BLOCK_HEADER_MAGIC + struct.pack('<I', size) + block


def test_block_with_header():
    data = lz4.decompress(_with_header(b'\x26ab\x02\x00\x10!', 13), CAP)
    assert data == b'abababababab!'


def test_block_with_header_from_a_real_block():
    block = JSON_FRAME[11:-8]  # the frame's only block (between size and end mark)
    assert lz4.decompress(_with_header(block, len(JSON_TEXT)), CAP) == JSON_TEXT


def test_block_with_header_size_mismatch():
    with pytest.raises(lz4.Lz4Error, match='header announces'):
        lz4.decompress(_with_header(b'\x50hello', 6), CAP)


def test_block_with_header_size_checked_before_decoding():
    with pytest.raises(lz4.Lz4SizeError, match='announces'):
        lz4.decompress(_with_header(b'\x50hello', 5000), 1000)


def test_block_with_header_truncated():
    with pytest.raises(lz4.Lz4Error, match='truncated'):
        lz4.decompress(lz4.BLOCK_HEADER_MAGIC + b'\x05\x00', CAP)


# --- frame format --------------------------------------------------------------


@pytest.mark.parametrize('frame', [JSON_FRAME, JSON_FRAME_CHECKED])
def test_frames_from_the_reference_tool(frame):
    assert lz4.decompress(frame, CAP) == JSON_TEXT


@pytest.mark.parametrize('frame', [LINKED_FRAME, INDEPENDENT_FRAME])
def test_multi_block_frames(frame):
    assert lz4.decompress(frame, CAP) == REPEATED_TEXT


def test_linked_blocks_need_the_previous_block():
    # declared independent, the second block's match into the first block is out of range
    with pytest.raises(lz4.Lz4Error, match='before the start'):
        lz4.decompress(_with_new_header_checksum(LINKED_FRAME, LINKED_FRAME[4] | 0x20), CAP)


def test_uncompressed_block():
    body = struct.pack('<I', 0x80000005) + b'hello' + b'\x00\x00\x00\x00'
    assert lz4.decompress(_frame(0x60, 0x40, body), CAP) == b'hello'


def test_concatenated_and_skippable_frames():
    skippable = lz4.SKIPPABLE_MAGICS[3] + struct.pack('<I', 3) + b'xyz'
    assert lz4.decompress(skippable + JSON_FRAME + JSON_FRAME, CAP) == JSON_TEXT * 2


def test_content_checksum_mismatch():
    bad = JSON_FRAME[:-1] + bytes([JSON_FRAME[-1] ^ 1])
    with pytest.raises(lz4.Lz4Error, match='content checksum'):
        lz4.decompress(bad, CAP)


def test_block_checksum_mismatch():
    # the stored block checksum sits right before the end mark and content checksum
    pos = len(JSON_FRAME_CHECKED) - 12
    bad = JSON_FRAME_CHECKED[:pos] + bytes([JSON_FRAME_CHECKED[pos] ^ 1]) + JSON_FRAME_CHECKED[pos + 1 :]
    with pytest.raises(lz4.Lz4Error, match='block checksum'):
        lz4.decompress(bad, CAP)


def test_header_checksum_mismatch():
    bad = JSON_FRAME[:6] + bytes([JSON_FRAME[6] ^ 1]) + JSON_FRAME[7:]
    with pytest.raises(lz4.Lz4Error, match='header checksum'):
        lz4.decompress(bad, CAP)


@pytest.mark.parametrize('cut', [5, 11, 40, len(JSON_FRAME) - 6, len(JSON_FRAME) - 2])
def test_truncated_frame(cut):
    with pytest.raises(lz4.Lz4Error):
        lz4.decompress(JSON_FRAME[:cut], CAP)


def test_dictionary_frames_are_unsupported():
    frame = _frame(0x61, 0x40, b'\x00\x00\x00\x00', extra_descriptor=b'\x01\x02\x03\x04')
    with pytest.raises(lz4.Lz4Error, match='dictionary'):
        lz4.decompress(frame, CAP)


def test_legacy_frame_is_unsupported():
    with pytest.raises(lz4.Lz4Error, match='legacy'):
        lz4.decompress(lz4.LEGACY_FRAME_MAGIC + b'\x00' * 8, CAP)


def test_trailing_garbage_is_an_error():
    with pytest.raises(lz4.Lz4Error, match='unexpected data'):
        lz4.decompress(JSON_FRAME + b'junk', CAP)


def test_frame_size_cap():
    with pytest.raises(lz4.Lz4SizeError):
        lz4.decompress(INDEPENDENT_FRAME, 50_000)


def test_announced_content_size_over_the_cap():
    with pytest.raises(lz4.Lz4SizeError, match='announces'):
        lz4.decompress(JSON_FRAME_CHECKED, 100)


def test_stop_at_returns_the_head():
    head = lz4.decompress(INDEPENDENT_FRAME, CAP, stop_at=512)
    assert len(head) >= 512
    assert REPEATED_TEXT.startswith(head)


def test_unknown_magic():
    with pytest.raises(lz4.Lz4Error, match='not LZ4'):
        lz4.decompress(b'plain text', CAP)


def test_xxh32_across_unpack_chunks():
    # longer than one unpack chunk (256 KiB), with a tail that is not a whole stripe
    data = bytes(range(256)) * 1100 + b'tail!'
    assert lz4.xxh32(data) == 0xE9891945  # reference value from the xxhash package
    assert lz4.xxh32(memoryview(data)) == 0xE9891945
    body = struct.pack('<I', 0x80000000 | 60000) + data[:60000] + b'\x00\x00\x00\x00'
    frame = _frame(0x64, 0x40, body + struct.pack('<I', lz4.xxh32(data[:60000])))
    assert lz4.decompress(frame, CAP) == data[:60000]


# --- size caps -----------------------------------------------------------------


def test_literals_over_the_cap():
    with pytest.raises(lz4.Lz4SizeError, match='size cap of 3 bytes'):
        _decode_block(b'\x50hello', max_bytes=3)


def test_overlapping_match_over_the_cap():
    # 'ab' + match offset 2 length 10 = 12 bytes before the last literal
    with pytest.raises(lz4.Lz4SizeError):
        _decode_block(b'\x26ab\x02\x00\x10!', max_bytes=11)


def test_output_exactly_at_the_cap_is_fine():
    assert _decode_block(b'\x26ab\x02\x00\x10!', max_bytes=13) == b'abababababab!'
    assert lz4.decompress(JSON_FRAME_CHECKED, len(JSON_TEXT)) == JSON_TEXT


def test_uncompressed_block_over_the_cap():
    body = struct.pack('<I', 0x80000005) + b'hello' + b'\x00\x00\x00\x00'
    with pytest.raises(lz4.Lz4SizeError):
        lz4.decompress(_frame(0x60, 0x40, body), 4)


def test_block_with_header_announcing_the_cap_exactly():
    assert lz4.decompress(_with_header(b'\x50hello', 5), 5) == b'hello'


def test_cap_counts_all_concatenated_frames():
    # the second frame announces its size, which together with the first is over the cap
    with pytest.raises(lz4.Lz4SizeError, match='announces'):
        lz4.decompress(JSON_FRAME + JSON_FRAME_CHECKED, 2 * len(JSON_TEXT) - 1)
    assert lz4.decompress(JSON_FRAME + JSON_FRAME_CHECKED, 2 * len(JSON_TEXT)) == JSON_TEXT * 2


def test_cap_counts_frames_without_a_content_size():
    with pytest.raises(lz4.Lz4SizeError, match='size cap'):
        lz4.decompress(JSON_FRAME + JSON_FRAME, 2 * len(JSON_TEXT) - 1)


def test_block_larger_than_the_frame_block_maximum():
    # block size code 4 = 64 KiB; a stored block that claims more is corrupt
    body = struct.pack('<I', 0x80000000 | (64 << 10) + 1) + bytes((64 << 10) + 1) + b'\x00\x00\x00\x00'
    with pytest.raises(lz4.Lz4Error, match='maximum'):
        lz4.decompress(_frame(0x60, 0x40, body), CAP)


# --- announced content size vs decoded size ------------------------------------


def _sized_frame(content_size: int, payload: bytes = b'hello') -> bytes:
    """An independent-block frame with a content size field and one stored block."""
    body = struct.pack('<I', 0x80000000 | len(payload)) + payload + b'\x00\x00\x00\x00'
    return _frame(0x68, 0x40, body, extra_descriptor=struct.pack('<Q', content_size))


def test_frame_with_a_correct_content_size():
    assert lz4.decompress(_sized_frame(5), CAP) == b'hello'


@pytest.mark.parametrize('announced', [0, 4, 6, 1000])
def test_frame_content_size_mismatch(announced):
    with pytest.raises(lz4.Lz4Error, match=f'decoded to 5 bytes, header announces {announced}') as info:
        lz4.decompress(_sized_frame(announced), CAP)
    assert not isinstance(info.value, lz4.Lz4SizeError)


def test_frame_content_size_is_not_checked_when_stopping_early():
    # sniffing (stop_at) returns the head without reading the rest of the frame
    assert lz4.decompress(_sized_frame(1000), CAP, stop_at=2) == b'hello'


def test_block_with_header_announcing_more_bytes_than_it_holds():
    with pytest.raises(lz4.Lz4Error, match='decoded to 5 bytes, header announces 9') as info:
        lz4.decompress(_with_header(b'\x50hello', 9), CAP)
    assert not isinstance(info.value, lz4.Lz4SizeError)


def test_block_with_header_announcing_fewer_bytes_than_it_holds():
    with pytest.raises(lz4.Lz4Error, match='header announces 4') as info:
        lz4.decompress(_with_header(b'\x50hello', 4), CAP)
    assert not isinstance(info.value, lz4.Lz4SizeError)


def test_block_with_header_announcing_zero_bytes():
    assert lz4.decompress(_with_header(b'', 0), CAP) == b''
