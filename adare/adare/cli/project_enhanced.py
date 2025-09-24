"""
Enhanced CLI commands for project management in the new multi-database architecture.

This module provides command-line interface for managing projects that work
with the global registry system for VMs and environments.
"""

import click
import logging
from pathlib import Path
from typing import Optional
from tabulate import tabulate

from adare.database.api.project_database import ProjectDatabaseApi
from adare.database.api.resource_resolver import ResourceResolver
from adare.database.exceptions import DatabaseError, ValidationError, EntityNotFoundError

log = logging.getLogger(__name__)


@click.group()
def project():
    """Manage projects in the new architecture."""
    pass


@project.command()
@click.argument('name', type=str)
@click.argument('path', type=click.Path(path_type=Path), required=False)
@click.option('--description', '-d', default='', help='Project description')
@click.option('--version', default='1.0.0', help='Project version')
def init(name: str, path: Optional[Path], description: str, version: str):
    """Initialize a new project with the new database architecture."""
    try:
        # Use current directory if no path specified
        if path is None:
            path = Path.cwd() / name

        # Create project directory
        path.mkdir(parents=True, exist_ok=True)

        # Initialize project database
        project_db = ProjectDatabaseApi(path)

        # Update project metadata
        project_db.update_project_metadata(
            name=name,
            description=description,
            version=version
        )

        click.echo(f"✅ Successfully initialized project '{name}'")
        click.echo(f"   Location: {path}")
        click.echo(f"   Database: {path / '.adare' / 'project.db'}")
        click.echo(f"\n💡 Next steps:")
        click.echo(f"   - Add global resources: adare project add-vm/add-environment")
        click.echo(f"   - Create experiments: adare project create-experiment")

    except DatabaseError as e:
        click.echo(f"❌ Database error: {e}", err=True)
        exit(1)
    except Exception as e:
        click.echo(f"❌ Unexpected error: {e}", err=True)
        log.exception("Unexpected error initializing project")
        exit(1)


@project.command()
@click.option('--project-path', type=click.Path(exists=True, path_type=Path),
              default=Path.cwd(), help='Project directory path')
def info(project_path: Path):
    """Show project information and statistics."""
    try:
        project_db = ProjectDatabaseApi(project_path)
        stats = project_db.get_project_statistics()

        click.echo(f"📁 Project: {stats['project_name']}")
        click.echo(f"   Path: {stats['project_path']}")
        click.echo(f"   Database: {project_path / '.adare' / 'project.db'}")

        size_mb = round((stats['database_size_bytes'] or 0) / (1024**2), 2)
        click.echo(f"   Database Size: {size_mb:.1f} MB")

        click.echo(f"\n📊 Content Statistics:")
        click.echo(f"   Experiments: {stats['experiments_count']}")
        click.echo(f"   Experiment Runs: {stats['runs_count']}")
        click.echo(f"   Test Function Files: {stats['test_function_files_count']}")
        click.echo(f"   Test Functions: {stats['test_functions_count']}")

        click.echo(f"\n🔗 Global Resources:")
        click.echo(f"   VM References: {stats['global_resource_references']['vm_references']}")
        click.echo(f"   Environment References: {stats['global_resource_references']['environment_references']}")

        # Show recent activity
        if stats['recent_runs']:
            click.echo(f"\n📈 Recent Activity:")
            for run in stats['recent_runs']:
                status_emoji = {"in_progress": "🔄", "success": "✅", "failed": "❌", "warning": "⚠️"}.get(run['status'], "❓")
                duration = f" ({run['duration_seconds']:.1f}s)" if run['duration_seconds'] else ""
                click.echo(f"   {status_emoji} {run['experiment_name']} - {run['started_at'][:16]}{duration}")

        # Show resource summary
        resolver = ResourceResolver(project_path)
        resource_summary = resolver.get_project_resource_summary()

        if resource_summary['vm_resources']['vms']:
            click.echo(f"\n🖥️  VMs in use:")
            for vm in resource_summary['vm_resources']['vms']:
                click.echo(f"   - {vm['alias']} ({vm['os_display_name']}) - {vm['file_size_gb']:.1f} GB")

        if resource_summary['environment_resources']['environments']:
            click.echo(f"\n🌍 Environments in use:")
            for env in resource_summary['environment_resources']['environments']:
                click.echo(f"   - {env['alias']} v{env['version']} - {env['file_size_mb']:.1f} MB")

        if resource_summary['resolution_errors']:
            click.echo(f"\n⚠️  Resource Resolution Issues:")
            for error in resource_summary['resolution_errors']:
                click.echo(f"   - {error}")

    except DatabaseError as e:
        click.echo(f"❌ Database error: {e}", err=True)
        exit(1)
    except Exception as e:
        click.echo(f"❌ Unexpected error: {e}", err=True)
        log.exception("Unexpected error getting project info")
        exit(1)


@project.command()
@click.argument('vm_name', type=str)
@click.option('--project-path', type=click.Path(exists=True, path_type=Path),
              default=Path.cwd(), help='Project directory path')
@click.option('--alias', help='Project-specific alias for the VM')
@click.option('--notes', help='Usage notes')
def add_vm(vm_name: str, project_path: Path, alias: str, notes: str):
    """Add a global VM to this project."""
    try:
        # Find VM in global registry
        from adare.database.api.global_registry.vm_registry import VmRegistryApi
        with VmRegistryApi() as vm_registry:
            vm = vm_registry.get_vm_by_name(vm_name)
            if not vm:
                click.echo(f"❌ VM '{vm_name}' not found in global registry")
                click.echo("   Use 'adare global-vm list' to see available VMs")
                exit(1)

            # Track usage
            vm_registry.track_vm_usage(
                vm_id=vm.id,
                project_path=str(project_path),
                project_name=project_path.name,
                alias_name=alias,
                usage_notes=notes
            )

        # Add reference to project
        project_db = ProjectDatabaseApi(project_path)
        reference = project_db.add_global_resource_reference(
            resource_type='vm',
            global_resource_id=vm.id,
            project_alias=alias,
            usage_notes=notes
        )

        click.echo(f"✅ Successfully added VM '{vm_name}' to project")
        click.echo(f"   VM ID: {vm.id}")
        click.echo(f"   Alias: {alias or vm_name}")
        click.echo(f"   OS: {vm.os_display_name}")
        if notes:
            click.echo(f"   Notes: {notes}")

    except ValidationError as e:
        click.echo(f"❌ Validation error: {e}", err=True)
        exit(1)
    except DatabaseError as e:
        click.echo(f"❌ Database error: {e}", err=True)
        exit(1)
    except Exception as e:
        click.echo(f"❌ Unexpected error: {e}", err=True)
        log.exception("Unexpected error adding VM to project")
        exit(1)


@project.command()
@click.argument('env_name', type=str)
@click.option('--project-path', type=click.Path(exists=True, path_type=Path),
              default=Path.cwd(), help='Project directory path')
@click.option('--alias', help='Project-specific alias for the environment')
@click.option('--notes', help='Usage notes')
def add_environment(env_name: str, project_path: Path, alias: str, notes: str):
    """Add a global environment to this project."""
    try:
        # Find environment in global registry
        from adare.database.api.global_registry.environment_registry import EnvironmentRegistryApi
        with EnvironmentRegistryApi() as env_registry:
            environment = env_registry.get_environment_by_name(env_name)
            if not environment:
                click.echo(f"❌ Environment '{env_name}' not found in global registry")
                click.echo("   Use 'adare global-environment list' to see available environments")
                exit(1)

            # Track usage
            env_registry.track_environment_usage(
                env_id=environment.id,
                project_path=str(project_path),
                project_name=project_path.name,
                alias_name=alias,
                usage_notes=notes
            )

        # Add reference to project
        project_db = ProjectDatabaseApi(project_path)
        reference = project_db.add_global_resource_reference(
            resource_type='environment',
            global_resource_id=environment.id,
            project_alias=alias,
            usage_notes=notes
        )

        click.echo(f"✅ Successfully added environment '{env_name}' to project")
        click.echo(f"   Environment ID: {environment.id}")
        click.echo(f"   Alias: {alias or env_name}")
        click.echo(f"   Version: {environment.version}")
        if notes:
            click.echo(f"   Notes: {notes}")

    except ValidationError as e:
        click.echo(f"❌ Validation error: {e}", err=True)
        exit(1)
    except DatabaseError as e:
        click.echo(f"❌ Database error: {e}", err=True)
        exit(1)
    except Exception as e:
        click.echo(f"❌ Unexpected error: {e}", err=True)
        log.exception("Unexpected error adding environment to project")
        exit(1)


@project.command()
@click.option('--project-path', type=click.Path(exists=True, path_type=Path),
              default=Path.cwd(), help='Project directory path')
@click.option('--resource-type', type=click.Choice(['vm', 'environment', 'all']),
              default='all', help='Type of resources to list')
def list_resources(project_path: Path, resource_type: str):
    """List global resources used by this project."""
    try:
        resolver = ResourceResolver(project_path)
        summary = resolver.get_project_resource_summary()

        click.echo(f"📁 Project: {project_path.name}")
        click.echo(f"   Path: {summary['project_path']}\n")

        if resource_type in ['vm', 'all'] and summary['vm_resources']['vms']:
            click.echo(f"🖥️  VMs ({summary['vm_resources']['count']}):")

            headers = ['Alias', 'Name', 'OS', 'Size (GB)', 'Usage Count']
            rows = []

            for vm in summary['vm_resources']['vms']:
                rows.append([
                    vm['alias'],
                    vm['name'],
                    vm['os_display_name'],
                    f"{vm['file_size_gb']:.1f}",
                    vm['usage_count']
                ])

            click.echo(tabulate(rows, headers=headers, tablefmt='grid'))
            click.echo()

        if resource_type in ['environment', 'all'] and summary['environment_resources']['environments']:
            click.echo(f"🌍 Environments ({summary['environment_resources']['count']}):")

            headers = ['Alias', 'Name', 'Version', 'Size (MB)', 'Usage Count']
            rows = []

            for env in summary['environment_resources']['environments']:
                rows.append([
                    env['alias'],
                    env['name'],
                    env['version'],
                    f"{env['file_size_mb']:.1f}",
                    env['usage_count']
                ])

            click.echo(tabulate(rows, headers=headers, tablefmt='grid'))
            click.echo()

        if resource_type in ['vm', 'all'] and not summary['vm_resources']['vms']:
            click.echo("🖥️  No VMs in use")

        if resource_type in ['environment', 'all'] and not summary['environment_resources']['environments']:
            click.echo("🌍 No environments in use")

        if summary['resolution_errors']:
            click.echo("⚠️  Resource Resolution Issues:")
            for error in summary['resolution_errors']:
                click.echo(f"   - {error}")

    except DatabaseError as e:
        click.echo(f"❌ Database error: {e}", err=True)
        exit(1)
    except Exception as e:
        click.echo(f"❌ Unexpected error: {e}", err=True)
        log.exception("Unexpected error listing project resources")
        exit(1)


@project.command()
@click.argument('experiment_name', type=str)
@click.argument('env_name', type=str)
@click.option('--project-path', type=click.Path(exists=True, path_type=Path),
              default=Path.cwd(), help='Project directory path')
@click.option('--description', '-d', default='', help='Experiment description')
@click.option('--playbook-file', help='Path to playbook file (relative to project)')
@click.option('--metadata-file', help='Path to metadata file (relative to project)')
@click.option('--is-primary', is_flag=True, help='Make this the primary environment for the experiment')
def create_experiment(experiment_name: str, env_name: str, project_path: Path,
                     description: str, playbook_file: str, metadata_file: str, is_primary: bool):
    """Create a new experiment in this project."""
    try:
        project_db = ProjectDatabaseApi(project_path)

        # Find environment reference
        env_refs = project_db.get_global_resource_references('environment')
        env_ref = None
        for ref in env_refs:
            resolver = ResourceResolver(project_path)
            resolved_env = resolver.resolve_environment_reference(ref.global_resource_id)
            if resolved_env and (resolved_env['name'] == env_name or ref.project_alias == env_name):
                env_ref = ref
                break

        if not env_ref:
            click.echo(f"❌ Environment '{env_name}' not found in project")
            click.echo("   Use 'adare project add-environment' to add it first")
            exit(1)

        # Create experiment
        experiment = project_db.create_experiment(
            name=experiment_name,
            description=description,
            playbook_file=playbook_file,
            metadata_file=metadata_file
        )

        # Add environment reference to experiment
        exp_env_ref = project_db.add_environment_to_experiment(
            experiment_name=experiment_name,
            global_environment_id=env_ref.global_resource_id,
            environment_alias=env_name,
            is_primary=is_primary
        )

        click.echo(f"✅ Successfully created experiment '{experiment_name}'")
        click.echo(f"   ID: {experiment.id}")
        click.echo(f"   Environment: {env_name}")
        if description:
            click.echo(f"   Description: {description}")
        if playbook_file:
            click.echo(f"   Playbook: {playbook_file}")
        if is_primary:
            click.echo(f"   Primary Environment: Yes")

    except ValidationError as e:
        click.echo(f"❌ Validation error: {e}", err=True)
        exit(1)
    except EntityNotFoundError as e:
        click.echo(f"❌ {e}", err=True)
        exit(1)
    except DatabaseError as e:
        click.echo(f"❌ Database error: {e}", err=True)
        exit(1)
    except Exception as e:
        click.echo(f"❌ Unexpected error: {e}", err=True)
        log.exception("Unexpected error creating experiment")
        exit(1)


@project.command()
@click.option('--project-path', type=click.Path(exists=True, path_type=Path),
              default=Path.cwd(), help='Project directory path')
def list_experiments(project_path: Path):
    """List all experiments in this project."""
    try:
        project_db = ProjectDatabaseApi(project_path)
        experiments = project_db.get_all_experiments(include_environment_refs=True)

        if not experiments:
            click.echo("No experiments found in this project")
            return

        click.echo(f"📁 Project: {project_path.name}")
        click.echo(f"   Experiments: {len(experiments)}\n")

        headers = ['Name', 'Description', 'Environments', 'Last Run', 'Status']
        rows = []

        for exp in experiments:
            env_count = len(exp.environment_refs)
            env_names = [ref.environment_alias or ref.global_environment_id[:8] + '...'
                        for ref in exp.environment_refs[:2]]  # Show first 2
            if env_count > 2:
                env_names.append(f"... +{env_count - 2}")

            env_display = ', '.join(env_names) if env_names else 'None'
            last_run = exp.last_run.strftime('%Y-%m-%d %H:%M') if exp.last_run else 'Never'

            rows.append([
                exp.name,
                (exp.description[:30] + '...') if exp.description and len(exp.description) > 30 else exp.description or '',
                env_display,
                last_run,
                exp.status
            ])

        click.echo(tabulate(rows, headers=headers, tablefmt='grid'))

    except DatabaseError as e:
        click.echo(f"❌ Database error: {e}", err=True)
        exit(1)
    except Exception as e:
        click.echo(f"❌ Unexpected error: {e}", err=True)
        log.exception("Unexpected error listing experiments")
        exit(1)


@project.command()
@click.option('--project-path', type=click.Path(exists=True, path_type=Path),
              default=Path.cwd(), help='Project directory path')
def validate_resources(project_path: Path):
    """Validate that all project resource references are resolvable."""
    try:
        resolver = ResourceResolver(project_path)
        validation_results = resolver.validate_project_references()

        click.echo(f"🔍 Resource Validation for {project_path.name}")
        click.echo("=" * 50)

        # VM validation results
        total_vm_refs = validation_results['valid_vm_references'] + validation_results['invalid_vm_references']
        if total_vm_refs > 0:
            click.echo(f"\n🖥️  VMs:")
            click.echo(f"   Valid: {validation_results['valid_vm_references']}")
            click.echo(f"   Invalid: {validation_results['invalid_vm_references']}")

            if validation_results['invalid_vm_references'] > 0:
                click.echo("   ❌ Issues found")
            else:
                click.echo("   ✅ All VM references are valid")
        else:
            click.echo(f"\n🖥️  VMs: No VM references found")

        # Environment validation results
        total_env_refs = validation_results['valid_environment_references'] + validation_results['invalid_environment_references']
        if total_env_refs > 0:
            click.echo(f"\n🌍 Environments:")
            click.echo(f"   Valid: {validation_results['valid_environment_references']}")
            click.echo(f"   Invalid: {validation_results['invalid_environment_references']}")

            if validation_results['invalid_environment_references'] > 0:
                click.echo("   ❌ Issues found")
            else:
                click.echo("   ✅ All environment references are valid")
        else:
            click.echo(f"\n🌍 Environments: No environment references found")

        # Show missing resources
        if validation_results['missing_resources']:
            click.echo(f"\n❌ Missing Resources:")
            for resource in validation_results['missing_resources']:
                click.echo(f"   - {resource}")

        # Show errors
        if validation_results['errors']:
            click.echo(f"\n⚠️  Validation Errors:")
            for error in validation_results['errors']:
                click.echo(f"   - {error}")

        # Overall status
        total_valid = validation_results['valid_vm_references'] + validation_results['valid_environment_references']
        total_invalid = validation_results['invalid_vm_references'] + validation_results['invalid_environment_references']

        if total_invalid == 0:
            click.echo(f"\n✅ All resource references are valid!")
        else:
            click.echo(f"\n❌ Found {total_invalid} invalid resource references")
            exit(1)

    except DatabaseError as e:
        click.echo(f"❌ Database error: {e}", err=True)
        exit(1)
    except Exception as e:
        click.echo(f"❌ Unexpected error: {e}", err=True)
        log.exception("Unexpected error validating resources")
        exit(1)


@project.command()
@click.option('--project-path', type=click.Path(exists=True, path_type=Path),
              default=Path.cwd(), help='Project directory path')
@click.option('--older-than-days', default=30, type=int,
              help='Clean up data older than this many days')
@click.option('--cleanup-runs', is_flag=True, help='Clean up old experiment runs')
@click.option('--cleanup-logs', is_flag=True, help='Clean up old log files')
@click.option('--dry-run', is_flag=True, help='Show what would be cleaned without cleaning')
def cleanup(project_path: Path, older_than_days: int, cleanup_runs: bool, cleanup_logs: bool, dry_run: bool):
    """Clean up old project data."""
    try:
        project_db = ProjectDatabaseApi(project_path)
        results = project_db.cleanup_project_data(
            older_than_days=older_than_days,
            cleanup_runs=cleanup_runs,
            cleanup_logs=cleanup_logs,
            dry_run=dry_run
        )

        click.echo(f"🧹 Project Cleanup Results")
        click.echo("=" * 30)
        click.echo(f"Mode: {'DRY RUN' if dry_run else 'EXECUTION'}")
        click.echo(f"Threshold: {older_than_days} days")

        if cleanup_runs:
            click.echo(f"Experiment runs: {results['runs_deleted']} {'would be deleted' if dry_run else 'deleted'}")

        if cleanup_logs:
            click.echo(f"Log files: {results['logs_deleted']} {'would be deleted' if dry_run else 'deleted'}")

        if results['space_freed_bytes'] > 0:
            space_mb = round(results['space_freed_bytes'] / (1024**2), 2)
            click.echo(f"Space freed: {space_mb:.1f} MB")

        if results['errors']:
            click.echo(f"\n⚠️  Errors:")
            for error in results['errors']:
                click.echo(f"   - {error}")

        if dry_run and (results['runs_deleted'] > 0 or results['logs_deleted'] > 0):
            click.echo(f"\n💡 Run without --dry-run to actually perform cleanup")

    except DatabaseError as e:
        click.echo(f"❌ Database error: {e}", err=True)
        exit(1)
    except Exception as e:
        click.echo(f"❌ Unexpected error: {e}", err=True)
        log.exception("Unexpected error during project cleanup")
        exit(1)


if __name__ == '__main__':
    project()