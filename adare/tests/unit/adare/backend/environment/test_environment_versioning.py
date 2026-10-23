"""Environment versions: reloading a changed file keeps the old version and its runs."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import sqlalchemy
from sqlalchemy.exc import IntegrityError

from adare.backend.environment import commands as env_commands
from adare.backend.environment import database as env_database
from adare.backend.environment.exceptions import EnvironmentAlreadyExists, EnvironmentDeletionError
from adare.database.api.environment import EnvironmentDbApi
from adare.database.migrations import add_environment_versioning
from adare.database.models.global_models import Environment, Vm

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
    """Point the global database at a fresh file for this test."""
    db_file = tmp_path / 'global.db'
    with patch('adare.config.database.get_global_database_location', return_value=db_file):
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


def _new_version(name: str, sha: str, vm_id=None) -> str:
    with EnvironmentDbApi() as db:
        env = db.create_environment_version(
            name=name,
            description='',
            vm_id=vm_id,
            vm_hash=None,
            tags=[],
            installations=[],
            environment_file=Path(f'/envs/{name}_{sha[:8]}.yml'),
            sha256hash=sha,
            hypervisor='qemu',
        )
        return env.id


class TestEnvironmentVersions:
    def test_new_version_supersedes_the_current_one(self, global_db):
        first = _new_version('ubuntu', '1' * 64)
        second = _new_version('ubuntu', '2' * 64)

        with EnvironmentDbApi() as db:
            assert db.get_current_environment('ubuntu').id == second
            versions = db.get_environment_versions('ubuntu')
            assert [v.id for v in versions] == [first, second]
            assert versions[0].superseded_at is not None
            assert versions[1].is_current

    def test_superseded_versions_are_hidden_from_name_lookups_and_listings(self, global_db):
        _new_version('ubuntu', '1' * 64)
        current = _new_version('ubuntu', '2' * 64)

        assert env_database.resolve_environment_identifier('ubuntu') == current
        with EnvironmentDbApi() as db:
            assert [env.id for env in db.get_environments()] == [current]
            assert len(db.get_environments(include_superseded=True)) == 2

    def test_old_version_still_resolves_by_ulid(self, global_db):
        first = _new_version('ubuntu', '1' * 64)
        _new_version('ubuntu', '2' * 64)

        assert env_database.resolve_environment_identifier(first) == first

    def test_database_allows_only_one_current_version_per_name(self, global_db):
        _new_version('ubuntu', '1' * 64)
        with EnvironmentDbApi() as db:
            db._session.add(Environment(name='ubuntu', sha256hash='3' * 64, hypervisor='qemu'))
            with pytest.raises(IntegrityError):
                db._session.commit()

    def test_registered_version_pins_the_disk_hash(self, global_db):
        vm_id = _add_vm(file_hash='f' * 64)
        metadata = SimpleNamespace(name='ubuntu', description='', tags=[], postsetupinstallations=[], hypervisor='qemu')

        env_id = env_database.register_environment_version(metadata, Path('/envs/ubuntu.yml'), '1' * 64, vm_id)

        with EnvironmentDbApi() as db:
            assert db.get_environment_by_ulid(env_id).vm_hash == 'f' * 64


class TestEnvironmentLoad:
    @pytest.fixture
    def env_file(self, tmp_path):
        disk = tmp_path / 'disk.qcow2'
        disk.write_bytes(b'disk')
        env_file = tmp_path / 'ubuntu.yml'
        env_file.write_text(_ENV_YAML.format(disk=disk))
        return env_file

    @pytest.fixture(autouse=True)
    def _no_vm_processing(self, global_db, managed_dirs):
        vm_id = _add_vm()
        with (
            patch(
                'adare.backend.vm.registration.load_vm_file_for_environment',
                return_value={'vm_id': vm_id, 'was_existing': True},
            ),
            patch.object(env_commands, 'environment_sync'),
            patch('adare.helperfunctions.integrity.protect_loaded_files', return_value=[]),
        ):
            yield

    def test_reloading_an_identical_file_is_a_no_op(self, env_file):
        first, created = env_commands.environment_load(str(env_file))
        again, created_again = env_commands.environment_load(str(env_file))

        assert created and not created_again
        assert again == first

    def test_changed_file_without_force_is_refused(self, env_file):
        env_commands.environment_load(str(env_file))
        env_file.write_text(env_file.read_text() + "description: changed\n")

        with pytest.raises(EnvironmentAlreadyExists):
            env_commands.environment_load(str(env_file))

    def test_force_adds_a_version_and_never_deletes_runs(self, env_file):
        first, _ = env_commands.environment_load(str(env_file))
        env_file.write_text(env_file.read_text() + "description: changed\n")

        with patch.object(env_database, 'delete_environment') as delete:
            second, created = env_commands.environment_load(str(env_file), force=True)

        delete.assert_not_called()
        assert created and second != first
        assert env_database.resolve_environment_identifier(first) == first
        assert env_database.resolve_environment_identifier('ubuntu') == second

    def test_loading_the_managed_copy_keeps_the_original_name(self, env_file, managed_dirs):
        env_id, _ = env_commands.environment_load(str(env_file))
        with EnvironmentDbApi() as db:
            managed_copy = Path(db.get_environment_by_ulid(env_id).file)
        assert managed_copy.parent == managed_dirs and managed_copy.stem != 'ubuntu'

        again, created = env_commands.environment_load(str(managed_copy))

        assert (again, created) == (env_id, False)

    def test_local_disk_must_match_declared_vm_sha256(self, env_file):
        env_file.write_text(env_file.read_text() + f"vm_sha256: {'0' * 64}\n")

        with pytest.raises(env_commands.EnvironmentLoadFailed, match='integrity check failed'):
            env_commands.environment_load(str(env_file))

    def test_disk_environment_without_os_block_is_refused(self, tmp_path):
        env_file = tmp_path / 'no-os.yml'
        env_file.write_text("vm: /disks/disk.qcow2\nhypervisor: qemu\n")

        with pytest.raises(env_commands.EnvironmentLoadFailed, match='"os" block'):
            env_commands.environment_load(str(env_file))

    def test_vagrant_only_environment_is_refused(self, tmp_path):
        env_file = tmp_path / 'vagrant.yml'
        env_file.write_text("vagrantbox: owner/box\n")

        with pytest.raises(env_commands.EnvironmentLoadFailed, match='no longer supported'):
            env_commands.environment_load(str(env_file))


class TestEnvironmentDelete:
    def test_deletes_every_version_of_the_name(self, global_db):
        _new_version('ubuntu', '1' * 64)
        current = _new_version('ubuntu', '2' * 64)

        with patch.object(env_database, '_find_environment_references', return_value=({}, [])):
            env_database.delete_environment(current, cleanup_vm=False)

        with EnvironmentDbApi() as db:
            assert db.get_environment_versions('ubuntu') == []

    def test_refuses_while_an_old_version_has_runs(self, global_db):
        first = _new_version('ubuntu', '1' * 64)
        current = _new_version('ubuntu', '2' * 64)

        def references(version_ids):
            assert first in version_ids
            return {Path('/project'): 3}, []

        with (
            patch.object(env_database, '_find_environment_references', side_effect=references),
            pytest.raises(EnvironmentDeletionError, match='3 experiment run'),
        ):
            env_database.delete_environment(current, cleanup_vm=False)


class TestVersioningMigration:
    def test_upgrades_an_old_schema_and_backfills_vm_hash(self):
        engine = sqlalchemy.create_engine('sqlite://')
        with engine.begin() as conn:
            conn.execute(sqlalchemy.text("CREATE TABLE vm (id CHAR(26) PRIMARY KEY, hash VARCHAR)"))
            conn.execute(
                sqlalchemy.text(
                    "CREATE TABLE environment (id CHAR(26) PRIMARY KEY, name VARCHAR NOT NULL, vm_id CHAR(26))"
                )
            )
            conn.execute(sqlalchemy.text("CREATE UNIQUE INDEX ix_environment_name ON environment (name)"))
            conn.execute(sqlalchemy.text("INSERT INTO vm VALUES ('v1', 'abc')"))
            conn.execute(sqlalchemy.text("INSERT INTO environment VALUES ('e1', 'ubuntu', 'v1')"))

            add_environment_versioning.upgrade(conn)
            add_environment_versioning.upgrade(conn)  # idempotent

            columns = {row[1] for row in conn.execute(sqlalchemy.text("PRAGMA table_info(environment)"))}
            indexes = {row[1]: bool(row[2]) for row in conn.execute(sqlalchemy.text("PRAGMA index_list(environment)"))}
            vm_hash = conn.execute(sqlalchemy.text("SELECT vm_hash FROM environment")).scalar()

            # A superseded row may now share the name; a second current row may not.
            conn.execute(
                sqlalchemy.text(
                    "INSERT INTO environment (id, name, superseded_at) VALUES ('e0', 'ubuntu', '2026-01-01')"
                )
            )
            with pytest.raises(IntegrityError):
                conn.execute(sqlalchemy.text("INSERT INTO environment (id, name) VALUES ('e2', 'ubuntu')"))

        assert {'superseded_at', 'vm_hash'} <= columns
        assert indexes['ix_environment_name'] is False
        assert indexes['idx_environment_current_name'] is True
        assert vm_hash == 'abc'


class TestDiskPin:
    def test_run_is_refused_when_the_shared_disk_was_replaced(self, global_db):
        vm_id = _add_vm(file_hash='a' * 64)
        env_id = _new_version('ubuntu', '1' * 64, vm_id=vm_id)
        with EnvironmentDbApi() as db:
            db.get_environment_by_ulid(env_id).vm_hash = 'a' * 64
            db._session.query(Vm).filter_by(id=vm_id).one().hash = 'b' * 64
            db._session.commit()

        with pytest.raises(env_database.EnvironmentDiskChanged, match='now has disk bbbb'):
            env_database.verify_environment_vm(env_id)

    def test_matching_or_unpinned_disk_passes(self, global_db):
        vm_id = _add_vm(file_hash='a' * 64)
        env_id = _new_version('ubuntu', '1' * 64, vm_id=vm_id)  # vm_hash unpinned (pre-migration row)

        env_database.verify_environment_vm(env_id)

    def test_run_is_refused_when_environment_and_vm_disagree_on_hypervisor(self, global_db):
        vm_id = _add_vm()  # registered for qemu
        env_id = _new_version('ubuntu', '1' * 64, vm_id=vm_id)
        with EnvironmentDbApi() as db:
            db.get_environment_by_ulid(env_id).hypervisor = 'virtualbox'
            db._session.commit()

        with pytest.raises(env_database.EnvironmentDiskChanged, match="registered for 'qemu'"):
            env_database.verify_environment_vm(env_id)
