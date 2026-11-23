"""Unit tests for standard.file_count (test_standard.py is at its size budget).

Runs on the guests' Python 3.10 too (``make test-testfunctions-guest``).
"""

import io
import os
import zipfile
from pathlib import Path

import pytest

from adarelib.constants import StatusEnum
from adarelib.helper.module import import_module_from_pyfile

pytestmark = pytest.mark.unit

COLLECTIONS = Path(__file__).resolve().parents[3] / 'appdata' / 'testfunctions'
standard = import_module_from_pyfile(COLLECTIONS / 'standard' / 'standard.py')
FileCount = standard.file_count._test_class
FileCountParameter = standard.file_count._parameter_class


def _count(dst, **params):
    return FileCount(name='t', parameter=FileCountParameter(dst=str(dst), **params)).test()


@pytest.fixture
def logs(tmp_path):
    """3 .log files, 1 .txt, 1 dotfile, 1 directory named like a log."""
    for name in ('a.log', 'b.log', 'c.log', 'notes.txt', '.hidden.log'):
        (tmp_path / name).write_text(name)
    (tmp_path / 'old.log').mkdir()
    return tmp_path


@pytest.mark.parametrize(
    ('expected_count', 'comparison_type', 'status'),
    [
        (3, 'equals', StatusEnum.SUCCESS),
        (2, 'equals', StatusEnum.FAILED),
        (2, 'greater', StatusEnum.SUCCESS),
        (3, 'greater', StatusEnum.FAILED),
        (4, 'less', StatusEnum.SUCCESS),
        (3, 'less', StatusEnum.FAILED),
        (3, 'greater_equal', StatusEnum.SUCCESS),
        (3, 'less_equal', StatusEnum.SUCCESS),
        (2, 'less_equal', StatusEnum.FAILED),
    ],
)
def test_comparison_types(logs, expected_count, comparison_type, status):
    """``*`` skips the dotfile, kind file skips the directory."""
    result = _count(logs / '*.log', expected_count=expected_count, comparison_type=comparison_type)

    assert result.status == status, result.details
    assert result.details[0].startswith('3 file path(s) match')


@pytest.mark.parametrize(('kind', 'count'), [('file', 3), ('dir', 1), ('any', 4)])
def test_kind(logs, kind, count):
    result = _count(logs / '*.log', expected_count=count, kind=kind)

    assert result.status == StatusEnum.SUCCESS, result.details


def test_no_match_counts_zero(tmp_path):
    """An existence test: no match is a count of 0, not an error."""
    assert _count(tmp_path / '*.tmp', expected_count=0).status == StatusEnum.SUCCESS
    assert _count(tmp_path / '*.tmp', expected_count=1).status == StatusEnum.FAILED
    assert _count(tmp_path / 'missing' / '*.tmp', expected_count=0).status == StatusEnum.SUCCESS


def test_plain_path(logs):
    assert _count(logs / 'a.log', expected_count=1).status == StatusEnum.SUCCESS
    assert _count(logs / 'missing.log', expected_count=0).status == StatusEnum.SUCCESS
    assert _count(logs / 'old.log', expected_count=0).status == StatusEnum.SUCCESS  # a dir, not a file
    assert _count(logs / 'old.log', expected_count=1, kind='dir').status == StatusEnum.SUCCESS


@pytest.mark.skipif(not hasattr(os, 'symlink') or os.name == 'nt', reason='symlinks')
def test_symlinks(logs):
    (logs / 'link.log').symlink_to(logs / 'a.log')
    (logs / 'broken.log').symlink_to(logs / 'nowhere')

    assert _count(logs / '*.log', expected_count=4).status == StatusEnum.SUCCESS  # link to a file
    assert _count(logs / '*.log', expected_count=6, kind='any').status == StatusEnum.SUCCESS  # broken too


def _zip(path, names):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as zf:
        for name in names:
            if name.endswith('/'):
                zf.writestr(zipfile.ZipInfo(name), '')
            else:
                zf.writestr(name, name)
    path.write_bytes(buffer.getvalue())
    return path


def test_archive_members(tmp_path):
    archive = _zip(tmp_path / 'a.zip', ['logs/', 'logs/1.log', 'logs/2.log', 'logs/x.txt', 'other/3.log'])

    assert _count(f'{archive}!/logs/*.log', expected_count=2).status == StatusEnum.SUCCESS
    assert _count(f'{archive}!/*/*.log', expected_count=3).status == StatusEnum.SUCCESS
    assert _count(f'{archive}!/logs/*.bak', expected_count=0).status == StatusEnum.SUCCESS
    assert _count(f'{archive}!/logs/1.log', expected_count=1).status == StatusEnum.SUCCESS
    assert _count(f'{archive}!/logs/9.log', expected_count=0).status == StatusEnum.SUCCESS


def test_unusable_archive_is_error(tmp_path):
    (tmp_path / 'bad.zip').write_bytes(b'PK\x03\x04 not really a zip')

    assert _count(f'{tmp_path}/missing.zip!/*.log', expected_count=0).status == StatusEnum.ERROR
    assert _count(f'{tmp_path}/bad.zip!/*.log', expected_count=0).status == StatusEnum.ERROR


def test_dir_inside_archive_is_error(tmp_path):
    archive = _zip(tmp_path / 'a.zip', ['logs/', 'logs/1.log'])

    result = _count(f'{archive}!/*', expected_count=0, kind='dir')
    assert result.status == StatusEnum.ERROR
    assert 'inside an archive' in result.details[0]


@pytest.mark.parametrize(
    'params',
    [
        {'expected_count': -1},
        {'expected_count': 'two'},
        {'expected_count': True},
        {'expected_count': 1, 'comparison_type': 'roughly'},
        {'expected_count': 1, 'kind': 'symlink'},
    ],
)
def test_bad_parameters_are_errors(logs, params):
    assert _count(logs / '*.log', **params).status == StatusEnum.ERROR


@pytest.mark.parametrize('dst', ['', '  ', '{{ unset }}/*.log', '/home/{{ user }}/a.log'])
def test_empty_or_unresolved_dst_is_error(dst):
    """An absence count must not pass on a path that was never resolved."""
    assert _count(dst, expected_count=0).status == StatusEnum.ERROR
