# internal imports
from adare.config.database import get_database_location
from pathlib import Path
import shutil
import os

# configure logging
import logging
log = logging.getLogger(__name__)


def exec_manage_reset_db(arguments):
    """Reset the database."""
    # get database location
    database_location = get_database_location()
    # remove database
    if database_location.exists():
        log.info(f'removing database {database_location}')
        database_location.unlink()


def exec_manage_reset_vm(arguments):
    """Reset all VMs in the system."""
    from adare.backend.vm.commands import clear_all_vms, list_all_vms
    
    try:
        # Show what will be deleted
        vms = list_all_vms()
        print(f"⚠️  This will delete ALL {len(vms)} VMs from the system!")
        
        if vms:
            print("\nVMs to be deleted:")
            for vm in vms[:10]:  # Show max 10 VMs
                if hasattr(vm, 'name'):  # VM object
                    name = vm.name
                    vm_id = vm.id
                else:  # Dict
                    name = vm['name']
                    vm_id = vm['id']
                print(f"  - {name} ({vm_id})")
            
            if len(vms) > 10:
                print(f"  ... and {len(vms) - 10} more")
        else:
            print("No VMs found to delete")
            return
            
        # Ask for confirmation
        if not arguments.force:
            response = input("\nAre you sure you want to delete all VMs? (yes/no): ").strip().lower()
            if response not in ['yes', 'y']:
                print("Operation cancelled.")
                return
        
        # Delete VMs
        print("\nDeleting VMs...")
        results = clear_all_vms(force=True)
        
        # Show simple results
        print(f"✅ Successfully deleted: {results['deleted_count']} VMs")
        if results['failed_count'] > 0:
            print(f"❌ Failed to delete: {results['failed_count']} VMs")
            for error in results['failed_vms'][:3]:
                print(f"  - {error}")
        
    except Exception as e:
        log.error(f"Failed to clear VMs: {e}")
        print(f"Error: {e}")


def exec_manage_vm_runtime_refresh(arguments):
    """Force refresh VM runtime files in project directories."""
    from adare.backend.project.database import get_all_projects

    try:
        projects = get_all_projects()
        total_refreshed = 0

        for project in projects:
            project_path = Path(project['path'])

            # Refresh project-level vm_runtime cache
            project_vm_runtime = project_path / 'vm_runtime'
            if project_vm_runtime.exists():
                print(f"Removing project VM runtime cache: {project_vm_runtime}")
                shutil.rmtree(project_vm_runtime)
                total_refreshed += 1

                # Recreate empty directory for next project operations
                project_vm_runtime.mkdir()

        print(f"✅ Refreshed {total_refreshed} VM runtime caches")
        print("VM runtime files will be recreated on next experiment run")

    except Exception as e:
        log.error(f"Failed to refresh VM runtime: {e}")
        print(f"Error: {e}")


def exec_manage_vm_runtime_clean(arguments):
    """Remove all cached VM runtime files from projects."""
    from adare.backend.project.database import get_all_projects

    try:
        projects = get_all_projects()
        total_cleaned = 0
        total_size = 0

        for project in projects:
            project_path = Path(project['path'])

            # Clean project-level vm_runtime cache
            project_vm_runtime = project_path / 'vm_runtime'
            if project_vm_runtime.exists():
                # Calculate size before deletion
                size = sum(f.stat().st_size for f in project_vm_runtime.rglob('*') if f.is_file())
                total_size += size

                print(f"Removing project VM runtime cache: {project_vm_runtime}")
                shutil.rmtree(project_vm_runtime)
                total_cleaned += 1

        size_mb = total_size / (1024 * 1024)
        print(f"✅ Cleaned {total_cleaned} VM runtime caches")
        print(f"💾 Freed {size_mb:.1f} MB of disk space")

    except Exception as e:
        log.error(f"Failed to clean VM runtime: {e}")
        print(f"Error: {e}")


def exec_manage_vm_runtime_status(arguments):
    """Show status of VM runtime caches."""
    from adare.backend.project.database import get_all_projects
    from adare.config.configdirectory import ADAREVM_DIR, ADARELIB_DIR

    try:
        projects = get_all_projects()
        total_caches = 0
        total_size = 0
        outdated_caches = 0

        # Get source modification times
        adarevm_source_time = _get_latest_mtime(ADAREVM_DIR) if ADAREVM_DIR.exists() else 0
        adarelib_source_time = _get_latest_mtime(ADARELIB_DIR) if ADARELIB_DIR.exists() else 0

        print("VM Runtime Cache Status")
        print("=" * 40)
        print(f"Source adarevm:  {ADAREVM_DIR}")
        print(f"Source adarelib: {ADARELIB_DIR}")
        print()

        for project in projects:
            project_path = Path(project['path'])

            project_caches = 0
            project_outdated = 0

            # Check project-level vm_runtime cache
            project_vm_runtime = project_path / 'vm_runtime'
            if project_vm_runtime.exists():
                # Calculate size
                size = sum(f.stat().st_size for f in project_vm_runtime.rglob('*') if f.is_file())
                total_size += size
                project_caches += 1
                total_caches += 1

                # Check if outdated
                cache_time = _get_latest_mtime(project_vm_runtime)
                if cache_time < max(adarevm_source_time, adarelib_source_time):
                    project_outdated += 1
                    outdated_caches += 1


            if project_caches > 0:
                status = f"({project_outdated} outdated)" if project_outdated > 0 else "(up-to-date)"
                print(f"📁 {project['name']}: {project_caches} caches {status}")

        size_mb = total_size / (1024 * 1024)
        print()
        print(f"Total: {total_caches} VM runtime caches using {size_mb:.1f} MB")
        if outdated_caches > 0:
            print(f"⚠️  {outdated_caches} caches are outdated (run 'adare manage vm-runtime refresh' to update)")
        else:
            print("✅ All caches are up-to-date")

    except Exception as e:
        log.error(f"Failed to get VM runtime status: {e}")
        print(f"Error: {e}")


def exec_manage_vm_runtime_init(arguments):
    """Initialize VM runtime files in project directories that are missing them."""
    from adare.backend.project.database import get_all_projects
    from adare.backend.project.directory import ProjectDirectory

    try:
        projects = get_all_projects()
        total_initialized = 0

        for project in projects:
            project_path = Path(project['path'])
            project_vm_runtime = project_path / 'vm_runtime'

            # Check if project vm_runtime needs initialization
            needs_init = False
            if not project_vm_runtime.exists():
                print(f"Project VM runtime missing: {project['name']}")
                needs_init = True
            elif not (project_vm_runtime / 'adarevm').exists() or not (project_vm_runtime / 'adarelib').exists():
                print(f"Project VM runtime incomplete: {project['name']}")
                needs_init = True

            if needs_init:
                try:
                    project_dir = ProjectDirectory(project_path)
                    project_dir.copy_vm_runtime_files()
                    print(f"✅ Initialized VM runtime for project: {project['name']}")
                    total_initialized += 1
                except Exception as e:
                    print(f"❌ Failed to initialize VM runtime for {project['name']}: {e}")

        if total_initialized == 0:
            print("✅ All project VM runtime caches are already initialized")
        else:
            print(f"✅ Initialized {total_initialized} project VM runtime caches")

    except Exception as e:
        log.error(f"Failed to initialize VM runtime: {e}")
        print(f"Error: {e}")


def _get_latest_mtime(directory: Path) -> float:
    """Get the latest modification time in a directory tree."""
    if not directory.exists():
        return 0.0

    latest = 0.0
    for root, dirs, files in os.walk(directory):
        # Skip __pycache__ directories
        dirs[:] = [d for d in dirs if d != '__pycache__']

        for file in files:
            if file.endswith('.pyc'):
                continue
            file_path = Path(root) / file
            try:
                mtime = file_path.stat().st_mtime
                latest = max(latest, mtime)
            except (OSError, PermissionError):
                continue
    return latest

