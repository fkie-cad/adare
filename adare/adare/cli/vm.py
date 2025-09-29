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


async def exec_vm_test(arguments):
    """Test OVA file compatibility with ADARE."""
    from adare.backend.experiment.commands import ova_test
    from pathlib import Path
    import sys
    
    ova_path = Path(arguments.ova_file).resolve()
    
    try:
        log.info("CLAUDE: Starting VM test for OVA file compatibility")
        success = await ova_test(
            ova_file_path=ova_path,
            guest_platform=arguments.platform,
            verbose=arguments.verbose,
            vm_cleanup_mode=getattr(arguments, 'vm_cleanup_mode', 'prompt')
        )
        
        if success:
            print("✅ VM test completed successfully! OVA file is compatible with ADARE.")
            sys.exit(0)
        else:
            print("❌ VM test failed! OVA file may not be compatible with ADARE.")
            sys.exit(1)
            
    except Exception as e:
        log.error(f"VM test error: {e}")
        print(f"❌ VM test failed with error: {e}")
        if arguments.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


# ==========================================
# VM INSTANCE MANAGEMENT COMMANDS
# ==========================================

def exec_vm_list_instances(arguments):
    """List all VM instances in the system."""
    from adare.frontend.terminal.vm_instances import print_vm_instances_list
    print_vm_instances_list()


def exec_vm_instance_info(arguments):
    """Get detailed information about a specific VM instance."""
    from adare.frontend.terminal.vm_instances import print_vm_instance_info
    print_vm_instance_info(arguments.instance_id)


async def exec_vm_instance_cleanup(arguments):
    """Clean up VM instances based on criteria."""
    from adare.backend.vm.instance_manager import cleanup_old_vm_instances, cleanup_vm_instance
    from adare.frontend.terminal.vm_instances import print_vm_instance_cleanup_results

    try:
        if arguments.instance_id:
            # Clean up specific instance
            await cleanup_vm_instance(arguments.instance_id, force=arguments.force)
            print_vm_instance_cleanup_results([arguments.instance_id], "specific instance")
        elif arguments.age_days:
            # Clean up old instances
            old_instances = await cleanup_old_vm_instances(arguments.age_days)
            print_vm_instance_cleanup_results(old_instances, f"instances older than {arguments.age_days} days")
        elif arguments.experiment_id:
            # Clean up instances for specific experiment
            from adare.backend.vm.commands import cleanup_vm_instances_for_experiment
            await cleanup_vm_instances_for_experiment(arguments.experiment_id)
            print_vm_instance_cleanup_results([arguments.experiment_id], "experiment instances")
        else:
            log.error("No cleanup criteria specified. Use --instance-id, --age-days, or --experiment-id")

    except Exception as e:
        log.error(f"Failed to cleanup VM instances: {e}")


def exec_vm_instance_usage(arguments):
    """Show VM instance usage statistics."""
    from adare.frontend.terminal.vm_instances import print_vm_instance_usage
    print_vm_instance_usage()


def exec_vm_port_usage(arguments):
    """Show websocket port usage statistics."""
    from adare.frontend.terminal.vm_instances import print_port_usage_stats
    print_port_usage_stats()