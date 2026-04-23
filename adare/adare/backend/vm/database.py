"""
VM database operations.

Thin layer over the database API for VM-related operations.
Keeps database logic separate from file management logic.
"""

import logging
from pathlib import Path

from adare.database.api.vm import VmApi
from adare.database.models.global_models import Vm

log = logging.getLogger(__name__)




def _get_vm(lookup_fn_name: str, lookup_value, fields: list[str] = None) -> Vm | None | dict | None:
    """
    Internal helper: lookup a VM by any criterion and optionally extract fields.

    Args:
        lookup_fn_name: Name of the VmApi method to call (e.g. 'get_vm_by_hash')
        lookup_value: Value to pass to the lookup method
        fields: Optional list of fields to extract. If None, returns full object.

    Returns:
        VM: Full object if fields=None
        dict: VM data if fields specified
        None: If VM not found
    """
    from adare.database.utils.field_extractor import VM_FIELD_MAP, extract_fields

    with VmApi() as api:
        fn = getattr(api, lookup_fn_name)
        vm = fn(lookup_value)
        if not vm:
            return None
        return extract_fields(vm, fields, VM_FIELD_MAP)


def get_vm_by_hash(file_hash: str, fields: list[str] = None) -> Vm | None | dict | None:
    """
    Get VM by file hash from global database.

    Args:
        file_hash: SHA256 hash of VM file
        fields: Optional list of fields to extract. If None, returns full object.
                Available fields: 'id', 'name', 'file', 'hash', 'description', 'osinfo'

    Returns:
        VM: Full object if fields=None
        dict: VM data if fields specified
        None: If VM not found
    """
    return _get_vm('get_vm_by_hash', file_hash, fields)


def get_vm_by_name(name: str, fields: list[str] = None) -> Vm | None | dict | None:
    """
    Get VM by name from global database.

    Args:
        name: VM name
        fields: Optional list of fields to extract. If None, returns full object.

    Returns:
        VM: Full object if fields=None
        dict: VM data if fields specified
        None: If VM not found
    """
    return _get_vm('get_vm_by_name', name, fields)


def create_vm(project_path: Path, name: str, file_path: Path, file_hash: str, description: str = '',
              os_platform: str = '', os_type: str = '', os_distribution: str = '',
              os_version: str = '', os_language: str = '', os_architecture: str = 'x86_64',
              silent: bool = False, no_copy: bool = False, fields: list[str] = None,
              hypervisor: str = 'virtualbox', force: bool = False) -> Vm | dict:
    """
    Create a new VM entry in the database with file operations.

    Args:
        name: VM name
        file_path: Path to VM file
        file_hash: SHA256 hash of VM file
        description: VM description
        os_platform: OS platform (windows, linux, etc.)
        os_type: OS type
        os_distribution: OS distribution
        os_version: OS version
        os_language: OS language
        os_architecture: Architecture (default: x86_64)
        quiet: If True, suppress progress bars
        no_copy: If True, reference file at original location instead of copying
        fields: Optional list of fields to extract. If None, returns full object.
        hypervisor: Hypervisor type ('virtualbox', 'qemu') - default: 'virtualbox'
        force: If True, overwrite existing VM with same name but different hash

    Returns:
        VM: Full object if fields=None
        dict: VM data if fields specified

    Raises:
        VMError: If creation fails
    """
    with VmApi() as api:
        vm = api.create_vm(
            project_path=project_path,
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
            silent=silent,
            no_copy=no_copy,
            hypervisor=hypervisor,
            force=force
        )


        # Use field extraction utility
        from adare.database.utils.field_extractor import VM_FIELD_MAP, extract_fields
        return extract_fields(vm, fields, VM_FIELD_MAP)




def create_vm_with_uuid_capture(project_path: Path, name: str, file_path: Path, file_hash: str,
                                description: str = '', os_platform: str = '', os_type: str = '',
                                os_distribution: str = '', os_version: str = '', os_language: str = '',
                                os_architecture: str = 'x86_64', silent: bool = False,
                                capture_uuid_after_import: bool = True, fields: list[str] = None) -> Vm | dict:
    """
    Create a new VM entry with UUID capture after VirtualBox import - ENHANCED for snapshot workflow.

    Args:
        All standard create_vm args plus:
        capture_uuid_after_import: If True, attempt to capture VBox UUID after import

    Returns:
        VM with UUID captured if successful
    """

    # Create VM using standard method
    vm = create_vm(
        project_path=project_path, name=name, file_path=file_path, file_hash=file_hash,
        description=description, os_platform=os_platform, os_type=os_type,
        os_distribution=os_distribution, os_version=os_version, os_language=os_language,
        os_architecture=os_architecture, silent=silent
    )

    # Note: UUID capture is now handled at VmInstance level, not Vm level
    # VmInstances are created when experiments run and track actual VirtualBox VMs
    # Return according to fields parameter
    if fields is None:
        return vm

    # Extract requested fields from updated VM
    updated_vm = get_vm_by_name(name, fields=fields)
    return updated_vm if updated_vm else vm


def get_vm_by_id(vm_id: str, fields: list[str] = None) -> Vm | None | dict | None:
    """
    Get VM by database ID.

    Args:
        vm_id: VM database ID
        fields: Optional list of fields to extract. If None, returns full object.

    Returns:
        VM: Full object if fields=None
        dict: VM data if fields specified
        None: If VM not found
    """
    return _get_vm('get_vm_by_id', vm_id, fields)


def get_vm_data(vm_id: str = None, name: str = None, file_hash: str = None) -> dict | None:
    """Get full VM data - convenience function for common case."""
    if vm_id:
        return get_vm_by_id(vm_id, fields=['id', 'name', 'file', 'hash', 'description', 'osinfo'])
    if name:
        return get_vm_by_name(name, fields=['id', 'name', 'file', 'hash', 'description', 'osinfo'])
    if file_hash:
        return get_vm_by_hash(file_hash, fields=['id', 'name', 'file', 'hash', 'description', 'osinfo'])
    log.error("Must provide vm_id, name, or file_hash")
    return None


async def import_vm_to_virtualbox(vm: Vm, capture_uuid_after_import: bool = True, environment_ulid: str = None) -> Vm:
    """
    Import existing VM record to VirtualBox.

    Args:
        vm: VM database record
        capture_uuid_after_import: If True, capture VBox UUID after import

    Returns:
        Updated VM record with UUID
    """
    from pathlib import Path

    from adare.database.api.vm import VmApi
    from adare.hypervisor.virtualbox.vm import VirtualBoxVM

    # Check if a VM with the same name already exists in VirtualBox
    original_vm_name = vm.name
    vbox_vm_name = vm.name  # This will be the name used in VirtualBox

    try:
        existing_uuid = VirtualBoxVM.get_vm_uuid_by_name(vbox_vm_name)
        if existing_uuid:
            # Generate unique VM name for VirtualBox to avoid conflicts
            import random
            import time
            timestamp = int(time.time())
            unique_suffix = f"_{timestamp}_{random.randint(1000, 9999)}"
            vbox_vm_name = f"{original_vm_name}{unique_suffix}"

            log.info(f"VM '{original_vm_name}' already exists in VirtualBox, creating new VM with unique name: '{vbox_vm_name}'")

    except Exception as e:
        log.debug(f"VM '{vbox_vm_name}' not found in VirtualBox, proceeding with import: {e}")

    # Actually import the VM to VirtualBox
    try:
        log.info(f"Importing VM '{vbox_vm_name}' to VirtualBox from file: {vm.file}")
        vm_file = Path(vm.file)

        # Get OS info from environment if available
        guest_os = "Other"
        if environment_ulid:
            try:
                from adare.backend.environment import database as env_db
                guest_os = env_db.get_environment_os(environment_ulid) or "Other"
            except (ImportError, ValueError, KeyError):
                log.debug(f"Could not get OS info from environment {environment_ulid}, using default")

        # Create VirtualBoxVM instance and import using the unique name
        from adare.backend.vm.exceptions import VMImportError
        from adare.config import get_vm_credentials
        from adare.hypervisor.virtualbox.manager import VirtualBoxManager
        manager = VirtualBoxManager()
        username, password = get_vm_credentials(guest_os)
        vbox_vm = VirtualBoxVM(vbox_vm_name, guest_os, manager, username, password, manager.executables)

        # Import VM and capture detailed error output
        try:
            import_result, vbox_output = await vbox_vm.create_from_ovf_or_ova(vm_file, silent=True)
        except Exception as e:
            # If the import method itself raised an exception, extract the error details
            error_msg = str(e)
            raise VMImportError(log, f"VirtualBox import failed: {error_msg}")

        # Check if import was successful
        if import_result != 0:
            # Include actual VirtualBox error output in the error message
            vbox_error = vbox_output.strip() if vbox_output and vbox_output.strip() else "No error details available"
            raise VMImportError(log, f"VirtualBox import failed with return code {import_result}. VirtualBox error: {vbox_error}")

        # Disable time synchronization to prevent VM from syncing with host time
        # await vbox_vm.disable_time_sync(silent=True)  # Commented out - makes clock weird

        # Note: UUID capture is now handled at VmInstance level when creating instances
        # This function imports the base VM template to VirtualBox
        if vbox_vm_name != original_vm_name:
            log.info(f"Updating VM database name from '{original_vm_name}' to '{vbox_vm_name}' to match VirtualBox")
            with VmApi() as api:
                api.update_vm_name(vm.id, vbox_vm_name)
            vm = get_vm_by_id(vm.id)  # Refresh with updated data

        log.info(f"Successfully imported VM '{vbox_vm_name}' to VirtualBox")

    except Exception as e:
        log.error(f"Failed to import VM '{vbox_vm_name}' to VirtualBox: {e}", exc_info=True)
        raise

    return vm


def get_vm_summary(vm_id: str = None, name: str = None, file_hash: str = None) -> dict | None:
    """Get basic VM info - lighter version."""
    if vm_id:
        log.warning("get_vm_summary by ID not implemented - use name or hash")
        return None
    if name:
        return get_vm_by_name(name, fields=['id', 'name', 'description'])
    if file_hash:
        return get_vm_by_hash(file_hash, fields=['id', 'name', 'description'])
    log.error("Must provide vm_id, name, or file_hash")
    return None


def delete_vm(vm_id: str) -> bool:
    """
    Delete a VM from the database.

    Args:
        vm_id: VM database ID

    Returns:
        True if successfully deleted

    Raises:
        VMError: If deletion fails
    """
    from adare.backend.vm.exceptions import VMError

    try:
        with VmApi() as api:
            return api.delete_vm(vm_id)
    except Exception as e:
        log.error(f"Failed to delete VM {vm_id}: {e}", exc_info=True)
        raise VMError(log, f"Failed to delete VM {vm_id}: {e}")


def get_all_vms(fields: list[str] = None) -> list:
    """
    Get all VMs from the database.

    Args:
        fields: Optional list of fields to extract. If None, returns full objects.

    Returns:
        List of VM objects or dictionaries (if fields specified)
    """
    from adare.database.utils.field_extractor import VM_FIELD_MAP, extract_fields

    with VmApi() as api:
        vms = api.get_all_vms()

        if fields is None:
            return vms

        # Use field extraction utility for each VM
        results = [extract_fields(vm, fields, VM_FIELD_MAP) for vm in vms]
        return results


def get_vms_by_environment(environment_ulid: str) -> list:
    """
    Get VMs associated with a specific environment.

    Args:
        environment_ulid: Environment ULID

    Returns:
        List of VM objects associated with the environment
    """
    from sqlalchemy.exc import SQLAlchemyError
    from sqlalchemy.orm import joinedload

    from adare.backend.environment import database as env_database
    from adare.database.models.global_models import Vm

    try:
        # Get VMs used by this environment
        vm_ids = env_database.get_environment_vm_ids(environment_ulid)

        if not vm_ids:
            return []

        # Fix N+1 query: Single query with IN clause and eager loading
        with VmApi() as api:
            vms = api._session.query(Vm).options(
                joinedload(Vm.osinfo)  # Eager load relationships
            ).filter(
                Vm.id.in_(vm_ids)
            ).all()

            # Detach to make them safe for use outside session
            for vm in vms:
                api._session.expunge(vm)

            return vms

    except SQLAlchemyError as e:
        log.error(f"Database error getting VMs for environment {environment_ulid}: {e}", exc_info=True)
        return []
    except OSError as e:
        log.error(f"File system error getting VMs for environment {environment_ulid}: {e}", exc_info=True)
        return []


def delete_all_vms(force: bool = False) -> dict:
    """
    Delete all VMs from the database and VirtualBox.

    Args:
        force: If True, force deletion even if VMs are in use

    Returns:
        Dictionary with deletion results
    """
    from adare.backend.vm.snapshot_manager import SnapshotManager

    results = {
        'deleted_count': 0,
        'failed_count': 0,
        'skipped_count': 0,
        'deleted_vms': [],
        'failed_vms': [],
        'skipped_vms': []
    }

    try:
        all_vms = get_all_vms()
        log.info(f"Found {len(all_vms)} VMs to delete")

        snapshot_manager = SnapshotManager()

        for vm in all_vms:
            try:
                # Delete associated VmInstance records - they will handle VirtualBox cleanup
                # VmInstances track actual VirtualBox VMs, not the abstract Vm model
                from adare.database.api.vm import VmApi
                with VmApi() as api:
                    instances = api.get_vm_instances_by_vm_id(vm.id)
                    if instances:
                        log.info(f"Found {len(instances)} instances for VM '{vm.name}'")
                        from adare.backend.vm.instance_manager import delete_vm_instance
                        for instance in instances:
                            try:
                                delete_vm_instance(instance.id, force=True)
                                log.info(f"Deleted VM instance: {instance.instance_name}")
                            except Exception as inst_error:
                                log.warning(f"Failed to delete instance {instance.instance_name}: {inst_error}")

                # Delete from database (cascade will remove instances)
                delete_vm(vm.id)
                results['deleted_count'] += 1
                results['deleted_vms'].append(vm.name)
                log.info(f"Successfully deleted VM: {vm.name}")

            except Exception as e:
                results['failed_count'] += 1
                results['failed_vms'].append(f"{vm.name}: {str(e)}")
                log.error(f"Failed to delete VM '{vm.name}': {e}")

        log.info(f"VM cleanup completed - deleted: {results['deleted_count']}, failed: {results['failed_count']}")
        return results

    except Exception as e:
        log.error(f"Error during VM cleanup: {e}")
        results['failed_count'] += len(results.get('deleted_vms', [])) + len(results.get('failed_vms', []))
        return results


def delete_vms_by_environment(environment_ulid: str, force: bool = False) -> dict:
    """
    Delete all VMs associated with a specific environment.

    Args:
        environment_ulid: Environment ULID
        force: If True, force deletion even if VMs are in use

    Returns:
        Dictionary with deletion results
    """
    results = {
        'deleted_count': 0,
        'failed_count': 0,
        'skipped_count': 0,
        'deleted_vms': [],
        'failed_vms': [],
        'skipped_vms': []
    }

    try:
        vms = get_vms_by_environment(environment_ulid)
        if not vms:
            log.info(f"No VMs found for environment {environment_ulid}")
            return results

        log.info(f"Found {len(vms)} VMs for environment {environment_ulid}")


        for vm in vms:
            try:
                # Delete associated VmInstance records - they will handle VirtualBox cleanup
                from adare.database.api.vm import VmApi
                with VmApi() as api:
                    instances = api.get_vm_instances_by_vm_id(vm.id)
                    if instances:
                        log.info(f"Found {len(instances)} instances for VM '{vm.name}'")
                        from adare.backend.vm.instance_manager import delete_vm_instance
                        for instance in instances:
                            try:
                                delete_vm_instance(instance.id, force=True)
                                log.info(f"Deleted VM instance: {instance.instance_name}")
                            except Exception as inst_error:
                                log.warning(f"Failed to delete instance {instance.instance_name}: {inst_error}")

                # Delete from database
                delete_vm(vm.id)
                results['deleted_count'] += 1
                results['deleted_vms'].append(vm.name)
                log.info(f"Successfully deleted VM: {vm.name}")

            except Exception as e:
                results['failed_count'] += 1
                results['failed_vms'].append(f"{vm.name}: {str(e)}")
                log.error(f"Failed to delete VM '{vm.name}': {e}")

        log.info(f"Environment VM cleanup completed - deleted: {results['deleted_count']}, failed: {results['failed_count']}")
        return results

    except Exception as e:
        log.error(f"Error during environment VM cleanup: {e}")
        return results


def load_vm_from_file(file_path: Path, name: str = None, description: str = '',
                     os_platform: str = '', os_type: str = '', os_distribution: str = '',
                     os_version: str = '', os_language: str = '', os_architecture: str = 'x86_64',
                     quiet: bool = False) -> Vm:
    """
    Load a VM from file into the database.

    This is a convenience function that delegates to the database API.

    Args:
        file_path: Path to VM file
        name: VM name (defaults to filename without extension)
        description: VM description
        os_platform: OS platform (windows, linux, etc.)
        os_type: OS type
        os_distribution: OS distribution
        os_version: OS version
        os_language: OS language
        os_architecture: Architecture (default: x86_64)
        quiet: If True, suppress progress bars

    Returns:
        Created VM instance
    """
    from adare.database.api.vm import load_vm_from_file as db_load_vm
    return db_load_vm(
        file_path=file_path,
        name=name,
        description=description,
        os_platform=os_platform,
        os_type=os_type,
        os_distribution=os_distribution,
        os_version=os_version,
        os_language=os_language,
        os_architecture=os_architecture,
        silent=quiet
    )
