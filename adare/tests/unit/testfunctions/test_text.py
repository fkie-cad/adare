"""Unit tests for the text collection (occurrence_count, line_count).

Runs on the guests' Python 3.10 too (``make test-testfunctions-guest``).
"""

from pathlib import Path

import pytest

from adarelib.constants import StatusEnum
from adarelib.helper.module import import_module_from_pyfile

pytestmark = pytest.mark.unit

COLLECTIONS = Path(__file__).resolve().parents[3] / 'appdata' / 'testfunctions'
text = import_module_from_pyfile(COLLECTIONS / 'text' / 'text.py')
OccurrenceCount = text.occurrence_count._test_class
OccurrenceCountParameter = text.occurrence_count._parameter_class
LineCount = text.line_count._test_class
LineCountParameter = text.line_count._parameter_class


def _occurrences(dst, **params):
    return OccurrenceCount(name='t', parameter=OccurrenceCountParameter(dst=str(dst), **params)).test()


def _lines(dst, **params):
    return LineCount(name='t', parameter=LineCountParameter(dst=str(dst), **params)).test()


def _file(tmp_path, data: bytes, name='data.bin'):
    path = tmp_path / name
    path.write_bytes(data)
    return path


# ============================================================================
# occurrence_count
# ============================================================================

BINARY = (
    b'\x00\x01token\x01'
    + 'token'.encode('utf-16-le')
    + b'\xff\xfeTOKEN tokentoken'
    + 'TOKEN'.encode('utf-16-be')
    + 'Grüße'.encode()
    + 'GRÜSSE'.encode()
)


class TestOccurrenceCount:
    """Tests for occurrence_count."""

    def test_utf16_text_is_not_counted_again_in_the_other_byte_order(self, tmp_path):
        # 'xab' in UTF-16-LE also contains 'ab' in UTF-16-BE, shifted by one byte
        path = _file(tmp_path, 'xab'.encode('utf-16-le'))
        result = _occurrences(path, content='ab', expected_count=1, encoding=['utf-16'])
        assert result.status == StatusEnum.SUCCESS, result.details

    def test_single_encoding_name(self, tmp_path):
        """``encodings: utf-16-le`` in a playbook is one name, not a list of characters."""
        path = _file(tmp_path, 'token'.encode('utf-16-le'))
        result = _occurrences(path, content='token', expected_count=1, encoding='utf-16-le')
        assert result.status == StatusEnum.SUCCESS, result.details

    def test_encoding_name_split_into_characters_is_an_error(self, tmp_path):
        # a safety net: what a list[str]-only structuring would make of `encodings: utf-8`
        result = _occurrences(_file(tmp_path, b'token'), content='token', expected_count=1, encoding=list('utf-8'))
        assert result.status == StatusEnum.ERROR
        assert "characters of 'utf-8'" in result.details[0]

    @pytest.mark.parametrize(
        ('params', 'count'),
        [
            ({'content': 'token'}, 3),
            ({'content': 'token', 'encoding': ['utf-16-le']}, 1),
            ({'content': 'token', 'encoding': 'utf-16-le'}, 1),
            ({'content': 'token', 'encoding': ['utf-8', 'utf-16-le']}, 4),
            # utf-16 = both byte orders without BOM; duplicates are counted once
            ({'content': 'TOKEN', 'encoding': ['utf-16', 'utf-16-be']}, 1),
            ({'content': 'token', 'encoding': ['utf-8', 'utf8', 'UTF-8']}, 3),
            ({'content': 'token', 'case_sensitive': False}, 4),
            ({'content': 'token', 'case_sensitive': False, 'encoding': ['utf-16']}, 2),
            ({'content': 'grüße', 'case_sensitive': False}, 1),  # no ß -> SS mapping
            ({'content': 'tokentoken'}, 1),
            ({'content': r'\x00\x01token', 'content_type': 'bytes'}, 1),
            ({'content': 't\x00o\x00k', 'content_type': 'bytes'}, 1),
            ({'content': '74 6f 6b 65 6e', 'content_type': 'hex'}, 3),
            ({'content': 'FFFE', 'content_type': 'hex'}, 1),
            ({'content': 'absent'}, 0),
        ],
    )
    def test_counts(self, tmp_path, params, count):
        result = _occurrences(_file(tmp_path, BINARY), expected_count=count, **params)

        assert result.status == StatusEnum.SUCCESS, result.details
        assert result.details[0].startswith(f'{count} occurrence(s)')

    def test_non_overlapping(self, tmp_path):
        path = _file(tmp_path, b'aaaa')

        assert _occurrences(path, content='aa', expected_count=2).status == StatusEnum.SUCCESS
        result = _occurrences(path, content='a', case_sensitive=False, expected_count=4)
        assert result.status == StatusEnum.SUCCESS

    def test_bytes_mode_is_strict_about_non_ascii(self, tmp_path):
        """A literal non-ASCII character in bytes mode is an error, never a guessed encoding."""
        path = _file(tmp_path, b'caf\xe9')

        result = _occurrences(path, content='café', content_type='bytes', expected_count=1)
        assert result.status == StatusEnum.ERROR
        assert 'xNN' in result.details[0]
        assert (
            _occurrences(path, content=r'caf\xe9', content_type='bytes', expected_count=1).status == StatusEnum.SUCCESS
        )
        assert _occurrences(path, content='café', encoding=['latin-1'], expected_count=1).status == StatusEnum.SUCCESS
        assert _occurrences(path, content='café', expected_count=0).status == StatusEnum.SUCCESS  # utf-8 form

    @pytest.mark.parametrize(
        ('expected_count', 'comparison_type', 'status'),
        [
            (3, 'equals', StatusEnum.SUCCESS),
            (2, 'equals', StatusEnum.FAILED),
            (2, 'greater', StatusEnum.SUCCESS),
            (3, 'greater', StatusEnum.FAILED),
            (4, 'less', StatusEnum.SUCCESS),
            (3, 'greater_equal', StatusEnum.SUCCESS),
            (2, 'less_equal', StatusEnum.FAILED),
        ],
    )
    def test_comparison_types(self, tmp_path, expected_count, comparison_type, status):
        result = _occurrences(
            _file(tmp_path, BINARY), content='token', expected_count=expected_count, comparison_type=comparison_type
        )

        assert result.status == status, result.details

    def test_absence(self, tmp_path):
        path = _file(tmp_path, BINARY)

        assert _occurrences(path, content='wiped', expected_count=0).status == StatusEnum.SUCCESS
        assert _occurrences(path, content='token', expected_count=0).status == StatusEnum.FAILED

    def test_empty_file(self, tmp_path):
        path = _file(tmp_path, b'')

        assert _occurrences(path, content='x', expected_count=0).status == StatusEnum.SUCCESS

    @pytest.mark.parametrize(
        'params',
        [
            {'content': 'x', 'expected_count': -1},
            {'content': 'x', 'expected_count': 'one'},
            {'content': 'x', 'expected_count': 1, 'comparison_type': 'roughly'},
            {'content': '', 'expected_count': 0},
            {'content': 'x', 'expected_count': 0, 'content_type': 'regex'},
            {'content': 'x', 'expected_count': 0, 'encoding': ['no-such-codec']},
            {'content': 'x', 'expected_count': 0, 'encoding': []},
            {'content': 'x', 'expected_count': 0, 'encoding': [1]},
            {'content': '€', 'expected_count': 0, 'encoding': ['latin-1']},
            {'content': '€', 'expected_count': 0, 'content_type': 'bytes'},
            {'content': r'\x4', 'expected_count': 0, 'content_type': 'bytes'},
            {'content': r'€', 'expected_count': 0, 'content_type': 'bytes'},
            {'content': 'é', 'expected_count': 0, 'content_type': 'bytes'},
            {'content': r'\q', 'expected_count': 0, 'content_type': 'bytes'},
            {'content': r'\u00e9', 'expected_count': 0, 'content_type': 'bytes'},
            {'content': r'\777', 'expected_count': 0, 'content_type': 'bytes'},
            {'content': 'ab\\', 'expected_count': 0, 'content_type': 'bytes'},
            {'content': '4g', 'expected_count': 0, 'content_type': 'hex'},
            {'content': 'abc', 'expected_count': 0, 'content_type': 'hex'},
            {'content': ' ', 'expected_count': 0, 'content_type': 'hex'},
            {'content': 'ab', 'expected_count': 0, 'content_type': 'hex', 'case_sensitive': False},
        ],
    )
    def test_bad_parameters_are_errors(self, tmp_path, params):
        result = _occurrences(_file(tmp_path, BINARY), **params)

        assert result.status == StatusEnum.ERROR, result.details

    def test_missing_file_is_an_error(self, tmp_path):
        # ERROR, not FAILED: expect_to_fail inverts only SUCCESS/FAILED
        result = _occurrences(tmp_path / 'missing.bin', content='x', expected_count=0)

        assert result.status == StatusEnum.ERROR
        assert 'does not exist' in result.details[0]

    @pytest.mark.parametrize('pattern', ['nothing*.bin', 'a*.bin'])
    def test_glob_without_unique_match_is_an_error(self, tmp_path, pattern):
        _file(tmp_path, b'x', 'a1.bin')
        _file(tmp_path, b'x', 'a2.bin')

        assert _occurrences(tmp_path / pattern, content='x', expected_count=1).status == StatusEnum.ERROR

    def test_directory_is_an_error(self, tmp_path):
        assert _occurrences(tmp_path, content='x', expected_count=0).status == StatusEnum.ERROR

    def test_file_over_read_cap_is_an_error(self, tmp_path, monkeypatch):
        from adarelib.testset.archive import MAX_BYTES_ENV

        monkeypatch.setenv(MAX_BYTES_ENV, '4')
        result = _occurrences(_file(tmp_path, b'0123456789'), content='x', expected_count=0)

        assert result.status == StatusEnum.ERROR


# ============================================================================
# line_count
# ============================================================================

LOG = 'start\ndeleted: report.txt\nkept: notes.txt\nDELETED: report2.txt\r\ndeleted: other\rend\n'


class TestLineCount:
    """Tests for line_count."""

    @pytest.mark.parametrize(
        ('params', 'count'),
        [
            ({'content': 'deleted'}, 2),
            ({'content': 'report'}, 2),
            ({'content': '(?i)^deleted: .*report', 'regex_match': True}, 2),
            ({'content': r'\.txt$', 'regex_match': True}, 3),
            ({'content': ''}, 6),  # every line
            ({'content': 'absent'}, 0),
        ],
    )
    def test_counts(self, tmp_path, params, count):
        result = _lines(_file(tmp_path, LOG.encode(), 'app.log'), expected_count=count, **params)

        assert result.status == StatusEnum.SUCCESS, result.details
        assert result.details[0].startswith(f'{count} of 6 line(s)')

    @pytest.mark.parametrize(
        ('params', 'count'),
        [
            ({'content': 'deleted'}, 3),
            ({'content': 'DELETED: REPORT'}, 2),
            ({'content': 'Straße'}, 2),  # casefold: sharp s = ss
            ({'content': '^deleted: .*report', 'regex_match': True}, 2),
            ({'content': '^DELETED', 'regex_match': True}, 3),
        ],
    )
    def test_case_insensitive(self, tmp_path, params, count):
        data = LOG + 'STRASSE 1\nstraße 2\n'
        result = _lines(_file(tmp_path, data.encode(), 'app.log'), expected_count=count, case_sensitive=False, **params)

        assert result.status == StatusEnum.SUCCESS, result.details
        assert result.details[0].startswith(f'{count} of 8 line(s)')
        assert '(case-insensitive)' in result.details[0]

    def test_case_sensitive_by_default(self, tmp_path):
        path = _file(tmp_path, LOG.encode(), 'app.log')

        assert _lines(path, content='DELETED', expected_count=1).status == StatusEnum.SUCCESS
        assert _lines(path, content='DELETED', expected_count=3).status == StatusEnum.FAILED
        assert _lines(path, content='^DELETED', regex_match=True, expected_count=1).status == StatusEnum.SUCCESS

    def test_case_insensitive_mismatch_fails(self, tmp_path):
        path = _file(tmp_path, LOG.encode(), 'app.log')

        result = _lines(path, content='Deleted', case_sensitive=False, expected_count=2)

        assert result.status == StatusEnum.FAILED, result.details
        assert 'count 3 == 2 does not hold' in result.details[1]

    @pytest.mark.parametrize('encoding', ['utf-16-le', 'utf-16-be', 'utf-8-sig', 'utf-32'])
    def test_encoding_detected_from_bom_or_zero_bytes(self, tmp_path, encoding):
        data = LOG.encode(encoding)
        if encoding == 'utf-16-be':
            data = b'\xfe\xff' + data  # with BOM
        path = _file(tmp_path, data, 'app.log')

        assert _lines(path, content='deleted', expected_count=2).status == StatusEnum.SUCCESS

    def test_explicit_encoding(self, tmp_path):
        path = _file(tmp_path, 'café ok\nthé\n'.encode('latin-1'), 'app.log')

        assert _lines(path, content='café', encoding='latin-1', expected_count=1).status == StatusEnum.SUCCESS
        result = _lines(path, content='café', expected_count=1)  # not valid UTF-8
        assert result.status == StatusEnum.ERROR

    def test_empty_file_has_no_lines(self, tmp_path):
        path = _file(tmp_path, b'', 'empty.log')

        assert _lines(path, content='', expected_count=0).status == StatusEnum.SUCCESS

    def test_last_line_without_line_break(self, tmp_path):
        path = _file(tmp_path, b'a\nb', 'app.log')

        assert _lines(path, content='', expected_count=2).status == StatusEnum.SUCCESS

    @pytest.mark.parametrize(
        ('expected_count', 'comparison_type', 'status'),
        [
            (1, 'greater', StatusEnum.SUCCESS),
            (2, 'greater', StatusEnum.FAILED),
            (3, 'less', StatusEnum.SUCCESS),
            (2, 'greater_equal', StatusEnum.SUCCESS),
            (1, 'less_equal', StatusEnum.FAILED),
            (3, 'equals', StatusEnum.FAILED),
        ],
    )
    def test_comparison_types(self, tmp_path, expected_count, comparison_type, status):
        path = _file(tmp_path, LOG.encode(), 'app.log')

        result = _lines(path, content='deleted', expected_count=expected_count, comparison_type=comparison_type)

        assert result.status == status, result.details

    @pytest.mark.parametrize(
        'params',
        [
            {'content': 'x', 'expected_count': -1},
            {'content': 'x', 'expected_count': 1.0},
            {'content': 'x', 'expected_count': 1, 'comparison_type': 'roughly'},
            {'content': '[unclosed', 'expected_count': 1, 'regex_match': True},
            {'content': 'x', 'expected_count': 1, 'encoding': 'no-such-codec'},
            {'content': 5, 'expected_count': 1},
            {'content': 'x', 'expected_count': 1, 'case_sensitive': 'no'},
        ],
    )
    def test_bad_parameters_are_errors(self, tmp_path, params):
        result = _lines(_file(tmp_path, LOG.encode(), 'app.log'), **params)

        assert result.status == StatusEnum.ERROR, result.details

    def test_missing_file_is_an_error(self, tmp_path):
        result = _lines(tmp_path / 'missing.log', content='x', expected_count=0)

        assert result.status == StatusEnum.ERROR
        assert 'does not exist' in result.details[0]

    @pytest.mark.parametrize('pattern', ['nothing*.log', 'a*.log'])
    def test_glob_without_unique_match_is_an_error(self, tmp_path, pattern):
        _file(tmp_path, b'x', 'a1.log')
        _file(tmp_path, b'x', 'a2.log')

        assert _lines(tmp_path / pattern, content='x', expected_count=1).status == StatusEnum.ERROR
