"""Unit tests for the text collection (occurrence_count, line_count, lines_in_order).

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
LinesInOrder = text.lines_in_order._test_class
LinesInOrderParameter = text.lines_in_order._parameter_class


def _occurrences(dst, **params):
    return OccurrenceCount(name='t', parameter=OccurrenceCountParameter(dst=str(dst), **params)).test()


def _lines(dst, **params):
    return LineCount(name='t', parameter=LineCountParameter(dst=str(dst), **params)).test()


def _in_order(dst, **params):
    return LinesInOrder(name='t', parameter=LinesInOrderParameter(dst=str(dst), **params)).test()


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


# ============================================================================
# lines_in_order
# ============================================================================

SERVICE_LOG = (
    '10:00 service started\n'  # 1
    '10:01 opened /data/report.txt\n'  # 2
    '10:02 heartbeat\n'  # 3
    '10:03 Deleted /data/report.txt\n'  # 4
    '10:04 opened /data/notes.txt\n'  # 5
    '10:05 service stopped\n'  # 6
)


class TestLinesInOrder:
    """Tests for lines_in_order."""

    @pytest.fixture
    def log(self, tmp_path):
        return _file(tmp_path, SERVICE_LOG.encode(), 'service.log')

    def test_patterns_in_order_pass_and_report_line_numbers(self, log):
        result = _in_order(log, patterns=['started', 'opened', 'Deleted', 'stopped'])

        assert result.status == StatusEnum.SUCCESS, result.details
        assert result.details[0] == '4 pattern(s) matched in order on lines 1, 2, 4, 6'
        assert "pattern 3 'Deleted' matched line 4" in result.details

    def test_each_pattern_takes_the_earliest_later_line(self, log):
        # 'opened' twice: the first one takes line 2, the second one line 5
        result = _in_order(log, patterns=['opened', 'opened', 'stopped'])

        assert result.status == StatusEnum.SUCCESS, result.details
        assert 'lines 2, 5, 6' in result.details[0]

    def test_two_patterns_never_share_a_line(self, log):
        result = _in_order(log, patterns=['Deleted', 'report'])

        assert result.status == StatusEnum.FAILED, result.details
        assert "pattern 2 'report' matches no line after line 4" in result.details[0]
        assert 'only earlier, on line(s) 2, 4' in result.details[0]

    def test_out_of_order_names_the_pattern_and_its_earlier_lines(self, log):
        result = _in_order(log, patterns=['heartbeat', 'started'])

        assert result.status == StatusEnum.FAILED, result.details
        assert result.details[0] == (
            "pattern 2 'started' matches no line after line 3 (6 line(s)); "
            'it occurs only earlier, on line(s) 1: out of order'
        )
        assert result.details[1] == "pattern 1 'heartbeat' matched line 3"

    def test_missing_pattern_fails(self, log):
        result = _in_order(log, patterns=['started', 'renamed'])

        assert result.status == StatusEnum.FAILED, result.details
        assert "pattern 2 'renamed' matches no line after line 1" in result.details[0]
        assert 'earlier' not in result.details[0]

    def test_first_pattern_missing_fails(self, log):
        result = _in_order(log, patterns=['renamed'])

        assert result.status == StatusEnum.FAILED
        assert "matches no line in the file" in result.details[0]

    def test_regex_and_case_insensitive(self, log):
        assert _in_order(log, patterns=[r'opened .*report\.txt', r'deleted'], regex=True).status == StatusEnum.FAILED
        result = _in_order(log, patterns=[r'opened .*report\.txt', r'^\S+ deleted'], regex=True, case_sensitive=False)
        assert result.status == StatusEnum.SUCCESS, result.details
        assert _in_order(log, patterns=['STARTED', 'deleted'], case_sensitive=False).status == StatusEnum.SUCCESS

    def test_regex_metacharacters_are_literal_without_regex(self, tmp_path):
        path = _file(tmp_path, b'a.c\nabc\n', 'app.log')

        assert _in_order(path, patterns=['abc', 'a.c']).status == StatusEnum.FAILED
        assert _in_order(path, patterns=['abc', 'a.c'], regex=True).status == StatusEnum.FAILED
        assert _in_order(path, patterns=['a.c', 'abc']).status == StatusEnum.SUCCESS

    def test_utf16_with_bom_and_auto_encoding(self, tmp_path):
        path = _file(tmp_path, SERVICE_LOG.encode('utf-16'), 'service.log')

        assert _in_order(path, patterns=['started', 'stopped']).status == StatusEnum.SUCCESS
        bomless = _file(tmp_path, SERVICE_LOG.encode('utf-16-le'), 'bomless.log')
        assert _in_order(bomless, patterns=['started', 'stopped'], encoding=None).status == StatusEnum.SUCCESS

    def test_undecodable_content_is_an_error(self, tmp_path):
        path = _file(tmp_path, 'café\nthé\n'.encode('latin-1'), 'app.log')

        assert _in_order(path, patterns=['caf']).status == StatusEnum.ERROR
        assert _in_order(path, patterns=['café', 'thé'], encoding='latin-1').status == StatusEnum.SUCCESS

    def test_empty_file_fails(self, tmp_path):
        result = _in_order(_file(tmp_path, b'', 'empty.log'), patterns=['x'])

        assert result.status == StatusEnum.FAILED

    def test_archive_member(self, tmp_path):
        import io
        import tarfile

        archive = tmp_path / 'logs.tar.gz'
        with tarfile.open(archive, 'w:gz') as tar:
            info = tarfile.TarInfo('logs/service.log')
            info.size = len(SERVICE_LOG.encode())
            tar.addfile(info, io.BytesIO(SERVICE_LOG.encode()))

        result = _in_order(f'{archive}!/logs/service.log', patterns=['started', 'stopped'])
        assert result.status == StatusEnum.SUCCESS, result.details
        missing = _in_order(f'{archive}!/logs/other.log', patterns=['started'])
        assert missing.status == StatusEnum.ERROR, missing.details

    @pytest.mark.parametrize(
        'params',
        [
            {'patterns': []},
            {'patterns': 'started'},
            {'patterns': None},
            {'patterns': ['started', 5]},
            {'patterns': ['started', '']},
            {'patterns': ['[unclosed'], 'regex': True},
            {'patterns': ['{{value}}']},
            {'patterns': ['x'], 'encoding': 'no-such-codec'},
            {'patterns': ['x'], 'regex': 'yes'},
            {'patterns': ['x'], 'case_sensitive': 'no'},
        ],
    )
    def test_bad_parameters_are_errors(self, log, params):
        result = _in_order(log, **params)

        assert result.status == StatusEnum.ERROR, result.details

    def test_missing_file_is_an_error(self, tmp_path):
        result = _in_order(tmp_path / 'missing.log', patterns=['x'])

        assert result.status == StatusEnum.ERROR
        assert 'does not exist' in result.details[0]
