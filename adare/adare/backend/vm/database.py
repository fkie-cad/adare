"""
VM database operations.

Thin layer over the database API for VM-related operations.
Keeps database logic separate from file management logic.
"""

from pathlib import Path
from typing import Optional
import logging

from adare.database.api.vm import VmApi
from adare.database.models.experiment import Vm
from adare.backend.vm.exceptions import VMNotFoundError

log = logging.getLogger(__name__)


def get_vm_by_hash(file_hash: str, project_id: str = None, fields: list[str] = None) -> Optional[Vm] | dict | None:
    """
    Get VM by file hash.
    
    Args:
        file_hash: SHA256 hash of VM file
        project_id: Project ID for scoped lookup (not used yet - VMs are global)
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


def get_vm_by_name(name: str, project_id: str = None, fields: list[str] = None) -> Optional[Vm] | dict | None:
    """
    Get VM by name.
    
    Args:
        name: VM name
        project_id: Project ID for scoped lookup (not used yet - VMs are global)
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


def get_vm_data(vm_id: str = None, name: str = None, file_hash: str = None, project_id: str = None) -> dict | None:
    """Get full VM data - convenience function for common case."""
    if vm_id:
        # Would need get_vm_by_id function
        log.warning("get_vm_data by ID not implemented - use name or hash")
        return None
    elif name:
        return get_vm_by_name(name, project_id, fields=['id', 'name', 'file', 'hash', 'description', 'osinfo'])
    elif file_hash:
        return get_vm_by_hash(file_hash, project_id, fields=['id', 'name', 'file', 'hash', 'description', 'osinfo'])
    else:
        log.error("Must provide vm_id, name, or file_hash")
        return None


def get_vm_summary(vm_id: str = None, name: str = None, file_hash: str = None, project_id: str = None) -> dict | None:
    """Get basic VM info - lighter version."""
    if vm_id:
        log.warning("get_vm_summary by ID not implemented - use name or hash")
        return None
    elif name:
        return get_vm_by_name(name, project_id, fields=['id', 'name', 'description'])
    elif file_hash:
        return get_vm_by_hash(file_hash, project_id, fields=['id', 'name', 'description'])
    else:
        log.error("Must provide vm_id, name, or file_hash")
        return None


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