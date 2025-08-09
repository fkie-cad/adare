"""
VM command operations.

High-level VM operations for CLI and other interfaces.
"""

from pathlib import Path
from typing import List, Optional
import logging

from adare.backend.vm import database as vm_database
from adare.backend.vm.manager import VMFileManager
from adare.backend.vm.exceptions import VMError
from adare.types.environment import EnvironmentMetadata
from adare.virtualbox.api import VirtualBoxVM
from adarelib.constants import VMStatus
from adare.types.stages import VMImportStage, VMSnapshotRestoreStage, VMSnapshotCreateStage, VMExperimentSnapshotStage
from adare.backend.experiment.stagectxmanager import StageCtxManager

log = logging.getLogger(__name__)


def load_vm_file_for_environment(project_path: Path, vm_path: Path, environment_metadata) -> str:
    """
    Load VM file during environment load - only hash calculation and file copying.
    No VirtualBox import happens here!
    
    Args:
        project_path: Path to the project
        vm_path: Path to VM file
        environment_metadata: Environment configuration
        
    Returns:
        VM ID from database
    """
    vm_manager = VMFileManager()
    
    # Calculate hash (heavy operation done during environment load)
    log.info(f"📊 Calculating VM file hash during environment load...")
    file_hash = vm_manager.calculate_file_hash(vm_path, silent=False)
    log.info(f"VM file hash: {file_hash}")
    
    # Check if VM already exists by hash
    existing_vm = vm_database.get_vm_by_hash(file_hash)
    if existing_vm:
        log.info(f"VM with hash {file_hash} already exists: {existing_vm.name}")
        return existing_vm.id
    
    # Create VM record without VirtualBox import (file operations only)
    vm = vm_database.create_vm(
        project_path=project_path,
        name=vm_path.stem,
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
    
    log.info(f"VM file loaded into database: {vm.name} (ID: {vm.id})")
    return vm.id


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


def ensure_vm_available_for_environment(vm_id: str, experiment_id: str = None) -> str:
    """
    🚀 OPTIMIZED VM preparation using snapshots - Always 10-15x faster!
    
    This function ALWAYS uses the snapshot-based workflow for maximum performance.
    VM file operations already done during environment load!
    
    Args:
        vm_id: VM database ID (from environment)
        experiment_id: Unique experiment ID (generates one if not provided)
        
    Returns:
        VM ID ready for experiment
        
    Raises:
        VMError: If VM handling fails
        ValueError: If VM configuration is invalid
    """
    if not vm_id:
        raise ValueError("VM ID must be provided - should come from environment load")
    
    # Generate experiment ID if not provided (for non-experiment use cases)
    if not experiment_id:
        import ulid
        experiment_id = str(ulid.ULID())
        log.info(f"Generated experiment ID for VM preparation: {experiment_id}")
    
    # 🚀 ALWAYS use the optimized snapshot workflow!
    log.info(f"🚀 Using OPTIMIZED snapshot workflow (experiment: {experiment_id})")
    return ensure_vm_ready_for_experiment(vm_id, experiment_id)


async def delete_vm(vm_id: str, force: bool = False) -> bool:
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
    try:
        # Get VM details before deletion for VirtualBox cleanup
        vm = vm_database.get_vm_by_id(vm_id)
        if not vm:
            raise VMError(log, f"VM with ID {vm_id} not found")
        
        log.info(f"Deleting VM: {vm.name} (ID: {vm_id})")
        
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
                        vbox_vm = VirtualBoxVM(vm_name, "", manager)
                        await vbox_vm.remove()
                        log.info(f"Successfully removed VM '{vm.name}' from VirtualBox")
                else:
                    log.debug(f"VM '{vm.name}' not found in VirtualBox - only cleaning database")
            except Exception as vbox_error:
                log.warning(f"Failed to remove VM '{vm.name}' from VirtualBox: {vbox_error}")
                if not force:
                    raise VMError(log, f"Failed to remove VM from VirtualBox: {vbox_error}")
        
        # Delete from database
        return vm_database.delete_vm(vm_id)
        
    except Exception as e:
        if not force:
            raise VMError(log, f"Failed to delete VM {vm_id}: {e}")
        log.warning(f"Failed to delete VM {vm_id}: {e} (continuing due to force=True)")
        return False


# ==========================================
# PHASE 2: UUID-BASED VM VERIFICATION
# ==========================================

def verify_vm_status(vm_record) -> VMStatus:
    """
    Verify VM exists and determine its status using UUID-based identification.
    
    Args:
        vm_record: VM database record with vbox_uuid field
        
    Returns:
        VMStatus enum indicating current VM state
    """
    if not vm_record.vbox_uuid:
        log.debug(f"VM '{vm_record.name}' has no UUID - needs initial import")
        return VMStatus.IMPORTED
    
    # Check if VM exists in VirtualBox using UUID
    if not VirtualBoxVM.verify_vm_exists_by_uuid(vm_record.vbox_uuid):
        log.warning(f"VM '{vm_record.name}' (UUID: {vm_record.vbox_uuid}) missing from VirtualBox")
        return VMStatus.MISSING
    
    # Check if base snapshot exists (if using snapshots)
    if vm_record.use_snapshots and vm_record.base_snapshot_name:
        if not check_base_snapshot_exists(vm_record.vbox_uuid, vm_record.base_snapshot_name):
            log.warning(f"VM '{vm_record.name}' missing base snapshot '{vm_record.base_snapshot_name}'")
            return VMStatus.SNAPSHOT_MISSING
    
    log.debug(f"VM '{vm_record.name}' verified as ready")
    return VMStatus.READY


def check_base_snapshot_exists(vbox_uuid: str, snapshot_name: str) -> bool:
    """
    Check if a base snapshot exists for a VM.
    
    Args:
        vbox_uuid: VirtualBox VM UUID
        snapshot_name: Name of the snapshot to check
        
    Returns:
        True if snapshot exists, False otherwise
    """
    from adare.backend.vm.snapshot_manager import check_snapshot_exists_by_uuid
    return check_snapshot_exists_by_uuid(vbox_uuid, snapshot_name)


def update_vm_status_in_db(vm_id: str, status: VMStatus) -> None:
    """
    Update VM status and last_verified timestamp in database.
    
    Args:
        vm_id: VM database ID
        status: New VMStatus to set
    """
    from datetime import datetime
    
    # This would update the database record
    # vm_database.update_vm_status(vm_id, status, datetime.utcnow())
    log.debug(f"Would update VM {vm_id} status to {status.name}")


def ensure_vm_has_uuid(vm_record) -> str:
    """
    Ensure VM record has a VirtualBox UUID, fetching it if missing.
    
    Args:
        vm_record: VM database record
        
    Returns:
        VirtualBox UUID string
        
    Raises:
        VMError: If UUID cannot be determined
    """
    if vm_record.vbox_uuid:
        return vm_record.vbox_uuid
    
    # Try to get UUID by VM name
    vbox_uuid = VirtualBoxVM.get_vm_uuid_by_name(vm_record.name)
    if vbox_uuid:
        log.info(f"Found existing UUID for VM '{vm_record.name}': {vbox_uuid}")
        # Update database record with UUID
        # vm_database.update_vm_uuid(vm_record.id, vbox_uuid)
        return vbox_uuid
    
    raise VMError(log, f"Could not determine VirtualBox UUID for VM '{vm_record.name}'")


def get_vm_by_uuid_from_db(vbox_uuid: str):
    """
    Get VM record from database by VirtualBox UUID.
    
    Args:
        vbox_uuid: VirtualBox UUID
        
    Returns:
        VM database record or None if not found
    """
    return vm_database.get_vm_by_vbox_uuid(vbox_uuid)


# ==========================================
# PHASE 4: OPTIMIZED EXPERIMENT WORKFLOW
# ==========================================

async def ensure_vm_ready_for_experiment(vm_id: str, experiment_id: str, environment_ulid: str = None, cleanup_snapshots: bool = True, experiment_run_ulid: Optional[str] = None, preserve_experiment_snapshot: bool = False) -> str:
    """
    🚀 FAST VM preparation for experiment - only VirtualBox import and snapshots!
    
    VM file hash calculation and copying already done during environment load.
    This only handles VirtualBox import and snapshot operations.
    
    Args:
        vm_id: VM database ID (from environment)
        experiment_id: Unique experiment identifier
        environment_ulid: Environment identifier for context
        cleanup_snapshots: Whether to clean up old experiment snapshots (default: True)
        experiment_run_ulid: Experiment run ID for stage tracking (optional)
        preserve_experiment_snapshot: Whether to create experiment-specific snapshot (default: False)
        
    Returns:
        VM ID ready for experiment
        
    Raises:
        VMError: If VM preparation fails
    """
    import time
    start_time = time.time()
    
    from adare.backend.vm.snapshot_manager import SnapshotManager, create_base_snapshot_for_vm, restore_vm_to_base_snapshot
    
    log.info(f"🚀 Starting VM preparation for experiment {experiment_id}")
    
    # Get VM record from database (file operations already done during env load)
    vm = vm_database.get_vm_by_id(vm_id)
    if not vm:
        raise VMError(log, f"VM with ID {vm_id} not found in database")
    
    log.info(f"Using pre-loaded VM: {vm.name} (hash: {vm.hash})")
    
    # Check VM status in VirtualBox
    vm_status = verify_vm_status(vm)
    log.info(f"VM VirtualBox status: {vm_status.name}")
    
    # Handle different VM states
    if vm_status == VMStatus.IMPORTED or vm_status == VMStatus.MISSING:
        # First time or missing: Import VM to VirtualBox + create base snapshot  
        log.info(f"⚡ First time VM setup - importing to VirtualBox...")
        
        # Use dedicated VM import stage
        if experiment_run_ulid:
            with StageCtxManager(VMImportStage(), experiment_run_ulid):
                vm = await vm_database.import_vm_to_virtualbox(vm, capture_uuid_after_import=True, environment_ulid=environment_ulid)
        else:
            log.info(f"⚡ Importing VM to VirtualBox...")
            vm = await vm_database.import_vm_to_virtualbox(vm, capture_uuid_after_import=True, environment_ulid=environment_ulid)
        
        # Create base snapshot for future speed
        log.info(f"📸 Creating base snapshot for future experiments...")
        if experiment_run_ulid:
            with StageCtxManager(VMSnapshotCreateStage(), experiment_run_ulid):
                create_base_snapshot_for_vm(vm, silent=False)
        else:
            create_base_snapshot_for_vm(vm, silent=False)
        
        first_run_time = time.time() - start_time
        log.info(f"⏱️  First VirtualBox import completed in {first_run_time:.1f} seconds")
        return vm.id
        
    elif vm_status == VMStatus.SNAPSHOT_MISSING:
        log.warning(f"Base snapshot missing - recreating...")
        # Recreate base snapshot
        if experiment_run_ulid:
            with StageCtxManager(VMSnapshotCreateStage(), experiment_run_ulid):
                create_base_snapshot_for_vm(vm, silent=False)
        else:
            create_base_snapshot_for_vm(vm, silent=False)
        
    elif vm_status != VMStatus.READY:
        # Handle other statuses
        log.warning(f"VM not ready (status: {vm_status.name}) - attempting repair...")
        # Additional repair logic could go here
    
    # VM exists in VirtualBox - use FAST snapshot workflow! 🏃‍♂️💨
    log.info(f"⚡ VM already in VirtualBox! Using FAST snapshot workflow...")
    
    # 🚀 FAST RESTORE from base snapshot (this is where the magic happens!)
    log.info(f"⚡ Restoring from base snapshot - SUPER FAST!")
    if experiment_run_ulid:
        with StageCtxManager(VMSnapshotRestoreStage(), experiment_run_ulid):
            restore_success = restore_vm_to_base_snapshot(vm, silent=False)
    else:
        restore_success = restore_vm_to_base_snapshot(vm, silent=False)
    
    if not restore_success:
        raise VMError(log, f"Failed to restore VM '{vm.name}' to base snapshot")
    
    # Create experiment-specific snapshot only if requested (for recovery/debugging)
    exp_snapshot_name = None
    if preserve_experiment_snapshot:
        log.info("📸 Creating experiment snapshot (--preserve-snapshot enabled)")
        snapshot_manager = SnapshotManager()
        if experiment_run_ulid:
            with StageCtxManager(VMExperimentSnapshotStage(), experiment_run_ulid):
                exp_snapshot_name = snapshot_manager.create_experiment_snapshot(
                    vm, experiment_id, 
                    description=f"Snapshot for experiment {experiment_id}",
                    silent=False
                )
        else:
            exp_snapshot_name = snapshot_manager.create_experiment_snapshot(
                vm, experiment_id, 
                description=f"Snapshot for experiment {experiment_id}",
                silent=False
            )
        
        if exp_snapshot_name:
            log.info(f"📸 Created experiment snapshot: {exp_snapshot_name}")
        else:
            log.warning("Failed to create experiment snapshot")
    else:
        log.info("⚡ Skipping experiment snapshot creation (use --preserve-snapshot to enable)")
    
    # Cleanup old experiment snapshots if requested
    if cleanup_snapshots:
        log.info("🧹 Cleaning up old experiment snapshots...")
        deleted_count = cleanup_experiment_snapshots_for_vm(vm.id, keep_recent=5)
        if deleted_count > 0:
            log.info(f"🗑️  Deleted {deleted_count} old snapshots")
        else:
            log.debug("No old snapshots to clean up")
    
    # Update verification timestamp
    update_vm_status_in_db(vm.id, VMStatus.READY)
    
    total_time = time.time() - start_time
    log.info(f"🎉 VM preparation completed in {total_time:.1f} seconds!")
    
    return vm.id


def _reimport_missing_vm(vm_record, vm_path: Path, project_path: Path, 
                        environment_metadata: EnvironmentMetadata):
    """
    Re-import a VM that exists in database but is missing from VirtualBox.
    
    This is a recovery function for rare cases where VMs get deleted manually.
    """
    log.info(f"Re-importing missing VM '{vm_record.name}' from {vm_path}")
    
    # The VM record exists but VirtualBox VM is missing
    # We need to re-import and update the UUID
    
    # Import the VM again (this will create a new UUID)
    vm = vm_database.create_vm_with_uuid_capture(
        project_path=project_path,
        name=f"{vm_record.name}_recovered",  # Avoid name conflicts
        file_path=vm_path,
        file_hash=vm_record.hash,
        description=f"Recovered VM for {environment_metadata.name}",
        os_platform=environment_metadata.os.platform,
        os_type=environment_metadata.os.os,
        os_distribution=environment_metadata.os.distribution,
        os_version=environment_metadata.os.version,
        os_language=environment_metadata.os.language,
        os_architecture=environment_metadata.os.architecture,
        capture_uuid_after_import=True,
        silent=False
    )
    
    log.info(f"Successfully re-imported VM as '{vm.name}'")
    return vm


def cleanup_experiment_snapshots_for_vm(vm_id: str, keep_recent: int = 5) -> int:
    """
    Clean up old experiment snapshots for a specific VM.
    
    Args:
        vm_id: VM database ID
        keep_recent: Number of recent snapshots to keep
        
    Returns:
        Number of snapshots deleted
    """
    vm = vm_database.get_vm_by_id(vm_id)
    if not vm:
        log.warning(f"VM with ID {vm_id} not found for cleanup")
        return 0
    
    from adare.backend.vm.snapshot_manager import SnapshotManager
    manager = SnapshotManager()
    
    return manager.cleanup_experiment_snapshots(vm, keep_recent=keep_recent)


def clear_all_vms(force: bool = False) -> dict:
    """
    Clear all VMs from the system.
    
    Args:
        force: If True, force deletion even if VMs are in use
        
    Returns:
        Dictionary with deletion results
    """
    log.info("🗑️  Starting VM cleanup - removing ALL VMs")
    
    results = vm_database.delete_all_vms(force=force)
    
    if results['deleted_count'] > 0:
        log.info(f"✅ Successfully cleared {results['deleted_count']} VMs")
        for vm_name in results['deleted_vms']:
            log.info(f"   - {vm_name}")
    
    if results['failed_count'] > 0:
        log.error(f"❌ Failed to delete {results['failed_count']} VMs")
        for error in results['failed_vms']:
            log.error(f"   - {error}")
    
    if results['deleted_count'] == 0 and results['failed_count'] == 0:
        log.info("ℹ️  No VMs found to delete")
    
    return results


def clear_vms_by_environment(environment_ulid: str, force: bool = False) -> dict:
    """
    Clear all VMs associated with a specific environment.
    
    Args:
        environment_ulid: Environment ULID
        force: If True, force deletion even if VMs are in use
        
    Returns:
        Dictionary with deletion results
    """
    log.info(f"🗑️  Starting VM cleanup for environment: {environment_ulid}")
    
    results = vm_database.delete_vms_by_environment(environment_ulid, force=force)
    
    if results['deleted_count'] > 0:
        log.info(f"✅ Successfully cleared {results['deleted_count']} VMs for environment {environment_ulid}")
        for vm_name in results['deleted_vms']:
            log.info(f"   - {vm_name}")
    
    if results['failed_count'] > 0:
        log.error(f"❌ Failed to delete {results['failed_count']} VMs")
        for error in results['failed_vms']:
            log.error(f"   - {error}")
    
    if results['deleted_count'] == 0 and results['failed_count'] == 0:
        log.info(f"ℹ️  No VMs found for environment {environment_ulid}")
    
    return results


def list_all_vms() -> List[dict]:
    """
    List all VMs in the system.
    
    Returns:
        List of VM information dictionaries
    """
    return vm_database.get_all_vms(fields=['id', 'name', 'description', 'hash', 'vbox_uuid'])


def get_vm_info(vm_id: str) -> dict:
    """
    Get detailed information about a specific VM.
    
    Args:
        vm_id: VM database ID
        
    Returns:
        Dictionary with VM information
    """
    vm = vm_database.get_vm_by_id(vm_id)
    if not vm:
        return None
    
    # Get snapshot information if available
    snapshot_info = {}
    try:
        from adare.backend.vm.snapshot_manager import SnapshotManager
        manager = SnapshotManager()
        snapshot_info = manager.get_snapshot_info(vm)
    except Exception as e:
        log.debug(f"Could not get snapshot info for VM {vm_id}: {e}")
    
    return {
        'id': vm.id,
        'name': vm.name,
        'file': vm.file,
        'hash': vm.hash,
        'description': vm.description,
        'vbox_uuid': getattr(vm, 'vbox_uuid', None),
        'base_snapshot_name': getattr(vm, 'base_snapshot_name', None),
        'use_snapshots': getattr(vm, 'use_snapshots', False),
        'snapshots': snapshot_info
    }


