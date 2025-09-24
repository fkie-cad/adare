"""
CLI commands for global environment registry management.

This module provides command-line interface for managing environments in the global registry,
which can be shared across multiple projects.
"""

import click
import logging
from pathlib import Path
from typing import Optional
from tabulate import tabulate

from adare.database.api.global_registry.environment_registry import EnvironmentRegistryApi
from adare.database.api.global_registry.vm_registry import VmRegistryApi
from adare.database.exceptions import DatabaseError, ValidationError, EntityNotFoundError

log = logging.getLogger(__name__)


@click.group()
def global_environment():
    """Manage global environment registry."""
    pass


@global_environment.command()
@click.argument('name', type=str)
@click.argument('vm_name', type=str)
@click.argument('file_path', type=click.Path(exists=True, path_type=Path))
@click.option('--description', '-d', default='', help='Environment description')
@click.option('--version', default='1.0.0', help='Environment version')
@click.option('--tags', multiple=True, help='Environment tags (can be used multiple times)')
@click.option('--created-by', default='cli_user', help='User who created the environment')
def add(name: str, vm_name: str, file_path: Path, description: str, version: str,
        tags: tuple, created_by: str):
    """Add an environment to the global registry."""
    try:
        # Calculate file hash
        import hashlib
        with open(file_path, 'rb') as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()

        # Find VM in global registry
        with VmRegistryApi() as vm_registry:
            vm = vm_registry.get_vm_by_name(vm_name)
            if not vm:
                click.echo(f"❌ VM '{vm_name}' not found in global registry")
                click.echo("   Use 'adare global-vm list' to see available VMs")
                exit(1)

        with EnvironmentRegistryApi() as env_registry:
            environment = env_registry.create_environment(
                name=name,
                vm_id=vm.id,
                file_path=file_path,
                sha256hash=file_hash,
                description=description,
                tags=list(tags) if tags else None,
                version=version,
                created_by=created_by
            )

        click.echo(f"✅ Successfully added environment '{name}' to global registry")
        click.echo(f"   ID: {environment.id}")
        click.echo(f"   Version: {version}")
        click.echo(f"   VM: {vm_name}")
        click.echo(f"   File: {environment.full_file_path}")
        if tags:
            click.echo(f"   Tags: {', '.join(tags)}")

    except ValidationError as e:
        click.echo(f"❌ Validation error: {e}", err=True)
        exit(1)
    except DatabaseError as e:
        click.echo(f"❌ Database error: {e}", err=True)
        exit(1)
    except Exception as e:
        click.echo(f"❌ Unexpected error: {e}", err=True)
        log.exception("Unexpected error adding environment to global registry")
        exit(1)


@global_environment.command()
@click.option('--format', 'output_format', type=click.Choice(['table', 'json', 'yaml']),
              default='table', help='Output format')
@click.option('--include-vm-info', is_flag=True, help='Include VM information')
@click.option('--vm-filter', help='Filter by VM name')
@click.option('--tag-filter', help='Filter by tag')
def list(output_format: str, include_vm_info: bool, vm_filter: str, tag_filter: str):
    """List all environments in the global registry."""
    try:
        with EnvironmentRegistryApi() as env_registry:
            if vm_filter:
                # First find the VM
                with VmRegistryApi() as vm_registry:
                    vm = vm_registry.get_vm_by_name(vm_filter)
                    if not vm:
                        click.echo(f"❌ VM '{vm_filter}' not found")
                        exit(1)

                environments = env_registry.get_environments_by_vm(vm.id)
            elif tag_filter:
                environments = env_registry.get_environments_by_tag(tag_filter)
            else:
                environments = env_registry.get_all_environments(include_vm_info=include_vm_info)

        if not environments:
            filter_msg = ""
            if vm_filter:
                filter_msg = f" for VM '{vm_filter}'"
            elif tag_filter:
                filter_msg = f" with tag '{tag_filter}'"
            click.echo(f"No environments found in global registry{filter_msg}")
            return

        if output_format == 'table':
            headers = ['Name', 'ID', 'Version', 'VM', 'Size (MB)', 'Usage Count', 'Created']
            rows = []

            for env in environments:
                size_mb = round((env.file_size_bytes or 0) / (1024**2), 2)
                created = env.created_at.strftime('%Y-%m-%d') if env.created_at else 'Unknown'

                # Get VM name
                vm_name = "Unknown"
                if include_vm_info and env.vm:
                    vm_name = env.vm.name
                elif env.vm_id:
                    # Quick lookup
                    with VmRegistryApi() as vm_registry:
                        vm = vm_registry.get_vm_by_id(env.vm_id)
                        if vm:
                            vm_name = vm.name

                rows.append([
                    env.name,
                    env.id[:8] + '...',
                    env.version or '1.0.0',
                    vm_name,
                    f"{size_mb:.1f}",
                    env.usage_count,
                    created
                ])

            click.echo(tabulate(rows, headers=headers, tablefmt='grid'))
            click.echo(f"\nTotal: {len(environments)} environments")

        elif output_format == 'json':
            import json
            env_data = []

            for env in environments:
                data = {
                    'id': env.id,
                    'name': env.name,
                    'description': env.description,
                    'version': env.version,
                    'vm_id': env.vm_id,
                    'file_size_bytes': env.file_size_bytes,
                    'usage_count': env.usage_count,
                    'created_at': env.created_at.isoformat() if env.created_at else None,
                    'file_path': str(env.full_file_path),
                    'tags': env.tag_list
                }

                if include_vm_info and env.vm:
                    data['vm_name'] = env.vm.name

                env_data.append(data)

            click.echo(json.dumps(env_data, indent=2))

        elif output_format == 'yaml':
            import yaml
            env_data = []

            for env in environments:
                data = {
                    'id': env.id,
                    'name': env.name,
                    'description': env.description,
                    'version': env.version,
                    'vm_id': env.vm_id,
                    'file_size_bytes': env.file_size_bytes,
                    'usage_count': env.usage_count,
                    'created_at': env.created_at.isoformat() if env.created_at else None,
                    'file_path': str(env.full_file_path),
                    'tags': env.tag_list
                }

                if include_vm_info and env.vm:
                    data['vm_name'] = env.vm.name

                env_data.append(data)

            click.echo(yaml.dump(env_data, default_flow_style=False))

    except DatabaseError as e:
        click.echo(f"❌ Database error: {e}", err=True)
        exit(1)
    except Exception as e:
        click.echo(f"❌ Unexpected error: {e}", err=True)
        log.exception("Unexpected error listing environments")
        exit(1)


@global_environment.command()
@click.argument('env_identifier', type=str)
@click.option('--by-name', is_flag=True, help='Identify environment by name instead of ID')
@click.option('--include-usage', is_flag=True, help='Include usage information')
def info(env_identifier: str, by_name: bool, include_usage: bool):
    """Show detailed information about an environment."""
    try:
        with EnvironmentRegistryApi() as env_registry:
            if by_name:
                environment = env_registry.get_environment_by_name(env_identifier)
            else:
                environment = env_registry.get_environment_by_id(env_identifier)

            if not environment:
                click.echo(f"❌ Environment '{env_identifier}' not found in global registry")
                exit(1)

            # Get VM information
            vm_name = "Unknown"
            vm_os = "Unknown"
            if environment.vm_id:
                with VmRegistryApi() as vm_registry:
                    vm = vm_registry.get_vm_by_id(environment.vm_id)
                    if vm:
                        vm_name = vm.name
                        vm_os = vm.os_display_name

            # Display environment information
            click.echo(f"🌍 Environment: {environment.name}")
            click.echo(f"   ID: {environment.id}")
            click.echo(f"   Description: {environment.description or 'None'}")
            click.echo(f"   Version: {environment.version or '1.0.0'}")
            click.echo(f"   File: {environment.full_file_path}")
            click.echo(f"   Hash: {environment.sha256hash}")

            size_mb = round((environment.file_size_bytes or 0) / (1024**2), 2)
            click.echo(f"   Size: {size_mb:.1f} MB")

            click.echo(f"\n🖥️  VM Information:")
            click.echo(f"   VM Name: {vm_name}")
            click.echo(f"   VM ID: {environment.vm_id}")
            click.echo(f"   OS: {vm_os}")

            click.echo(f"\n🏷️  Configuration:")
            if environment.tag_list:
                click.echo(f"   Tags: {', '.join(environment.tag_list)}")
            else:
                click.echo("   Tags: None")

            # Show installations if any
            import json
            installations = json.loads(environment.installations or '[]')
            if installations:
                click.echo(f"\n📦 Post-Setup Installations ({len(installations)}):")
                for inst in installations:
                    click.echo(f"   - {inst.get('name', 'Unknown')}: {inst.get('command', 'N/A')}")
                    if inst.get('description'):
                        click.echo(f"     {inst['description']}")
            else:
                click.echo(f"\n📦 Post-Setup Installations: None")

            click.echo(f"\n📊 Usage Statistics:")
            click.echo(f"   Usage Count: {environment.usage_count}")
            last_used = environment.last_used.strftime('%Y-%m-%d %H:%M:%S') if environment.last_used else 'Never'
            click.echo(f"   Last Used: {last_used}")

            click.echo(f"\n📅 Metadata:")
            created_at = environment.created_at.strftime('%Y-%m-%d %H:%M:%S') if environment.created_at else 'Unknown'
            click.echo(f"   Created: {created_at}")
            click.echo(f"   Created By: {environment.created_by or 'Unknown'}")
            if environment.updated_at:
                updated_at = environment.updated_at.strftime('%Y-%m-%d %H:%M:%S')
                click.echo(f"   Updated: {updated_at}")

            # Show versioning info if applicable
            if environment.parent_environment_id:
                click.echo(f"\n🔗 Versioning:")
                click.echo(f"   Parent Environment ID: {environment.parent_environment_id}")

            # Show usage details if requested
            if include_usage:
                usage_records = env_registry.get_environment_usage(environment.id)
                if usage_records:
                    click.echo(f"\n🔗 Project Usage ({len(usage_records)} projects):")
                    for usage in usage_records:
                        click.echo(f"   📁 {usage.project_name or Path(usage.project_path).name}")
                        click.echo(f"      Path: {usage.project_path}")
                        if usage.alias_name:
                            click.echo(f"      Alias: {usage.alias_name}")
                        click.echo(f"      Usage Count: {usage.usage_count}")
                        click.echo(f"      Last Used: {usage.last_used.strftime('%Y-%m-%d %H:%M:%S')}")
                        if usage.usage_notes:
                            click.echo(f"      Notes: {usage.usage_notes}")
                        click.echo()
                else:
                    click.echo("\n🔗 No project usage recorded")

    except EntityNotFoundError as e:
        click.echo(f"❌ {e}", err=True)
        exit(1)
    except DatabaseError as e:
        click.echo(f"❌ Database error: {e}", err=True)
        exit(1)
    except Exception as e:
        click.echo(f"❌ Unexpected error: {e}", err=True)
        log.exception("Unexpected error showing environment info")
        exit(1)


@global_environment.command()
@click.argument('query', type=str)
def search(query: str):
    """Search environments by name, description, or tags."""
    try:
        with EnvironmentRegistryApi() as env_registry:
            environments = env_registry.search_environments(query)

        if not environments:
            click.echo(f"No environments found matching '{query}'")
            return

        click.echo(f"🔍 Found {len(environments)} environment(s) matching '{query}':\n")

        for env in environments:
            click.echo(f"📦 {env.name} (v{env.version or '1.0.0'})")
            click.echo(f"   ID: {env.id}")
            if env.description:
                click.echo(f"   Description: {env.description}")
            if env.tag_list:
                click.echo(f"   Tags: {', '.join(env.tag_list)}")
            click.echo()

    except DatabaseError as e:
        click.echo(f"❌ Database error: {e}", err=True)
        exit(1)
    except Exception as e:
        click.echo(f"❌ Unexpected error: {e}", err=True)
        log.exception("Unexpected error searching environments")
        exit(1)


@global_environment.command()
@click.argument('env_identifier', type=str)
@click.option('--by-name', is_flag=True, help='Identify environment by name instead of ID')
@click.option('--force', is_flag=True, help='Force deletion even if environment is in use')
@click.confirmation_option(prompt='Are you sure you want to delete this environment?')
def delete(env_identifier: str, by_name: bool, force: bool):
    """Delete an environment from the global registry."""
    try:
        with EnvironmentRegistryApi() as env_registry:
            # Get environment to show info before deletion
            if by_name:
                environment = env_registry.get_environment_by_name(env_identifier)
            else:
                environment = env_registry.get_environment_by_id(env_identifier)

            if not environment:
                click.echo(f"❌ Environment '{env_identifier}' not found in global registry")
                exit(1)

            env_id = environment.id
            env_name = environment.name

            # Check usage if not forcing
            if not force:
                usage_records = env_registry.get_environment_usage(env_id)
                if usage_records:
                    click.echo(f"⚠️  Environment '{env_name}' is used by {len(usage_records)} project(s):")
                    for usage in usage_records:
                        click.echo(f"   - {usage.project_name or Path(usage.project_path).name}")
                    click.echo("\nUse --force to delete anyway, or remove environment from projects first.")
                    exit(1)

            # Delete environment
            success = env_registry.delete_environment(env_id, force=force)

            if success:
                click.echo(f"✅ Successfully deleted environment '{env_name}' from global registry")
            else:
                click.echo(f"❌ Failed to delete environment '{env_name}'")
                exit(1)

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
        log.exception("Unexpected error deleting environment")
        exit(1)


@global_environment.command()
@click.argument('parent_env_name', type=str)
@click.argument('new_version', type=str)
@click.argument('file_path', type=click.Path(exists=True, path_type=Path))
@click.option('--description', '-d', help='New version description')
@click.option('--created-by', default='cli_user', help='User who created the version')
def create_version(parent_env_name: str, new_version: str, file_path: Path,
                  description: str, created_by: str):
    """Create a new version of an existing environment."""
    try:
        # Calculate file hash
        import hashlib
        with open(file_path, 'rb') as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()

        with EnvironmentRegistryApi() as env_registry:
            # Find parent environment
            parent_env = env_registry.get_environment_by_name(parent_env_name)
            if not parent_env:
                click.echo(f"❌ Parent environment '{parent_env_name}' not found in global registry")
                exit(1)

            # Create new version
            new_env = env_registry.create_environment_version(
                parent_env_id=parent_env.id,
                new_version=new_version,
                file_path=file_path,
                sha256hash=file_hash,
                description=description,
                created_by=created_by
            )

        click.echo(f"✅ Successfully created version {new_version} of environment '{parent_env_name}'")
        click.echo(f"   New Environment: {new_env.name}")
        click.echo(f"   ID: {new_env.id}")
        click.echo(f"   Parent: {parent_env.name} (v{parent_env.version})")

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
        log.exception("Unexpected error creating environment version")
        exit(1)


@global_environment.command()
@click.option('--threshold-days', default=30, type=int,
              help='Remove environments unused for this many days')
@click.option('--dry-run', is_flag=True, help='Show what would be deleted without deleting')
def cleanup(threshold_days: int, dry_run: bool):
    """Clean up unused environments from the global registry."""
    try:
        with EnvironmentRegistryApi() as env_registry:
            results = env_registry.cleanup_unused_environments(
                threshold_days=threshold_days,
                dry_run=dry_run
            )

        if dry_run:
            click.echo(f"🔍 DRY RUN: Found {results['found_unused']} unused environments")
        else:
            click.echo(f"🧹 Cleanup completed:")
            click.echo(f"   Found: {results['found_unused']} unused environments")
            click.echo(f"   Deleted: {results['deleted']} environments")
            click.echo(f"   Failed: {results['failed']} environments")

        if results['environment_list']:
            click.echo(f"\n📋 {'Would delete' if dry_run else 'Processed'} environments:")
            for env_name in results['environment_list']:
                click.echo(f"   - {env_name}")

        if results['failed'] > 0:
            click.echo(f"\n⚠️  {results['failed']} environments failed to delete")

    except DatabaseError as e:
        click.echo(f"❌ Database error: {e}", err=True)
        exit(1)
    except Exception as e:
        click.echo(f"❌ Unexpected error: {e}", err=True)
        log.exception("Unexpected error during environment cleanup")
        exit(1)


@global_environment.command()
def stats():
    """Show global environment registry statistics."""
    try:
        with EnvironmentRegistryApi() as env_registry:
            stats = env_registry.get_registry_stats()

        click.echo("📊 Global Environment Registry Statistics")
        click.echo("=" * 42)
        click.echo(f"Total environments: {stats['total_environments']}")
        click.echo(f"Projects using environments: {stats['total_projects_using']}")
        click.echo(f"Total storage: {stats['total_storage_mb']:.1f} MB")

        if stats['top_used_environments']:
            click.echo(f"\n🏆 Most Used Environments:")
            for env_info in stats['top_used_environments']:
                click.echo(f"   {env_info['name']}: {env_info['usage_count']} projects")

        if stats['environments_per_vm']:
            click.echo(f"\n🖥️  Environments by VM:")
            for vm_info in stats['environments_per_vm']:
                click.echo(f"   VM {vm_info['vm_id'][:8]}...: {vm_info['environment_count']} environments")

    except DatabaseError as e:
        click.echo(f"❌ Database error: {e}", err=True)
        exit(1)
    except Exception as e:
        click.echo(f"❌ Unexpected error: {e}", err=True)
        log.exception("Unexpected error getting environment registry stats")
        exit(1)


if __name__ == '__main__':
    global_environment()