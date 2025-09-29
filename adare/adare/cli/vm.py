# internal imports
from adare.backend.basics import determine_projectdirectory
from adare.exceptions import NoProjectFoundError


# configure logging
import logging
log = logging.getLogger(__name__)


def exec_vm_list(arguments):
    """List all VMs and instances in the system."""
    from adare.frontend.terminal.vm_list import print_vm_and_instances_list
    print_vm_and_instances_list()


def exec_vm_info(arguments):
    """Get detailed information about a VM or instance (auto-detected)."""
    from adare.frontend.terminal.vm import print_vm_or_instance_info
    print_vm_or_instance_info(arguments.vm_id)


def exec_vm_list_snapshots(arguments):
    """List all snapshots, optionally filtered by VM instance."""
    from adare.frontend.terminal.vm import print_all_snapshots
    print_all_snapshots(arguments.instance_id)


def exec_vm_delete_snapshot(arguments):
    """Delete a single snapshot from a specific VM instance."""
    from adare.backend.vm.snapshot_manager import SnapshotManager
    from adare.database.api.vm import VmApi

    try:
        # Get VM instance record from database
        with VmApi() as api:
            instance = api.get_vm_instance_by_id(arguments.instance_id)
            if not instance:
                log.error(f"VM instance with ID '{arguments.instance_id}' not found")
                return

            # Get the parent VM record
            vm_record = api.get_vm_by_id(instance.vm_id)
            if not vm_record:
                log.error(f"Parent VM with ID '{instance.vm_id}' not found")
                return

        # Initialize snapshot manager
        snapshot_manager = SnapshotManager()

        # Delete the snapshot
        success, msg = snapshot_manager._delete_snapshot(vm_record, arguments.snapshot_name)

        if success:
            print(f"Successfully deleted snapshot '{arguments.snapshot_name}' from VM instance '{instance.instance_name}'")
        else:
            print(f"Failed to delete snapshot '{arguments.snapshot_name}' from VM instance '{instance.instance_name}'\nReason: {msg}")

    except Exception as e:
        log.error(f"Error deleting snapshot '{arguments.snapshot_name}' from VM instance '{arguments.instance_id}': {e}")
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


async def exec_vm_instance_remove(arguments):
    """Remove VM instances based on criteria."""
    from adare.backend.vm.instance_manager import cleanup_vm_instance, remove_all_instances
    from adare.frontend.terminal.vm_instances import print_vm_instance_cleanup_results

    try:
        if arguments.instance_id:
            # Remove specific instance by ULID
            # Validate ULID format
            if not _is_valid_ulid(arguments.instance_id):
                log.error(f"Invalid instance ID format: {arguments.instance_id}. Expected ULID string.")
                return

            await cleanup_vm_instance(arguments.instance_id)
            print_vm_instance_cleanup_results([arguments.instance_id], "specific instance")
        elif arguments.all:
            # Remove all stopped instances
            if not _confirm_removal("all stopped instances"):
                log.info("Operation cancelled by user")
                return

            removed_instances = await remove_all_instances()
            print_vm_instance_cleanup_results(removed_instances, "all stopped instances")
        elif arguments.experiment_id:
            # Remove instances for specific experiment
            from adare.backend.vm.commands import cleanup_vm_instances_for_experiment
            await cleanup_vm_instances_for_experiment(arguments.experiment_id)
            print_vm_instance_cleanup_results([arguments.experiment_id], "experiment instances")
        else:
            log.error("No removal criteria specified. Use --instance-id, --all, or --experiment-id")

    except Exception as e:
        log.error(f"Failed to remove VM instances: {e}")


def _is_valid_ulid(ulid_string):
    """Validate ULID format."""
    import re
    # ULID format: 26 characters, base32 encoded (0-9, A-Z excluding I, L, O, U)
    ulid_pattern = r'^[0-9A-HJKMNP-TV-Z]{26}$'
    return bool(re.match(ulid_pattern, ulid_string))


def _confirm_removal(target):
    """Ask user for confirmation before destructive operations."""
    try:
        response = input(f"Are you sure you want to remove {target}? This cannot be undone. [y/N]: ")
        return response.lower() in ['y', 'yes']
    except (EOFError, KeyboardInterrupt):
        return False


def exec_vm_instance_usage(arguments):
    """Show VM instance usage statistics."""
    from adare.frontend.terminal.vm_instances import print_vm_instance_usage
    print_vm_instance_usage()