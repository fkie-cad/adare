"""
Database migration tool for ADARE global registry architecture.

This module provides tools to migrate from the current single-database architecture
to the new multi-database architecture with global registries and per-project databases.

Migration Process:
1. Create global VM registry and migrate VMs
2. Create global environment registry and migrate environments
3. For each project, create project database and migrate project-specific data
4. Create resource usage tracking records
5. Validate migration completeness
"""

import logging
import shutil
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
import json

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from adare.config.configdirectory import APPDATA_DIR, VMS_DIR
from adare.config.database import get_database_location
from adare.database.api.global_registry.vm_registry import VmRegistryApi
from adare.database.api.global_registry.environment_registry import EnvironmentRegistryApi
from adare.database.models.experiment import (
    Project, Vm, Environment, Experiment, TestFunctionFile, TestFunction
)
from adare.database.models.global_registry import (
    GlobalVm, GlobalEnvironment, ResourceUsage, GlobalResourceMetadata
)
from adare.database.models.project_database import (
    ProjectMetadata, GlobalResourceReference, ProjectExperiment,
    ExperimentEnvironmentReference, ProjectTestFunctionFile, ProjectTestFunction
)

log = logging.getLogger(__name__)


class GlobalRegistryMigration:
    """
    Handles migration from single database to global registry architecture.
    """

    def __init__(self, dry_run: bool = True):
        """
        Initialize migration tool.

        Args:
            dry_run: If True, simulate migration without making changes
        """
        self.dry_run = dry_run
        self.current_db_path = get_database_location()
        self.migration_stats = {
            'vms_migrated': 0,
            'environments_migrated': 0,
            'projects_migrated': 0,
            'experiments_migrated': 0,
            'test_functions_migrated': 0,
            'usage_records_created': 0,
            'errors': []
        }

        # Initialize registry APIs
        self.vm_registry = VmRegistryApi()
        self.environment_registry = EnvironmentRegistryApi()

        # Create connection to current database
        self._setup_current_db_connection()

    def _setup_current_db_connection(self):
        """Setup connection to current database."""
        try:
            self.current_engine = create_engine(f'sqlite:///{self.current_db_path.as_posix()}')
            self.current_session_factory = sessionmaker(bind=self.current_engine)
            log.info(f"Connected to current database: {self.current_db_path}")
        except Exception as e:
            log.error(f"Failed to connect to current database: {e}")
            raise

    def validate_current_database(self) -> Dict[str, Any]:
        """
        Validate the current database structure and content.

        Returns:
            Dict with validation results
        """
        log.info("Validating current database structure...")

        validation_results = {
            'database_exists': False,
            'tables_exist': False,
            'projects_count': 0,
            'vms_count': 0,
            'environments_count': 0,
            'experiments_count': 0,
            'issues': []
        }

        try:
            if not self.current_db_path.exists():
                validation_results['issues'].append("Current database file does not exist")
                return validation_results

            validation_results['database_exists'] = True

            with self.current_session_factory() as session:
                # Check if required tables exist
                required_tables = ['project', 'vm', 'environment', 'experiment']
                existing_tables = []

                for table in required_tables:
                    result = session.execute(text(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'"))
                    if result.fetchone():
                        existing_tables.append(table)

                if len(existing_tables) == len(required_tables):
                    validation_results['tables_exist'] = True
                else:
                    missing = set(required_tables) - set(existing_tables)
                    validation_results['issues'].append(f"Missing tables: {', '.join(missing)}")

                # Count records
                try:
                    validation_results['projects_count'] = session.query(Project).count()
                    validation_results['vms_count'] = session.query(Vm).count()
                    validation_results['environments_count'] = session.query(Environment).count()
                    validation_results['experiments_count'] = session.query(Experiment).count()
                except Exception as e:
                    validation_results['issues'].append(f"Error counting records: {e}")

        except Exception as e:
            validation_results['issues'].append(f"Database validation error: {e}")

        log.info(f"Validation results: {validation_results}")
        return validation_results

    def migrate_vms_to_global_registry(self) -> Dict[str, Any]:
        """
        Migrate VMs from current database to global VM registry.

        Returns:
            Dict with migration results
        """
        log.info("Migrating VMs to global registry...")

        results = {
            'migrated': 0,
            'skipped': 0,
            'errors': 0,
            'vm_mapping': {}  # old_id -> new_id
        }

        if self.dry_run:
            log.info("DRY RUN: Simulating VM migration")

        try:
            with self.current_session_factory() as current_session:
                vms = current_session.query(Vm).all()
                log.info(f"Found {len(vms)} VMs to migrate")

                for vm in vms:
                    try:
                        if not self.dry_run:
                            # Check if VM already exists in global registry
                            with self.vm_registry:
                                existing_vm = self.vm_registry.get_vm_by_hash(vm.hash)
                                if existing_vm:
                                    log.info(f"VM {vm.name} already exists in global registry")
                                    results['vm_mapping'][vm.id] = existing_vm.id
                                    results['skipped'] += 1
                                    continue

                                # Migrate VM
                                global_vm = self.vm_registry.create_vm(
                                    name=vm.name,
                                    file_path=Path(vm.file),
                                    file_hash=vm.hash,
                                    description=vm.description or '',
                                    os_platform=vm.osinfo.platform if vm.osinfo else '',
                                    os_type=vm.osinfo.os if vm.osinfo else '',
                                    os_distribution=vm.osinfo.distribution if vm.osinfo else '',
                                    os_version=vm.osinfo.version if vm.osinfo else '',
                                    os_language=vm.osinfo.language if vm.osinfo else '',
                                    os_architecture=vm.osinfo.architecture if vm.osinfo else 'x86_64',
                                    created_by='migration_tool'
                                )

                                results['vm_mapping'][vm.id] = global_vm.id
                                log.info(f"Migrated VM: {vm.name} -> {global_vm.id}")
                        else:
                            results['vm_mapping'][vm.id] = f"simulated_vm_{results['migrated']}"

                        results['migrated'] += 1

                    except Exception as e:
                        log.error(f"Failed to migrate VM {vm.name}: {e}")
                        results['errors'] += 1
                        self.migration_stats['errors'].append(f"VM {vm.name}: {e}")

        except Exception as e:
            log.error(f"Error during VM migration: {e}")
            results['errors'] += 1

        self.migration_stats['vms_migrated'] = results['migrated']
        log.info(f"VM migration completed: {results}")
        return results

    def migrate_environments_to_global_registry(self, vm_mapping: Dict[str, str]) -> Dict[str, Any]:
        """
        Migrate environments from current database to global environment registry.

        Args:
            vm_mapping: Mapping from old VM IDs to new global VM IDs

        Returns:
            Dict with migration results
        """
        log.info("Migrating environments to global registry...")

        results = {
            'migrated': 0,
            'skipped': 0,
            'errors': 0,
            'environment_mapping': {}  # old_id -> new_id
        }

        if self.dry_run:
            log.info("DRY RUN: Simulating environment migration")

        try:
            with self.current_session_factory() as current_session:
                environments = current_session.query(Environment).all()
                log.info(f"Found {len(environments)} environments to migrate")

                for env in environments:
                    try:
                        if not self.dry_run:
                            # Check if environment already exists in global registry
                            with self.environment_registry:
                                existing_env = self.environment_registry.get_environment_by_hash(env.sha256hash)
                                if existing_env:
                                    log.info(f"Environment {env.name} already exists in global registry")
                                    results['environment_mapping'][env.id] = existing_env.id
                                    results['skipped'] += 1
                                    continue

                                # Get corresponding global VM ID
                                global_vm_id = vm_mapping.get(env.vm_id)
                                if not global_vm_id:
                                    log.error(f"No global VM mapping found for environment {env.name}")
                                    results['errors'] += 1
                                    continue

                                # Prepare installations data
                                installations = []
                                if hasattr(env, 'installations') and env.installations:
                                    installations = [
                                        {
                                            'name': inst.name,
                                            'command': inst.command,
                                            'description': inst.description
                                        }
                                        for inst in env.installations
                                    ]

                                # Prepare tags
                                tags = []
                                if hasattr(env, 'tags') and env.tags:
                                    tags = [tag.name for tag in env.tags]

                                # Migrate environment
                                global_env = self.environment_registry.create_environment(
                                    name=env.name,
                                    vm_id=global_vm_id,
                                    file_path=Path(env.file) if env.file else Path("placeholder.yml"),
                                    sha256hash=env.sha256hash or 'placeholder_hash',
                                    description=env.description or '',
                                    installations=installations,
                                    tags=tags,
                                    version="1.0.0",
                                    created_by='migration_tool'
                                )

                                results['environment_mapping'][env.id] = global_env.id
                                log.info(f"Migrated environment: {env.name} -> {global_env.id}")
                        else:
                            results['environment_mapping'][env.id] = f"simulated_env_{results['migrated']}"

                        results['migrated'] += 1

                    except Exception as e:
                        log.error(f"Failed to migrate environment {env.name}: {e}")
                        results['errors'] += 1
                        self.migration_stats['errors'].append(f"Environment {env.name}: {e}")

        except Exception as e:
            log.error(f"Error during environment migration: {e}")
            results['errors'] += 1

        self.migration_stats['environments_migrated'] = results['migrated']
        log.info(f"Environment migration completed: {results}")
        return results

    def migrate_projects_to_individual_databases(self, vm_mapping: Dict[str, str],
                                                environment_mapping: Dict[str, str]) -> Dict[str, Any]:
        """
        Migrate projects to individual project databases.

        Args:
            vm_mapping: Mapping from old VM IDs to new global VM IDs
            environment_mapping: Mapping from old environment IDs to new global environment IDs

        Returns:
            Dict with migration results
        """
        log.info("Migrating projects to individual databases...")

        results = {
            'projects_migrated': 0,
            'experiments_migrated': 0,
            'test_functions_migrated': 0,
            'errors': 0,
            'project_databases': []
        }

        if self.dry_run:
            log.info("DRY RUN: Simulating project migration")

        try:
            with self.current_session_factory() as current_session:
                projects = current_session.query(Project).all()
                log.info(f"Found {len(projects)} projects to migrate")

                for project in projects:
                    try:
                        project_result = self._migrate_single_project(
                            project, vm_mapping, environment_mapping
                        )

                        results['projects_migrated'] += 1
                        results['experiments_migrated'] += project_result.get('experiments', 0)
                        results['test_functions_migrated'] += project_result.get('test_functions', 0)
                        results['project_databases'].append(project_result.get('database_path'))

                        log.info(f"Migrated project: {project.name}")

                    except Exception as e:
                        log.error(f"Failed to migrate project {project.name}: {e}")
                        results['errors'] += 1
                        self.migration_stats['errors'].append(f"Project {project.name}: {e}")

        except Exception as e:
            log.error(f"Error during project migration: {e}")
            results['errors'] += 1

        self.migration_stats['projects_migrated'] = results['projects_migrated']
        self.migration_stats['experiments_migrated'] = results['experiments_migrated']
        self.migration_stats['test_functions_migrated'] = results['test_functions_migrated']

        log.info(f"Project migration completed: {results}")
        return results

    def _migrate_single_project(self, project: Project, vm_mapping: Dict[str, str],
                               environment_mapping: Dict[str, str]) -> Dict[str, Any]:
        """
        Migrate a single project to its own database.

        Args:
            project: Project instance from current database
            vm_mapping: VM ID mapping
            environment_mapping: Environment ID mapping

        Returns:
            Dict with migration results for this project
        """
        result = {
            'project_id': project.id,
            'project_name': project.name,
            'database_path': None,
            'experiments': 0,
            'test_functions': 0,
            'errors': []
        }

        project_path = Path(project.path)
        project_db_dir = project_path / '.adare'
        project_db_path = project_db_dir / 'project.db'

        if not self.dry_run:
            # Create project database directory
            project_db_dir.mkdir(parents=True, exist_ok=True)

            # Create project database
            project_engine = create_engine(f'sqlite:///{project_db_path.as_posix()}')

            # Import project database models and create tables
            from adare.database.models.project_database import Base as ProjectBase
            ProjectBase.metadata.create_all(project_engine)

            project_session_factory = sessionmaker(bind=project_engine)

            with project_session_factory() as project_session:
                # Create project metadata
                project_metadata = ProjectMetadata(
                    name=project.name,
                    description=project.description,
                    path=str(project_path),
                    created_by='migration_tool',
                    schema_version="1.0.0"
                )
                project_session.add(project_metadata)
                project_session.flush()

                # Migrate experiments
                with self.current_session_factory() as current_session:
                    experiments = current_session.query(Experiment).filter(
                        Experiment.id.in_([env.id for env in project.environments if env.experiments])
                    ).all()

                    for experiment in experiments:
                        self._migrate_experiment_to_project_db(
                            experiment, project_session, environment_mapping
                        )
                        result['experiments'] += 1

                    # Migrate test function files
                    for tf_file in project.test_function_files:
                        self._migrate_test_function_file_to_project_db(
                            tf_file, project_session
                        )
                        result['test_functions'] += len(tf_file.test_functions)

                project_session.commit()

        result['database_path'] = str(project_db_path)
        return result

    def _migrate_experiment_to_project_db(self, experiment: Experiment, project_session,
                                         environment_mapping: Dict[str, str]):
        """Migrate an experiment to project database."""
        try:
            # Create project experiment
            project_experiment = ProjectExperiment(
                name=experiment.name,
                description=experiment.description,
                playbook_file=experiment.playbook_file,
                metadata_file=experiment.metadata_file,
                bibtex_file=experiment.bibtex_file,
                markdown_file=experiment.markdown_file,
                sha256_playbook=experiment.sha256_playbook,
                sha256_metadata=experiment.sha256_metadata,
                sha256_bibtex=experiment.sha256_bibtex,
                sha256_markdown=experiment.sha256_markdown,
                sha256=experiment.sha256
            )
            project_session.add(project_experiment)
            project_session.flush()

            # Create environment references
            for env in experiment.environments:
                global_env_id = environment_mapping.get(env.id)
                if global_env_id:
                    env_ref = ExperimentEnvironmentReference(
                        experiment_id=project_experiment.id,
                        global_environment_id=global_env_id,
                        environment_alias=env.name
                    )
                    project_session.add(env_ref)

        except Exception as e:
            log.error(f"Failed to migrate experiment {experiment.name}: {e}")
            raise

    def _migrate_test_function_file_to_project_db(self, tf_file: TestFunctionFile, project_session):
        """Migrate a test function file to project database."""
        try:
            # Create project test function file
            project_tf_file = ProjectTestFunctionFile(
                name=tf_file.name,
                path=tf_file.path,
                requirements_path=tf_file.requirements_path,
                sha256hash=tf_file.sha256hash,
                description=tf_file.description
            )
            project_session.add(project_tf_file)
            project_session.flush()

            # Migrate test functions
            for tf in tf_file.test_functions:
                project_tf = ProjectTestFunction(
                    type=tf.type,
                    name=tf.name,
                    description=tf.description,
                    sha256hash=tf.sha256hash,
                    file_id=project_tf_file.id
                )
                project_session.add(project_tf)

        except Exception as e:
            log.error(f"Failed to migrate test function file {tf_file.name}: {e}")
            raise

    def create_usage_tracking_records(self, vm_mapping: Dict[str, str],
                                     environment_mapping: Dict[str, str]) -> Dict[str, Any]:
        """
        Create resource usage tracking records based on current project-resource relationships.

        Args:
            vm_mapping: VM ID mapping
            environment_mapping: Environment ID mapping

        Returns:
            Dict with tracking results
        """
        log.info("Creating resource usage tracking records...")

        results = {
            'vm_usage_records': 0,
            'environment_usage_records': 0,
            'errors': 0
        }

        if self.dry_run:
            log.info("DRY RUN: Simulating usage tracking creation")
            return results

        try:
            with self.current_session_factory() as current_session:
                projects = current_session.query(Project).all()

                for project in projects:
                    try:
                        # Track VM usage through environments
                        for env in project.environments:
                            global_env_id = environment_mapping.get(env.id)
                            global_vm_id = vm_mapping.get(env.vm_id) if env.vm_id else None

                            if global_env_id:
                                # Track environment usage
                                self.environment_registry.track_environment_usage(
                                    env_id=global_env_id,
                                    project_path=project.path,
                                    project_name=project.name,
                                    alias_name=env.name
                                )
                                results['environment_usage_records'] += 1

                            if global_vm_id:
                                # Track VM usage
                                self.vm_registry.track_vm_usage(
                                    vm_id=global_vm_id,
                                    project_path=project.path,
                                    project_name=project.name
                                )
                                results['vm_usage_records'] += 1

                    except Exception as e:
                        log.error(f"Failed to create usage tracking for project {project.name}: {e}")
                        results['errors'] += 1

        except Exception as e:
            log.error(f"Error creating usage tracking records: {e}")
            results['errors'] += 1

        self.migration_stats['usage_records_created'] = (
            results['vm_usage_records'] + results['environment_usage_records']
        )

        log.info(f"Usage tracking creation completed: {results}")
        return results

    def validate_migration(self) -> Dict[str, Any]:
        """
        Validate that migration was completed successfully.

        Returns:
            Dict with validation results
        """
        log.info("Validating migration results...")

        validation = {
            'global_vm_registry_exists': False,
            'global_environment_registry_exists': False,
            'project_databases_created': 0,
            'data_integrity_checks': {
                'vm_count_match': False,
                'environment_count_match': False,
                'project_count_match': False
            },
            'issues': [],
            'migration_summary': self.migration_stats
        }

        try:
            # Check global registries
            vm_registry_path = APPDATA_DIR / 'vm_registry.db'
            env_registry_path = APPDATA_DIR / 'environment_registry.db'

            validation['global_vm_registry_exists'] = vm_registry_path.exists()
            validation['global_environment_registry_exists'] = env_registry_path.exists()

            if not self.dry_run:
                # Check data counts
                with self.vm_registry:
                    global_vm_count = len(self.vm_registry.get_all_vms())

                with self.environment_registry:
                    global_env_count = len(self.environment_registry.get_all_environments())

                with self.current_session_factory() as current_session:
                    original_vm_count = current_session.query(Vm).count()
                    original_env_count = current_session.query(Environment).count()
                    original_project_count = current_session.query(Project).count()

                validation['data_integrity_checks']['vm_count_match'] = (
                    global_vm_count == original_vm_count
                )
                validation['data_integrity_checks']['environment_count_match'] = (
                    global_env_count == original_env_count
                )
                validation['data_integrity_checks']['project_count_match'] = (
                    self.migration_stats['projects_migrated'] == original_project_count
                )

                # Count project databases
                for project_path in Path().rglob('*/.adare/project.db'):
                    if project_path.exists():
                        validation['project_databases_created'] += 1

        except Exception as e:
            validation['issues'].append(f"Validation error: {e}")

        log.info(f"Migration validation completed: {validation}")
        return validation

    def run_full_migration(self) -> Dict[str, Any]:
        """
        Run the complete migration process.

        Returns:
            Dict with complete migration results
        """
        log.info(f"Starting ADARE global registry migration (dry_run={self.dry_run})...")

        migration_results = {
            'started_at': datetime.utcnow().isoformat(),
            'dry_run': self.dry_run,
            'validation': {},
            'vm_migration': {},
            'environment_migration': {},
            'project_migration': {},
            'usage_tracking': {},
            'final_validation': {},
            'completed_at': None,
            'success': False
        }

        try:
            # Step 1: Validate current database
            migration_results['validation'] = self.validate_current_database()
            if not migration_results['validation']['database_exists']:
                raise Exception("Current database does not exist or is invalid")

            # Step 2: Migrate VMs to global registry
            migration_results['vm_migration'] = self.migrate_vms_to_global_registry()

            # Step 3: Migrate environments to global registry
            migration_results['environment_migration'] = self.migrate_environments_to_global_registry(
                migration_results['vm_migration']['vm_mapping']
            )

            # Step 4: Migrate projects to individual databases
            migration_results['project_migration'] = self.migrate_projects_to_individual_databases(
                migration_results['vm_migration']['vm_mapping'],
                migration_results['environment_migration']['environment_mapping']
            )

            # Step 5: Create usage tracking records
            migration_results['usage_tracking'] = self.create_usage_tracking_records(
                migration_results['vm_migration']['vm_mapping'],
                migration_results['environment_migration']['environment_mapping']
            )

            # Step 6: Final validation
            migration_results['final_validation'] = self.validate_migration()

            migration_results['success'] = True
            log.info("Migration completed successfully!")

        except Exception as e:
            log.error(f"Migration failed: {e}")
            migration_results['error'] = str(e)
            self.migration_stats['errors'].append(f"Migration failed: {e}")

        migration_results['completed_at'] = datetime.utcnow().isoformat()
        migration_results['stats'] = self.migration_stats

        return migration_results

    def create_migration_backup(self) -> Path:
        """
        Create a backup of the current database before migration.

        Returns:
            Path to backup file
        """
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_path = self.current_db_path.parent / f"adare_backup_{timestamp}.db"

        try:
            shutil.copy2(self.current_db_path, backup_path)
            log.info(f"Created database backup: {backup_path}")
            return backup_path
        except Exception as e:
            log.error(f"Failed to create backup: {e}")
            raise


def main():
    """Main migration entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Migrate ADARE to global registry architecture")
    parser.add_argument("--dry-run", action="store_true", default=True,
                       help="Simulate migration without making changes")
    parser.add_argument("--execute", action="store_true",
                       help="Execute actual migration (overrides --dry-run)")
    parser.add_argument("--backup", action="store_true", default=True,
                       help="Create backup before migration")
    parser.add_argument("--log-level", default="INFO",
                       choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                       help="Logging level")

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Determine if this is a dry run
    dry_run = args.dry_run and not args.execute

    # Create migration tool
    migration = GlobalRegistryMigration(dry_run=dry_run)

    try:
        # Create backup if requested and not dry run
        if args.backup and not dry_run:
            backup_path = migration.create_migration_backup()
            print(f"Created backup: {backup_path}")

        # Run migration
        results = migration.run_full_migration()

        # Print results
        print("\n" + "="*60)
        print("MIGRATION RESULTS")
        print("="*60)
        print(f"Mode: {'DRY RUN' if dry_run else 'EXECUTION'}")
        print(f"Success: {results['success']}")
        print(f"VMs migrated: {migration.migration_stats['vms_migrated']}")
        print(f"Environments migrated: {migration.migration_stats['environments_migrated']}")
        print(f"Projects migrated: {migration.migration_stats['projects_migrated']}")
        print(f"Experiments migrated: {migration.migration_stats['experiments_migrated']}")
        print(f"Usage records created: {migration.migration_stats['usage_records_created']}")
        print(f"Errors: {len(migration.migration_stats['errors'])}")

        if migration.migration_stats['errors']:
            print("\nErrors encountered:")
            for error in migration.migration_stats['errors']:
                print(f"  - {error}")

        if dry_run:
            print("\nThis was a DRY RUN. No changes were made.")
            print("Use --execute to perform actual migration.")

    except Exception as e:
        print(f"Migration failed: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())