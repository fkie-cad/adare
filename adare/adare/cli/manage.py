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
    """Refresh VM runtime files in current project, ensuring they are up-to-date."""
    from adare.backend.basics import determine_projectdirectory
    from adare.backend.project.directory import ProjectDirectory
    from adare.exceptions import NoProjectFoundError

    try:
        # Get current project using the same logic as other CLI commands
        project_path = determine_projectdirectory(project_name=None)
        if not project_path:
            raise NoProjectFoundError(log, message='no project directory found')

        project_vm_runtime = project_path / 'vm_runtime'

        # Remove existing vm_runtime if it exists
        if project_vm_runtime.exists():
            print(f"Removing existing VM runtime cache: {project_vm_runtime}")
            shutil.rmtree(project_vm_runtime)

        # Initialize/recreate vm_runtime with fresh files
        try:
            project_dir = ProjectDirectory(project_path)
            project_dir.copy_vm_runtime_files()
            print(f"✅ Refreshed VM runtime for current project")
            print("VM runtime files are now up-to-date")
        except Exception as e:
            print(f"❌ Failed to refresh VM runtime: {e}")

    except Exception as e:
        log.error(f"Failed to refresh VM runtime: {e}")
        print(f"Error: {e}")



