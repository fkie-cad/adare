# internal imports
from adare.api import AdareAPI
from adare.console import print_success_message, print_error_message


# configure logging
import logging
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


def exec_vm_list(arguments):
    """List all VMs and instances in the system."""
    from adare.frontend.terminal.vm_list import print_vm_and_instances_list
    from adare.run import get_formatter_from_context

    formatter, output_file, dual_output = get_formatter_from_context()
    print_vm_and_instances_list(formatter, output_file, dual_output)


def exec_vm_info(arguments):
    """Get detailed information about a VM or instance (auto-detected)."""
    from adare.frontend.terminal.vm import print_vm_or_instance_info
    from adare.run import get_formatter_from_context

    formatter, output_file, dual_output = get_formatter_from_context()
    print_vm_or_instance_info(arguments.vm_id, formatter, output_file, dual_output)


def exec_vm_list_snapshots(arguments):
    """List all snapshots, optionally filtered by VM instance."""
    from adare.frontend.terminal.vm import print_all_snapshots
    from adare.run import get_formatter_from_context

    formatter, output_file, dual_output = get_formatter_from_context()
    print_all_snapshots(arguments.instance_id, formatter, output_file, dual_output)


def exec_vm_delete_snapshot(arguments):
    """Delete a single snapshot from a specific VM instance using AdareAPI."""
    api = AdareAPI()
    result = api.vm.delete_snapshot(arguments.instance_id, arguments.snapshot_name)

    if result.success:
        print_success_message(
            title=f'Snapshot "{arguments.snapshot_name}" deleted successfully!'
        )
    else:
        _handle_api_error(result)


def exec_vm_clear_all(arguments):
    """Clear all VMs from the system using AdareAPI."""
    from adare.frontend.terminal.vm_cleanup import (
        print_vm_clear_all_confirmation, print_vm_clear_all_results
    )

    if not arguments.force:
        print_vm_clear_all_confirmation()
        return

    api = AdareAPI()
    result = api.vm.clear_all(force=arguments.force)

    if result.success:
        # Convert VmClearResult to dict format expected by print function
        results = {
            'deleted_count': result.data.deleted_count,
            'deleted_vms': result.data.deleted_vms,
            'failed_count': result.data.failed_count,
            'failed_vms': result.data.failed_vms,
        }
        print_vm_clear_all_results(results)
    else:
        _handle_api_error(result)


def exec_vm_clear_by_environment(arguments):
    """Clear VMs associated with a specific environment using AdareAPI."""
    from adare.frontend.terminal.vm_cleanup import (
        print_vm_clear_environment_confirmation, print_vm_clear_environment_results
    )

    if not arguments.force:
        print_vm_clear_environment_confirmation(arguments.environment_ulid)
        return

    api = AdareAPI()
    result = api.vm.clear_by_environment(arguments.environment_ulid, force=arguments.force)

    if result.success:
        # Convert VmClearResult to dict format expected by print function
        results = {
            'deleted_count': result.data.deleted_count,
            'deleted_vms': result.data.deleted_vms,
            'failed_count': result.data.failed_count,
            'failed_vms': result.data.failed_vms,
        }
        print_vm_clear_environment_results(results, arguments.environment_ulid)
    else:
        _handle_api_error(result)


async def exec_vm_test(arguments):
    """Test OVA file compatibility with ADARE using AdareAPI."""
    from adare.core.dto.vm import VmTestRequest
    from pathlib import Path
    import sys

    ova_path = Path(arguments.ova_file).resolve()

    api = AdareAPI()
    result = await api.vm.test_ova(VmTestRequest(
        ova_file_path=ova_path,
        guest_platform=arguments.platform,
        verbose=arguments.verbose,
        vm_cleanup_mode=getattr(arguments, 'vm_cleanup_mode', 'prompt')
    ))

    if result.success:
        if result.data.success:
            print(f"✅ {result.data.message}")
            sys.exit(0)
        else:
            print(f"❌ {result.data.message}")
            sys.exit(1)
    else:
        _handle_api_error(result)


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
    """Remove VM instances based on criteria using AdareAPI."""
    from adare.frontend.terminal.vm_instances import print_vm_instance_cleanup_results

    api = AdareAPI()

    if arguments.instance_id:
        # Remove specific instance by ULID
        # Validate ULID format
        if not _is_valid_ulid(arguments.instance_id):
            print_error_message(
                title="Invalid instance ID format",
                next_steps=[f"Instance ID '{arguments.instance_id}' is not a valid ULID format"]
            )
            return

        result = await api.vm.remove_instance(arguments.instance_id)
        if result.success:
            print_vm_instance_cleanup_results([arguments.instance_id], "specific instance")
        else:
            _handle_api_error(result)

    elif arguments.all:
        # Remove all stopped instances
        if not _confirm_removal("all stopped instances"):
            log.info("Operation cancelled by user")
            return

        result = await api.vm.remove_all_stopped_instances()
        if result.success:
            print_vm_instance_cleanup_results(result.data.removed_instances, "all stopped instances")
        else:
            _handle_api_error(result)

    elif arguments.experiment_id:
        # Remove instances for specific experiment (keep using backend directly for this complex case)
        from adare.backend.vm.commands import cleanup_vm_instances_for_experiment
        await cleanup_vm_instances_for_experiment(arguments.experiment_id)
        print_vm_instance_cleanup_results([arguments.experiment_id], "experiment instances")

    else:
        print_error_message(
            title="No removal criteria specified",
            next_steps=["Use --instance-id, --all, or --experiment-id"]
        )


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
    from adare.run import get_formatter_from_context

    formatter, output_file, dual_output = get_formatter_from_context()
    print_vm_instance_usage(formatter, output_file, dual_output)