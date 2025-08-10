# internal imports
from adare.backend.basics import determine_projectdirectory
from adare.exceptions import NoProjectFoundError


# configure logging
import logging
log = logging.getLogger(__name__)


def exec_vm_list(arguments):
    """List all VMs in the system."""
    from adare.frontend.terminal.vm_list import print_vm_list
    print_vm_list()


def exec_vm_info(arguments):
    """Get detailed information about a specific VM."""
    from adare.frontend.terminal.vm import print_vm_info
    print_vm_info(arguments.vm_id)


async def exec_vm_delete(arguments):
    """Delete a specific VM."""
    from adare.backend.vm.commands import delete_vm
    from adare.frontend.terminal.vm_cleanup import print_vm_delete_success, print_vm_delete_failure
    
    try:
        success = await delete_vm(arguments.vm_id, force=arguments.force)
        
        if success:
            print_vm_delete_success(arguments.vm_id)
        else:
            print_vm_delete_failure(arguments.vm_id, "Unknown error")
            
    except Exception as e:
        print_vm_delete_failure(arguments.vm_id, str(e))


def exec_vm_delete_snapshot(arguments):
    """Delete a single snapshot from a specific VM."""
    from adare.backend.vm.snapshot_manager import SnapshotManager
    from adare.database.api.vm import VmApi
    
    try:
        # Get VM record from database
        with VmApi() as api:
            vm_record = api.get_vm_by_id(arguments.vm_id)
            if not vm_record:
                log.error(f"VM with ID '{arguments.vm_id}' not found")
                return
        
        # Initialize snapshot manager
        snapshot_manager = SnapshotManager()
        
        # Delete the snapshot
        success, msg = snapshot_manager._delete_snapshot(vm_record, arguments.snapshot_name)
        
        if success:
            print(f"Successfully deleted snapshot '{arguments.snapshot_name}' from VM '{vm_record.name}'")
        else:
            print(f"Failed to delete snapshot '{arguments.snapshot_name}' from VM '{vm_record.name}'\nReason: {msg}")
            
    except Exception as e:
        log.error(f"Error deleting snapshot '{arguments.snapshot_name}' from VM '{arguments.vm_id}': {e}")
        print(f"Error: {str(e)}")


def exec_vm_clear_all(arguments):
    """Clear all VMs from the system."""
    from adare.backend.vm.commands import clear_all_vms
    from adare.frontend.terminal.vm_cleanup import (
        print_vm_clear_all_confirmation, print_vm_clear_all_results
    )
    
    if not arguments.force:
        print_vm_clear_all_confirmation()
        return
    
    try:
        results = clear_all_vms(force=arguments.force)
        print_vm_clear_all_results(results)
            
    except Exception as e:
        log.error(f"Failed to clear VMs: {e}")


def exec_vm_clear_by_environment(arguments):
    """Clear VMs associated with a specific environment."""
    from adare.backend.vm.commands import clear_vms_by_environment
    from adare.frontend.terminal.vm_cleanup import (
        print_vm_clear_environment_confirmation, print_vm_clear_environment_results
    )
    
    if not arguments.force:
        print_vm_clear_environment_confirmation(arguments.environment_ulid)
        return
    
    try:
        results = clear_vms_by_environment(arguments.environment_ulid, force=arguments.force)
        print_vm_clear_environment_results(results, arguments.environment_ulid)
            
    except Exception as e:
        log.error(f"Failed to clear environment VMs: {e}")