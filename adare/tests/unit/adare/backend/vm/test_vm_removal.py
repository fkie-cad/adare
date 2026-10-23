"""Removing a registered VM (with its environments) and resolving what a name refers to."""

import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from adare.backend.environment import database as env_database
from adare.backend.vm import removal
from adare.backend.vm.exceptions import AmbiguousVmTargetError, VMInUseByEnvironmentError, VMRemovalError
from adare.backend.vm.resolve import VmTarget, resolve_vm_target
from adare.config import configdirectory
from adare.database.api.base import ProjectDatabaseApi
from adare.database.api.environment import EnvironmentDbApi
from adare.database.api.vm import VmApi
from adare.database.api.vm.exceptions import VMNotFoundError
from adare.database.models.global_models import Project, Vm, VmInstance
from adare.database.models.project_models import Experiment, ExperimentRun
from adare.database.reference_manager import reference_manager

pytestmark = pytest.mark.unit

DEAD_PID = 2**22 + 12345  # above the default pid_max: never a live process


@pytest.fixture
def global_db(tmp_path):
    with (
        patch('adare.config.database.get_global_database_location', return_value=tmp_path / 'global.db'),
        patch.object(reference_manager, '_global_api', None),
        patch.object(reference_manager, '_cache', {}),
        patch.object(reference_manager, '_cache_timestamps', {}),
    ):
        yield


@pytest.fixture
def vms_dir(tmp_path, global_db):
    managed = tmp_path / 'vms'
    managed.mkdir()
    with patch.object(configdirectory, 'VMS_DIR', managed):
        yield managed


@pytest.fixture
def hypervisor():
    """No real hypervisor: instances are stopped, and delete_vm drops the row like the real one."""

    async def delete_vm(vm_id, force=False):
        with VmApi() as api:
            return api.delete_vm(vm_id)

    with (
        patch('adare.backend.vm.instance_manager.get_instance_hypervisor_state', return_value='not_found'),
        patch('adare.backend.vm.commands.delete_vm', side_effect=delete_vm) as fake_delete,
    ):
        yield fake_delete


def _add_vm(name: str, disk: Path) -> str:
    with VmApi() as api:
        vm = Vm(name=name, file=str(disk), hash=name.ljust(64, '0'), hypervisor='qemu')
        api._session.add(vm)
        api._session.commit()
        return vm.id


def _add_instance(vm_id: str, name: str, owner_pid=None) -> str:
    with VmApi() as api:
        instance = VmInstance(vm_id=vm_id, instance_name=name, status='active', owner_pid=owner_pid)
        api._session.add(instance)
        api._session.commit()
        return instance.id


def _add_env(name: str, sha: str, vm_id: str | None) -> str:
    with EnvironmentDbApi() as db:
        return db.create_environment_version(
            name=name,
            description='',
            vm_id=vm_id,
            vm_hash=None,
            tags=[],
            installations=[],
            environment_file=Path(f'/envs/{name}_{sha[:8]}.yml'),
            sha256hash=sha * 64,
            hypervisor='qemu',
        ).id


def _add_project_run(tmp_path: Path, environment_id: str) -> Path:
    project_path = tmp_path / 'project'
    project_path.mkdir(exist_ok=True)
    with EnvironmentDbApi() as db:
        db._session.add(Project(name='project', path=str(project_path)))
        db._session.commit()
    with ProjectDatabaseApi(project_path) as api:
        api._session.add(Experiment(name='exp', sha256='0' * 64, environment_ids=[environment_id]))
        api._session.add(ExperimentRun(environment_id=environment_id))
        api._session.commit()
    return project_path


def _vm_exists(vm_id: str) -> bool:
    with VmApi() as api:
        return api.get_vm_by_id(vm_id) is not None


def _env_names() -> list[str]:
    with EnvironmentDbApi() as db:
        return sorted({env.name for env in db.get_environments()})


class TestResolveVmTarget:
    def test_registered_vm_by_name_and_by_id(self, global_db, tmp_path):
        vm_id = _add_vm('ubuntu', tmp_path / 'u.qcow2')

        assert resolve_vm_target('ubuntu') == VmTarget('vm', vm_id, 'ubuntu')
        assert resolve_vm_target(vm_id) == VmTarget('vm', vm_id, 'ubuntu')

    def test_instance_by_name(self, global_db, tmp_path):
        instance_id = _add_instance(_add_vm('ubuntu', tmp_path / 'u.qcow2'), 'ubuntu_run_12345678')

        assert resolve_vm_target('ubuntu_run_12345678') == VmTarget('instance', instance_id, 'ubuntu_run_12345678')

    def test_unknown_name_suggests_similar_vms(self, global_db, tmp_path):
        _add_vm('ubuntu2404-20261023', tmp_path / 'u.qcow2')

        with pytest.raises(VMNotFoundError) as excinfo:
            resolve_vm_target('ubuntu2404')

        assert 'ubuntu2404-20261023' in excinfo.value.possible_solutions[0]

    def test_a_name_shared_by_a_vm_and_an_instance_is_ambiguous(self, global_db, tmp_path):
        _add_instance(_add_vm('ubuntu', tmp_path / 'u.qcow2'), 'ubuntu')

        with pytest.raises(AmbiguousVmTargetError):
            resolve_vm_target('ubuntu')


class TestRemoveVm:
    def test_removes_the_environment_every_version_and_the_managed_disk(self, vms_dir, hypervisor):
        disk = vms_dir / 'ubuntu.qcow2'
        disk.write_bytes(b'disk')
        vm_id = _add_vm('ubuntu', disk)
        _add_env('ubuntu', '1', vm_id)
        _add_env('ubuntu', '2', vm_id)
        _add_env('debian', '3', None)

        outcome = removal.remove_vm(vm_id)

        assert outcome.environments == ['ubuntu']
        assert outcome.disk_deleted and not disk.exists()
        assert not _vm_exists(vm_id)
        assert _env_names() == ['debian']

    def test_keeps_a_disk_outside_managed_storage(self, vms_dir, hypervisor, tmp_path):
        disk = tmp_path / 'external.qcow2'
        disk.write_bytes(b'disk')
        vm_id = _add_vm('external', disk)

        plan = removal.plan_vm_removal(vm_id)
        outcome = removal.remove_vm(vm_id)

        assert not plan.disk_managed
        assert not outcome.disk_deleted and disk.exists()
        assert not _vm_exists(vm_id)

    def test_without_cascade_a_vm_environments_use_is_refused(self, vms_dir, hypervisor):
        vm_id = _add_vm('ubuntu', vms_dir / 'u.qcow2')
        _add_env('ubuntu', '1', vm_id)

        with pytest.raises(VMInUseByEnvironmentError, match='ubuntu'):
            removal.remove_vm(vm_id, force=True, cascade=False)

        assert _vm_exists(vm_id)
        assert _env_names() == ['ubuntu']

    def test_never_takes_along_a_vm_another_version_runs_on(self, vms_dir, hypervisor):
        old_vm = _add_vm('ubuntu-old', vms_dir / 'old.qcow2')
        new_vm = _add_vm('ubuntu-new', vms_dir / 'new.qcow2')
        _add_env('ubuntu', '1', old_vm)
        _add_env('ubuntu', '2', new_vm)

        with pytest.raises(VMRemovalError, match='ubuntu-new'):
            removal.remove_vm(old_vm, force=True)

        assert _vm_exists(old_vm) and _vm_exists(new_vm)
        assert _env_names() == ['ubuntu']

    def test_refuses_runs_before_deleting_anything(self, vms_dir, hypervisor, tmp_path):
        vm_id = _add_vm('ubuntu', vms_dir / 'u.qcow2')
        _add_env('alpha', '1', vm_id)  # deleted first if nothing were checked up front
        _add_project_run(tmp_path, _add_env('beta', '2', vm_id))

        with pytest.raises(VMRemovalError, match='use no other environment'):
            removal.remove_vm(vm_id)

        assert _env_names() == ['alpha', 'beta']
        assert _vm_exists(vm_id)

    def test_force_deletes_the_runs_and_detaches_the_experiments(self, vms_dir, hypervisor, tmp_path):
        vm_id = _add_vm('ubuntu', vms_dir / 'u.qcow2')
        project = _add_project_run(tmp_path, _add_env('ubuntu', '1', vm_id))

        plan = removal.plan_vm_removal(vm_id)
        removal.remove_vm(vm_id, force=True)

        assert plan.run_count == 1
        assert not _vm_exists(vm_id)
        with ProjectDatabaseApi(project) as api:
            assert api._session.query(ExperimentRun).count() == 0
            assert api._session.query(Experiment).one().environment_ids == []

    def test_refuses_while_an_instance_is_live_even_with_force(self, vms_dir, hypervisor):
        vm_id = _add_vm('ubuntu', vms_dir / 'u.qcow2')
        _add_instance(vm_id, 'ubuntu_run_live', owner_pid=os.getpid())

        with pytest.raises(VMRemovalError, match='ubuntu_run_live'):
            removal.remove_vm(vm_id, force=True)

        assert _vm_exists(vm_id)

    def test_a_crashed_runs_instance_is_not_live(self, vms_dir, hypervisor):
        vm_id = _add_vm('ubuntu', vms_dir / 'u.qcow2')
        _add_instance(vm_id, 'ubuntu_run_dead', owner_pid=DEAD_PID)

        plan = removal.plan_vm_removal(vm_id)

        assert plan.live_instances == [] and plan.stopped_instances == ['ubuntu_run_dead']
        removal.remove_vm(vm_id)
        assert not _vm_exists(vm_id)

    def test_finds_vms_no_environment_uses(self, vms_dir):
        used = _add_vm('used', vms_dir / 'used.qcow2')
        unused = _add_vm('unused', vms_dir / 'unused.qcow2')
        _add_env('env', '1', used)

        assert removal.find_unreferenced_vms() == [('unused', unused)]


class TestEnvironmentRemoveTearsDownTheVm:
    def test_env_remove_deletes_the_vm_and_its_managed_disk(self, vms_dir, hypervisor):
        disk = vms_dir / 'u.qcow2'
        disk.write_bytes(b'disk')
        vm_id = _add_vm('ubuntu', disk)
        env_id = _add_env('ubuntu', '1', vm_id)

        env_database.delete_environment(env_id)

        assert not _vm_exists(vm_id) and not disk.exists()


class TestDeleteVmForwardsForce:
    @pytest.mark.parametrize('force', [False, True])
    def test_instance_cleanup_gets_force(self, vms_dir, force):
        from adare.backend.vm import commands as vm_commands
        from adare.backend.vm.database import run_blocking

        vm_id = _add_vm('ubuntu', vms_dir / 'u.qcow2')
        instance_id = _add_instance(vm_id, 'ubuntu_run_1')

        with (
            patch('adare.backend.vm.instance_manager.cleanup_vm_instance', new_callable=AsyncMock) as cleanup,
            patch('adare.hypervisor.qemu.run_resources.remove_vm_templates'),
        ):
            run_blocking(vm_commands.delete_vm(vm_id, force=force))

        cleanup.assert_awaited_once_with(instance_id, force=force)
