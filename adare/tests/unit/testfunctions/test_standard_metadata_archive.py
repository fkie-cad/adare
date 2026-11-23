"""standard.file_timestamps / file_permissions refuse an archive member (test_standard.py is at its size budget).

The member would be read through a temporary extracted copy, whose times, mode and owner are
not the member's: ``within_last`` passed on the extraction time. Runs on the guests' Python 3.10
too (``make test-testfunctions-guest``).
"""

import zipfile
from pathlib import Path

import pytest

from adarelib.constants import StatusEnum
from adarelib.helper.module import import_module_from_pyfile

pytestmark = pytest.mark.unit

COLLECTIONS = Path(__file__).resolve().parents[3] / 'appdata' / 'testfunctions'
standard = import_module_from_pyfile(COLLECTIONS / 'standard' / 'standard.py')


def _run(function, **params):
    func = getattr(standard, function)
    return func._test_class(name='t', parameter=func._parameter_class(**params)).test()


@pytest.fixture
def archive(tmp_path):
    path = tmp_path / 'backup.zip'
    with zipfile.ZipFile(path, 'w') as zf:
        info = zipfile.ZipInfo('notes.txt', date_time=(2001, 1, 1, 0, 0, 0))
        zf.writestr(info, 'old content')
    return path


def test_timestamps_of_a_member_are_an_error_not_the_extraction_time(archive):
    result = _run('file_timestamps', dst=f'{archive}!/notes.txt', comparison_type='within_last', within_duration='1h')
    assert result.status == StatusEnum.ERROR
    assert 'archive member' in result.details[0]


def test_permissions_of_a_member_are_an_error(archive):
    result = _run('file_permissions', dst=f'{archive}!/notes.txt', expected_permissions='644')
    assert result.status == StatusEnum.ERROR
    assert 'archive member' in result.details[0]


def test_the_archive_file_itself_still_works(archive):
    result = _run('file_timestamps', dst=str(archive), comparison_type='within_last', within_duration='1h')
    assert result.status == StatusEnum.SUCCESS
