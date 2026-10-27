"""Runs must not start on a nearly full disk."""

from collections import namedtuple
from unittest.mock import patch

import pytest

from adare.backend.system import disk_guard
from adare.backend.system.disk_guard import LowDiskSpaceError, ensure_free_disk

pytestmark = pytest.mark.unit

Usage = namedtuple('Usage', 'total used free')
GiB = 1024**3


def _free(gib: float):
    return patch.object(disk_guard.shutil, 'disk_usage', return_value=Usage(100 * GiB, 0, int(gib * GiB)))


def test_refuses_below_the_default_limit(tmp_path, monkeypatch):
    monkeypatch.delenv(disk_guard.MIN_FREE_ENV, raising=False)
    with _free(3), pytest.raises(LowDiskSpaceError, match='less than 10 GiB free'):
        ensure_free_disk([tmp_path])


def test_starts_with_enough_space(tmp_path, monkeypatch):
    monkeypatch.delenv(disk_guard.MIN_FREE_ENV, raising=False)
    with _free(50):
        ensure_free_disk([tmp_path])


def test_limit_is_configurable_and_zero_disables_it(tmp_path, monkeypatch):
    monkeypatch.setenv(disk_guard.MIN_FREE_ENV, '2')
    with _free(3):
        ensure_free_disk([tmp_path])
    monkeypatch.setenv(disk_guard.MIN_FREE_ENV, '0')
    with _free(0):
        ensure_free_disk([tmp_path])


def test_a_path_that_does_not_exist_yet_is_checked_on_its_filesystem(tmp_path, monkeypatch):
    monkeypatch.delenv(disk_guard.MIN_FREE_ENV, raising=False)
    with _free(1), pytest.raises(LowDiskSpaceError):
        ensure_free_disk([tmp_path / 'run' / 'not-created-yet'])


def test_suggests_the_cleanup_commands(tmp_path, monkeypatch):
    monkeypatch.delenv(disk_guard.MIN_FREE_ENV, raising=False)
    with _free(1), pytest.raises(LowDiskSpaceError) as exc:
        ensure_free_disk([tmp_path])
    assert any('dev remove --stopped' in s for s in exc.value.possible_solutions)
