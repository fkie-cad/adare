# internal imports
from adare.config.database import get_database_location

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

