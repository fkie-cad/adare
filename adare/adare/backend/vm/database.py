"""
VM database operations.

Thin layer over the database API for VM-related operations.
Keeps database logic separate from file management logic.
"""

from pathlib import Path
from typing import Optional
import logging

from adare.database.api.vm import VmApi
from adare.database.models.global_models import Vm
from adare.backend.vm.exceptions import VMNotFoundError

log = logging.getLogger(__name__)




def get_vm_by_hash(file_hash: str, fields: list[str] = None) -> Optional[Vm] | dict | None:
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
    with VmApi() as api:
        vm = api.get_vm_by_hash(file_hash)
        if not vm:
            return None
        
        # Return full object for backward compatibility
        if fields is None:
            return vm
        
        # Extract requested fields
        result = {}
        for field in fields:
            if field == 'id':
                result['id'] = vm.id
            elif field == 'name':
                result['name'] = vm.name
            elif field == 'file':
                result['file'] = vm.file
            elif field == 'hash':
                result['hash'] = vm.hash
            elif field == 'description':
                result['description'] = vm.description
            elif field == 'osinfo':
                result['osinfo'] = vm.osinfo
            else:
                log.warning(f'Unknown field requested: {field}. Available: id, name, file, hash, description, osinfo')
        
        return result


def get_vm_by_name(name: str, fields: list[str] = None) -> Optional[Vm] | dict | None:
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
    with VmApi() as api:
        vm = api.get_vm_by_name(name)
        if not vm:
            return None
        
        # Return full object for backward compatibility
        if fields is None:
            return vm
        
        # Extract requested fields
        result = {}
        for field in fields:
            if field == 'id':
                result['id'] = vm.id
            elif field == 'name':
                result['name'] = vm.name
            elif field == 'file':
                result['file'] = vm.file
            elif field == 'hash':
                result['hash'] = vm.hash
            elif field == 'description':
                result['description'] = vm.description
            elif field == 'osinfo':
                result['osinfo'] = vm.osinfo
            else:
                log.warning(f'Unknown field requested: {field}. Available: id, name, file, hash, description, osinfo')
        
        return result


def create_vm(project_path: Path, name: str, file_path: Path, file_hash: str, description: str = '', 
              os_platform: str = '', os_type: str = '', os_distribution: str = '', 
              os_version: str = '', os_language: str = '', os_architecture: str = 'x86_64',
              silent: bool = False, fields: list[str] = None) -> Vm | dict:
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
        fields: Optional list of fields to extract. If None, returns full object.
        
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
            silent=silent
        )
        
        # Return full object for backward compatibility
        if fields is None:
            return vm
        
        # Extract requested fields
        result = {}
        for field in fields:
            if field == 'id':
                result['id'] = vm.id
            elif field == 'name':
                result['name'] = vm.name
            elif field == 'file':
                result['file'] = vm.file
            elif field == 'hash':
                result['hash'] = vm.hash
            elif field == 'description':
                result['description'] = vm.description
            elif field == 'osinfo':
                result['osinfo'] = vm.osinfo
            else:
                log.warning(f'Unknown field requested: {field}. Available: id, name, file, hash, description, osinfo')
        
        return result


def get_vm_by_vbox_uuid(vbox_uuid: str, fields: list[str] = None) -> Optional[Vm] | dict | None:
    """
    Get VM by VirtualBox UUID - NEW for snapshot workflow.
    
    Args:
        vbox_uuid: VirtualBox VM UUID
        fields: Optional list of fields to extract. If None, returns full object.
        
    Returns:
        VM: Full object if fields=None
        dict: VM data if fields specified
        None: If VM not found
    """
    with VmApi() as api:
        vm = api.get_vm_by_vbox_uuid(vbox_uuid)
        if not vm:
            return None
        
        # Return full object for backward compatibility
        if fields is None:
            return vm
        
        # Extract requested fields
        result = {}
        for field in fields:
            if field == 'id':
                result['id'] = vm.id
            elif field == 'name':
                result['name'] = vm.name
            elif field == 'file':
                result['file'] = vm.file
            elif field == 'hash':
                result['hash'] = vm.hash
            elif field == 'description':
                result['description'] = vm.description
            elif field == 'vbox_uuid':
                result['vbox_uuid'] = vm.vbox_uuid
            elif field == 'base_snapshot_name':
                result['base_snapshot_name'] = vm.base_snapshot_name
            elif field == 'import_status':
                result['import_status'] = vm.import_status
            elif field == 'osinfo':
                result['osinfo'] = vm.osinfo
            else:
                log.warning(f'Unknown field requested: {field}. Available: id, name, file, hash, description, vbox_uuid, base_snapshot_name, import_status, osinfo')
        
        return result


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
    from adare.virtualbox.api import VirtualBoxVM
    
    # Create VM using standard method
    vm = create_vm(
        project_path=project_path, name=name, file_path=file_path, file_hash=file_hash,
        description=description, os_platform=os_platform, os_type=os_type, 
        os_distribution=os_distribution, os_version=os_version, os_language=os_language,
        os_architecture=os_architecture, silent=silent
    )
    
    # Attempt to capture VirtualBox UUID after VM creation
    if capture_uuid_after_import and isinstance(vm, Vm):
        try:
            vbox_uuid = VirtualBoxVM.get_vm_uuid_by_name(vm.name)
            if vbox_uuid:
                # Update the VM with the captured UUID
                with VmApi() as api:
                    success = api.update_vm_uuid_and_snapshot_info(
                        vm.id, 
                        vbox_uuid=vbox_uuid,
                        base_snapshot_name=f"adare_base_{file_hash[:8]}",
                        use_snapshots=True
                    )
                if success:
                    log.info(f"Captured VirtualBox UUID for VM '{vm.name}': {vbox_uuid}")
                else:
                    log.error(f"Failed to update UUID in database for VM '{vm.name}'")
            else:
                log.warning(f"Could not capture VirtualBox UUID for VM '{vm.name}' - may not be imported yet")
        except Exception as e:
            log.warning(f"Failed to capture UUID for VM '{vm.name}': {e}")
    
    # Return according to fields parameter
    if fields is None:
        return vm
    
    # Extract requested fields from updated VM
    updated_vm = get_vm_by_name(name, fields=fields)
    return updated_vm if updated_vm else vm


def get_vm_by_id(vm_id: str, fields: list[str] = None) -> Optional[Vm] | dict | None:
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
    from adare.database.api.vm import VmApi
    
    with VmApi() as api:
        vm = api.get_vm_by_id(vm_id)
        if not vm:
            return None
        
        # Return full object for backward compatibility
        if fields is None:
            return vm
        
        # Extract requested fields
        result = {}
        for field in fields:
            if field == 'id':
                result['id'] = vm.id
            elif field == 'name':
                result['name'] = vm.name
            elif field == 'file':
                result['file'] = vm.file
            elif field == 'hash':
                result['hash'] = vm.hash
            elif field == 'description':
                result['description'] = vm.description
            # Add other fields as needed
        
        return result


def get_vm_data(vm_id: str = None, name: str = None, file_hash: str = None) -> dict | None:
    """Get full VM data - convenience function for common case."""
    if vm_id:
        return get_vm_by_id(vm_id, fields=['id', 'name', 'file', 'hash', 'description', 'osinfo'])
    elif name:
        return get_vm_by_name(name, fields=['id', 'name', 'file', 'hash', 'description', 'osinfo'])
    elif file_hash:
        return get_vm_by_hash(file_hash, fields=['id', 'name', 'file', 'hash', 'description', 'osinfo'])
    else:
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
    import asyncio
    from pathlib import Path
    from adare.virtualbox.api import VirtualBoxVM
    from adare.database.api.vm import VmApi
    
    # Check if a VM with the same name already exists in VirtualBox
    original_vm_name = vm.name
    vbox_vm_name = vm.name  # This will be the name used in VirtualBox
    
    try:
        existing_uuid = VirtualBoxVM.get_vm_uuid_by_name(vbox_vm_name)
        if existing_uuid:
            # Generate unique VM name for VirtualBox to avoid conflicts
            import time
            import random
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
            except:
                log.debug(f"Could not get OS info from environment {environment_ulid}, using default")
        
        # Create VirtualBoxVM instance and import using the unique name
        from adare.virtualbox.api import VirtualBoxManager
        from adare.config import get_vm_credentials
        from adare.backend.vm.exceptions import VMImportError
        manager = VirtualBoxManager()
        username, password = get_vm_credentials(guest_os)
        vbox_vm = VirtualBoxVM(vbox_vm_name, guest_os, manager, username, password)

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
        
        # Capture UUID after successful import using the VirtualBox VM name
        if capture_uuid_after_import:
            vbox_uuid = VirtualBoxVM.get_vm_uuid_by_name(vbox_vm_name)
            if vbox_uuid:
                # Update the VM with the captured UUID and actual VirtualBox name
                with VmApi() as api:
                    # If we used a different name in VirtualBox, update the database name too
                    if vbox_vm_name != original_vm_name:
                        log.info(f"Updating VM database name from '{original_vm_name}' to '{vbox_vm_name}' to match VirtualBox")
                        api.update_vm_name(vm.id, vbox_vm_name)
                    
                    success = api.update_vm_uuid_and_snapshot_info(
                        vm.id, 
                        vbox_uuid=vbox_uuid,
                        base_snapshot_name=f"adare_base_{vm.hash[:8]}",
                        use_snapshots=True
                    )
                if success:
                    log.info(f"Successfully imported VM '{vbox_vm_name}' with UUID: {vbox_uuid}")
                    vm = get_vm_by_id(vm.id)  # Refresh with updated data
                else:
                    log.error(f"Failed to update UUID in database for VM '{vbox_vm_name}'")
            else:
                log.warning(f"Could not capture UUID for VM '{vbox_vm_name}' after import")
        
    except Exception as e:
        log.error(f"Failed to import VM '{vbox_vm_name}' to VirtualBox: {e}", exc_info=True)
        raise
    
    return vm


def get_vm_summary(vm_id: str = None, name: str = None, file_hash: str = None) -> dict | None:
    """Get basic VM info - lighter version."""
    if vm_id:
        log.warning("get_vm_summary by ID not implemented - use name or hash")
        return None
    elif name:
        return get_vm_by_name(name, fields=['id', 'name', 'description'])
    elif file_hash:
        return get_vm_by_hash(file_hash, fields=['id', 'name', 'description'])
    else:
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
    with VmApi() as api:
        vms = api.get_all_vms()
        
        if fields is None:
            return vms
        
        # Extract requested fields
        results = []
        for vm in vms:
            result = {}
            for field in fields:
                if field == 'id':
                    result['id'] = vm.id
                elif field == 'name':
                    result['name'] = vm.name
                elif field == 'file':
                    result['file'] = vm.file
                elif field == 'hash':
                    result['hash'] = vm.hash
                elif field == 'description':
                    result['description'] = vm.description
                elif field == 'vbox_uuid':
                    result['vbox_uuid'] = getattr(vm, 'vbox_uuid', None)
                elif field == 'osinfo':
                    result['osinfo'] = vm.osinfo
                else:
                    log.warning(f'Unknown field requested: {field}')
            results.append(result)
        
        return results


def get_vms_by_environment(environment_ulid: str) -> list:
    """
    Get VMs associated with a specific environment.
    
    Args:
        environment_ulid: Environment ULID
        
    Returns:
        List of VM objects associated with the environment
    """
    try:
        # Get VMs used by this environment
        from adare.backend.environment import database as env_database
        vm_ids = env_database.get_environment_vm_ids(environment_ulid)
        
        if not vm_ids:
            return []
        
        vms = []
        with VmApi() as api:
            for vm_id in vm_ids:
                vm = api.get_vm_by_id(vm_id)
                if vm:
                    vms.append(vm)
        
        return vms
        
    except Exception as e:
        log.error(f"Failed to get VMs for environment {environment_ulid}: {e}", exc_info=True)
        return []


def delete_all_vms(force: bool = False) -> dict:
    """
    Delete all VMs from the database and VirtualBox.
    
    Args:
        force: If True, force deletion even if VMs are in use
        
    Returns:
        Dictionary with deletion results
    """
    from adare.virtualbox.api import VirtualBoxVM
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
                # Clean up VirtualBox VM and snapshots if it exists
                if hasattr(vm, 'vbox_uuid') and vm.vbox_uuid:
                    try:
                        # Check if VM exists in VirtualBox
                        if VirtualBoxVM.verify_vm_exists_by_uuid(vm.vbox_uuid):
                            log.info(f"Removing VM '{vm.name}' from VirtualBox")
                            
                            # Get VM name from UUID for VirtualBox operations
                            vm_name = VirtualBoxVM.get_vm_name_by_uuid(vm.vbox_uuid)
                            if vm_name:
                                # Remove VM from VirtualBox (this also removes snapshots)
                                from adare.virtualbox.api import VirtualBoxManager
                                manager = VirtualBoxManager()
                                vbox_vm = VirtualBoxVM(vm_name, "", manager, "dummy", "dummy")
                                vbox_vm.delete_vm()
                                log.info(f"Successfully removed VM '{vm.name}' from VirtualBox")
                        else:
                            log.debug(f"VM '{vm.name}' not found in VirtualBox - only cleaning database")
                    except Exception as vbox_error:
                        log.warning(f"Failed to remove VM '{vm.name}' from VirtualBox: {vbox_error}")
                
                # Delete from database
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
        
        from adare.virtualbox.api import VirtualBoxVM
        
        for vm in vms:
            try:
                # Clean up VirtualBox VM and snapshots if it exists
                if hasattr(vm, 'vbox_uuid') and vm.vbox_uuid:
                    try:
                        # Check if VM exists in VirtualBox
                        if VirtualBoxVM.verify_vm_exists_by_uuid(vm.vbox_uuid):
                            log.info(f"Removing VM '{vm.name}' from VirtualBox")
                            
                            # Get VM name from UUID for VirtualBox operations
                            vm_name = VirtualBoxVM.get_vm_name_by_uuid(vm.vbox_uuid)
                            if vm_name:
                                # Remove VM from VirtualBox (this also removes snapshots)
                                from adare.virtualbox.api import VirtualBoxManager
                                manager = VirtualBoxManager()
                                vbox_vm = VirtualBoxVM(vm_name, "", manager, "dummy", "dummy")
                                vbox_vm.delete_vm()
                                log.info(f"Successfully removed VM '{vm.name}' from VirtualBox")
                    except Exception as vbox_error:
                        log.warning(f"Failed to remove VM '{vm.name}' from VirtualBox: {vbox_error}")
                
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
        quiet=quiet
    )