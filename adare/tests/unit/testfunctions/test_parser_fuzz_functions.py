"""Testfunctions that parse binary formats, fed mutated files: SUCCESS, FAILED or ERROR, never a crash.

The second layer of ``tests/unit/adarelib/testset/test_parser_fuzz.py``: the same kind of seeded
mutations, run through the ``@testfunction`` wrapper. The wrapper turns any exception into an
ERROR, so a crash shows up as an ERROR whose first detail is the wrapper's
``Error in testfunction '...'``; that is what these tests reject. Kept small (tens of cases per
function) so the guest run stays fast.

Runs on the guests' Python 3.10 too (``make test-testfunctions-guest``).
"""

import gzip
import io
import os
import random
import sqlite3
import struct
import tarfile
from pathlib import Path

import pytest

from adarelib.constants import StatusEnum
from adarelib.helper.module import import_module_from_pyfile

pytestmark = pytest.mark.unit

COLLECTIONS = Path(__file__).resolve().parents[3] / 'appdata' / 'testfunctions'
binary = import_module_from_pyfile(COLLECTIONS / 'binary' / 'binary.py')
sqlite = import_module_from_pyfile(COLLECTIONS / 'sqlite' / 'sqlite.py')
json_tf = import_module_from_pyfile(COLLECTIONS / 'json' / 'json.py')

CASES = int(os.environ.get('ADARE_FUZZ_CASES', '40'))  # mutated inputs per function
SEED = 20261123
CRASH_MARKER = 'Error in testfunction'


def _mutate(rng: random.Random, data: bytes) -> bytes:
    buf = bytearray(data)
    for _ in range(rng.choice((1, 1, 2, 3))):
        kind = rng.randrange(5)
        if kind == 0 and buf:
            i = rng.randrange(len(buf))
            buf[i] ^= 1 << rng.randrange(8)
        elif kind == 1:
            del buf[rng.randrange(len(buf) + 1) :]
        elif kind == 2:
            i = rng.randrange(len(buf) + 1)
            buf[i:i] = bytes(rng.randrange(256) for _ in range(rng.randint(1, 8)))
        elif kind == 3 and len(buf) >= 4:
            i = rng.randrange(len(buf) - 3)
            value = rng.choice((0, 0x7FFFFFFF, 0x80000000, 0xFFFFFFFF, rng.getrandbits(32)))
            buf[i : i + 4] = value.to_bytes(4, rng.choice(('little', 'big')))
        elif kind == 4 and buf:
            i = rng.randrange(len(buf))
            del buf[i : i + rng.randint(1, 8)]
    return bytes(buf)


def _run(testfunction, **params):
    parameter = testfunction._parameter_class(**params)
    return testfunction._test_class(name='t', parameter=parameter).test()


def _assert_no_crash(result, data: bytes, params: dict):
    assert result.status in (StatusEnum.SUCCESS, StatusEnum.FAILED, StatusEnum.ERROR), result.status
    crashed = result.status == StatusEnum.ERROR and any(
        isinstance(d, str) and d.startswith(CRASH_MARKER) for d in result.details
    )
    assert not crashed, f'{params} on input {data.hex()}:\n' + '\n'.join(map(str, result.details))


# --- binary.* ------------------------------------------------------------------------------

TABLE = b'content-type\x00text/plain\x00origin\x00https://example.org/a\x00'
META = struct.pack('>IIII', 3, 7, 1767261600, 0x10) + TABLE
PAYLOAD = b'\x89DATA' + bytes(range(64))
ENTRY = PAYLOAD + META + struct.pack('>I', len(PAYLOAD))

OFFSETS = (0, -4, 4, 'u32be@-4', 'u32be@-4+8', 'u32be@-4+16', 'find:6f726967696e', 'u8@(u32be@-4+3)', -1)
FORMATS = ('u8', 'i16le', 'u32be', 'i64be', 'f32le', 'f64be', 'bytes:4', 'string:6', 'cstring')


def _binary_cases(rng: random.Random):
    for _ in range(CASES):
        yield _mutate(rng, ENTRY), rng.choice(OFFSETS), rng.choice(FORMATS)


def test_struct_value_matches_on_mutated_files(tmp_path):
    rng = random.Random(f'{SEED}-struct')
    path = tmp_path / 'entry.bin'
    for data, offset, value_format in _binary_cases(rng):
        path.write_bytes(data)
        expected = 'text' if value_format.startswith(('string', 'cstring')) else 0
        if value_format.startswith('bytes'):
            expected = '00000000'
        params = {'dst': str(path), 'offset': offset, 'value_format': value_format, 'expected_value': expected}
        if value_format in ('u32be', 'i64be') and rng.random() < 0.5:
            params.update(timestamp_epoch=1970, expected_value='2026-01-01T10:00:00Z', comparison_type='greater')
        _assert_no_crash(_run(binary.struct_value_matches, **params), data, params)


def test_pattern_count_on_mutated_files(tmp_path):
    rng = random.Random(f'{SEED}-pattern')
    path = tmp_path / 'entry.bin'
    for data, start, _ in _binary_cases(rng):
        path.write_bytes(data)
        params = {
            'dst': str(path),
            'pattern': rng.choice(('origin', r'\x00', 'o.i', '00 01')),
            'pattern_type': rng.choice(('bytes', 'regex', 'hex', 'text')),
            'start': start,
            'end': rng.choice((None, -4, 'u32be@-4+16')),
            'expected_count': 1,
        }
        _assert_no_crash(_run(binary.pattern_count, **params), data, params)


@pytest.mark.parametrize('function', ['pair_value_matches', 'pair_count'])
def test_string_table_functions_on_mutated_files(tmp_path, function):
    rng = random.Random(f'{SEED}-{function}')
    path = tmp_path / 'entry.bin'
    for data, _, _ in _binary_cases(rng):
        path.write_bytes(data)
        params = {
            'dst': str(path),
            'key': 'origin',
            'start': rng.choice(('u32be@-4+16', 'find:636f6e74656e74', 0)),
            'end': rng.choice((-4, None, 'find:00+1')),
            'encoding': rng.choice(('utf-8', 'utf-16-le', 'latin-1')),
        }
        if function == 'pair_count':
            params['expected_count'] = 1
            testfunction = binary.pair_count
        else:
            params['expected_value'] = 'https://example.org/a'
            testfunction = binary.pair_value_matches
        _assert_no_crash(_run(testfunction, **params), data, params)


# --- sqlite.wal_frame_count ----------------------------------------------------------------


@pytest.fixture(scope='module')
def wal_seed(tmp_path_factory):
    db = tmp_path_factory.mktemp('wal') / 'app.db'
    conn = sqlite3.connect(str(db))
    try:
        conn.execute('PRAGMA page_size=512')
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA wal_autocheckpoint=0')
        conn.execute('CREATE TABLE items (id INTEGER, name TEXT)')
        conn.commit()
        for i in range(3):
            conn.execute('INSERT INTO items VALUES (?, ?)', (i, 'x' * 40))
            conn.commit()
        wal = Path(f'{db}-wal').read_bytes()
        main = db.read_bytes()
    finally:
        conn.close()
    return main, wal


@pytest.mark.parametrize('frames', ['valid', 'commits', 'all', 'stale'])
def test_wal_frame_count_on_mutated_wals(tmp_path, wal_seed, frames):
    main, wal = wal_seed
    db = tmp_path / 'app.db'
    db.write_bytes(main)
    rng = random.Random(f'{SEED}-wal-{frames}')
    for _ in range(CASES // 2):
        data = _mutate(rng, wal)
        Path(f'{db}-wal').write_bytes(data)
        params = {'dst': str(db), 'expected_count': 3, 'frames': frames}
        _assert_no_crash(_run(sqlite.wal_frame_count, **params), data, params)


# --- json through an archive member --------------------------------------------------------

CONFIG = b'{"name": "app", "port": 8080, "items": [1, 2, 3]}\n'


def _tar_gz() -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w:gz') as tar:
        info = tarfile.TarInfo('etc/app/config.json')
        info.size = len(CONFIG)
        tar.addfile(info, io.BytesIO(CONFIG))
    return buf.getvalue()


@pytest.mark.parametrize(
    ('seed', 'member'),
    [(_tar_gz(), '!/etc/app/config.json'), (gzip.compress(CONFIG, mtime=0), '!')],
    ids=['tar.gz-member', 'gz-content'],
)
def test_json_through_mutated_archives(tmp_path, seed, member):
    rng = random.Random(f'{SEED}-json-{member}')
    path = tmp_path / 'backup.bin'
    for _ in range(CASES):
        data = _mutate(rng, seed)
        path.write_bytes(data)
        params = {'dst': f'{path}{member}', 'key_path': 'port', 'expected_value': 8080}
        _assert_no_crash(_run(json_tf.value_matches, **params), data, params)
