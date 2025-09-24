"""
Test suite for the global registry migration system.

This module contains comprehensive tests for the new multi-database architecture,
including migration from the old system, global registries, and resource resolution.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
import hashlib
import json

from adare.database.migration.global_registry_migration import GlobalRegistryMigration
from adare.database.api.global_registry.vm_registry import VmRegistryApi
from adare.database.api.global_registry.environment_registry import EnvironmentRegistryApi
from adare.database.api.project_database import ProjectDatabaseApi
from adare.database.api.resource_resolver import ResourceResolver
from adare.database.exceptions import DatabaseError, ValidationError, EntityNotFoundError


class TestGlobalRegistryMigration:
    """Test the migration from single database to global registry architecture."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def sample_vm_file(self, temp_dir):
        """Create a sample VM file for testing."""
        vm_file = temp_dir / "test_vm.ova"
        vm_file.write_text("Sample VM content for testing")
        return vm_file

    @pytest.fixture
    def sample_environment_file(self, temp_dir):
        """Create a sample environment file for testing."""
        env_file = temp_dir / "test_environment.yml"
        env_content = """
name: test_environment
description: Test environment for migration
vm: test_vm
postsetupinstallations:
  - name: test_tool
    command: apt install test-tool
tags:
  - test
  - migration
"""
        env_file.write_text(env_content)
        return env_file

    def test_migration_validation(self, temp_dir):
        """Test migration validation functionality."""
        # Test with non-existent database
        migration = GlobalRegistryMigration(dry_run=True)

        # Override database path for testing
        test_db_path = temp_dir / "test_adare.db"
        migration.current_db_path = test_db_path
        migration._setup_current_db_connection()

        validation = migration.validate_current_database()

        assert not validation['database_exists']
        assert validation['projects_count'] == 0
        assert len(validation['issues']) > 0

    def test_dry_run_migration(self, temp_dir, sample_vm_file, sample_environment_file):
        """Test dry run migration without making actual changes."""
        migration = GlobalRegistryMigration(dry_run=True)

        # Create minimal test data
        results = migration.run_full_migration()

        assert results['dry_run'] is True
        assert 'started_at' in results
        assert 'completed_at' in results
        assert isinstance(results['stats'], dict)


class TestVmRegistryApi:
    """Test the global VM registry API."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def sample_vm_file(self, temp_dir):
        """Create a sample VM file for testing."""
        vm_file = temp_dir / "test_vm.ova"
        vm_content = b"Sample VM content for testing - this is a mock VM file"
        vm_file.write_bytes(vm_content)
        return vm_file, hashlib.sha256(vm_content).hexdigest()

    @pytest.fixture
    def vm_registry(self, temp_dir, monkeypatch):
        """Create a VM registry with temporary database."""
        # Patch the VM registry to use temporary database
        test_db_path = temp_dir / "test_vm_registry.db"

        def mock_init(self):
            self.db_path = test_db_path
            from adare.database.api.base import EnhancedDatabaseApi
            EnhancedDatabaseApi.__init__(self, db_path=test_db_path)
            # Skip directory creation for tests
            self._ensure_registry_metadata()

        monkeypatch.setattr(VmRegistryApi, '__init__', mock_init)
        return VmRegistryApi()

    def test_create_vm(self, vm_registry, sample_vm_file):
        """Test creating a VM in the global registry."""
        vm_file, file_hash = sample_vm_file

        with vm_registry:
            vm = vm_registry.create_vm(
                name="test_vm",
                file_path=vm_file,
                file_hash=file_hash,
                description="Test VM for unit tests",
                os_platform="linux",
                os_distribution="ubuntu",
                os_version="22.04",
                created_by="test_user"
            )

        assert vm.name == "test_vm"
        assert vm.hash == file_hash
        assert vm.os_platform == "linux"
        assert vm.os_distribution == "ubuntu"
        assert vm.created_by == "test_user"

    def test_get_vm_by_name(self, vm_registry, sample_vm_file):
        """Test retrieving a VM by name."""
        vm_file, file_hash = sample_vm_file

        with vm_registry:
            # Create VM
            created_vm = vm_registry.create_vm(
                name="test_vm_lookup",
                file_path=vm_file,
                file_hash=file_hash,
                description="Test VM for lookup"
            )

            # Retrieve by name
            retrieved_vm = vm_registry.get_vm_by_name("test_vm_lookup")

        assert retrieved_vm is not None
        assert retrieved_vm.name == "test_vm_lookup"
        assert retrieved_vm.id == created_vm.id

    def test_vm_usage_tracking(self, vm_registry, sample_vm_file, temp_dir):
        """Test VM usage tracking functionality."""
        vm_file, file_hash = sample_vm_file
        project_path = str(temp_dir / "test_project")

        with vm_registry:
            # Create VM
            vm = vm_registry.create_vm(
                name="test_vm_usage",
                file_path=vm_file,
                file_hash=file_hash
            )

            # Track usage
            usage = vm_registry.track_vm_usage(
                vm_id=vm.id,
                project_path=project_path,
                project_name="Test Project",
                alias_name="my_test_vm"
            )

        assert usage.resource_type == 'vm'
        assert usage.resource_id == vm.id
        assert usage.project_path == project_path
        assert usage.alias_name == "my_test_vm"
        assert usage.usage_count == 1

    def test_delete_vm_with_usage(self, vm_registry, sample_vm_file, temp_dir):
        """Test that VM deletion respects usage tracking."""
        vm_file, file_hash = sample_vm_file
        project_path = str(temp_dir / "test_project")

        with vm_registry:
            # Create VM and track usage
            vm = vm_registry.create_vm(
                name="test_vm_delete",
                file_path=vm_file,
                file_hash=file_hash
            )

            vm_registry.track_vm_usage(
                vm_id=vm.id,
                project_path=project_path,
                project_name="Test Project"
            )

            # Should fail without force
            with pytest.raises(ValidationError, match="is used by.*project"):
                vm_registry.delete_vm(vm.id, force=False)

            # Should succeed with force
            success = vm_registry.delete_vm(vm.id, force=True)
            assert success is True

            # VM should be gone
            deleted_vm = vm_registry.get_vm_by_id(vm.id)
            assert deleted_vm is None


class TestEnvironmentRegistryApi:
    """Test the global environment registry API."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def sample_environment_file(self, temp_dir):
        """Create a sample environment file for testing."""
        env_file = temp_dir / "test_environment.yml"
        env_content = """
name: test_environment
description: Test environment for unit tests
vm: test_vm
postsetupinstallations:
  - name: test_tool
    command: apt install test-tool
tags:
  - test
  - unittest
"""
        env_file.write_text(env_content)
        content_hash = hashlib.sha256(env_content.encode()).hexdigest()
        return env_file, content_hash

    @pytest.fixture
    def vm_and_env_registries(self, temp_dir, monkeypatch):
        """Create both VM and environment registries for testing."""
        vm_db_path = temp_dir / "test_vm_registry.db"
        env_db_path = temp_dir / "test_env_registry.db"

        def mock_vm_init(self):
            self.db_path = vm_db_path
            from adare.database.api.base import EnhancedDatabaseApi
            EnhancedDatabaseApi.__init__(self, db_path=vm_db_path)
            self._ensure_registry_metadata()

        def mock_env_init(self):
            self.db_path = env_db_path
            from adare.database.api.base import EnhancedDatabaseApi
            EnhancedDatabaseApi.__init__(self, db_path=env_db_path)
            self._ensure_registry_metadata()

        monkeypatch.setattr(VmRegistryApi, '__init__', mock_vm_init)
        monkeypatch.setattr(EnvironmentRegistryApi, '__init__', mock_env_init)

        return VmRegistryApi(), EnvironmentRegistryApi()

    def test_create_environment(self, vm_and_env_registries, sample_environment_file, temp_dir):
        """Test creating an environment in the global registry."""
        vm_registry, env_registry = vm_and_env_registries
        env_file, file_hash = sample_environment_file

        # Create a VM first
        vm_file = temp_dir / "test_vm.ova"
        vm_file.write_bytes(b"test vm content")
        vm_hash = hashlib.sha256(b"test vm content").hexdigest()

        with vm_registry:
            vm = vm_registry.create_vm(
                name="test_vm_for_env",
                file_path=vm_file,
                file_hash=vm_hash
            )

        # Create environment
        with env_registry:
            environment = env_registry.create_environment(
                name="test_environment",
                vm_id=vm.id,
                file_path=env_file,
                sha256hash=file_hash,
                description="Test environment for unit tests",
                installations=[{"name": "test_tool", "command": "apt install test-tool"}],
                tags=["test", "unittest"],
                created_by="test_user"
            )

        assert environment.name == "test_environment"
        assert environment.vm_id == vm.id
        assert environment.sha256hash == file_hash
        assert environment.created_by == "test_user"
        assert "test" in environment.tag_list

    def test_environment_search(self, vm_and_env_registries, sample_environment_file, temp_dir):
        """Test environment search functionality."""
        vm_registry, env_registry = vm_and_env_registries
        env_file, file_hash = sample_environment_file

        # Create VM and environment
        vm_file = temp_dir / "test_vm.ova"
        vm_file.write_bytes(b"test vm content")
        vm_hash = hashlib.sha256(b"test vm content").hexdigest()

        with vm_registry:
            vm = vm_registry.create_vm(
                name="search_test_vm",
                file_path=vm_file,
                file_hash=vm_hash
            )

        with env_registry:
            env_registry.create_environment(
                name="searchable_environment",
                vm_id=vm.id,
                file_path=env_file,
                sha256hash=file_hash,
                description="Environment for search testing",
                tags=["searchable", "unittest"]
            )

            # Search by name
            results = env_registry.search_environments("searchable")
            assert len(results) == 1
            assert results[0].name == "searchable_environment"

            # Search by tag
            tag_results = env_registry.get_environments_by_tag("searchable")
            assert len(tag_results) == 1
            assert tag_results[0].name == "searchable_environment"


class TestProjectDatabaseApi:
    """Test the project-specific database API."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def test_project(self, temp_dir):
        """Create a test project directory."""
        project_dir = temp_dir / "test_project"
        project_dir.mkdir(parents=True)
        return project_dir

    def test_project_initialization(self, test_project):
        """Test project database initialization."""
        project_db = ProjectDatabaseApi(test_project)

        # Check that database file was created
        db_file = test_project / '.adare' / 'project.db'
        assert db_file.exists()

        # Check that metadata was created
        metadata = project_db.get_project_metadata()
        assert metadata.name == test_project.name
        assert metadata.path == str(test_project)

    def test_global_resource_references(self, test_project):
        """Test adding and managing global resource references."""
        project_db = ProjectDatabaseApi(test_project)

        # Add VM reference
        vm_ref = project_db.add_global_resource_reference(
            resource_type='vm',
            global_resource_id='test-vm-id-123',
            project_alias='my_test_vm',
            usage_notes='Used for testing'
        )

        assert vm_ref.resource_type == 'vm'
        assert vm_ref.global_resource_id == 'test-vm-id-123'
        assert vm_ref.project_alias == 'my_test_vm'

        # Get references
        vm_refs = project_db.get_global_resource_references('vm')
        assert len(vm_refs) == 1
        assert vm_refs[0].global_resource_id == 'test-vm-id-123'

    def test_experiment_creation(self, test_project):
        """Test creating experiments in project database."""
        project_db = ProjectDatabaseApi(test_project)

        # Add environment reference first
        env_ref = project_db.add_global_resource_reference(
            resource_type='environment',
            global_resource_id='test-env-id-456',
            project_alias='test_environment'
        )

        # Create experiment
        experiment = project_db.create_experiment(
            name='test_experiment',
            description='Test experiment for unit tests',
            playbook_file='playbook.yml'
        )

        assert experiment.name == 'test_experiment'
        assert experiment.description == 'Test experiment for unit tests'
        assert experiment.playbook_file == 'playbook.yml'

        # Add environment to experiment
        exp_env_ref = project_db.add_environment_to_experiment(
            experiment_name='test_experiment',
            global_environment_id='test-env-id-456',
            environment_alias='test_environment',
            is_primary=True
        )

        assert exp_env_ref.global_environment_id == 'test-env-id-456'
        assert exp_env_ref.is_primary is True

    def test_experiment_runs(self, test_project):
        """Test experiment run management."""
        project_db = ProjectDatabaseApi(test_project)

        # Create experiment and environment reference
        env_ref = project_db.add_global_resource_reference(
            resource_type='environment',
            global_resource_id='test-env-id-789'
        )

        experiment = project_db.create_experiment(
            name='run_test_experiment'
        )

        exp_env_ref = project_db.add_environment_to_experiment(
            experiment_name='run_test_experiment',
            global_environment_id='test-env-id-789'
        )

        # Create experiment run
        run = project_db.create_experiment_run(
            experiment_name='run_test_experiment',
            environment_ref_id=exp_env_ref.id,
            executed_by='test_user',
            execution_notes='Test run'
        )

        assert run.experiment_id == experiment.id
        assert run.environment_ref_id == exp_env_ref.id
        assert run.executed_by == 'test_user'

        # Update run status
        project_db.update_experiment_run_status(
            run_id=run.id,
            status='success',
            completed_at=datetime.utcnow(),
            results_path='results/test_run_results'
        )

        # Get runs
        runs = project_db.get_experiment_runs('run_test_experiment')
        assert len(runs) == 1
        assert runs[0].status == 'success'
        assert runs[0].results_path == 'results/test_run_results'


class TestResourceResolver:
    """Test the resource resolution system."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def test_project(self, temp_dir):
        """Create a test project directory."""
        project_dir = temp_dir / "resolver_test_project"
        project_dir.mkdir(parents=True)
        return project_dir

    @pytest.fixture
    def mock_registries_with_data(self, temp_dir, monkeypatch):
        """Create mock registries with test data."""
        vm_db_path = temp_dir / "resolver_vm_registry.db"
        env_db_path = temp_dir / "resolver_env_registry.db"

        def mock_vm_init(self):
            self.db_path = vm_db_path
            from adare.database.api.base import EnhancedDatabaseApi
            EnhancedDatabaseApi.__init__(self, db_path=vm_db_path)
            self._ensure_registry_metadata()

        def mock_env_init(self):
            self.db_path = env_db_path
            from adare.database.api.base import EnhancedDatabaseApi
            EnhancedDatabaseApi.__init__(self, db_path=env_db_path)
            self._ensure_registry_metadata()

        monkeypatch.setattr(VmRegistryApi, '__init__', mock_vm_init)
        monkeypatch.setattr(EnvironmentRegistryApi, '__init__', mock_env_init)

        # Create test data
        vm_registry = VmRegistryApi()
        env_registry = EnvironmentRegistryApi()

        # Create test VM file
        vm_file = temp_dir / "resolver_test_vm.ova"
        vm_file.write_bytes(b"resolver test vm content")
        vm_hash = hashlib.sha256(b"resolver test vm content").hexdigest()

        with vm_registry:
            test_vm = vm_registry.create_vm(
                name="resolver_test_vm",
                file_path=vm_file,
                file_hash=vm_hash,
                description="VM for resolver testing",
                os_platform="linux",
                os_distribution="ubuntu"
            )

        # Create test environment file
        env_file = temp_dir / "resolver_test_env.yml"
        env_content = "test environment content"
        env_file.write_text(env_content)
        env_hash = hashlib.sha256(env_content.encode()).hexdigest()

        with env_registry:
            test_env = env_registry.create_environment(
                name="resolver_test_environment",
                vm_id=test_vm.id,
                file_path=env_file,
                sha256hash=env_hash,
                description="Environment for resolver testing"
            )

        return vm_registry, env_registry, test_vm, test_env

    def test_vm_resolution(self, test_project, mock_registries_with_data):
        """Test resolving VM references."""
        vm_registry, env_registry, test_vm, test_env = mock_registries_with_data

        # Add VM reference to project
        project_db = ProjectDatabaseApi(test_project)
        vm_ref = project_db.add_global_resource_reference(
            resource_type='vm',
            global_resource_id=test_vm.id,
            project_alias='my_resolver_vm',
            usage_notes='VM for resolver testing'
        )

        # Resolve VM reference
        resolver = ResourceResolver(test_project)
        resolved_vm = resolver.resolve_vm_reference(vm_ref)

        assert resolved_vm is not None
        assert resolved_vm['id'] == test_vm.id
        assert resolved_vm['name'] == test_vm.name
        assert resolved_vm['os_info']['platform'] == 'linux'
        assert resolved_vm['project_reference']['project_alias'] == 'my_resolver_vm'

    def test_environment_resolution(self, test_project, mock_registries_with_data):
        """Test resolving environment references."""
        vm_registry, env_registry, test_vm, test_env = mock_registries_with_data

        # Add environment reference to project
        project_db = ProjectDatabaseApi(test_project)
        env_ref = project_db.add_global_resource_reference(
            resource_type='environment',
            global_resource_id=test_env.id,
            project_alias='my_resolver_environment'
        )

        # Resolve environment reference
        resolver = ResourceResolver(test_project)
        resolved_env = resolver.resolve_environment_reference(env_ref, include_vm_info=True)

        assert resolved_env is not None
        assert resolved_env['id'] == test_env.id
        assert resolved_env['name'] == test_env.name
        assert resolved_env['vm_id'] == test_vm.id
        assert resolved_env['vm_info']['name'] == test_vm.name
        assert resolved_env['project_reference']['project_alias'] == 'my_resolver_environment'

    def test_project_resource_summary(self, test_project, mock_registries_with_data):
        """Test getting project resource summary."""
        vm_registry, env_registry, test_vm, test_env = mock_registries_with_data

        # Add resources to project
        project_db = ProjectDatabaseApi(test_project)
        project_db.add_global_resource_reference(
            resource_type='vm',
            global_resource_id=test_vm.id,
            project_alias='summary_test_vm'
        )
        project_db.add_global_resource_reference(
            resource_type='environment',
            global_resource_id=test_env.id,
            project_alias='summary_test_environment'
        )

        # Get resource summary
        resolver = ResourceResolver(test_project)
        summary = resolver.get_project_resource_summary()

        assert summary['vm_resources']['count'] == 1
        assert summary['environment_resources']['count'] == 1
        assert len(summary['vm_resources']['vms']) == 1
        assert len(summary['environment_resources']['environments']) == 1
        assert summary['vm_resources']['vms'][0]['alias'] == 'summary_test_vm'
        assert summary['environment_resources']['environments'][0]['alias'] == 'summary_test_environment'

    def test_resource_validation(self, test_project, mock_registries_with_data):
        """Test resource reference validation."""
        vm_registry, env_registry, test_vm, test_env = mock_registries_with_data

        # Add valid and invalid references
        project_db = ProjectDatabaseApi(test_project)
        project_db.add_global_resource_reference(
            resource_type='vm',
            global_resource_id=test_vm.id,  # Valid reference
            project_alias='valid_vm'
        )
        project_db.add_global_resource_reference(
            resource_type='environment',
            global_resource_id='non-existent-env-id',  # Invalid reference
            project_alias='invalid_environment'
        )

        # Validate references
        resolver = ResourceResolver(test_project)
        validation = resolver.validate_project_references()

        assert validation['valid_vm_references'] == 1
        assert validation['invalid_vm_references'] == 0
        assert validation['valid_environment_references'] == 0
        assert validation['invalid_environment_references'] == 1
        assert len(validation['missing_resources']) == 1


class TestIntegration:
    """Integration tests for the complete system."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir)

    def test_complete_workflow(self, temp_dir):
        """Test a complete workflow from VM creation to experiment execution."""
        # This test would be more complex and would test the entire workflow
        # from creating global resources to running experiments
        pass  # Placeholder for full integration test

    def test_migration_roundtrip(self, temp_dir):
        """Test that migration preserves all data correctly."""
        # This test would create sample data, run migration, and verify
        # that all data is preserved correctly
        pass  # Placeholder for migration roundtrip test


def run_tests():
    """Run all tests."""
    pytest.main([__file__, "-v", "--tb=short"])


if __name__ == "__main__":
    run_tests()