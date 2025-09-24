"""
CLI commands for migrating ADARE to the new global registry architecture.

This module provides command-line interface for migrating from the current
single-database architecture to the new multi-database architecture.
"""

import click
import logging
from pathlib import Path
from typing import Optional
import json

from adare.database.migration.global_registry_migration import GlobalRegistryMigration
from adare.database.exceptions import DatabaseError

log = logging.getLogger(__name__)


@click.group()
def migrate():
    """Migrate ADARE to new global registry architecture."""
    pass


@migrate.command()
def validate():
    """Validate current database before migration."""
    try:
        migration = GlobalRegistryMigration(dry_run=True)
        validation_results = migration.validate_current_database()

        click.echo("🔍 Database Validation Results")
        click.echo("=" * 35)

        if validation_results['database_exists']:
            click.echo("✅ Current database file exists")
        else:
            click.echo("❌ Current database file not found")

        if validation_results['tables_exist']:
            click.echo("✅ Required tables exist")
        else:
            click.echo("❌ Missing required tables")

        click.echo(f"\n📊 Data Counts:")
        click.echo(f"   Projects: {validation_results['projects_count']}")
        click.echo(f"   VMs: {validation_results['vms_count']}")
        click.echo(f"   Environments: {validation_results['environments_count']}")
        click.echo(f"   Experiments: {validation_results['experiments_count']}")

        if validation_results['issues']:
            click.echo(f"\n⚠️  Issues Found:")
            for issue in validation_results['issues']:
                click.echo(f"   - {issue}")

        if not validation_results['issues'] and validation_results['database_exists']:
            click.echo(f"\n✅ Database is ready for migration!")
        else:
            click.echo(f"\n❌ Database has issues that need to be resolved before migration")
            exit(1)

    except Exception as e:
        click.echo(f"❌ Validation error: {e}", err=True)
        log.exception("Unexpected error during validation")
        exit(1)


@migrate.command()
@click.option('--backup/--no-backup', default=True, help='Create backup before migration')
@click.option('--dry-run', is_flag=True, help='Simulate migration without making changes')
def run(backup: bool, dry_run: bool):
    """Run the complete migration to global registry architecture."""
    if not dry_run:
        click.confirm(
            '⚠️  This will migrate your ADARE database to the new architecture. '
            'This is a significant change. Continue?',
            abort=True
        )

    try:
        migration = GlobalRegistryMigration(dry_run=dry_run)

        # Create backup if requested
        backup_path = None
        if backup and not dry_run:
            backup_path = migration.create_migration_backup()
            click.echo(f"📁 Created backup: {backup_path}")

        # Run migration
        click.echo(f"🚀 Starting migration {'(DRY RUN)' if dry_run else ''}...")

        with click.progressbar(length=6, label='Migrating') as bar:
            # Step 1: Validate
            bar.label = 'Validating database...'
            validation = migration.validate_current_database()
            bar.update(1)

            if not validation['database_exists']:
                click.echo("\n❌ Current database not found")
                exit(1)

            # Step 2: Migrate VMs
            bar.label = 'Migrating VMs to global registry...'
            vm_results = migration.migrate_vms_to_global_registry()
            bar.update(1)

            # Step 3: Migrate environments
            bar.label = 'Migrating environments to global registry...'
            env_results = migration.migrate_environments_to_global_registry(vm_results['vm_mapping'])
            bar.update(1)

            # Step 4: Migrate projects
            bar.label = 'Creating project databases...'
            project_results = migration.migrate_projects_to_individual_databases(
                vm_results['vm_mapping'],
                env_results['environment_mapping']
            )
            bar.update(1)

            # Step 5: Create usage tracking
            bar.label = 'Creating usage tracking records...'
            usage_results = migration.create_usage_tracking_records(
                vm_results['vm_mapping'],
                env_results['environment_mapping']
            )
            bar.update(1)

            # Step 6: Validate migration
            bar.label = 'Validating migration...'
            final_validation = migration.validate_migration()
            bar.update(1)

        # Show results
        click.echo(f"\n{'🔍 DRY RUN RESULTS' if dry_run else '✅ MIGRATION COMPLETED'}")
        click.echo("=" * 50)
        click.echo(f"VMs migrated: {vm_results['migrated']}")
        click.echo(f"Environments migrated: {env_results['migrated']}")
        click.echo(f"Projects migrated: {project_results['projects_migrated']}")
        click.echo(f"Experiments migrated: {project_results['experiments_migrated']}")
        click.echo(f"VM usage records: {usage_results['vm_usage_records']}")
        click.echo(f"Environment usage records: {usage_results['environment_usage_records']}")

        if vm_results['errors'] > 0 or env_results['errors'] > 0 or project_results['errors'] > 0:
            total_errors = vm_results['errors'] + env_results['errors'] + project_results['errors']
            click.echo(f"\n⚠️  {total_errors} errors encountered during migration")

        # Show validation results
        if final_validation['global_vm_registry_exists']:
            click.echo("\n✅ Global VM registry created")
        if final_validation['global_environment_registry_exists']:
            click.echo("✅ Global environment registry created")
        if final_validation['project_databases_created'] > 0:
            click.echo(f"✅ {final_validation['project_databases_created']} project databases created")

        # Data integrity checks
        integrity_checks = final_validation['data_integrity_checks']
        if not dry_run:
            if integrity_checks['vm_count_match']:
                click.echo("✅ VM count matches original")
            else:
                click.echo("❌ VM count mismatch")

            if integrity_checks['environment_count_match']:
                click.echo("✅ Environment count matches original")
            else:
                click.echo("❌ Environment count mismatch")

            if integrity_checks['project_count_match']:
                click.echo("✅ Project count matches original")
            else:
                click.echo("❌ Project count mismatch")

        if dry_run:
            click.echo(f"\n💡 This was a dry run. No changes were made.")
            click.echo(f"   Use 'adare migrate run --no-dry-run' to perform actual migration.")
        else:
            click.echo(f"\n🎉 Migration completed successfully!")
            if backup_path:
                click.echo(f"   Original database backed up to: {backup_path}")
            click.echo(f"\n💡 Next steps:")
            click.echo(f"   - Use 'adare global-vm list' to manage VMs")
            click.echo(f"   - Use 'adare global-environment list' to manage environments")
            click.echo(f"   - Use 'adare project info' to check project status")

    except Exception as e:
        click.echo(f"\n❌ Migration failed: {e}", err=True)
        log.exception("Migration failed")
        exit(1)


@migrate.command()
@click.option('--format', 'output_format', type=click.Choice(['table', 'json']),
              default='table', help='Output format')
def status():
    """Check migration status and architecture version."""
    try:
        from adare.config.configdirectory import APPDATA_DIR
        from adare.config.database import get_database_location

        current_db_exists = get_database_location().exists()
        vm_registry_exists = (APPDATA_DIR / 'vm_registry.db').exists()
        env_registry_exists = (APPDATA_DIR / 'environment_registry.db').exists()

        # Count project databases
        project_databases = list(Path().rglob('*/.adare/project.db'))
        project_db_count = len(project_databases)

        # Determine architecture
        if current_db_exists and not vm_registry_exists and not env_registry_exists:
            architecture = "legacy"
            status = "Not migrated"
        elif not current_db_exists and vm_registry_exists and env_registry_exists:
            architecture = "global_registry"
            status = "Fully migrated"
        elif current_db_exists and vm_registry_exists and env_registry_exists:
            architecture = "hybrid"
            status = "Migration in progress or both systems present"
        else:
            architecture = "unknown"
            status = "Unknown state"

        if output_format == 'table':
            click.echo("📊 ADARE Architecture Status")
            click.echo("=" * 30)
            click.echo(f"Architecture: {architecture}")
            click.echo(f"Status: {status}")
            click.echo()
            click.echo("Database Files:")
            click.echo(f"  Current DB: {'✅ Present' if current_db_exists else '❌ Missing'}")
            click.echo(f"  VM Registry: {'✅ Present' if vm_registry_exists else '❌ Missing'}")
            click.echo(f"  Environment Registry: {'✅ Present' if env_registry_exists else '❌ Missing'}")
            click.echo(f"  Project Databases: {project_db_count} found")

            if project_db_count > 0:
                click.echo("\nProject Databases Found:")
                for project_db in project_databases[:5]:  # Show first 5
                    project_name = project_db.parent.parent.name
                    click.echo(f"  - {project_name}: {project_db}")
                if project_db_count > 5:
                    click.echo(f"  ... and {project_db_count - 5} more")

        elif output_format == 'json':
            data = {
                'architecture': architecture,
                'status': status,
                'database_files': {
                    'current_db_exists': current_db_exists,
                    'vm_registry_exists': vm_registry_exists,
                    'environment_registry_exists': env_registry_exists,
                    'project_database_count': project_db_count
                },
                'project_databases': [str(db) for db in project_databases]
            }
            click.echo(json.dumps(data, indent=2))

        # Recommendations
        if architecture == "legacy":
            click.echo(f"\n💡 Recommendation: Run 'adare migrate run' to migrate to new architecture")
        elif architecture == "global_registry":
            click.echo(f"\n✅ You're using the new global registry architecture!")

    except Exception as e:
        click.echo(f"❌ Error checking migration status: {e}", err=True)
        log.exception("Error checking migration status")
        exit(1)


@migrate.command()
@click.argument('backup_path', type=click.Path(exists=True, path_type=Path))
@click.confirmation_option(prompt='This will restore from backup and overwrite current data. Continue?')
def restore_backup(backup_path: Path):
    """Restore from a migration backup."""
    try:
        import shutil
        from adare.config.database import get_database_location
        from adare.config.configdirectory import APPDATA_DIR

        current_db_path = get_database_location()

        # Backup current state before restore
        if current_db_path.exists():
            backup_current = current_db_path.parent / f"{current_db_path.stem}_pre_restore_backup.db"
            shutil.copy2(current_db_path, backup_current)
            click.echo(f"📁 Backed up current database to: {backup_current}")

        # Restore from backup
        shutil.copy2(backup_path, current_db_path)

        # Remove global registries if they exist
        vm_registry = APPDATA_DIR / 'vm_registry.db'
        env_registry = APPDATA_DIR / 'environment_registry.db'

        if vm_registry.exists():
            vm_registry.unlink()
            click.echo("🗑️  Removed VM registry")

        if env_registry.exists():
            env_registry.unlink()
            click.echo("🗑️  Removed environment registry")

        # Remove project databases
        project_databases = list(Path().rglob('*/.adare/project.db'))
        for project_db in project_databases:
            project_db.unlink()
            click.echo(f"🗑️  Removed project database: {project_db}")

        click.echo(f"\n✅ Successfully restored from backup: {backup_path}")
        click.echo(f"   Current database restored to legacy architecture")

    except Exception as e:
        click.echo(f"❌ Restore failed: {e}", err=True)
        log.exception("Restore from backup failed")
        exit(1)


if __name__ == '__main__':
    migrate()