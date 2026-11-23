"""Seeded mutation fuzzing of the pure-Python parsers that read untrusted guest files.

Each corpus is a few valid inputs built in the test (real encoders where the standard library
has one, fixtures made with the reference tools otherwise) plus a parser and the errors the
parser documents. Every mutation (bit flips, truncation, inserted or deleted bytes,
length fields overwritten with zero / huge / sign-bit values) must either parse or raise one of
those errors; any other exception is a parser bug. Seeds are fixed, so a failure reproduces;
the crashing input is printed (pytest shows it with the failure).

A bug found here gets a named regression test with its minimal input next to the parser's other
tests (test_archive.py, test_binary.py, ...).

Adding a corpus: append a :class:`Corpus` to ``CORPORA`` (see the hook comment there) with
``seeds`` (valid inputs), ``parse`` (bytes -> anything, raising only ``errors``) and, for
formats with checksums, ``fix`` (recompute them after a mutation so the fuzzer gets past the
checksum check).

Runs on the guests' Python 3.10 too (``make test-adarelib-guest``); standard library only.
"""

import bz2
import contextlib
import gzip
import io
import os
import random
import sqlite3
import struct
import tarfile
import tempfile
import zipfile
from collections.abc import Callable
from dataclasses import dataclass

import pytest

from adarelib.testset import archive, binary, lz4, snappy, sqlite_wal

pytestmark = pytest.mark.unit

ROUNDS = int(os.environ.get('ADARE_FUZZ_ROUNDS', '300'))  # mutated inputs per seed (raise it to explore)
SEED = 20261123
CAP = 1 << 20  # decompression size cap while fuzzing

# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------

_INTERESTING_U32 = (0, 1, 0x7F, 0x80, 0xFF, 0x7FFF, 0x8000, 0xFFFF, 0x7FFFFFFF, 0x80000000, 0xFFFFFFFF)


@dataclass(frozen=True)
class Field:
    """A length/size field of a seed input: ``offset``, ``width`` in bytes, byte order."""

    offset: int
    width: int = 4
    byteorder: str = 'little'


def mutate(rng: random.Random, data: bytes, fields: tuple[Field, ...] = ()) -> bytes:
    """One random mutation of ``data``; ``fields`` are length fields worth overwriting."""
    buf = bytearray(data)
    kind = rng.randrange(8)
    if kind == 0 and buf:  # flip 1..4 bits
        for _ in range(rng.randint(1, 4)):
            i = rng.randrange(len(buf))
            buf[i] ^= 1 << rng.randrange(8)
    elif kind == 1:  # truncate
        del buf[rng.randrange(len(buf) + 1) :]
    elif kind == 2:  # insert random bytes
        i = rng.randrange(len(buf) + 1)
        buf[i:i] = bytes(rng.randrange(256) for _ in range(rng.randint(1, 16)))
    elif kind == 3 and buf:  # delete a range
        i = rng.randrange(len(buf))
        del buf[i : i + rng.randint(1, 16)]
    elif kind == 4 and fields:  # overwrite a known length field
        field = rng.choice(fields)
        if field.offset + field.width <= len(buf):
            value = rng.choice(_INTERESTING_U32 + (rng.getrandbits(32),)) & ((1 << (8 * field.width)) - 1)
            buf[field.offset : field.offset + field.width] = value.to_bytes(field.width, field.byteorder)
    elif kind == 5 and len(buf) >= 4:  # an interesting u32 at any position
        i = rng.randrange(len(buf) - 3)
        buf[i : i + 4] = rng.choice(_INTERESTING_U32).to_bytes(4, rng.choice(('little', 'big')))
    elif kind == 6 and buf:  # interesting byte values
        for _ in range(rng.randint(1, 3)):
            buf[rng.randrange(len(buf))] = rng.choice((0x00, 0x01, 0x0F, 0x7F, 0x80, 0xF0, 0xFF))
    elif kind == 7 and buf:  # duplicate a chunk
        i = rng.randrange(len(buf))
        chunk = buf[i : i + rng.randint(1, 64)]
        j = rng.randrange(len(buf) + 1)
        buf[j:j] = chunk
    return bytes(buf)


def mutated(rng: random.Random, data: bytes, fields: tuple[Field, ...] = ()) -> bytes:
    """``data`` after one to three stacked mutations."""
    for _ in range(rng.choice((1, 1, 2, 3))):
        data = mutate(rng, data, fields)
    return data


@dataclass(frozen=True)
class Corpus:
    name: str
    seeds: Callable[[], list[bytes]]
    parse: Callable[[bytes], object]
    errors: tuple[type[BaseException], ...]
    fields: tuple[Field, ...] = ()
    fix: Callable[[bytes], bytes] | None = None  # recompute checksums after a mutation


def check(corpus: Corpus, data: bytes, label: str) -> None:
    """``corpus.parse(data)`` returns or raises one of ``corpus.errors``; anything else fails the test."""
    done = False
    try:
        corpus.parse(data)
        done = True
    except corpus.errors:
        done = True
    finally:
        if not done:
            print(f'{corpus.name} {label}: crashing input {data.hex()}')


# ---------------------------------------------------------------------------
# LZ4 (fixtures made with the lz4 command-line tool, as in test_lz4.py)
# ---------------------------------------------------------------------------

JSON_TEXT = b'{"items": [' + b', '.join(b'{"id": %d, "name": "entry"}' % i for i in range(8)) + b']}'
# lz4 json.txt (independent blocks, content checksum): magic, FLG BD HC, u32 block size, block, end, checksum
LZ4_FRAME = bytes.fromhex(
    '04224d186440a753000000f3187b226974656d73223a205b7b226964223a20302c20226e616d65223a2022656e74'
    '7279227d2c201c001f311c00081f321c00081f331c00081f341c00081f351c00081f361c00081b371c005079227d'
    '5d7d0000000047e18278'
)
# lz4 -BX --content-size json.txt (block checksum, 8-byte content size)
LZ4_FRAME_CHECKED = bytes.fromhex(
    '04224d187c40eb00000000000000bf53000000f3187b226974656d73223a205b7b226964223a20302c20226e616d'
    '65223a2022656e747279227d2c201c001f311c00081f321c00081f331c00081f341c00081f351c00081f361c0008'
    '1b371c005079227d5d7de8f4f57c0000000047e18278'
)
LZ4_BLOCK = LZ4_FRAME[11 : 11 + 0x53]


def _lz4_block_with_header() -> bytes:
    return lz4.BLOCK_HEADER_MAGIC + struct.pack('<I', len(JSON_TEXT)) + LZ4_BLOCK


def _lz4_frame_without_checksum() -> bytes:
    """``LZ4_FRAME`` with the content checksum flag cleared (so mutated blocks get decoded)."""
    return _lz4_fix_header(LZ4_FRAME[:4] + bytes([LZ4_FRAME[4] & ~0x04]) + LZ4_FRAME[5:-4])


def _lz4_fix_header(data: bytes) -> bytes:
    """Recompute the frame header checksum, so a mutated descriptor is parsed further."""
    if len(data) < 7 or data[:4] != lz4.FRAME_MAGIC:
        return data
    end = 6 + (8 if data[4] & 0x08 else 0) + (4 if data[4] & 0x01 else 0)
    if len(data) <= end:
        return data
    return data[:end] + bytes([(lz4.xxh32(data[4:end]) >> 8) & 0xFF]) + data[end + 1 :]


def _lz4_decode_block(data: bytes) -> bytes:
    out = bytearray()
    lz4.decode_block(data, out, CAP)
    return bytes(out)


# ---------------------------------------------------------------------------
# Snappy (fixtures made with python-snappy, as in test_snappy.py)
# ---------------------------------------------------------------------------

SNAPPY_RAW = bytes.fromhex(
    'eb01987b226974656d73223a205b7b226964223a20302c20226e616d65223a2022656e747279227d2c200d1c0031'
    '6a1c0000326a1c0000336a1c0000346a1c0000356a1c0000366a1c000037461c00045d7d'
)
SNAPPY_FRAMED = bytes.fromhex('ff060000734e61507059005600009dc49355') + SNAPPY_RAW


def _snappy_fix_crc(data: bytes) -> bytes:
    """Recompute the checksum of every data chunk whose content still decodes."""
    out = bytearray(data)
    pos = 0
    while pos + 4 <= len(out):
        chunk_type = out[pos]
        size = int.from_bytes(out[pos + 1 : pos + 4], 'little')
        body_start = pos + 4
        if body_start + size > len(out):
            break
        if chunk_type in (0x00, 0x01) and size >= 4:
            payload = bytes(out[body_start + 4 : body_start + size])
            if chunk_type == 0x00:
                try:
                    payload = snappy.decompress_raw(payload, CAP)
                except snappy.SnappyError:
                    payload = None
            if payload is not None:
                out[body_start : body_start + 4] = struct.pack('<I', snappy.masked_crc32c(payload))
        pos = body_start + size
    return bytes(out)


# ---------------------------------------------------------------------------
# SQLite WAL (written by the stdlib sqlite3 module)
# ---------------------------------------------------------------------------


def _wal_seed() -> list[bytes]:
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, 'app.db')
        conn = sqlite3.connect(db)
        try:
            conn.execute('PRAGMA page_size=512')
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('PRAGMA wal_autocheckpoint=0')
            conn.execute('CREATE TABLE items (id INTEGER, name TEXT)')
            conn.commit()
            for i in range(3):
                conn.execute('INSERT INTO items VALUES (?, ?)', (i, 'x' * 40))
                conn.commit()
            with open(f'{db}-wal', 'rb') as f:
                wal = f.read()
        finally:
            conn.close()
    return [wal]


def _wal_fix_header(data: bytes) -> bytes:
    """Recompute the header checksum, so a mutated header (or the frames after it) is parsed."""
    if len(data) < sqlite_wal.WAL_HEADER_SIZE:
        return data
    big_endian = bool(struct.unpack('>I', data[:4])[0] & 1)
    checksum = sqlite_wal.wal_checksum(data[:24], big_endian=big_endian)
    return data[:24] + struct.pack('>2I', *checksum) + data[32:]


@contextlib.contextmanager
def _as_file(data: bytes, suffix: str = ''):
    """``data`` in a temporary file; yields its path."""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, f'input{suffix}')
        with open(path, 'wb') as f:
            f.write(data)
        yield path


def _parse_wal(data: bytes):
    with _as_file(data, '-wal') as path:
        info = sqlite_wal.parse_wal(path)
    assert 0 <= info.commit_frames <= info.valid_frames <= info.total_frames
    return info


# ---------------------------------------------------------------------------
# Archives (tar, zip, gzip, tar.gz, bz2)
# ---------------------------------------------------------------------------

MEMBER = 'etc/app/config.json'
CONFIG = b'{"name": "app", "port": 8080, "items": [1, 2, 3]}\n'


def _tar_bytes(mode: str = 'w') -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode=mode) as tar:
        for name, data in ((MEMBER, CONFIG), ('etc/app/other.txt', b'other\n')):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _zip_bytes(compression: int) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', compression) as zf:
        zf.writestr(MEMBER, CONFIG)
        zf.writestr('etc/app/other.txt', b'other\n')
    return buf.getvalue()


def _resolve(data: bytes, members: list[str]):
    with _as_file(data, '.bin') as path, tempfile.TemporaryDirectory() as work:
        return archive.resolve_archive_path(path, members, work, max_bytes=CAP)


# ---------------------------------------------------------------------------
# The corpora
# ---------------------------------------------------------------------------

_LZ4_ERRORS = (lz4.Lz4Error,)
_SNAPPY_ERRORS = (snappy.SnappyError,)

CORPORA: list[Corpus] = [
    Corpus(
        'lz4-frame',
        lambda: [LZ4_FRAME, LZ4_FRAME_CHECKED],
        lambda d: lz4.decompress(d, CAP),
        _LZ4_ERRORS,
        fields=(Field(7), Field(6, 8), Field(15)),
    ),
    Corpus(
        'lz4-frame-fixed-header',
        lambda: [_lz4_frame_without_checksum(), LZ4_FRAME_CHECKED],
        lambda d: lz4.decompress(d, CAP),
        _LZ4_ERRORS,
        fields=(Field(4, 1), Field(5, 1), Field(7), Field(6, 8)),
        fix=_lz4_fix_header,
    ),
    Corpus('lz4-block', lambda: [LZ4_BLOCK], _lz4_decode_block, _LZ4_ERRORS),
    Corpus(
        'lz4-block-with-header',
        lambda: [_lz4_block_with_header()],
        lambda d: lz4.decompress(d, CAP),
        _LZ4_ERRORS,
        fields=(Field(8),),
    ),
    Corpus('snappy-raw', lambda: [SNAPPY_RAW], lambda d: snappy.decompress_raw(d, CAP), _SNAPPY_ERRORS),
    Corpus(
        'snappy-framed',
        lambda: [SNAPPY_FRAMED],
        lambda d: snappy.decompress_framed(d, CAP),
        _SNAPPY_ERRORS,
        fields=(Field(11, 3),),
        fix=_snappy_fix_crc,
    ),
    Corpus(
        'sqlite-wal',
        _wal_seed,
        _parse_wal,
        (sqlite_wal.WalFormatError,),
        fields=(Field(8, 4, 'big'), Field(32, 4, 'big'), Field(36, 4, 'big')),
    ),
    Corpus(
        'sqlite-wal-fixed-header',
        _wal_seed,
        _parse_wal,
        (sqlite_wal.WalFormatError,),
        fields=(Field(0, 4, 'big'), Field(4, 4, 'big'), Field(8, 4, 'big'), Field(16, 4, 'big')),
        fix=_wal_fix_header,
    ),
    Corpus(
        'archive-member',
        lambda: [_tar_bytes(), _tar_bytes('w:gz'), _zip_bytes(zipfile.ZIP_STORED), _zip_bytes(zipfile.ZIP_DEFLATED)],
        lambda d: _resolve(d, [MEMBER]),
        (archive.ArchiveError,),
        fields=(Field(124, 12), Field(18), Field(22), Field(26, 2)),
    ),
    Corpus(
        'archive-stream',
        lambda: [gzip.compress(CONFIG, mtime=0), bz2.compress(CONFIG), LZ4_FRAME, SNAPPY_FRAMED],
        lambda d: _resolve(d, ['']),
        (archive.ArchiveError,),
    ),
    # Integration hook: the SQLite free-space parser (sqlite_freespace.py) goes here, e.g.
    #   Corpus('sqlite-freespace', _db_with_deleted_rows_seed,
    #          lambda d: <parse the db bytes via a temp file, like _parse_wal>,
    #          (sqlite_freespace.<its documented error>,), fields=(Field(16, 2, 'big'),)),
]


@pytest.mark.parametrize('corpus', CORPORA, ids=[c.name for c in CORPORA])
def test_mutated_inputs_parse_or_raise_documented_errors(corpus):
    seeds = corpus.seeds()
    for seed_index, seed in enumerate(seeds):
        corpus.parse(seed)  # the unmutated seed is valid
        rng = random.Random(f'{SEED}-{corpus.name}-{seed_index}')
        for round_index in range(ROUNDS):
            data = mutated(rng, seed, corpus.fields)
            if corpus.fix is not None and rng.random() < 0.5:
                data = corpus.fix(data)
            check(corpus, data, f'seed {seed_index} round {round_index}')


# ---------------------------------------------------------------------------
# Offset expressions of the binary collection
# ---------------------------------------------------------------------------

_EXPRESSION_TOKENS = (
    'u8', 'i8', 'u16le', 'u16be', 'i32le', 'u32be', 'u64le', 'i64be', '@', '@', '(', ')', '+', '-',
    '0', '4', '8', '255', '0x10', '0xffffffff', '18446744073709551615', '-4', 'find:', 'find:00',
    'find:4d5a', 'find:0', ' ', 'x', 'u32', '9' * 40,
)  # fmt: skip
_VALID_EXPRESSIONS = ('u32be@-4', 'u32be@-4+8', 'u32le@(u32le@0+4)', 'find:4d5a+3', '-8+2', 'u8@u8@u8@u8@0', '0x10')
# a small file with pointers: magic, u32le offset 8, u32be offset at the end
_OFFSET_FILE = b'MZ\x00\x00' + struct.pack('<I', 8) + bytes(range(32)) + struct.pack('>I', 4)


_TYPES = ('u8', 'i8', 'u16le', 'i16be', 'u32le', 'u32be', 'i32le', 'u64le', 'i64be')
_NUMBERS = ('0', '1', '4', '8', '-1', '-4', '-8', '0x7fffffff', '0xffffffffffffffff', '99999999999999999999')


def _grammar_expression(rng: random.Random, depth: int = 0) -> str:
    """A random expression of the offset grammar (it may still exceed the read limits)."""
    roll = rng.random()
    if depth >= 3 or roll < 0.3:
        term = rng.choice(_NUMBERS + ('find:4d5a', 'find:00', 'find:ff'))
    else:
        operand = _grammar_expression(rng, depth + 1)
        if not operand[0].isdigit() and rng.random() < 0.5 or '+' in operand or operand.count('-') > 1:
            operand = f'({operand})'
        term = f'{rng.choice(_TYPES)}@{operand}'
    for _ in range(rng.choice((0, 0, 1, 2))):
        term += rng.choice('+-') + rng.choice(_NUMBERS).lstrip('-')
    return term


def _random_expression(rng: random.Random) -> str:
    roll = rng.random()
    if roll < 0.4:
        return _grammar_expression(rng)
    if roll < 0.7:  # a mutation of a valid one
        text = rng.choice(_VALID_EXPRESSIONS)
        raw = mutate(rng, text.encode())
        return raw.decode('latin-1')
    return ''.join(rng.choice(_EXPRESSION_TOKENS) for _ in range(rng.randint(0, 12)))


def _evaluate_expression(text) -> None:
    node = binary.parse_offset(text)
    binary.describe(node)
    data = binary.BinaryFile(io.BytesIO(_OFFSET_FILE), len(_OFFSET_FILE), max_bytes=CAP)
    binary.resolve_offset(node, data)
    binary.region(data, node, None)


_OFFSET_CORPUS = Corpus(
    'offset-expression', lambda: [], _evaluate_expression, (binary.BinaryParameterError, binary.OffsetError)
)


def test_offset_expressions_parse_or_raise_documented_errors():
    for text in _VALID_EXPRESSIONS:
        binary.parse_offset(text)
    rng = random.Random(f'{SEED}-offset')
    for round_index in range(ROUNDS * 2):
        check(_OFFSET_CORPUS, _random_expression(rng), f'round {round_index}')  # type: ignore[arg-type]


@pytest.mark.parametrize('value', [None, True, 1.5, b'0', [0], -(1 << 70), 1 << 70, '', ' ', '(', '@'])
def test_odd_offset_values_raise_documented_errors(value):
    check(_OFFSET_CORPUS, value, repr(value))  # type: ignore[arg-type]
