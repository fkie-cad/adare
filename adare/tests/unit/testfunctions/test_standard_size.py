"""Unit tests for standard.file_size (test_standard.py is at its size budget).

Runs on the guests' Python 3.10 too (``make test-testfunctions-guest``).
"""

import io
import zipfile
from pathlib import Path

import pytest

from adarelib.constants import StatusEnum
from adarelib.helper.module import import_module_from_pyfile

pytestmark = pytest.mark.unit

COLLECTIONS = Path(__file__).resolve().parents[3] / 'appdata' / 'testfunctions'
standard = import_module_from_pyfile(COLLECTIONS / 'standard' / 'standard.py')
FileSize = standard.file_size._test_class
FileSizeParameter = standard.file_size._parameter_class


def _size(dst, **params):
    return FileSize(name='t', parameter=FileSizeParameter(dst=str(dst), **params)).test()


@pytest.fixture
def five(tmp_path):
    path = tmp_path / 'five.bin'
    path.write_bytes(b'\x00\x01abc')
    return path


@pytest.mark.parametrize(
    ('expected_size', 'comparison_type', 'status'),
    [
        (5, 'equals', StatusEnum.SUCCESS),
        (4, 'equals', StatusEnum.FAILED),
        (0, 'greater', StatusEnum.SUCCESS),
        (5, 'greater', StatusEnum.FAILED),
        (6, 'less', StatusEnum.SUCCESS),
        (5, 'less', StatusEnum.FAILED),
        (5, 'greater_equal', StatusEnum.SUCCESS),
        (6, 'greater_equal', StatusEnum.FAILED),
        (5, 'less_equal', StatusEnum.SUCCESS),
        (4, 'less_equal', StatusEnum.FAILED),
    ],
)
def test_comparison_types(five, expected_size, comparison_type, status):
    result = _size(five, expected_size=expected_size, comparison_type=comparison_type)

    assert result.status == status, result.details
    assert 'is 5 bytes' in result.details[0]


def test_empty_file(tmp_path):
    empty = tmp_path / 'empty.log'
    empty.write_bytes(b'')

    assert _size(empty, expected_size=0).status == StatusEnum.SUCCESS
    assert _size(empty, expected_size=0, comparison_type='greater').status == StatusEnum.FAILED


def test_glob_matching_one_file(five):
    assert _size(five.parent / 'fiv*.bin', expected_size=5).status == StatusEnum.SUCCESS


def test_archive_member_size(tmp_path):
    archive = tmp_path / 'a.zip'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        zf.writestr('p/x.txt', b'1234567')
    archive.write_bytes(buf.getvalue())

    assert _size(f'{archive}!/p/x.txt', expected_size=7).status == StatusEnum.SUCCESS


@pytest.mark.parametrize(
    'params',
    [
        {'expected_size': -1},
        {'expected_size': 'big'},
        {'expected_size': True},
        {'expected_size': 1.5},
        {'expected_size': 5, 'comparison_type': 'roughly'},
    ],
)
def test_bad_parameters_are_errors(five, params):
    assert _size(five, **params).status == StatusEnum.ERROR


def test_missing_file_is_an_error(tmp_path):
    # ERROR, not FAILED: expect_to_fail inverts only SUCCESS/FAILED
    result = _size(tmp_path / 'missing.bin', expected_size=0)

    assert result.status == StatusEnum.ERROR
    assert 'does not exist' in result.details[0]


def test_directory_is_an_error(tmp_path):
    result = _size(tmp_path, expected_size=0, comparison_type='greater_equal')

    assert result.status == StatusEnum.ERROR
    assert 'directory' in result.details[0]


@pytest.mark.parametrize('pattern', ['nothing*.bin', 'a*.bin'])
def test_glob_without_unique_match_is_an_error(tmp_path, pattern):
    (tmp_path / 'a1.bin').write_bytes(b'a')
    (tmp_path / 'a2.bin').write_bytes(b'a')

    assert _size(tmp_path / pattern, expected_size=1).status == StatusEnum.ERROR
