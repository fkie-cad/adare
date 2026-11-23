"""Unit tests for the binary collection (struct_value_matches, pattern_count, string_table_*).

The fixtures are hand-built generic shapes: an entry file with a payload, a metadata block and
a trailing big-endian pointer to that block; an index of fixed-size records; nested pointers.
Runs on the guests' Python 3.10 too (``make test-testfunctions-guest``).
"""

import calendar
import io
import struct
import tarfile
import tempfile
from pathlib import Path

import pytest

from adarelib.constants import StatusEnum
from adarelib.helper.module import import_module_from_pyfile

pytestmark = pytest.mark.unit

COLLECTIONS = Path(__file__).resolve().parents[3] / 'appdata' / 'testfunctions'
binary = import_module_from_pyfile(COLLECTIONS / 'binary' / 'binary.py')

FUNCTIONS = {
    'struct': binary.struct_value_matches,
    'count': binary.pattern_count,
    'table': binary.pair_value_matches,
    'table_count': binary.pair_count,
}
StructValue = binary.struct_value_matches._test_class
PatternCount = binary.pattern_count._test_class
StringTable = binary.pair_value_matches._test_class
StringTableCount = binary.pair_count._test_class


def _run(kind, dst, variable_metadata=None, **params):
    testfunction = FUNCTIONS[kind]
    parameter = testfunction._parameter_class(dst=str(dst), **params)
    return testfunction._test_class(name='t', parameter=parameter, variable_metadata=variable_metadata).test()


def _assert(result, status):
    assert result.status == status, f'expected {status.name}, got {result.status.name}: {result.details}'


# --- fixtures --------------------------------------------------------------------------------

MODIFIED = calendar.timegm((2026, 1, 1, 10, 0, 0))  # 2026-01-01T10:00:00Z
FILETIME = (MODIFIED + 11644473600) * 10_000_000  # the same instant, 100 ns since 1601
PAYLOAD = b'\x89DATA' + bytes(range(256)) * 2
TABLE = b'content-type\x00text/plain\x00origin\x00https://example.org/a\x00origin\x00https://example.org/b\x00'
# metadata block: u32be version, u32be hit count, u32be modified (unix s), u32be flags, then the table
META = struct.pack('>IIII', 3, 7, MODIFIED, 0x10) + TABLE
ENTRY = PAYLOAD + META + struct.pack('>I', len(PAYLOAD))

# index: magic, u16le record count, then 32-byte records: u32le id, f64le score, u64le time, 12-byte name
RECORD = struct.Struct('<Idq12s')
RECORDS = [(1, 0.5, FILETIME, b'alpha'), (2, 2.25, FILETIME + 10_000_000, b'beta'), (3, -1.0, 0, b'gamma')]
INDEX = b'IDX1' + struct.pack('<H', len(RECORDS)) + b''.join(RECORD.pack(*r) for r in RECORDS)
HEADER = 6


@pytest.fixture
def entry(tmp_path):
    path = tmp_path / 'entry.bin'
    path.write_bytes(ENTRY)
    return path


@pytest.fixture
def index(tmp_path):
    path = tmp_path / 'index.bin'
    path.write_bytes(INDEX)
    return path


def _record_offset(number: int, field: int = 0) -> int:
    return HEADER + number * RECORD.size + field


# ============================================================================
# struct_value_matches
# ============================================================================


class TestStructValueMatches:
    @pytest.mark.parametrize(
        ('offset', 'value_format', 'expected', 'extra'),
        [
            ('u32be@-4', 'u32be', 3, {}),
            ('u32be@-4+4', 'u32be', 7, {}),
            ('u32be@-4+4', 'u32be', 5, {'comparison_type': 'greater'}),
            ('u32be@-4+12', 'u32be', 16, {}),
            ('u32be@-4+16', 'cstring', 'content-type', {}),
            ('u32be@-4+16', 'string:7', 'content', {}),
            (0, 'bytes:5', '89 44 41 54 41', {}),
            ('find:89444154', 'bytes:2', '8944', {}),
            (-4, 'u32be', len(PAYLOAD), {}),
            (-1, 'u8', len(PAYLOAD) & 0xFF, {}),
            ('u32be@-4+4', 'u32be', '7', {}),  # a numeric string is a number
        ],
    )
    def test_entry_file(self, entry, offset, value_format, expected, extra):
        result = _run('struct', entry, offset=offset, value_format=value_format, expected_value=expected, **extra)
        _assert(result, StatusEnum.SUCCESS)

    @pytest.mark.parametrize(
        ('offset', 'value_format', 'expected'),
        [
            ('u32be@-4', 'u32be', 4),
            ('u32be@-4+16', 'cstring', 'content-length'),
            (0, 'bytes:2', '0000'),
        ],
    )
    def test_mismatch_fails(self, entry, offset, value_format, expected):
        result = _run('struct', entry, offset=offset, value_format=value_format, expected_value=expected)
        _assert(result, StatusEnum.FAILED)
        assert 'offset' in result.details[0]

    def test_little_endian_reading_differs(self, entry):
        result = _run('struct', entry, offset='u32be@-4', value_format='u32le', expected_value=3)
        _assert(result, StatusEnum.FAILED)
        assert str(3 << 24) in result.details[0]

    @pytest.mark.parametrize(
        ('number', 'field', 'value_format', 'expected'),
        [
            (0, 0, 'u32le', 1),
            (1, 0, 'u32le', 2),
            (1, 4, 'f64le', 2.25),
            (2, 4, 'f64le', -1),
            (1, 20, 'string:12', 'beta'),
        ],
    )
    def test_fixed_size_records(self, index, number, field, value_format, expected):
        result = _run(
            'struct', index, offset=_record_offset(number, field), value_format=value_format, expected_value=expected
        )
        _assert(result, StatusEnum.SUCCESS)

    def test_last_record_by_negative_offset(self, index):
        result = _run('struct', index, offset=-RECORD.size + 20, value_format='string:12', expected_value='gamma')
        _assert(result, StatusEnum.SUCCESS)

    def test_header_field(self, index):
        _assert(_run('struct', index, offset=4, value_format='u16le', expected_value=3), StatusEnum.SUCCESS)
        _assert(_run('struct', index, offset=0, value_format='string:4', expected_value='IDX1'), StatusEnum.SUCCESS)

    def test_nested_pointer(self, tmp_path):
        # offset 0: u32le position of a directory slot; the slot holds the u32le position of the value
        data = struct.pack('<I', 12) + b'\xee' * 8 + struct.pack('<I', 20) + b'\x00' * 4 + b'value\x00'
        path = tmp_path / 'nested.bin'
        path.write_bytes(data)
        ok = _run('struct', path, offset='u32le@u32le@0', value_format='cstring', expected_value='value')
        _assert(ok, StatusEnum.SUCCESS)
        shifted = _run('struct', path, offset='u32le@(u32le@0+0)+1', value_format='cstring', expected_value='alue')
        _assert(shifted, StatusEnum.SUCCESS)

    def test_float_tolerance(self, index):
        params = {'offset': _record_offset(0, 4), 'value_format': 'f64le'}
        _assert(_run('struct', index, expected_value=0.6, tolerance=0.2, **params), StatusEnum.SUCCESS)
        _assert(_run('struct', index, expected_value=0.6, tolerance=0.05, **params), StatusEnum.FAILED)

    def test_unix_timestamp(self, entry):
        params = {'offset': 'u32be@-4+8', 'value_format': 'u32be', 'timestamp_epoch': 1970}
        _assert(_run('struct', entry, expected_value='2026-01-01T10:00:00Z', **params), StatusEnum.SUCCESS)
        _assert(_run('struct', entry, expected_value='2026-01-01T12:00:00+02:00', **params), StatusEnum.SUCCESS)
        _assert(
            _run('struct', entry, expected_value='2025-12-31T00:00:00Z', comparison_type='greater', **params),
            StatusEnum.SUCCESS,
        )
        _assert(_run('struct', entry, expected_value='2026-01-01T10:00:05Z', tolerance=2, **params), StatusEnum.FAILED)
        _assert(
            _run('struct', entry, expected_value='2026-01-01T10:00:05Z', tolerance=10, **params), StatusEnum.SUCCESS
        )

    def test_filetime_in_a_record(self, index):
        params = {
            'offset': _record_offset(1, 12),
            'value_format': 'u64le',
            'timestamp_epoch': 1601,
            'timestamp_unit': '100ns',
        }
        _assert(_run('struct', index, expected_value='2026-01-01T10:00:01Z', **params), StatusEnum.SUCCESS)
        _assert(_run('struct', index, expected_value='2026-01-01T10:00:00Z', **params), StatusEnum.FAILED)

    def test_without_epoch_a_number_compares_as_number(self, entry):
        result = _run('struct', entry, offset='u32be@-4+8', value_format='u32be', expected_value=MODIFIED)
        _assert(result, StatusEnum.SUCCESS)
        assert result.details[1].startswith('number')

    def test_string_timestamp_with_time_format(self, tmp_path):
        path = tmp_path / 'stamp.bin'
        path.write_bytes(b'\x00\x0001.01.2026 10:00\x00')
        params = {'offset': 2, 'value_format': 'cstring', 'time_format': '%d.%m.%Y %H:%M'}
        _assert(
            _run('struct', path, expected_value='01.01.2026 09:59', comparison_type='greater', **params),
            StatusEnum.SUCCESS,
        )
        _assert(_run('struct', path, expected_value='01.01.2026 10:00', **params), StatusEnum.SUCCESS)
        _assert(_run('struct', path, expected_value='2026-01-01', **params), StatusEnum.ERROR)  # other format

    def test_text_not_equals(self, entry):
        params = {'offset': 'u32be@-4+16', 'value_format': 'cstring', 'comparison_type': 'not_equals'}
        _assert(_run('struct', entry, expected_value='other', **params), StatusEnum.SUCCESS)
        _assert(_run('struct', entry, expected_value='content-type', **params), StatusEnum.FAILED)

    def test_regex_match(self, entry):
        params = {'offset': 'u32be@-4+16', 'value_format': 'cstring', 'regex_match': True}
        _assert(_run('struct', entry, expected_value='type$', **params), StatusEnum.SUCCESS)
        _assert(_run('struct', entry, expected_value='^type', **params), StatusEnum.FAILED)

    def test_re_tag(self, entry):
        from adarelib.testset.yaml.customtags import YamlRegexString

        params = {'offset': 'u32be@-4+16', 'value_format': 'cstring'}
        _assert(_run('struct', entry, expected_value=YamlRegexString(r'content-\w+'), **params), StatusEnum.SUCCESS)
        _assert(_run('struct', entry, expected_value=YamlRegexString(r'type'), **params), StatusEnum.FAILED)

    @pytest.mark.parametrize(
        ('pattern', 'status'),
        [(r'content-\w+', StatusEnum.SUCCESS), ('other', StatusEnum.FAILED), ('[unclosed', StatusEnum.ERROR)],
    )
    def test_re_placeholder(self, entry, pattern, status):
        metadata = {'P': {'type': 'regex', 'raw_value': pattern, 'resolved_value': pattern}}
        result = _run('struct', entry, metadata, offset='u32be@-4+16', value_format='cstring', expected_value='{{ P }}')
        _assert(result, status)

    def test_timestamp_placeholder_reads_a_numeric_field(self, index):
        unix = MODIFIED + 1
        metadata = {
            'T': {
                'type': 'timestamp',
                'raw_value': str(unix),
                'resolved_value': str(unix),
                'tolerance': [-1, 1],
                'epoch': 1601,
                'unit': '100ns',
            }
        }
        result = _run(
            'struct', index, metadata, offset=_record_offset(1, 12), value_format='u64le', expected_value='{{ T }}'
        )
        _assert(result, StatusEnum.SUCCESS)

    def test_utf16_string(self, tmp_path):
        path = tmp_path / 'wide.bin'
        path.write_bytes(b'\x01\x02' + 'Report.txt'.encode('utf-16-le') + b'\x00\x00')
        params = {'offset': 2, 'value_format': 'cstring', 'encoding': 'utf-16-le'}
        _assert(_run('struct', path, expected_value='Report.txt', **params), StatusEnum.SUCCESS)

    @pytest.mark.parametrize(
        'params',
        [
            {'offset': len(ENTRY), 'value_format': 'u8', 'expected_value': 0},  # past the end
            {'offset': -2, 'value_format': 'u32be', 'expected_value': 0},  # value runs past the end
            {'offset': 'u32be@-4+1000', 'value_format': 'u8', 'expected_value': 0},
            {'offset': 'u32le@-4', 'value_format': 'u8', 'expected_value': 0},  # wrong byte order: far out
            {'offset': 'find:ffffffff', 'value_format': 'u8', 'expected_value': 0},
            {'offset': 'u32be@', 'value_format': 'u8', 'expected_value': 0},
            {'offset': 1.5, 'value_format': 'u8', 'expected_value': 0},
            {'offset': 0, 'value_format': 'u24le', 'expected_value': 0},
            {'offset': 0, 'value_format': 'u8', 'expected_value': 0, 'comparison_type': 'about'},
            {'offset': 0, 'value_format': 'u8', 'expected_value': 'x', 'comparison_type': 'greater'},  # no number
            {'offset': 0, 'value_format': 'u8', 'expected_value': 'abc'},  # no number
            {'offset': 0, 'value_format': 'bytes:2', 'expected_value': 'zz'},
            {'offset': 0, 'value_format': 'bytes:2', 'expected_value': '8944', 'comparison_type': 'greater'},
            {'offset': 'u32be@-4+16', 'value_format': 'cstring', 'expected_value': 'a', 'tolerance': 1},
            {'offset': 'u32be@-4+16', 'value_format': 'cstring', 'expected_value': 'a', 'encoding': 'nope'},
            {'offset': 'u32be@-4+16', 'value_format': 'cstring', 'expected_value': 'a', 'encoding': 'utf-16'},
            {'offset': 'u32be@-4+16', 'value_format': 'cstring', 'expected_value': 1, 'comparison_type': 'greater'},
            {'offset': 'u32be@-4', 'value_format': 'u32be', 'expected_value': 1, 'timestamp_epoch': 1900},
            {'offset': 'u32be@-4', 'value_format': 'u32be', 'expected_value': 1, 'value_type': 'date'},
            {'offset': 0, 'value_format': 'cstring', 'expected_value': 'x'},  # payload bytes are no UTF-8
            {
                'offset': 'u32be@-4',
                'value_format': 'u32be',
                'expected_value': '{{ P }}',
                'regex_match': True,
                'comparison_type': 'less',
            },
        ],
    )
    def test_errors(self, entry, params):
        _assert(_run('struct', entry, **params), StatusEnum.ERROR)

    def test_cstring_without_terminator_is_an_error(self, tmp_path):
        path = tmp_path / 'open.bin'
        path.write_bytes(b'\x00abc')
        _assert(_run('struct', path, offset=1, value_format='cstring', expected_value='abc'), StatusEnum.ERROR)

    def test_error_names_the_offset(self, entry):
        result = _run('struct', entry, offset='u32be@-4+1000', value_format='u8', expected_value=0)
        assert 'outside the file' in ' '.join(result.details)

    def test_member_of_an_archive(self, tmp_path, monkeypatch):
        tmp = tmp_path / 'tmp'
        tmp.mkdir()
        monkeypatch.setattr(tempfile, 'tempdir', str(tmp))
        archive = tmp_path / 'backup.tar'
        with tarfile.open(archive, 'w') as tar:
            info = tarfile.TarInfo('app/cache/entry.bin')
            info.size = len(ENTRY)
            tar.addfile(info, io.BytesIO(ENTRY))
        dst = f'{archive}!/app/cache/entry.bin'
        _assert(_run('struct', dst, offset='u32be@-4+4', value_format='u32be', expected_value=7), StatusEnum.SUCCESS)
        _assert(_run('count', dst, pattern='origin', start='u32be@-4', expected_count=2), StatusEnum.SUCCESS)


# ============================================================================
# pattern_count
# ============================================================================


class TestPatternCount:
    @pytest.mark.parametrize(
        ('params', 'count'),
        [
            ({'pattern': 'origin'}, 2),
            ({'pattern': 'origin', 'start': 'u32be@-4+16', 'end': -4}, 2),
            ({'pattern': 'origin', 'end': 'u32be@-4'}, 0),  # only the payload
            ({'pattern': '\\x00', 'start': 'u32be@-4+16', 'end': -4}, 6),
            ({'pattern': '00 00 00 03', 'pattern_type': 'hex', 'start': 'u32be@-4'}, 1),
            ({'pattern': r'https://example\.org/[a-z]', 'pattern_type': 'regex'}, 2),
            ({'pattern': r'[\x00-\x03]\x00', 'pattern_type': 'regex', 'start': 'u32be@-4', 'end': 'u32be@-4+4'}, 1),
            ({'pattern': 'origin', 'start': 'find:6f726967696e+1'}, 1),
            ({'pattern': 'nowhere'}, 0),
        ],
    )
    def test_counts(self, entry, params, count):
        result = _run('count', entry, expected_count=count, **params)
        _assert(result, StatusEnum.SUCCESS)
        assert f'{count} occurrence(s)' in result.details[0]

    def test_default_is_exactly_once(self, entry):
        _assert(_run('count', entry, pattern='content-type'), StatusEnum.SUCCESS)
        _assert(_run('count', entry, pattern='origin'), StatusEnum.FAILED)
        _assert(_run('count', entry, pattern='origin', comparison_type='greater_equal'), StatusEnum.SUCCESS)

    def test_absence(self, entry):
        _assert(_run('count', entry, pattern='secret', expected_count=0), StatusEnum.SUCCESS)
        _assert(_run('count', entry, pattern='origin', expected_count=0), StatusEnum.FAILED)

    def test_utf16_text(self, tmp_path):
        path = tmp_path / 'wide.bin'
        path.write_bytes(b'\x00' + 'name=Report;name=Draft'.encode('utf-16-le') + 'name'.encode('utf-16-be'))
        _assert(
            _run('count', path, pattern='name=', pattern_type='text', encoding='utf-16-le', expected_count=2),
            StatusEnum.SUCCESS,
        )
        _assert(_run('count', path, pattern='name=', pattern_type='text', expected_count=0), StatusEnum.SUCCESS)

    def test_empty_region(self, entry):
        _assert(_run('count', entry, pattern='a', start=-4, end=-4, expected_count=0), StatusEnum.SUCCESS)

    @pytest.mark.parametrize(
        'params',
        [
            {'pattern': ''},
            {'pattern': 'a', 'pattern_type': 'glob'},
            {'pattern': '\\q'},
            {'pattern': 'xyz', 'pattern_type': 'hex'},
            {'pattern': '[unclosed', 'pattern_type': 'regex'},
            {'pattern': 'a', 'pattern_type': 'text', 'encoding': 'utf-16'},
            {'pattern': 'a', 'pattern_type': 'text', 'encoding': 'nope'},
            {'pattern': 'a', 'expected_count': -1},
            {'pattern': 'a', 'comparison_type': 'not_equals'},
            {'pattern': 'a', 'start': 10, 'end': 5},
            {'pattern': 'a', 'start': len(ENTRY) + 1},
            {'pattern': 'a', 'end': 'u32le@-4'},
            {'pattern': 'a', 'start': 'bogus'},
            {'pattern': '{{ P }}'},
        ],
    )
    def test_errors(self, entry, params):
        _assert(_run('count', entry, **params), StatusEnum.ERROR)

    def test_region_over_the_read_cap_is_an_error(self, entry, monkeypatch):
        from adarelib.testset.archive import MAX_BYTES_ENV

        monkeypatch.setenv(MAX_BYTES_ENV, '16')
        _assert(_run('count', entry, pattern='a', expected_count=0), StatusEnum.ERROR)
        # a small region of a large file stays readable
        _assert(
            _run('count', entry, pattern='origin', start='u32be@-4+16', end='u32be@-4+32', expected_count=0),
            StatusEnum.SUCCESS,
        )


# ============================================================================
# pair_value_matches / pair_count
# ============================================================================

TABLE_REGION = {'start': 'u32be@-4+16', 'end': -4}


class TestStringTable:
    @pytest.mark.parametrize(
        ('key', 'expected', 'extra', 'status'),
        [
            ('content-type', 'text/plain', {}, StatusEnum.SUCCESS),
            ('content-type', 'text/html', {}, StatusEnum.FAILED),
            ('content-type', '^text/', {'regex_match': True}, StatusEnum.SUCCESS),
            ('origin', 'https://example.org/b', {}, StatusEnum.SUCCESS),
            ('origin', 'https://example.org/b', {'wildcard_mode': 'all'}, StatusEnum.FAILED),
            ('origin', 'example.org', {'wildcard_mode': 'all', 'regex_match': True}, StatusEnum.SUCCESS),
            ('missing', 'x', {}, StatusEnum.FAILED),
            ('text/plain', 'origin', {}, StatusEnum.FAILED),  # values are not keys
        ],
    )
    def test_matches(self, entry, key, expected, extra, status):
        result = _run('table', entry, key=key, expected_value=expected, **TABLE_REGION, **extra)
        _assert(result, status)

    def test_absent_key_says_so(self, entry):
        result = _run('table', entry, key='missing', expected_value='x', **TABLE_REGION)
        assert 'does not occur' in result.details[1]
        assert '3 key/value pair(s)' in result.details[0]

    def test_re_tag_and_placeholder(self, entry):
        from adarelib.testset.yaml.customtags import YamlRegexString

        _assert(
            _run('table', entry, key='content-type', expected_value=YamlRegexString('text/'), **TABLE_REGION),
            StatusEnum.SUCCESS,
        )
        metadata = {'P': {'type': 'regex', 'raw_value': 'plain', 'resolved_value': 'plain'}}
        _assert(
            _run('table', entry, metadata, key='content-type', expected_value='{{ P }}', **TABLE_REGION),
            StatusEnum.FAILED,  # !re matches at the start
        )

    def test_numbers_compare_as_text(self, tmp_path):
        path = tmp_path / 'meta.bin'
        path.write_bytes(b'size\x00512\x00')
        _assert(_run('table', path, key='size', expected_value=512), StatusEnum.SUCCESS)

    def test_utf16_table_and_custom_separator(self, tmp_path):
        path = tmp_path / 'wide.bin'
        sep = b'\x00\x00'
        path.write_bytes(b''.join(s.encode('utf-16-le') + sep for s in ('title', 'Draft Ā', 'lang', 'de')))
        params = {'separator': '\\x00\\x00', 'encoding': 'utf-16-le'}
        _assert(_run('table', path, key='title', expected_value='Draft Ā', **params), StatusEnum.SUCCESS)
        lines = tmp_path / 'lines.bin'
        lines.write_bytes(b'a\nb\nc\nd')
        _assert(_run('table', lines, key='c', expected_value='d', separator='\n'), StatusEnum.SUCCESS)

    @pytest.mark.parametrize(
        'params',
        [
            {'key': 'content-type', 'expected_value': 'x', 'start': 'u32be@-4+16', 'end': -3},  # odd strings
            {'key': '', 'expected_value': 'x', **TABLE_REGION},
            {'key': 'a', 'expected_value': 'x', 'separator': '', **TABLE_REGION},
            {'key': 'a', 'expected_value': 'x', 'separator': '\\q', **TABLE_REGION},
            {'key': 'a', 'expected_value': 'x', 'wildcard_mode': 'some', **TABLE_REGION},
            {'key': 'a', 'expected_value': 'x', 'encoding': 'utf-16-le', **TABLE_REGION},  # 1-byte separator
            {'key': 'a', 'expected_value': 'x', **TABLE_REGION, 'start': 'u8@'},
            {'key': 'origin', 'expected_value': '[unclosed', 'regex_match': True, **TABLE_REGION},
        ],
    )
    def test_errors(self, entry, params):
        _assert(_run('table', entry, **params), StatusEnum.ERROR)

    def test_undecodable_value_is_an_error(self, tmp_path):
        path = tmp_path / 'meta.bin'
        path.write_bytes(b'k\x00\xff\xfe\x00')
        _assert(_run('table', path, key='k', expected_value='x'), StatusEnum.ERROR)
        _assert(_run('table_count', path, key='k', expected_count=1), StatusEnum.SUCCESS)  # values not decoded

    @pytest.mark.parametrize(
        ('params', 'status'),
        [
            ({'key': 'origin', 'expected_count': 2}, StatusEnum.SUCCESS),
            ({'key': 'origin', 'expected_count': 1, 'comparison_type': 'greater'}, StatusEnum.SUCCESS),
            ({'key': 'origin', 'expected_count': 1, 'expected_value': 'https://example.org/a'}, StatusEnum.SUCCESS),
            ({'key': 'origin', 'expected_count': 2, 'expected_value': 'org/', 'regex_match': True}, StatusEnum.SUCCESS),
            ({'key': 'alt-source', 'expected_count': 0}, StatusEnum.SUCCESS),
            ({'key': 'origin', 'expected_count': 0}, StatusEnum.FAILED),
            ({'key': 'origin', 'expected_count': -1}, StatusEnum.ERROR),
            ({'key': 'origin', 'expected_count': 1, 'comparison_type': 'about'}, StatusEnum.ERROR),
        ],
    )
    def test_count(self, entry, params, status):
        _assert(_run('table_count', entry, **TABLE_REGION, **params), status)


# ============================================================================
# shared: missing files
# ============================================================================


@pytest.mark.parametrize(
    ('kind', 'params'),
    [
        ('struct', {'offset': 0, 'value_format': 'u8', 'expected_value': 0}),
        ('count', {'pattern': 'a'}),
        ('table', {'key': 'a', 'expected_value': 'b'}),
        ('table_count', {'key': 'a', 'expected_count': 0}),
    ],
)
def test_missing_file_and_directory_are_errors(tmp_path, kind, params):
    missing = _run(kind, tmp_path / 'missing.bin', **params)
    _assert(missing, StatusEnum.ERROR)
    assert 'does not exist' in missing.details[0]
    _assert(_run(kind, tmp_path, **params), StatusEnum.ERROR)


@pytest.mark.parametrize('raw', [struct.pack('>d', float('nan')), struct.pack('>d', float('inf'))], ids=['nan', 'inf'])
def test_non_finite_float_value_is_a_clean_error(tmp_path, raw):
    # found by test_parser_fuzz_functions.py: a NaN crashed into the decorator's catch-all
    path = tmp_path / 'entry.bin'
    path.write_bytes(raw)

    result = _run('struct', path, offset=0, value_format='f64be', expected_value=0)

    _assert(result, StatusEnum.ERROR)
    assert 'not a finite number' in result.details[0]
    assert not any(str(d).startswith('Error in testfunction') for d in result.details), result.details
