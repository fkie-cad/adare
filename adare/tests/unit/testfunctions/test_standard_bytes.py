"""Unit tests for standard.file_content_contains with ``content_type: bytes``
(test_standard.py is at its size budget).

Bytes mode is strict: ASCII characters and Python escapes only; anything else is an ERROR,
never a guessed encoding. Runs on the guests' Python 3.10 too (``make test-testfunctions-guest``).
"""

from pathlib import Path

import pytest

from adarelib.constants import StatusEnum
from adarelib.helper.module import import_module_from_pyfile
from adarelib.testset.content import parse_byte_string, parse_duration

pytestmark = pytest.mark.unit

COLLECTIONS = Path(__file__).resolve().parents[3] / 'appdata' / 'testfunctions'
standard = import_module_from_pyfile(COLLECTIONS / 'standard' / 'standard.py')
Contains = standard.file_content_contains._test_class
ContainsParameter = standard.file_content_contains._parameter_class

DATA = b'MZ\x90\x00\x03caf\xe9 \\path\nend\xc3\xa4'


def _contains(dst, content, **params):
    parameter = ContainsParameter(dst=str(dst), content=content, content_type='bytes', **params)
    return Contains(name='t', parameter=parameter).test()


@pytest.fixture
def blob(tmp_path):
    path = tmp_path / 'blob.bin'
    path.write_bytes(DATA)
    return path


@pytest.mark.parametrize(
    'content',
    [r'MZ\x90\x00', r'caf\xe9', r' \\path\n', r'\303\244', 'end', ''],
)
def test_found(blob, content):
    result = _contains(blob, content)

    assert result.status == StatusEnum.SUCCESS, result.details


@pytest.mark.parametrize('content', [r'MZ\x91', r'\\\\path', 'END'])
def test_not_found_is_failed(blob, content):
    assert _contains(blob, content).status == StatusEnum.FAILED


@pytest.mark.parametrize(
    'content',
    [
        'ä',  # was silently searched as UTF-8 c3 a4
        'café',  # was silently searched as UTF-8, not as the Latin-1 byte e9
        r'\q',  # was silently searched as the two characters
        r'\x9',
        r'\u00e4',
        r'\N{LATIN SMALL LETTER A WITH DIAERESIS}',
        r'\777',
        r'\400',
        'trailing\\',
    ],
)
def test_non_ascii_or_bad_escape_is_error(blob, content):
    result = _contains(blob, content)

    assert result.status == StatusEnum.ERROR, result.details
    assert 'content_type string' in result.details[0]


def test_bad_content_is_error_even_when_file_is_missing(tmp_path):
    """The parameter is checked first: the error names the content, not the file."""
    result = _contains(tmp_path / 'missing.bin', 'ä')

    assert result.status == StatusEnum.ERROR
    assert 'ä' in result.details[0]


def test_missing_file_is_error(tmp_path):
    assert _contains(tmp_path / 'missing.bin', 'x').status == StatusEnum.ERROR


def test_string_mode_unchanged(blob):
    """Non-ASCII text stays allowed in string mode (decoded with ``encoding``)."""
    parameter = ContainsParameter(dst=str(blob), content='café', encoding='latin-1')

    assert Contains(name='t', parameter=parameter).test().status == StatusEnum.SUCCESS


@pytest.mark.parametrize(
    ('content', 'expected'),
    [
        ('abc', b'abc'),
        (r'\x00\xff\xFF', b'\x00\xff\xff'),
        (r'\n\r\t\\\'\"\a\b\f\v', b'\n\r\t\\\'"\x07\x08\x0c\x0b'),
        (r'\0\101\377', b'\x00A\xff'),
        ('t\x00o', b't\x00o'),  # literal control characters are ASCII
        ('', b''),
    ],
)
def test_parse_byte_string(content, expected):
    assert parse_byte_string(content) == expected


@pytest.mark.parametrize(
    'content', ['é', '€', r'\q', r'\x4', r'\x', r'\u0041', r'\U00000041', r'\400', 'a\\', 'a\\\nb']
)
def test_parse_byte_string_rejects(content):
    with pytest.raises(ValueError):
        parse_byte_string(content)


@pytest.mark.parametrize(('duration', 'seconds'), [('30s', 30), ('5m', 300), ('2h', 7200), ('1d', 86400), ('0m', 0)])
def test_parse_duration(duration, seconds):
    assert parse_duration(duration) == seconds


@pytest.mark.parametrize('duration', ['-5m', ' 5m', '1_0m', '5', 'm', '5w', '', None, 5])
def test_parse_duration_rejects(duration):
    with pytest.raises(ValueError):
        parse_duration(duration)
