"""adarelib.testset.fileinfo: timestamp strings, file timestamps, permission strings, owner/group.

Runs on the guests' Python 3.10 too (``make test-adarelib-guest``): no ``adare`` import.
"""

import os
import stat
import sys
from datetime import datetime
from types import SimpleNamespace

import pytest

from adarelib.testset import fileinfo

pytestmark = pytest.mark.unit


# --- parse_timestamp --------------------------------------------------------------------


@pytest.mark.parametrize(
    ('value', 'expected'),
    [
        (1705314600, 1705314600.0),
        (1705314600.5, 1705314600.5),
        ('1705314600', 1705314600.0),
        ('1705314600.25', 1705314600.25),
        ('-5', -5.0),
    ],
)
def test_numbers_and_numeric_strings_are_epoch_seconds(value, expected):
    assert fileinfo.parse_timestamp(value) == expected


@pytest.mark.parametrize(
    ('text', 'naive'),
    [
        ('2024-01-15 10:30:00', datetime(2024, 1, 15, 10, 30)),
        ('2024-01-15T10:30:00', datetime(2024, 1, 15, 10, 30)),
        ('2024-01-15T10:30:00Z', datetime(2024, 1, 15, 10, 30)),
        ('2024-01-15', datetime(2024, 1, 15)),
        ('01/15/2024 10:30:00', datetime(2024, 1, 15, 10, 30)),
        ('01/15/2024', datetime(2024, 1, 15)),
    ],
)
def test_common_string_formats_are_local_wall_time(text, naive):
    # documented: naive strings (the trailing-Z format too) are read in the local timezone
    assert fileinfo.parse_timestamp(text) == naive.timestamp()


def test_custom_format_is_tried_first():
    assert fileinfo.parse_timestamp('15.01.2024 10:30', '%d.%m.%Y %H:%M') == datetime(2024, 1, 15, 10, 30).timestamp()


def test_custom_format_that_does_not_fit_falls_back_to_the_common_formats():
    assert fileinfo.parse_timestamp('2024-01-15', '%d.%m.%Y') == datetime(2024, 1, 15).timestamp()


def test_custom_format_is_tried_before_the_epoch_reading():
    assert fileinfo.parse_timestamp('20240115', '%Y%m%d') == datetime(2024, 1, 15).timestamp()


def test_numeric_string_without_format_is_epoch_seconds():
    assert fileinfo.parse_timestamp('20240115') == 20240115.0


@pytest.mark.parametrize('value', ['yesterday', '2024-13-45', '15.01.2024', '', None])
def test_unparseable_timestamp_raises_value_error(value):
    with pytest.raises(ValueError, match='Cannot parse timestamp'):
        fileinfo.parse_timestamp(value)


# --- file_timestamp ---------------------------------------------------------------------


@pytest.fixture
def stamped(tmp_path):
    path = tmp_path / 'f.txt'
    path.write_text('x')
    os.utime(path, (1_600_000_000, 1_700_000_000))  # atime, mtime
    return str(path)


def test_modified_and_accessed(stamped):
    assert fileinfo.file_timestamp(stamped, 'modified') == 1_700_000_000
    assert fileinfo.file_timestamp(stamped, 'accessed') == 1_600_000_000


def _fake_stat(**fields):
    return SimpleNamespace(stat=lambda _path: SimpleNamespace(**fields))


def test_created_on_windows_is_st_ctime(monkeypatch):
    monkeypatch.setattr(fileinfo, 'platform', SimpleNamespace(system=lambda: 'Windows'))
    monkeypatch.setattr(fileinfo, 'os', _fake_stat(st_ctime=11.0, st_birthtime=22.0))
    assert fileinfo.file_timestamp('x', 'created') == 11.0


def test_created_elsewhere_prefers_birthtime(monkeypatch):
    monkeypatch.setattr(fileinfo, 'platform', SimpleNamespace(system=lambda: 'Darwin'))
    monkeypatch.setattr(fileinfo, 'os', _fake_stat(st_ctime=11.0, st_birthtime=22.0))
    assert fileinfo.file_timestamp('x', 'created') == 22.0


def test_created_without_birthtime_falls_back_to_ctime(monkeypatch):
    monkeypatch.setattr(fileinfo, 'platform', SimpleNamespace(system=lambda: 'Linux'))
    monkeypatch.setattr(fileinfo, 'os', _fake_stat(st_ctime=11.0))
    assert fileinfo.file_timestamp('x', 'created') == 11.0


def test_created_on_a_real_file_is_a_number(stamped):
    assert isinstance(fileinfo.file_timestamp(stamped, 'created'), float)


@pytest.mark.parametrize('kind', ['changed', 'Modified', '', 'birth'])
def test_unsupported_timestamp_type_raises(stamped, kind):
    with pytest.raises(ValueError, match='Unsupported timestamp type'):
        fileinfo.file_timestamp(stamped, kind)


def test_missing_file_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        fileinfo.file_timestamp(str(tmp_path / 'missing'), 'modified')


# --- parse_permissions ------------------------------------------------------------------


@pytest.mark.parametrize(
    ('text', 'expected'),
    [
        ('644', 0o644),
        ('0755', 0o755),
        ('600', 0o600),
        ('0', 0),
        ('777', 0o777),
    ],
)
def test_octal_permissions(text, expected):
    assert fileinfo.parse_permissions(text) == expected


@pytest.mark.parametrize(
    ('text', 'expected'),
    [
        ('rwxr-xr-x', 0o755),
        ('rw-r--r--', 0o644),
        ('rw-------', 0o600),
        ('---------', 0),
        ('rwxrwxrwx', 0o777),
        ('r--r-----', 0o440),
        ('-w--w--w-', 0o222),
        ('--x--x--x', 0o111),
    ],
)
def test_symbolic_permissions(text, expected):
    assert fileinfo.parse_permissions(text) == expected


def test_symbolic_matches_the_stat_bits():
    assert fileinfo.parse_permissions('rwxr-x---') == stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP


@pytest.mark.parametrize('text', ['', 'rwx', 'drwxr-xr-x', 'rwxr-xr-x ', '0o755', 'u+rwx'])
def test_invalid_permission_format_raises(text):
    with pytest.raises(ValueError):
        fileinfo.parse_permissions(text)


@pytest.mark.parametrize('text', ['8', '779', '1239'])
def test_non_octal_digits_raise(text):
    with pytest.raises(ValueError):
        fileinfo.parse_permissions(text)


@pytest.mark.parametrize('text', ['zzzzzzzzz', 'rwxr-xr-q', 'xwrxwrxwr'])
def test_invalid_symbolic_letters_raise(text):
    with pytest.raises(ValueError):
        fileinfo.parse_permissions(text)


# --- owner_and_group --------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == 'win32', reason='pwd/grp exist only on Unix')
def test_owner_and_group_of_an_own_file(tmp_path):
    import grp
    import pwd

    path = tmp_path / 'f'
    path.write_text('x')
    owner, group = fileinfo.owner_and_group(str(path))
    assert owner == pwd.getpwuid(os.getuid()).pw_name
    assert group == grp.getgrgid(path.stat().st_gid).gr_name


def test_owner_and_group_of_a_missing_file_is_none(tmp_path):
    assert fileinfo.owner_and_group(str(tmp_path / 'missing')) == (None, None)


def test_owner_and_group_without_pwd_module_is_none(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, 'pwd', None)  # import pwd -> ImportError, as on Windows
    path = tmp_path / 'f'
    path.write_text('x')
    assert fileinfo.owner_and_group(str(path)) == (None, None)
