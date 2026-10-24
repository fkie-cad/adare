"""The record of a VM image: built by `vm create`, kept next to the disk, copied into runs."""

import dataclasses
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import yaml

from adare.backend.vm import image_record
from adare.hypervisor.qemu.vm_creator.os_catalog import SetupLevel, get_os_definition

pytestmark = pytest.mark.unit

OS_BLOCK = {'os': 'Ubuntu', 'platform': 'linux', 'architecture': 'x86_64'}


def test_sidecars_are_named_after_the_disk(tmp_path):
    disk = tmp_path / 'ubuntu2604-20261024.qcow2'

    assert image_record.record_path(disk).name == 'ubuntu2604-20261024.image.yml'
    assert image_record.packages_path(disk).name == 'ubuntu2604-20261024.packages.txt'


def test_record_summarises_the_package_list_next_to_the_disk(tmp_path):
    disk = tmp_path / 'vm.qcow2'
    image_record.write_packages(disk, 'zsh 5.9\n\nbash 5.2\n')

    record = image_record.new_record(disk=disk, sha256='a' * 64, hypervisor='qemu', os_block=OS_BLOCK, build=None)

    assert image_record.packages_path(disk).read_text() == 'bash 5.2\nzsh 5.9\n'
    assert record['packages']['count'] == 2
    assert record['packages']['file'] == 'vm.packages.txt'
    assert record['format'] == 'qcow2'
    assert record['checks'] == [] and record['published'] == []


def test_record_round_trips_through_its_sidecar(tmp_path):
    disk = tmp_path / 'vm.qcow2'
    record = image_record.new_record(disk=disk, sha256='a' * 64, hypervisor='qemu', os_block=OS_BLOCK, build=None)

    image_record.write_record(disk, record)

    assert image_record.read_record(disk) == record
    assert image_record.from_json(image_record.to_json(record)) == record


def test_build_entry_records_how_the_disk_was_made():
    os_def = get_os_definition('ubuntu2604')

    build = image_record.build_entry(
        os_def=os_def, setup_level=SetupLevel.FULL, iso_filename=os_def.iso_filename, iso_sha256=os_def.iso_sha256
    )

    assert build['method'] == 'playbook'
    assert build['profile'] == 'ubuntu2604'
    assert build['setup'] == 'full'
    assert build['iso'] == {'filename': os_def.iso_filename, 'sha256': os_def.iso_sha256}
    assert set(build['adare']) == {'version', 'commit'}


def test_profile_hash_changes_with_the_steps():
    os_def = get_os_definition('ubuntu2604')
    changed = dataclasses.replace(os_def, install_steps=[*os_def.install_steps, {'action': 'wait', 'seconds': 1}])

    assert image_record.profile_sha256(os_def) == image_record.profile_sha256(os_def)
    assert image_record.profile_sha256(changed) != image_record.profile_sha256(os_def)


def _image(tmp_path, build_record=None):
    return {
        'id': 'vm1',
        'name': 'vm',
        'file': str(tmp_path / 'vm.qcow2'),
        'hash': 'a' * 64,
        'hypervisor': 'qemu',
        'build_record': build_record,
        'os': OS_BLOCK,
    }


def test_image_without_a_record_gets_a_minimal_one(tmp_path):
    with patch('adare.backend.vm.database.get_image', return_value=_image(tmp_path)):
        _, record = image_record.record_of('vm')

    assert record['build'] is None
    assert record['sha256'] == 'a' * 64
    assert record['os'] == OS_BLOCK


def test_check_is_appended_to_the_record_and_its_sidecar(tmp_path):
    stored = {}
    with (
        patch('adare.backend.vm.database.get_image', return_value=_image(tmp_path)),
        patch('adare.backend.vm.database.set_vm_build_record', side_effect=lambda _id, j: stored.update(json=j)),
    ):
        image_record.add_check('vm', 'vm test', passed=True)

    (check,) = json.loads(stored['json'])['checks']
    assert check['run'] == 'vm test' and check['result'] == 'pass'
    assert image_record.read_record(tmp_path / 'vm.qcow2')['checks'] == [check]


def test_run_snapshot_names_the_environment_version_and_its_image(tmp_path):
    env = SimpleNamespace(name='ubuntu2604', id='ENV1', sha256hash='f' * 64, vm_hash='a' * 64, vm_id='vm1')
    record = {'sha256': 'a' * 64, 'build': {'profile': 'ubuntu2604'}}
    with (
        patch('adare.database.api.environment.EnvironmentDbApi') as api,
        patch.object(image_record, 'record_of', return_value=({}, record)),
    ):
        api.return_value.__enter__.return_value.get_environment_by_ulid.return_value = env
        image_record.write_run_snapshot(tmp_path / 'image.yml', {None: 'ENV1'})

    (machine,) = yaml.safe_load((tmp_path / 'image.yml').read_text())['machines']
    assert machine['environment'] == {'name': 'ubuntu2604', 'id': 'ENV1', 'file_sha256': 'f' * 64, 'vm_hash': 'a' * 64}
    assert machine['image'] == record


class TestVmCreateImageName:
    """`vm create` never overwrites a registered image."""

    def test_free_name_builds(self):
        from adare.cli import vm_create

        with patch('adare.backend.vm.database.get_image', return_value=None):
            assert vm_create._free_image_name('ubuntu2604-20261024', force=False)

    def test_registered_name_needs_force(self):
        from adare.cli import vm_create

        registered = {'id': 'vm1', 'hash': 'a' * 64}
        with (
            patch('adare.backend.vm.database.get_image', return_value=registered),
            patch.object(vm_create, 'print_error_message') as error,
        ):
            assert not vm_create._free_image_name('ubuntu2604-20261024', force=False)
        assert 'already registered' in error.call_args.kwargs['title']

    def test_force_retires_the_registered_image(self):
        from adare.cli import vm_create

        registered = {'id': 'vm1', 'hash': 'a' * 64}
        with (
            patch('adare.backend.vm.database.get_image', return_value=registered),
            patch('adare.backend.vm.registration.retire_image') as retire,
        ):
            assert vm_create._free_image_name('ubuntu2604-20261024', force=True)
        retire.assert_called_once_with('vm1')


def test_run_records_the_disk_its_environment_version_pinned(tmp_path):
    from adare.backend.experiment import database as experiment_database

    environment = SimpleNamespace(id='ENV1', vm_hash='a' * 64, vm=SimpleNamespace(hash='b' * 64))
    with patch.object(experiment_database, 'ExperimentApi') as api:
        session = api.return_value.__enter__.return_value
        session.get_environment.return_value = environment
        experiment_database.set_experiment_run_base_info('RUN1', 'exp', 'ubuntu2604', tmp_path)

    assert session.set_experiment_run_base_info.call_args.kwargs['vm_hash'] == 'a' * 64


class TestPublishing:
    """A published environment carries its image's record; loading it adopts the record."""

    def _stored(self, tmp_path, build_record=None):
        stored = {}
        patches = (
            patch('adare.backend.vm.database.get_image', return_value=_image(tmp_path, build_record)),
            patch('adare.backend.vm.database.set_vm_build_record', side_effect=lambda _id, j: stored.update(json=j)),
        )
        return stored, patches

    def test_url_is_recorded_once(self, tmp_path):
        stored, (get, put) = self._stored(tmp_path)
        with get, put:
            image_record.add_published('vm', 'https://zenodo.org/x', 'a' * 64)
        with patch('adare.backend.vm.database.get_image', return_value=_image(tmp_path, stored['json'])), put:
            record = image_record.add_published('vm', 'https://zenodo.org/x', 'a' * 64)

        assert record['published'] == [{'url': 'https://zenodo.org/x', 'sha256': 'a' * 64}]

    def test_compressed_copy_is_a_derived_image(self):
        record = {'sha256': 'a' * 64, 'format': 'qcow2', 'checks': [{'run': 'vm test'}], 'build': {'profile': 'p'}}

        derived = image_record.for_published_disk(record, 'c' * 64, 'qcow2')

        assert derived['sha256'] == 'c' * 64
        assert derived['derived_from'] == {'sha256': 'a' * 64, 'by': 'zstd compression'}
        assert derived['checks'] == []  # checks ran on the original bytes
        assert derived['build'] == record['build']
        assert image_record.for_published_disk(record, 'a' * 64, 'qcow2') is record

    def test_loaded_record_is_adopted_for_the_same_bytes(self, tmp_path):
        stored, (get, put) = self._stored(tmp_path)
        with get, put:
            image_record.import_from_environment('vm1', {'sha256': 'a' * 64, 'build': {'profile': 'p'}})

        assert json.loads(stored['json'])['build'] == {'profile': 'p'}

    def test_record_for_other_bytes_is_ignored(self, tmp_path):
        stored, (get, put) = self._stored(tmp_path)
        with get, put:
            image_record.import_from_environment('vm1', {'sha256': 'b' * 64})

        assert stored == {}

    def test_existing_record_is_kept(self, tmp_path):
        stored, (get, put) = self._stored(tmp_path, build_record='{"sha256": "aaa"}')
        with get, put:
            image_record.import_from_environment('vm1', {'sha256': 'a' * 64})

        assert stored == {}

    def test_publish_prepare_embeds_the_registered_images_record(self, tmp_path):
        from adare.services import environment_service

        disk = tmp_path / 'vm.qcow2'
        record = {'sha256': 'a' * 64, 'format': 'qcow2', 'build': {'profile': 'p'}, 'checks': []}
        with (
            patch('adare.helperfunctions.digest_cache.cached_file_sha256', return_value='a' * 64),
            patch.object(image_record, 'add_published', return_value=record) as add,
        ):
            embedded = environment_service._published_image_record(disk, 'https://h/vm.qcow2', 'a' * 64, 'qcow2')

        add.assert_called_once_with('a' * 64, 'https://h/vm.qcow2', 'a' * 64)
        assert embedded is record

    def test_unregistered_disk_embeds_nothing(self, tmp_path):
        from adare.services import environment_service

        with (
            patch('adare.helperfunctions.digest_cache.cached_file_sha256', return_value='a' * 64),
            patch.object(image_record, 'add_published', return_value=None),
        ):
            assert environment_service._published_image_record(tmp_path / 'x.qcow2', 'u', 'a' * 64, None) is None


def test_environment_without_os_takes_it_from_its_image_record():
    import cattrs

    from adare.types.environment import EnvironmentMetadata

    image = {'sha256': 'a' * 64, 'os': {**OS_BLOCK, 'distribution': 'Noble', 'version': '24.04', 'language': 'en'}}
    metadata = cattrs.structure(
        {'vm': 'https://h/vm.qcow2', 'vm_sha256': 'a' * 64, 'image': image}, EnvironmentMetadata
    )

    assert metadata.os.platform == 'linux'
    assert metadata.os.version == '24.04'
