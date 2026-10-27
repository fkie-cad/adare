"""Environment versions as seen from experiments, runs, loads and removal."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy.exc import IntegrityError

from adare.backend.environment import commands as env_commands
from adare.backend.environment import database as env_database
from adare.backend.environment.exceptions import EnvironmentAlreadyExists, EnvironmentDeletionError
from adare.backend.experiment import database as experiment_database
from adare.backend.experiment.exceptions import MultipleEnvironmentsError
from adare.backend.vm import registration
from adare.database.api.base import ProjectDatabaseApi
from adare.database.api.environment import EnvironmentDbApi
from adare.database.api.experiment import ExperimentApi
from adare.database.models.global_models import Project, Vm
from adare.database.models.project_models import Experiment, ExperimentRun
from adare.database.reference_manager import reference_manager

pytestmark = pytest.mark.unit

_ENV_YAML = """\
vm: {disk}
vm_type: path
hypervisor: qemu
os:
  os: Ubuntu
  platform: linux
  version: '22.04'
  distribution: Jammy
  language: English
"""


@pytest.fixture
def global_db(tmp_path):
    db_file = tmp_path / 'global.db'
    # reference_manager keeps one global API per process; give it this test's database.
    with (
        patch('adare.config.database.get_global_database_location', return_value=db_file),
        patch.object(reference_manager, '_global_api', None),
        patch.object(reference_manager, '_cache', {}),
        patch.object(reference_manager, '_cache_timestamps', {}),
    ):
        yield db_file


@pytest.fixture
def managed_dirs(tmp_path):
    environments_dir = tmp_path / 'environments'
    environments_dir.mkdir()
    with patch.object(env_commands, 'ENVIRONMENTS_DIR', environments_dir):
        yield environments_dir


def _add_vm(name='disk', file_hash='a' * 64) -> str:
    with EnvironmentDbApi() as db:
        vm = Vm(name=name, file=f'/disks/{name}.qcow2', hash=file_hash, hypervisor='qemu')
        db._session.add(vm)
        db._session.commit()
        return vm.id


def _new_version(name: str, sha: str, vm_id=None, vm_hash=None, file: Path | None = None) -> str:
    with EnvironmentDbApi() as db:
        env = db.create_environment_version(
            name=name,
            description='',
            vm_id=vm_id,
            vm_hash=vm_hash,
            tags=[],
            installations=[],
            environment_file=file or Path(f'/envs/{name}_{sha[:8]}.yml'),
            sha256hash=sha,
            hypervisor='qemu',
        )
        return env.id


@pytest.fixture
def project(tmp_path, global_db):
    project_path = tmp_path / 'project'
    project_path.mkdir()
    with EnvironmentDbApi() as db:
        db._session.add(Project(name='project', path=str(project_path)))
        db._session.commit()
    return project_path


def _add_experiment(project_path: Path, environment_ids: list[str]) -> str:
    with ProjectDatabaseApi(project_path) as api:
        experiment = Experiment(name='exp', sha256='0' * 64, environment_ids=environment_ids)
        api._session.add(experiment)
        api._session.commit()
        return experiment.id


def _environment_ids(project_path: Path) -> list[str]:
    with ProjectDatabaseApi(project_path) as api:
        return list(api._session.query(Experiment).one().environment_ids or [])


class TestExperimentEnvironmentIndicator:
    def test_new_version_replaces_the_old_one(self, project):
        first = _new_version('ubuntu', '1' * 64)
        second = _new_version('ubuntu', '2' * 64)
        other = _new_version('debian', '3' * 64)
        experiment_id = _add_experiment(project, [other, first])

        with ExperimentApi(project) as api:
            assert api.add_experiment_environment(experiment_id, second)

        assert _environment_ids(project) == [other, second]

    def test_older_version_does_not_replace_a_newer_one(self, project):
        first = _new_version('ubuntu', '1' * 64)
        second = _new_version('ubuntu', '2' * 64)
        experiment_id = _add_experiment(project, [second])

        with ExperimentApi(project) as api:
            assert not api.add_experiment_environment(experiment_id, first)

        assert _environment_ids(project) == [second]

    def test_run_without_e_after_a_forced_reload_resolves_the_name(self, project):
        # Experiments registered before the fix already hold two versions of one name.
        first = _new_version('ubuntu', '1' * 64)
        second = _new_version('ubuntu', '2' * 64)
        _add_experiment(project, [first, second])

        assert experiment_database.get_experiment_environment_name(project, 'exp') == 'ubuntu'

    def test_two_different_environments_still_need_e(self, project):
        _add_experiment(project, [_new_version('ubuntu', '1' * 64), _new_version('debian', '2' * 64)])

        with pytest.raises(MultipleEnvironmentsError):
            experiment_database.get_experiment_environment_name(project, 'exp')

    def test_run_of_a_version_without_vm_hash_records_its_vms_disk(self, project):
        # Versions loaded by code predating environment.vm_hash hold NULL there.
        _new_version('ubuntu', '1' * 64, vm_id=_add_vm(file_hash='b' * 64))
        _add_experiment(project, [])
        run_id = experiment_database.initialize_experiment_run(project)

        experiment_database.set_experiment_run_base_info(run_id, 'exp', 'ubuntu', project)

        with ProjectDatabaseApi(project) as api:
            assert api._session.get(ExperimentRun, run_id).vm_hash == 'b' * 64


class TestRunEnvironment:
    def test_reads_the_current_version_and_its_vm_in_one_go(self, global_db):
        vm_id = _add_vm()
        _new_version('ubuntu', '1' * 64, vm_id=vm_id)
        current = _new_version('ubuntu', '2' * 64, vm_id=vm_id)

        environment = env_database.get_run_environment('ubuntu')

        assert environment['ulid'] == current
        assert environment['file'] == Path(f'/envs/ubuntu_{"2" * 8}.yml')
        assert environment['vm_file'] == Path('/disks/disk.qcow2')
        assert environment['hypervisor'] == 'qemu'


class TestManagedCopyName:
    def test_strips_only_one_hash_suffix_from_an_unregistered_copy(self, global_db, managed_dirs):
        copy = managed_dirs / 'win_20261023_1a2b3c4d.yml'
        copy.write_text('')

        assert env_commands._environment_name_for(copy) == 'win_20261023'

    def test_a_registered_copy_loads_under_its_registered_name(self, global_db, managed_dirs):
        copy = managed_dirs / 'lab_deadbeef_1a2b3c4d.yml'
        copy.write_text('')
        _new_version('lab_deadbeef', '1' * 64, file=copy)

        assert env_commands._environment_name_for(copy) == 'lab_deadbeef'


class TestEnvironmentLoadFailures:
    @pytest.fixture
    def env_file(self, tmp_path):
        disk = tmp_path / 'disk.qcow2'
        disk.write_bytes(b'disk')
        env_file = tmp_path / 'ubuntu.yml'
        env_file.write_text(_ENV_YAML.format(disk=disk))
        return env_file

    @pytest.fixture(autouse=True)
    def _no_side_effects(self, global_db, managed_dirs):
        with (
            patch.object(env_commands, 'environment_sync'),
            patch('adare.helperfunctions.integrity.protect_loaded_files', return_value=[]),
        ):
            yield

    def test_concurrent_load_is_reported_and_its_leftovers_removed(self, env_file, managed_dirs):
        created_vm = _add_vm(name='new-disk')

        def lose_the_race(*args, **kwargs):
            _new_version('ubuntu', '9' * 64)  # another process registered the name first
            raise IntegrityError('insert', {}, Exception())

        with (
            patch(
                'adare.backend.vm.registration.load_vm_file_for_environment',
                return_value={'vm_id': created_vm, 'was_existing': False},
            ),
            patch.object(env_database, 'register_environment_version', side_effect=lose_the_race),
            pytest.raises(EnvironmentAlreadyExists, match='concurrently'),
        ):
            env_commands.environment_load(str(env_file))

        assert list(managed_dirs.iterdir()) == []
        with EnvironmentDbApi() as db:
            assert db._session.get(Vm, created_vm) is None

    def test_force_on_an_unchanged_file_and_disk_adds_no_version(self, env_file):
        vm_id = _add_vm()
        with patch(
            'adare.backend.vm.registration.load_vm_file_for_environment',
            return_value={'vm_id': vm_id, 'was_existing': True},
        ):
            first, _ = env_commands.environment_load(str(env_file))
            again, created = env_commands.environment_load(str(env_file), force=True)

        assert (again, created) == (first, False)
        with EnvironmentDbApi() as db:
            assert len(db.get_environment_versions('ubuntu')) == 1


class TestVmRegistration:
    def _load(self, tmp_path, force):
        disk = tmp_path / 'disk.qcow2'
        disk.write_bytes(b'new bytes')
        existing = SimpleNamespace(id='VM1', name='disk', hash='old')
        created = SimpleNamespace(id='VM2', name='disk', hash='new')
        metadata = SimpleNamespace(
            name='ubuntu',
            hypervisor='qemu',
            os=SimpleNamespace(
                platform='linux', os='Ubuntu', distribution='', version='', language='', architecture='x86_64'
            ),
        )
        with (
            patch('adare.helperfunctions.digest_cache.cached_file_sha256', return_value='new'),
            patch.object(registration.vm_database, 'get_vm_by_hash', return_value=None),
            patch.object(registration.vm_database, 'get_image', return_value=vars(existing)),
            patch.object(registration.vm_database, 'create_vm', return_value=created),
            patch.object(registration, 'retire_image') as retire,
        ):
            result = registration.load_vm_file_for_environment(None, disk, metadata, force=force)
        return result, retire

    def test_new_bytes_under_a_registered_name_are_a_new_image(self, tmp_path):
        """--force retires the old image (kept for its versions) instead of overwriting it."""
        result, retire = self._load(tmp_path, force=True)

        retire.assert_called_once_with('VM1', replacing=tmp_path / 'disk.qcow2')
        assert result == {'vm_id': 'VM2', 'was_existing': False}

    def test_without_force_the_registered_image_is_left_alone(self, tmp_path):
        _, retire = self._load(tmp_path, force=False)

        retire.assert_not_called()


class TestEnvironmentRemove:
    def test_refuses_when_a_project_cannot_be_checked(self, global_db, tmp_path):
        current = _new_version('ubuntu', '1' * 64)
        with EnvironmentDbApi() as db:
            db._session.add(Project(name='gone', path=str(tmp_path / 'unmounted')))
            db._session.commit()

        with pytest.raises(EnvironmentDeletionError, match='could not be checked'):
            env_database.delete_environment(current, cleanup_vm=False)

        assert env_database.resolve_environment_identifier('ubuntu') == current

    def test_force_deletes_runs_and_detaches_in_one_pass(self, project):
        current = _new_version('ubuntu', '1' * 64)
        _add_experiment(project, [current])
        with ProjectDatabaseApi(project) as api:
            api._session.add(ExperimentRun(environment_id=current))
            api._session.commit()

        env_database.delete_environment(current, force=True, cleanup_vm=False)

        assert _environment_ids(project) == []
        with ProjectDatabaseApi(project) as api:
            assert api._session.query(ExperimentRun).count() == 0

    def test_deletes_only_the_versions_it_checked(self, global_db):
        current = _new_version('ubuntu', '1' * 64)

        def load_meanwhile(version_ids, detach):
            _new_version('ubuntu', '2' * 64)
            return {}, [], []

        with patch.object(env_database, '_scan_environment_references', side_effect=load_meanwhile):
            env_database.delete_environment(current, cleanup_vm=False)

        with EnvironmentDbApi() as db:
            assert [v.sha256hash for v in db.get_environment_versions('ubuntu')] == ['2' * 64]

    def test_vm_reference_check_includes_superseded_versions(self, global_db):
        vm_id = _add_vm()
        _new_version('ubuntu', '1' * 64, vm_id=vm_id)
        _new_version('ubuntu', '2' * 64)

        with EnvironmentDbApi() as db:
            assert db.is_vm_referenced(vm_id)
            assert not db.is_vm_referenced('nope')
