"""Linux snapshot errors keep the error that caused them."""

import subprocess

import pytest

from adarevm.platforms import linux_fs_snapshot
from adarevm.platforms.linux_fs_snapshot import LinuxFSSnapshot, LinuxFSSnapshotException


@pytest.mark.parametrize(
    "cause",
    [subprocess.TimeoutExpired("find", 600), subprocess.SubprocessError("boom"), OSError("no find")],
)
def test_snapshot_error_is_chained_to_its_cause(monkeypatch, cause):
    def fail(*args, **kwargs):
        raise cause

    monkeypatch.setattr(linux_fs_snapshot.subprocess, "run", fail)
    with pytest.raises(LinuxFSSnapshotException) as exc:
        LinuxFSSnapshot.get_snapshot("/tmp")
    assert exc.value.__cause__ is cause


def test_bad_numeric_field_is_chained():
    with pytest.raises(ValueError, match="numeric fields") as exc:
        LinuxFSSnapshot._parse_line("/a|x|1|1|1")
    assert isinstance(exc.value.__cause__, ValueError)
