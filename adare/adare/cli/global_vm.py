"""
CLI commands for global VM registry management.

This module provides command-line interface for managing VMs in the global registry,
which can be shared across multiple projects.
"""

import click
import logging
from pathlib import Path
from typing import Optional
from tabulate import tabulate

from adare.database.api.global_registry.vm_registry import VmRegistryApi
from adare.database.exceptions import DatabaseError, ValidationError, EntityNotFoundError

log = logging.getLogger(__name__)


@click.group()
def global_vm():
    """Manage global VM registry."""
    pass


@global_vm.command()
@click.argument('name', type=str)
@click.argument('file_path', type=click.Path(exists=True, path_type=Path))
@click.option('--description', '-d', default='', help='VM description')
@click.option('--os-platform', default='', help='OS platform (windows, linux, macos)')
@click.option('--os-type', default='', help='OS type (workstation, server, embedded)')
@click.option('--os-distribution', default='', help='OS distribution (ubuntu, windows10, centos)')
@click.option('--os-version', default='', help='OS version (22.04, 10.0.19041, 8.4)')
@click.option('--os-language', default='', help='OS language (en-US, de-DE)')
@click.option('--os-architecture', default='x86_64', help='Architecture (x86_64, arm64, i386)')
@click.option('--created-by', default='cli_user', help='User who created the VM')
def add(name: str, file_path: Path, description: str, os_platform: str, os_type: str,
        os_distribution: str, os_version: str, os_language: str, os_architecture: str,
        created_by: str):
    """Add a VM to the global registry."""
    try:
        # Calculate file hash
        import hashlib
        with open(file_path, 'rb') as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()

        with VmRegistryApi() as vm_registry:
            vm = vm_registry.create_vm(
                name=name,
                file_path=file_path,
                file_hash=file_hash,
                description=description,
                os_platform=os_platform,
                os_type=os_type,
                os_distribution=os_distribution,
                os_version=os_version,
                os_language=os_language,
                os_architecture=os_architecture,
                created_by=created_by
            )

        click.echo(f"✅ Successfully added VM '{name}' to global registry")
        click.echo(f"   ID: {vm.id}")
        click.echo(f"   OS: {vm.os_display_name}")
        click.echo(f"   File: {vm.full_file_path}")

    except ValidationError as e:
        click.echo(f"❌ Validation error: {e}", err=True)
        exit(1)
    except DatabaseError as e:
        click.echo(f"❌ Database error: {e}", err=True)
        exit(1)
    except Exception as e:
        click.echo(f"❌ Unexpected error: {e}", err=True)
        log.exception("Unexpected error adding VM to global registry")
        exit(1)


@global_vm.command()
@click.option('--format', 'output_format', type=click.Choice(['table', 'json', 'yaml']),
              default='table', help='Output format')
@click.option('--include-usage', is_flag=True, help='Include usage statistics')
def list(output_format: str, include_usage: bool):
    """List all VMs in the global registry."""
    try:
        with VmRegistryApi() as vm_registry:
            vms = vm_registry.get_all_vms(include_usage_stats=include_usage)

        if not vms:
            click.echo("No VMs found in global registry")
            return

        if output_format == 'table':
            headers = ['Name', 'ID', 'OS', 'Size (GB)', 'Usage Count', 'Created']
            rows = []

            for vm in vms:
                size_gb = round((vm.file_size_bytes or 0) / (1024**3), 2)
                created = vm.created_at.strftime('%Y-%m-%d') if vm.created_at else 'Unknown'

                rows.append([
                    vm.name,
                    vm.id[:8] + '...',
                    vm.os_display_name,
                    f"{size_gb:.1f}",
                    vm.usage_count,
                    created
                ])

            click.echo(tabulate(rows, headers=headers, tablefmt='grid'))
            click.echo(f"\nTotal: {len(vms)} VMs")

        elif output_format == 'json':
            import json
            vm_data = [
                {
                    'id': vm.id,
                    'name': vm.name,
                    'description': vm.description,
                    'os_display_name': vm.os_display_name,
                    'file_size_bytes': vm.file_size_bytes,
                    'usage_count': vm.usage_count,
                    'created_at': vm.created_at.isoformat() if vm.created_at else None,
                    'file_path': str(vm.full_file_path)
                }
                for vm in vms
            ]
            click.echo(json.dumps(vm_data, indent=2))

        elif output_format == 'yaml':
            import yaml
            vm_data = [
                {
                    'id': vm.id,
                    'name': vm.name,
                    'description': vm.description,
                    'os_display_name': vm.os_display_name,
                    'file_size_bytes': vm.file_size_bytes,
                    'usage_count': vm.usage_count,
                    'created_at': vm.created_at.isoformat() if vm.created_at else None,
                    'file_path': str(vm.full_file_path)
                }
                for vm in vms
            ]
            click.echo(yaml.dump(vm_data, default_flow_style=False))

    except DatabaseError as e:
        click.echo(f"❌ Database error: {e}", err=True)
        exit(1)
    except Exception as e:
        click.echo(f"❌ Unexpected error: {e}", err=True)
        log.exception("Unexpected error listing VMs")
        exit(1)


@global_vm.command()
@click.argument('vm_identifier', type=str)
@click.option('--by-name', is_flag=True, help='Identify VM by name instead of ID')
@click.option('--include-usage', is_flag=True, help='Include usage information')
def info(vm_identifier: str, by_name: bool, include_usage: bool):
    """Show detailed information about a VM."""
    try:
        with VmRegistryApi() as vm_registry:
            if by_name:
                vm = vm_registry.get_vm_by_name(vm_identifier)
            else:
                vm = vm_registry.get_vm_by_id(vm_identifier)

            if not vm:
                click.echo(f"❌ VM '{vm_identifier}' not found in global registry")
                exit(1)

            # Display VM information
            click.echo(f"📦 VM: {vm.name}")
            click.echo(f"   ID: {vm.id}")
            click.echo(f"   Description: {vm.description or 'None'}")
            click.echo(f"   File: {vm.full_file_path}")
            click.echo(f"   Hash: {vm.hash}")

            size_gb = round((vm.file_size_bytes or 0) / (1024**3), 2)
            click.echo(f"   Size: {size_gb:.1f} GB")

            click.echo("\n🖥️  OS Information:")
            click.echo(f"   Platform: {vm.os_platform or 'Unknown'}")
            click.echo(f"   Type: {vm.os_type or 'Unknown'}")
            click.echo(f"   Distribution: {vm.os_distribution or 'Unknown'}")
            click.echo(f"   Version: {vm.os_version or 'Unknown'}")
            click.echo(f"   Language: {vm.os_language or 'Unknown'}")
            click.echo(f"   Architecture: {vm.os_architecture or 'Unknown'}")

            click.echo("\n⚙️  Technical Details:")
            click.echo(f"   VirtualBox UUID: {vm.vbox_uuid or 'None'}")
            click.echo(f"   Base Snapshot: {vm.base_snapshot_name or 'None'}")
            click.echo(f"   Import Status: {vm.import_status}")
            click.echo(f"   Use Snapshots: {vm.use_snapshots}")
            last_verified = vm.last_verified.strftime('%Y-%m-%d %H:%M:%S') if vm.last_verified else 'Never'
            click.echo(f"   Last Verified: {last_verified}")

            click.echo("\n📊 Usage Statistics:")
            click.echo(f"   Usage Count: {vm.usage_count}")
            last_used = vm.last_used.strftime('%Y-%m-%d %H:%M:%S') if vm.last_used else 'Never'
            click.echo(f"   Last Used: {last_used}")

            click.echo("\n📅 Metadata:")
            created_at = vm.created_at.strftime('%Y-%m-%d %H:%M:%S') if vm.created_at else 'Unknown'
            click.echo(f"   Created: {created_at}")
            click.echo(f"   Created By: {vm.created_by or 'Unknown'}")
            if vm.updated_at:
                updated_at = vm.updated_at.strftime('%Y-%m-%d %H:%M:%S')
                click.echo(f"   Updated: {updated_at}")

            # Show usage details if requested
            if include_usage:
                usage_records = vm_registry.get_vm_usage(vm.id)
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
        log.exception("Unexpected error showing VM info")
        exit(1)


@global_vm.command()
@click.argument('vm_identifier', type=str)
@click.option('--by-name', is_flag=True, help='Identify VM by name instead of ID')
@click.option('--force', is_flag=True, help='Force deletion even if VM is in use')
@click.confirmation_option(prompt='Are you sure you want to delete this VM?')
def delete(vm_identifier: str, by_name: bool, force: bool):
    """Delete a VM from the global registry."""
    try:
        with VmRegistryApi() as vm_registry:
            # Get VM to show info before deletion
            if by_name:
                vm = vm_registry.get_vm_by_name(vm_identifier)
            else:
                vm = vm_registry.get_vm_by_id(vm_identifier)

            if not vm:
                click.echo(f"❌ VM '{vm_identifier}' not found in global registry")
                exit(1)

            vm_id = vm.id
            vm_name = vm.name

            # Check usage if not forcing
            if not force:
                usage_records = vm_registry.get_vm_usage(vm_id)
                if usage_records:
                    click.echo(f"⚠️  VM '{vm_name}' is used by {len(usage_records)} project(s):")
                    for usage in usage_records:
                        click.echo(f"   - {usage.project_name or Path(usage.project_path).name}")
                    click.echo("\nUse --force to delete anyway, or remove VM from projects first.")
                    exit(1)

            # Delete VM
            success = vm_registry.delete_vm(vm_id, force=force)

            if success:
                click.echo(f"✅ Successfully deleted VM '{vm_name}' from global registry")
            else:
                click.echo(f"❌ Failed to delete VM '{vm_name}'")
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
        log.exception("Unexpected error deleting VM")
        exit(1)


@global_vm.command()
@click.option('--threshold-days', default=30, type=int,
              help='Remove VMs unused for this many days')
@click.option('--dry-run', is_flag=True, help='Show what would be deleted without deleting')
def cleanup(threshold_days: int, dry_run: bool):
    """Clean up unused VMs from the global registry."""
    try:
        with VmRegistryApi() as vm_registry:
            results = vm_registry.cleanup_unused_vms(
                threshold_days=threshold_days,
                dry_run=dry_run
            )

        if dry_run:
            click.echo(f"🔍 DRY RUN: Found {results['found_unused']} unused VMs")
        else:
            click.echo(f"🧹 Cleanup completed:")
            click.echo(f"   Found: {results['found_unused']} unused VMs")
            click.echo(f"   Deleted: {results['deleted']} VMs")
            click.echo(f"   Failed: {results['failed']} VMs")

        if results['vm_list']:
            click.echo(f"\n📋 {'Would delete' if dry_run else 'Processed'} VMs:")
            for vm_name in results['vm_list']:
                click.echo(f"   - {vm_name}")

        if results['failed'] > 0:
            click.echo(f"\n⚠️  {results['failed']} VMs failed to delete")

    except DatabaseError as e:
        click.echo(f"❌ Database error: {e}", err=True)
        exit(1)
    except Exception as e:
        click.echo(f"❌ Unexpected error: {e}", err=True)
        log.exception("Unexpected error during VM cleanup")
        exit(1)


@global_vm.command()
def stats():
    """Show global VM registry statistics."""
    try:
        with VmRegistryApi() as vm_registry:
            stats = vm_registry.get_registry_stats()

        click.echo("📊 Global VM Registry Statistics")
        click.echo("=" * 35)
        click.echo(f"Total VMs: {stats['total_vms']}")
        click.echo(f"Projects using VMs: {stats['total_projects_using']}")
        click.echo(f"Total storage: {stats['total_storage_gb']:.1f} GB")

        if stats['top_used_vms']:
            click.echo(f"\n🏆 Most Used VMs:")
            for vm_info in stats['top_used_vms']:
                click.echo(f"   {vm_info['name']}: {vm_info['usage_count']} projects")

    except DatabaseError as e:
        click.echo(f"❌ Database error: {e}", err=True)
        exit(1)
    except Exception as e:
        click.echo(f"❌ Unexpected error: {e}", err=True)
        log.exception("Unexpected error getting VM registry stats")
        exit(1)


if __name__ == '__main__':
    global_vm()