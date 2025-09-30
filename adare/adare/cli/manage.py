# internal imports
from adare.config.database import get_database_location, get_global_database_location
from adare.database.init import initialize_database_system, validate_database_integrity, repair_database_system, clean_install_database_system
from pathlib import Path
import shutil
import os

# configure logging
import logging
log = logging.getLogger(__name__)


def exec_manage_reset_db(arguments):
    """Reset the database."""
    # get database location (legacy - now resets global database)
    database_location = get_global_database_location()
    # remove database
    if database_location.exists():
        log.info(f'removing global database {database_location}')
        database_location.unlink()
        print(f"Global database reset: {database_location}")
    else:
        print("No global database found to reset")


def exec_manage_init_db(arguments):
    """Initialize the database system."""
    print("Initializing database system...")

    try:
        results = initialize_database_system()

        if results['global_db_initialized']:
            print(f"✅ Global database initialized: {results['global_db_location']}")
        else:
            print("❌ Failed to initialize global database")
            for error in results['errors']:
                print(f"  Error: {error}")
            return

        print("✅ Database system initialization completed successfully")

    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        log.error(f"Database initialization error: {e}")


def exec_manage_db_status(arguments):
    """Check database system status."""
    from adare.run import get_formatter_from_context

    formatter, output_file, dual_output = get_formatter_from_context()

    try:
        status = validate_database_integrity()

        if dual_output or formatter.format_type.value != 'rich':
            # Structured output
            formatter.print_or_save(status, output_file, dual_output)
        else:
            # Rich console output
            print("Checking database system status...")
            print(f"Global database exists: {'✅' if status['global_db_exists'] else '❌'}")
            print(f"Global database accessible: {'✅' if status['global_db_accessible'] else '❌'}")
            print(f"System valid: {'✅' if status['valid'] else '❌'}")

            if status['errors']:
                print("\nErrors found:")
                for error in status['errors']:
                    print(f"  ❌ {error}")

            if status['valid']:
                print("\n✅ Database system is healthy")
            else:
                print("\n❌ Database system has issues")

    except Exception as e:
        print(f"❌ Status check failed: {e}")
        log.error(f"Database status check error: {e}")


def exec_manage_repair_db(arguments):
    """Repair the database system."""
    print("Starting database system repair...")

    try:
        results = repair_database_system()

        if results['actions_taken']:
            print("Actions taken:")
            for action in results['actions_taken']:
                print(f"  ✅ {action}")

        if results['errors']:
            print("Errors encountered:")
            for error in results['errors']:
                print(f"  ❌ {error}")

        if results['repaired']:
            print("✅ Database system repair completed successfully")
        else:
            print("❌ Database system repair failed")

    except Exception as e:
        print(f"❌ Database repair failed: {e}")
        log.error(f"Database repair error: {e}")


def exec_manage_clean_install_db(arguments):
    """Perform clean database installation."""
    print("⚠️  WARNING: This will delete all existing database data!")

    if not arguments.force:
        response = input("Are you sure you want to proceed? (yes/no): ").strip().lower()
        if response != 'yes':
            print("Operation cancelled")
            return

    print("Starting clean database installation...")

    try:
        results = clean_install_database_system()

        if results['actions_taken']:
            print("Actions taken:")
            for action in results['actions_taken']:
                print(f"  ✅ {action}")

        if results['errors']:
            print("Errors encountered:")
            for error in results['errors']:
                print(f"  ❌ {error}")

        if results['installed']:
            print("✅ Clean database installation completed successfully")
        else:
            print("❌ Clean database installation failed")

    except Exception as e:
        print(f"❌ Clean installation failed: {e}")
        log.error(f"Clean installation error: {e}")


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



