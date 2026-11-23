"""Offset expressions, value formats and string tables (adarelib.testset.binary)."""

import io
import re
import struct

import pytest

from adarelib.testset.binary import (
    MAX_DEREFERENCES,
    Add,
    BinaryFile,
    BinaryParameterError,
    Deref,
    Find,
    Literal,
    NonFiniteValueError,
    OffsetError,
    compile_pattern,
    count_pattern,
    describe,
    parse_offset,
    parse_value_format,
    read_value,
    region,
    resolve_offset,
    split_strings,
    string_table,
)
from adarelib.testset.content import FileTooLargeError

pytestmark = pytest.mark.unit


def _file(data: bytes, max_bytes: int | None = None) -> BinaryFile:
    return BinaryFile(io.BytesIO(data), len(data), max_bytes=max_bytes)


# --- parsing ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ('expression', 'tree'),
    [
        (12, Literal(12)),
        (-4, Literal(-4)),
        ('12', Literal(12)),
        ('0x1f', Literal(31)),
        ('-4', Literal(-4)),
        ('-8+2', Add(Literal(-8), 2)),
        ('u32be@-4', Deref('u32be', Literal(-4))),
        ('u32be@-4+8', Add(Deref('u32be', Literal(-4)), 8)),
        (' u32be @ -4 + 8 ', Add(Deref('u32be', Literal(-4)), 8)),
        ('u16le@(u32le@0+4)-2', Add(Deref('u16le', Add(Deref('u32le', Literal(0)), 4)), -2)),
        ('i64be@u8@0', Deref('i64be', Deref('u8', Literal(0)))),
        ('find:6B6579', Find(b'key')),
        ('find:6b6579+3', Add(Find(b'key'), 3)),
    ],
)
def test_parse(expression, tree):
    assert parse_offset(expression) == tree


@pytest.mark.parametrize(
    'expression',
    [
        '',
        '   ',
        'u32be@',
        'u32@0',  # no byte order
        'u8le@0',
        'x',
        '1 2',
        '1+',
        '1+u8@0',  # addends are numbers
        '(4)',  # parentheses only after @
        'u8@(1',
        'find:abc',
        'find:',
        'find:zz',
        'u32be@-4*2',
        '@4',
        'u8@' * (MAX_DEREFERENCES + 1) + '0',
        '1' * 300,
        True,
        1.5,
        None,
        ['u8@0'],
    ],
)
def test_invalid_expressions(expression):
    with pytest.raises(BinaryParameterError):
        parse_offset(expression)


def test_dereference_limit_is_inclusive():
    parse_offset('u8@' * MAX_DEREFERENCES + '0')


@pytest.mark.parametrize('expression', ['u32be@-4+8', 'u16le@(u32le@0+4)', 'find:00ff-1', '-8'])
def test_describe_round_trips(expression):
    assert parse_offset(describe(parse_offset(expression))) == parse_offset(expression)


# --- resolving -------------------------------------------------------------------------------

PAYLOAD = b'P' * 20
META = b'key\x00value\x00'
TRAILER_FILE = PAYLOAD + META + struct.pack('>I', len(PAYLOAD))  # pointer to META in the last 4 bytes


@pytest.mark.parametrize(
    ('expression', 'offset'),
    [
        (0, 0),
        (-4, len(TRAILER_FILE) - 4),
        ('-4', len(TRAILER_FILE) - 4),
        ('-8+2', len(TRAILER_FILE) - 6),
        ('u32be@-4', 20),
        ('u32be@-4+4', 24),
        ('find:6b6579', 20),
        ('find:00+1', 24),
    ],
)
def test_resolve(expression, offset):
    assert resolve_offset(parse_offset(expression), _file(TRAILER_FILE)) == offset


def test_nested_pointer():
    # offset 0 holds the position of a little-endian pointer, which points at the value
    data = struct.pack('<I', 8) + b'\xff' * 4 + struct.pack('<I', 16) + b'\x00' * 4 + b'DATA'
    assert resolve_offset(parse_offset('u32le@u32le@0'), _file(data)) == 16
    assert resolve_offset(parse_offset('u32le@(u32le@0+0)+2'), _file(data)) == 18


@pytest.mark.parametrize(
    'expression',
    [
        len(TRAILER_FILE),  # one past the last byte
        -len(TRAILER_FILE) - 1,
        'u32be@-4+1000',
        'u32le@-4',  # the little-endian reading is far outside
        'u32be@-2',  # the pointer itself would run past the end
        'find:ffff',
        '-4-1000',
    ],
)
def test_unresolvable_offsets(expression):
    with pytest.raises(OffsetError):
        resolve_offset(parse_offset(expression), _file(TRAILER_FILE))


def test_end_of_file_is_a_valid_region_end():
    data = _file(TRAILER_FILE)
    assert resolve_offset(parse_offset(len(TRAILER_FILE)), data, allow_end=True) == len(TRAILER_FILE)
    assert region(data, parse_offset('u32be@-4'), parse_offset(-4))[2] == META


def test_region_end_before_start():
    with pytest.raises(OffsetError, match='before its start'):
        region(_file(TRAILER_FILE), parse_offset(10), parse_offset(5))


def test_find_and_regions_respect_the_read_cap():
    data = _file(TRAILER_FILE, max_bytes=8)
    with pytest.raises(FileTooLargeError):
        resolve_offset(parse_offset('find:00'), data)
    with pytest.raises(FileTooLargeError):
        region(data, parse_offset(0), None)
    assert resolve_offset(parse_offset('u32be@-4'), data) == 20  # small reads stay possible


# --- value formats ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ('value_format', 'raw', 'value'),
    [
        ('u8', b'\xff', 255),
        ('i8', b'\xff', -1),
        ('u16le', b'\x01\x02', 0x0201),
        ('u16be', b'\x01\x02', 0x0102),
        ('i32be', struct.pack('>i', -5), -5),
        ('u64le', struct.pack('<Q', 2**40), 2**40),
        ('I64BE', struct.pack('>q', -(2**40)), -(2**40)),
        ('f32le', struct.pack('<f', 1.5), 1.5),
        ('f64be', struct.pack('>d', -0.25), -0.25),
        ('bytes:3', b'\xde\xad\x01', 'dead01'),
        ('string:6', b'abc\x00\x00\x00', 'abc'),
        ('cstring', b'abc\x00def', 'abc'),
    ],
)
def test_read_value(value_format, raw, value):
    assert read_value(_file(raw + b'\x00'), 0, parse_value_format(value_format)) == value


def test_utf16_cstring_ends_at_an_aligned_nul():
    raw = 'aĀb'.encode('utf-16-le') + b'\x00\x00' + b'zz'
    assert read_value(_file(raw), 0, parse_value_format('cstring'), 'utf-16-le') == 'aĀb'


@pytest.mark.parametrize(
    ('raw', 'value_format', 'error'),
    [
        (b'abc', 'cstring', OffsetError),  # no terminator
        (b'\x01', 'u16le', OffsetError),
        (b'\xff\xfe\x00', 'cstring', UnicodeDecodeError),
        (struct.pack('<f', float('nan')), 'f32le', ValueError),
    ],
)
def test_unreadable_values(raw, value_format, error):
    with pytest.raises(error):
        read_value(_file(raw), 0, parse_value_format(value_format))


@pytest.mark.parametrize('value_format', ['u32', 'bytes:0', 'bytes:x', 'string:', 'float', 7, None])
def test_invalid_value_formats(value_format):
    with pytest.raises(BinaryParameterError):
        parse_value_format(value_format)


# --- patterns and string tables --------------------------------------------------------------


@pytest.mark.parametrize(
    ('pattern', 'pattern_type', 'data', 'count'),
    [
        ('\\x00\\x01', 'bytes', b'\x00\x01\x00\x01\x00', 2),
        ('aa', 'bytes', b'aaaa', 2),  # non-overlapping
        ('00 01', 'hex', b'\x00\x01\x00\x01', 2),
        (r'id-\d+', 'regex', b'id-1\x00id-22\x00id-', 2),
        (r'\x00*', 'regex', b'ab', 0),  # empty matches do not count
        ('key', 'text', 'key key'.encode('utf-16-le'), 0),
    ],
)
def test_count_pattern(pattern, pattern_type, data, count):
    assert count_pattern(data, compile_pattern(pattern, pattern_type)) == count


def test_text_pattern_in_utf16():
    pattern = compile_pattern('key', 'text', 'utf-16-le')
    assert count_pattern('key key'.encode('utf-16-le'), pattern) == 2


@pytest.mark.parametrize(
    ('pattern', 'pattern_type', 'encoding'),
    [
        ('', 'bytes', 'utf-8'),
        ('a', 'glob', 'utf-8'),
        ('\\q', 'bytes', 'utf-8'),
        ('zz', 'hex', 'utf-8'),
        ('  ', 'hex', 'utf-8'),
        ('[unclosed', 'regex', 'utf-8'),
        ('ä', 'regex', 'utf-8'),
        ('key', 'text', 'utf-16'),  # no fixed byte order
        ('ä', 'text', 'ascii'),
    ],
)
def test_invalid_patterns(pattern, pattern_type, encoding):
    with pytest.raises(BinaryParameterError):
        compile_pattern(pattern, pattern_type, encoding)


def test_regex_patterns_are_compiled_for_bytes():
    assert isinstance(compile_pattern('a.c', 'regex'), re.Pattern)


@pytest.mark.parametrize(
    ('raw', 'items'),
    [
        (b'k\x00v\x00', [b'k', b'v']),
        (b'k\x00v', [b'k', b'v']),
        (b'k\x00\x00', [b'k', b'']),  # an empty value
        (b'', [b'']),
    ],
)
def test_split_strings(raw, items):
    assert split_strings(raw, b'\x00', 'utf-8') == items


def test_split_utf16_strings_only_at_aligned_separators():
    raw = 'a'.encode('utf-16-le') + b'\x00\x00' + 'Ā'.encode('utf-16-le') + b'\x00\x00'
    assert split_strings(raw, b'\x00\x00', 'utf-16-le') == ['a'.encode('utf-16-le'), 'Ā'.encode('utf-16-le')]


def test_string_table_pairs():
    assert string_table(b'a\x001\x00b\x00\x00', b'\x00', 'utf-8') == [('a', b'1'), ('b', b'')]
    assert string_table(b'', b'\x00', 'utf-8') == []


def test_odd_string_table_is_an_error():
    with pytest.raises(OffsetError, match='3 strings'):
        string_table(b'a\x001\x00b\x00', b'\x00', 'utf-8')


def test_separator_must_fit_the_code_unit():
    with pytest.raises(BinaryParameterError):
        split_strings(b'a\x00', b'\x00', 'utf-16-le')


def test_non_finite_float_is_its_own_documented_error():
    # found by test_parser_fuzz.py: a plain ValueError, which the binary collection did not handle
    data = BinaryFile(io.BytesIO(struct.pack('>d', float('nan'))), 8)

    with pytest.raises(NonFiniteValueError, match='not a finite number'):
        read_value(data, 0, parse_value_format('f64be'))
