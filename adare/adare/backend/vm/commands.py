"""
VM command operations.

High-level VM operations for CLI and other interfaces.
"""

from pathlib import Path
from typing import List
import logging

from adare.backend.vm import database as vm_database
from adare.backend.vm.manager import VMFileManager
from adare.backend.vm.exceptions import VMError
from adare.types.environment import EnvironmentMetadata

log = logging.getLogger(__name__)


def load_vm(vm_file: Path, name: str = None, description: str = '', 
           os_platform: str = '', os_type: str = '', os_distribution: str = '', 
           os_version: str = '', os_language: str = '', os_architecture: str = 'x86_64',
           force: bool = False) -> str:
    """
    Load a VM from file into the system.
    
    Args:
        vm_file: Path to VM file
        name: VM name (defaults to filename)
        description: VM description
        os_platform: OS platform (windows, linux, etc.)
        os_type: OS type
        os_distribution: OS distribution
        os_version: OS version
        os_language: OS language
        os_architecture: Architecture (default: x86_64)
        force: If True, overwrite existing VM
        
    Returns:
        VM ID
        
    Raises:
        VMError: If loading fails
    """
    if not name:
        name = vm_file.stem
    
    # Check if VM already exists
    vm_manager = VMFileManager()
    file_hash = vm_manager.calculate_file_hash(vm_file)
    existing_vm = vm_database.get_vm_by_hash(file_hash)
    
    if existing_vm and not force:
        log.info(f"VM with hash {file_hash} already exists: {existing_vm.name}")
        return existing_vm.id
    
    # Load VM
    vm = vm_database.load_vm_from_file(
        file_path=vm_file,
        name=name,
        description=description,
        os_platform=os_platform,
        os_type=os_type,
        os_distribution=os_distribution,
        os_version=os_version,
        os_language=os_language,
        os_architecture=os_architecture,
        silent=False
    )
    
    log.info(f"Successfully loaded VM: {vm.name} (ID: {vm.id})")
    return vm.id


def list_vms() -> List[dict]:
    """
    List available VMs.
        
    Returns:
        List of VM information dictionaries
    """
    # Get all VMs using the database API
    from adare.database.api.vm import VmApi
    with VmApi() as api:
        vms = api.get_all_vms()
        return [{'id': vm.id, 'name': vm.name, 'description': vm.description, 'file': vm.file, 'hash': vm.hash} for vm in vms]


def ensure_vm_available_for_environment(project_path: Path, environment_metadata: EnvironmentMetadata) -> str:
    """
    Ensure VM specified in environment metadata is available in database.
    
    This function handles the complete workflow of:
    1. Resolving VM file path
    2. Calculating hash and checking if VM exists
    3. Importing VM if needed
    
    Args:
        project_path: Path to the project
        environment_metadata: Environment configuration containing VM info
        
    Returns:
        VM ID to use for the environment
        
    Raises:
        VMError: If VM handling fails
        ValueError: If VM configuration is invalid
        FileNotFoundError: If VM file not found
    """
    if not environment_metadata.vm:
        raise ValueError("Environment metadata must specify a VM")
    
    if environment_metadata.vm_type == "path":
        vm_path = Path(environment_metadata.vm)
        if not vm_path.exists():
            raise FileNotFoundError(f"VM file not found: {vm_path}")
    elif environment_metadata.vm_type == "url":
        raise NotImplementedError("URL-based VM import not yet implemented")
    elif environment_metadata.vm_type == "name":
        raise NotImplementedError("Name-based VM import not yet implemented")
    elif environment_metadata.vm_type == "ulid":
        raise NotImplementedError("ULID-based VM import not yet implemented")
    else:
        raise ValueError(f"Unknown vm_type: {environment_metadata.vm_type}")
    
    # Use VM file manager for validation and hash calculation
    vm_manager = VMFileManager()
    log.info(f"Calculating hash for VM file: {vm_path}")
    file_hash = vm_manager.calculate_file_hash(vm_path, silent=False)
    log.info(f"VM file hash: {file_hash}")
    
    # Try to find existing VM by hash
    vm = vm_database.get_vm_by_hash(file_hash)
    if vm:
        log.info(f"VM with hash '{file_hash}' already exists in database (name: '{vm.name}')")
        return vm.id
    
    # VM not found, need to import it
    log.info(f"VM with hash '{file_hash}' not found in database, importing from {vm_path}")
    
    # Create VM entry in database with file copying and OS info from environment metadata
    vm_name = vm_path.stem
    vm = vm_database.create_vm(
        project_path=project_path,
        name=vm_name,
        file_path=vm_path,
        file_hash=file_hash,
        description=f"VM for {environment_metadata.name}",
        os_platform=environment_metadata.os.platform,
        os_type=environment_metadata.os.os,
        os_distribution=environment_metadata.os.distribution,
        os_version=environment_metadata.os.version,
        os_language=environment_metadata.os.language,
        os_architecture=environment_metadata.os.architecture,
        silent=False
    )
    log.info(f"Successfully imported VM '{vm.name}' from {vm_path}")
    return vm.id


def delete_vm(vm_id: str, force: bool = False) -> bool:
    """
    Delete a VM from the system.
    
    Args:
        vm_id: VM ID to delete
        force: If True, force deletion even if in use
        
    Returns:
        True if successfully deleted
        
    Raises:
        VMError: If deletion fails
    """
    # Implementation would use vm_database.delete_vm()
    # This is a placeholder for the command structure
    log.info(f"Would delete VM {vm_id} with force={force}")
    return True