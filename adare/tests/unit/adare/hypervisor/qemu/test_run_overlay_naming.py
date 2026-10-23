"""Run overlays on a shared template are named after the run, so runs cannot touch each other's."""

import asyncio
from types import SimpleNamespace

import pytest

from adare.hypervisor.qemu.mixins import disk as disk_mixin
from adare.hypervisor.qemu.mixins.disk import DiskManagementMixin

pytestmark = pytest.mark.unit


class _RunVM(DiskManagementMixin):
    def __init__(self, vm_name, template):
        self.vm_name = vm_name
        self._external_disk_path = str(template)
        self.config = SimpleNamespace(disk_path=str(template))


@pytest.fixture
def layout(tmp_path, monkeypatch):
    user_dir = tmp_path / 'user'
    user_dir.mkdir()
    template = user_dir / 'ubuntu.qcow2'
    template.write_bytes(b'template')
    disks = tmp_path / 'disks'
    disks.mkdir()
    monkeypatch.setattr(disk_mixin, 'get_qemu_disk_dir', lambda: disks)
    return template, disks


def test_overlay_lives_in_managed_storage_named_after_the_run(layout):
    template, disks = layout
    vm = _RunVM('ubuntu_run_AAAAAAAA', template)

    overlay = vm.get_overlay_disk_path('01RUN')

    assert overlay == str(disks / 'ubuntu_run_AAAAAAAA-overlay-01RUN.qcow2')
    assert not overlay.startswith(str(template.parent))


def test_orphan_sweep_never_reaches_a_concurrent_runs_overlay(layout):
    template, disks = layout
    other_run = disks / 'ubuntu_run_BBBBBBBB-overlay-01OTHER.qcow2'
    other_run.write_bytes(b'')
    stale_retry = disks / 'ubuntu_run_AAAAAAAA-overlay-01OLD.qcow2'
    stale_retry.write_bytes(b'')

    asyncio.run(_RunVM('ubuntu_run_AAAAAAAA', template)._cleanup_orphaned_overlays('01RUN'))

    assert other_run.exists()
    assert not stale_retry.exists()
    assert template.exists()
