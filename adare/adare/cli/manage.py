# internal imports
# configure logging
import logging

from adare.api import AdareAPI
from adare.console import print_error_message, print_success_message

log = logging.getLogger(__name__)


def _handle_api_error(result) -> None:
    """
    Handle an API error result by printing formatted error message and exiting.

    Args:
        result: Result object with error information
    """
    error = result.error
    print_error_message(
        title=f'{error.code}: {error.message}',
        next_steps=error.solutions
    )
    exit(1)


def exec_manage_reset_db(arguments):
    """Reset the database using AdareAPI."""
    api = AdareAPI()
    result = api.manage.reset_db()

    if result.success:
        if result.data.was_reset:
            print_success_message(
                title='Global database reset successfully!',
                location=str(result.data.location)
            )
        else:
            print("No global database found to reset")
    else:
        _handle_api_error(result)


def exec_manage_init_db(arguments):
    """Initialize the database system using AdareAPI."""
    print("Initializing database system...")

    api = AdareAPI()
    result = api.manage.init_db()

    if result.success:
        if result.data.global_db_initialized:
            print(f"✅ Global database initialized: {result.data.global_db_location}")
            print("✅ Database system initialization completed successfully")
        else:
            print("❌ Failed to initialize global database")
            for error in result.data.errors:
                print(f"  Error: {error}")
    else:
        _handle_api_error(result)


def exec_manage_db_status(arguments):
    """Check database system status using AdareAPI."""
    from adare.run import get_formatter_from_context

    formatter, output_file, dual_output = get_formatter_from_context()

    api = AdareAPI()
    result = api.manage.get_db_status()

    if result.success:
        status = result.data

        if dual_output or formatter.format_type.value != 'rich':
            # Structured output
            status_dict = {
                'global_db_exists': status.global_db_exists,
                'global_db_accessible': status.global_db_accessible,
                'global_db_location': str(status.global_db_location) if status.global_db_location else None,
                'valid': status.valid,
                'errors': status.errors,
            }
            formatter.print_or_save(status_dict, output_file, dual_output)
        else:
            # Rich console output
            print("Checking database system status...")
            print(f"Global database exists: {'✅' if status.global_db_exists else '❌'}")
            print(f"Global database accessible: {'✅' if status.global_db_accessible else '❌'}")
            print(f"System valid: {'✅' if status.valid else '❌'}")

            if status.errors:
                print("\nErrors found:")
                for error in status.errors:
                    print(f"  ❌ {error}")

            if status.valid:
                print("\n✅ Database system is healthy")
            else:
                print("\n❌ Database system has issues")
    else:
        _handle_api_error(result)


def exec_manage_repair_db(arguments):
    """Repair the database system using AdareAPI."""
    print("Starting database system repair...")

    api = AdareAPI()
    result = api.manage.repair_db()

    if result.success:
        if result.data.actions_taken:
            print("Actions taken:")
            for action in result.data.actions_taken:
                print(f"  ✅ {action}")

        if result.data.errors:
            print("Errors encountered:")
            for error in result.data.errors:
                print(f"  ❌ {error}")

        if result.data.repaired:
            print("✅ Database system repair completed successfully")
        else:
            print("❌ Database system repair failed")
    else:
        _handle_api_error(result)


def exec_manage_clean_install_db(arguments):
    """Perform clean database installation using AdareAPI."""
    print("⚠️  WARNING: This will delete all existing database data!")

    if not arguments.force:
        response = input("Are you sure you want to proceed? (yes/no): ").strip().lower()
        if response != 'yes':
            print("Operation cancelled")
            return

    print("Starting clean database installation...")

    api = AdareAPI()
    result = api.manage.clean_install_db(force=True)

    if result.success:
        if result.data.actions_taken:
            print("Actions taken:")
            for action in result.data.actions_taken:
                print(f"  ✅ {action}")

        if result.data.errors:
            print("Errors encountered:")
            for error in result.data.errors:
                print(f"  ❌ {error}")

        if result.data.installed:
            print("✅ Clean database installation completed successfully")
        else:
            print("❌ Clean database installation failed")
    else:
        _handle_api_error(result)


def exec_manage_reset_vm(arguments):
    """Reset all VMs in the system using AdareAPI."""
    api = AdareAPI()

    # First list VMs to show what will be deleted
    vm_result = api.vm.list_all()
    if vm_result.success:
        vms = vm_result.data
        print(f"⚠️  This will delete ALL {len(vms)} VMs from the system!")

        if vms:
            print("\nVMs to be deleted:")
            for vm in vms[:10]:  # Show max 10 VMs
                print(f"  - {vm.name} ({vm.id})")

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
    result = api.manage.reset_all_vms(force=True)

    if result.success:
        print(f"✅ Successfully deleted: {result.data.deleted_count} VMs")
        if result.data.failed_count > 0:
            print(f"❌ Failed to delete: {result.data.failed_count} VMs")
            for error in result.data.failed_vms[:3]:
                print(f"  - {error}")
    else:
        _handle_api_error(result)


def exec_manage_vm_runtime_refresh(arguments):
    """Refresh VM runtime files in current project using AdareAPI."""
    api = AdareAPI()
    result = api.manage.refresh_vm_runtime()

    if result.success:
        print_success_message(
            title='VM runtime refreshed successfully!',
            location=str(result.data.project_path) if result.data.project_path else None
        )
        print("VM runtime files are now up-to-date")
    else:
        _handle_api_error(result)


def exec_manage_vm_runtime_build(arguments):
    """Build VM runtime wheels in current project using AdareAPI."""
    api = AdareAPI()
    print("Building VM runtime wheels...")
    result = api.manage.build_vm_runtime_wheels()

    if result.success:
        print_success_message(
            title='VM runtime wheels built successfully!',
            location=str(result.data.wheels_dir) if result.data.wheels_dir else None
        )
        if result.data.adarelib_wheel:
            print(f"  - {result.data.adarelib_wheel}")
        if result.data.adarevm_wheel:
            print(f"  - {result.data.adarevm_wheel}")
    else:
        _handle_api_error(result)
