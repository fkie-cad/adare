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


class TestReplacingSharedDisk:
    def _envs(self, *names):
        return [SimpleNamespace(name=name, vm_id='vm1') for name in names]

    def _run(self, env_names, new_hash='b' * 64):
        with (
            patch.object(registration.vm_database, 'get_vm_by_name', return_value=_vm()),
            patch('adare.database.api.environment.EnvironmentDbApi') as api,
        ):
            api.return_value.__enter__.return_value.get_environments.return_value = self._envs(*env_names)
            registration._refuse_replacing_shared_disk('disk', new_hash, 'env')

    def test_own_environment_may_replace_its_disk(self):
        self._run(['env'])

    def test_disk_used_by_another_environment_is_protected(self):
        with pytest.raises(EnvironmentLoadFailed, match='used by other environments \\(other\\)'):
            self._run(['env', 'other'])

    def test_same_bytes_are_not_a_replacement(self):
        self._run(['other'], new_hash='a' * 64)
