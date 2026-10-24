"""A Vm row is shared by every environment on the same disk; loads must not let them disagree."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from adare.backend.environment.exceptions import EnvironmentLoadFailed
from adare.backend.vm import registration

pytestmark = pytest.mark.unit


def _vm(hypervisor='qemu', platform='linux', architecture='x86_64'):
    return SimpleNamespace(
        id='vm1',
        name='disk',
        hash='a' * 64,
        hypervisor=hypervisor,
        osinfo=SimpleNamespace(platform=platform, architecture=architecture),
    )


def _metadata(platform='linux', architecture='x86_64'):
    return SimpleNamespace(name='env', os=SimpleNamespace(platform=platform, architecture=architecture))


class TestReusedVmConsistency:
    def test_matching_settings_reuse_the_vm(self):
        registration._check_reused_vm_consistency(_vm(), _metadata(), 'qemu')

    def test_different_hypervisor_is_refused(self):
        with pytest.raises(EnvironmentLoadFailed, match="hypervisor: registered 'qemu'"):
            registration._check_reused_vm_consistency(_vm(), _metadata(), 'virtualbox')

    def test_different_guest_platform_is_refused(self):
        with pytest.raises(EnvironmentLoadFailed, match='os.platform'):
            registration._check_reused_vm_consistency(_vm(), _metadata(platform='windows'), 'qemu')


class TestRetireImage:
    """Images never change: a replaced image is kept, renamed, for the versions using it."""

    def _retire(self, tmp_path, referenced=True, live=(), managed=True, replacing=None):
        disk = tmp_path / 'disk.qcow2'
        disk.write_bytes(b'old')
        (tmp_path / 'disk.image.yml').write_text('record_version: 1\n')
        (tmp_path / 'disk.packages.txt').write_text('bash 5.2\n')
        image = {'id': 'vm1', 'name': 'disk', 'hash': 'a' * 64, 'file': str(disk)}
        with (
            patch('adare.database.api.environment.EnvironmentDbApi') as api,
            patch('adare.backend.vm.removal.teardown_unreferenced_vm') as teardown,
            patch(
                'adare.backend.vm.removal.plan_vm_removal',
                return_value=SimpleNamespace(vm_name='disk', live_instances=list(live)),
            ),
            patch('adare.backend.vm.removal._is_managed', return_value=managed),
            patch.object(registration.vm_database, 'get_image', return_value=image),
            patch.object(registration.vm_database, 'set_vm_file') as set_file,
            patch.object(registration.vm_database, 'rename_vm') as rename,
        ):
            api.return_value.__enter__.return_value.is_vm_referenced.return_value = referenced
            registration.retire_image('vm1', replacing=replacing)
        return teardown, set_file, rename

    def test_unreferenced_image_is_removed(self, tmp_path):
        teardown, _, rename = self._retire(tmp_path, referenced=False)

        teardown.assert_called_once_with('vm1')
        rename.assert_not_called()

    def test_referenced_image_is_kept_under_its_hash(self, tmp_path):
        _, set_file, rename = self._retire(tmp_path)

        retired = 'disk-' + 'a' * 12
        rename.assert_called_once_with('vm1', retired)
        set_file.assert_called_once_with('vm1', str(tmp_path / f'{retired}.qcow2'))
        assert sorted(p.name for p in tmp_path.iterdir()) == [
            f'{retired}.image.yml',
            f'{retired}.packages.txt',
            f'{retired}.qcow2',
        ]

    def test_disk_overwritten_in_place_marks_the_old_image_lost(self, tmp_path):
        """The new bytes stay where they are; the old image's versions can no longer run."""
        _, set_file, rename = self._retire(tmp_path, replacing=tmp_path / 'disk.qcow2')

        rename.assert_called_once_with('vm1', 'disk-' + 'a' * 12)
        set_file.assert_called_once_with('vm1', f"{tmp_path / 'disk.qcow2'}.replaced-{'a' * 12}")
        assert (tmp_path / 'disk.qcow2').read_bytes() == b'old'  # not moved
        # the old image's record and package list go with it
        assert (tmp_path / f"disk-{'a' * 12}.image.yml").exists()
        assert not (tmp_path / 'disk.image.yml').exists()

    def test_external_disk_keeps_its_path(self, tmp_path):
        _, set_file, rename = self._retire(tmp_path, managed=False)

        rename.assert_called_once()
        set_file.assert_not_called()

    def test_running_image_is_not_replaced(self, tmp_path):
        from adare.backend.vm.exceptions import VMRemovalError

        with pytest.raises(VMRemovalError, match='running'):
            self._retire(tmp_path, live=['adare_run_1'])
