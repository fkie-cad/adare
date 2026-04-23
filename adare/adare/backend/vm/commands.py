"""
VM command operations.

High-level VM operations for CLI and other interfaces.
"""

import logging
import threading
from pathlib import Path

from adare.backend.experiment.stagectxmanager import StageCtxManager
from adare.backend.vm import database as vm_database
from adare.backend.vm.exceptions import VMError
from adare.backend.vm.manager import VMFileManager
from adare.database.exceptions import DatabaseError
from adare.hypervisor.virtualbox.vm import VirtualBoxVM
from adare.types.environment import EnvironmentMetadata
from adare.types.stages import (
    VMImportStage,
    VMSnapshotCreateStage,
    VMSnapshotRestoreStage,
)
from adarelib.constants import VMStatus

log = logging.getLogger(__name__)


async def verify_vm_integrity(vm_id: str, experiment_run_ulid: str = None, interrupt_event: threading.Event | None = None, test_mode: bool = False) -> None:
    """
    Verify VM file integrity before import/use.
    This ensures the VM file hasn't been tampered with since loading.

    Args:
        vm_id: Database ID of the VM to verify
        experiment_run_ulid: Optional experiment run ID for stage tracking
        interrupt_event: Optional event to check for user interruption
        test_mode: Skip verification in test/development mode
    """
    # Skip verification in test mode (follows same pattern as experiment integrity checks)
    if test_mode:
        log.info("Skipping VM integrity verification - running in test/development mode")
        if experiment_run_ulid:
            from adare.backend.experiment.stagectxmanager import StageCtxManager
            from adare.types.stages import VMIntegrityVerificationStage
            with StageCtxManager(VMIntegrityVerificationStage(), experiment_run_ulid, interrupt_event) as stage_ctx:
                stage_ctx.stage.sub_msg = "SKIPPED - Development/Test Mode"
                stage_ctx.set_status(stage_ctx.stage.status)
        return

    # Get VM record from database
    vm_record = vm_database.get_vm_by_id(vm_id)
    if not vm_record:
        from adare.exceptions import LoggedException
        raise LoggedException(log, f"VM with ID {vm_id} not found in database")

    # Get VM file path
    vm_file_path = Path(vm_record.file)

    # Check if this is an external VM file
    is_external = not _is_vm_managed(vm_file_path)

    if not vm_file_path.exists():
        from adare.backend.experiment.exceptions import ExperimentIntegrityError
        if is_external:
            raise ExperimentIntegrityError(
                log,
                f"External VM file not found: {vm_file_path}\n"
                f"This VM was loaded with --no-copy and the original file is missing.",
                possible_solutions=[
                    f"Restore the VM file to its original location: {vm_file_path}",
                    "Re-load the environment with a new VM file",
                    "Use 'adare environment load' without --no-copy to copy the VM to managed storage"
                ]
            )
        raise ExperimentIntegrityError(
            log,
            f"VM file not found: {vm_file_path}",
            possible_solutions=[
                "Check if VM file was moved or deleted",
                "Re-import VM with correct file path",
                "Verify file system permissions"
            ]
        )

    # Calculate current hash and compare with stored hash
    vm_manager = VMFileManager()

    async def verify_in_stage():
        log.info(f"Verifying integrity of VM: {vm_record.name}")

        # Safety check: Ensure we're checking the base disk, not an overlay
        # Overlay disks should never be stored in the database
        if '-overlay-' in str(vm_file_path):
            from adare.backend.experiment.exceptions import ExperimentIntegrityError
            raise ExperimentIntegrityError(
                log,
                f"Cannot verify integrity of overlay disk: {vm_file_path}. "
                "Database should store base disk path, not overlay.",
                possible_solutions=[
                    "Check database VM record for correct base disk path",
                    "Re-import VM to fix database entry",
                    "Ensure VM import creates base disk with -base suffix"
                ]
            )

        try:
            current_hash = await vm_manager.calculate_file_hash_async(vm_file_path, silent=True, interrupt_event=interrupt_event)
        except InterruptedError:
            log.info(f"VM integrity verification interrupted by user for {vm_record.name}")
            return  # Return gracefully, let the stage manager handle the interruption status

        if current_hash != vm_record.hash:
            from adare.backend.experiment.exceptions import ExperimentIntegrityError
            raise ExperimentIntegrityError(
                log,
                f"VM file integrity check failed for '{vm_record.name}'. File has been modified since import.",
                possible_solutions=[
                    "Re-import VM from original source",
                    "Check for unauthorized file modifications",
                    "Verify VM file hasn't been corrupted"
                ]
            )

        log.info(f"VM integrity verification passed: {vm_record.name}")

    # Run with stage context if experiment run provided
    if experiment_run_ulid:
        with StageCtxManager(VMIntegrityVerificationStage(), experiment_run_ulid, interrupt_event):
            await verify_in_stage()
    else:
        await verify_in_stage()


def load_vm_file_for_environment(project_path: Path, vm_path: Path, environment_metadata, no_copy: bool = False, force: bool = False) -> dict:
    """
    Load VM file during environment load - only hash calculation and file copying.
    No VirtualBox import happens here!

    Args:
        project_path: Path to the project
        vm_path: Path to VM file
        environment_metadata: Environment configuration
        no_copy: If True, reference file at original location instead of copying
        force: If True, overwrite existing VM with same name but different hash

    Returns:
        Dict with 'vm_id' and 'was_existing' keys
    """
    vm_manager = VMFileManager()

    # Extract hypervisor from environment metadata
    hypervisor = getattr(environment_metadata, 'hypervisor', 'virtualbox')
    log.info(f"Using hypervisor: {hypervisor}")

    # Calculate hash FIRST (heavy operation done during environment load)
    log.info("Calculating VM file hash during environment load...")
    file_hash = vm_manager.calculate_file_hash(vm_path, silent=False)
    log.info(f"VM file hash: {file_hash}")

    # Check if VM already exists by hash BEFORE copying
    existing_vm = vm_database.get_vm_by_hash(file_hash)
    if existing_vm:
        log.info(f"VM with hash {file_hash} already exists: {existing_vm.name}")
        log.info("Skipping file copy operation - using existing VM")

        # Check if existing VM has proper snapshot configuration
        if not existing_vm.use_snapshots:
            log.warning(f"Existing VM '{existing_vm.name}' has no snapshot configuration!")
            log.warning("This VM may be in an unknown state from previous experiments.")
            log.warning("Creating a NEW VM entry to ensure clean state.")
            log.warning(f"You may have a RELICT VM '{existing_vm.name}' in VirtualBox that needs manual cleanup!")
            log.warning(f"Consider running: VBoxManage unregistervm '{existing_vm.name}' --delete")

            # Don't reuse - fall through to create new VM
        else:
            # VM has snapshot configuration - safe to reuse
            log.info("VM ready for reuse with existing snapshot configuration")
            return {'vm_id': existing_vm.id, 'was_existing': True}

    # VM doesn't exist or existing VM can't be reused - create new one with file operations
    log.info("Creating new VM entry with file operations...")

    # Determine if we should copy or reference
    if no_copy:
        log.info("Using --no-copy mode: VM file will be referenced at original location")
        log.warning(f"IMPORTANT: VM file must remain at {vm_path} for experiments to work!")

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
        silent=False,
        no_copy=no_copy,  # Pass the flag
        hypervisor=hypervisor,  # NEW: Pass hypervisor type
        force=force  # Pass force flag for VM overwriting
    )

    log.info(f"VM file loaded into database: {vm.name} (ID: {vm.id})")
    return {'vm_id': vm.id, 'was_existing': False}


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


def list_vms() -> list[dict]:
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
    OPTIMIZED VM preparation using snapshots - Always 10-15x faster!

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

    log.info(f"Using OPTIMIZED snapshot workflow (experiment: {experiment_id})")
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

        # Delete associated VmInstance records - they handle VirtualBox VM cleanup
        from adare.database.api.vm import VmApi
        with VmApi() as api:
            instances = api.get_vm_instances_by_vm_id(vm_id)
            if instances:
                log.info(f"Found {len(instances)} VM instances to delete for '{vm.name}'")
                from adare.backend.vm.instance_manager import delete_vm_instance
                for instance in instances:
                    try:
                        await delete_vm_instance(instance.id, force=force)
                        log.info(f"Deleted VM instance: {instance.instance_name}")
                    except (VMError, OSError) as inst_error:
                        log.warning(f"Failed to delete instance {instance.instance_name}: {inst_error}")
                        if not force:
                            raise VMError(log, f"Failed to delete VM instance: {inst_error}") from inst_error

        # Delete from database (cascade will remove instances)
        return vm_database.delete_vm(vm_id)

    except (VMError, OSError, DatabaseError) as e:
        if not force:
            raise VMError(log, f"Failed to delete VM {vm_id}: {e}") from e
        log.warning(f"Failed to delete VM {vm_id}: {e} (continuing due to force=True)")
        return False


# ==========================================
# PHASE 2: UUID-BASED VM VERIFICATION
# ==========================================

def verify_vm_status(vm_record, auto_cleanup: bool = False, experiment_context: str = None) -> VMStatus:
    """
    DEPRECATED: This function operates on Vm records which no longer track VirtualBox UUIDs.
    Use VmInstance verification functions instead.

    For VmInstance verification, use instance_manager.verify_vm_instance_status()

    This function now only checks if the Vm model exists in database.
    """
    log.warning("verify_vm_status is deprecated - Vm records no longer track VirtualBox state")
    # Vm records are abstract templates, not concrete VMs
    # Return IMPORTED to indicate it's just a template
    return VMStatus.IMPORTED


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



def verify_and_cleanup_vm_for_experiment(vm_id: str, experiment_id: str = None) -> bool:
    """
    Verify VM exists and automatically cleanup if missing (experiment context only).

    Args:
        vm_id: VM database ID to verify
        experiment_id: Experiment context for logging

    Returns:
        True if VM exists and is ready, False if VM was missing and cleaned up

    Raises:
        VMError: If VM verification fails for reasons other than missing VM
    """
    # Get VM record from database
    vm_record = vm_database.get_vm_by_id(vm_id)
    if not vm_record:
        raise VMError(log, f"VM with ID {vm_id} not found in database")

    # VM record exists in database - that's all we need to verify
    # VmInstance records handle the actual VirtualBox state
    return True


def verify_and_cleanup_vm_instance_for_experiment(vm_instance_id: str, experiment_id: str = None) -> bool:
    """
    Verify VM instance exists in VirtualBox and automatically cleanup if missing.

    Args:
        vm_instance_id: VM instance database ID to verify
        experiment_id: Experiment context for logging

    Returns:
        True if VM instance exists and is ready, False if VM instance was missing and cleaned up

    Raises:
        VMError: If VM instance verification fails for reasons other than missing VM instance
    """
    from adare.database.api.vm import VmApi

    # Get VM instance record from database
    with VmApi() as api:
        vm_instance = api.get_vm_instance_by_id(vm_instance_id)

    if not vm_instance:
        raise VMError(log, f"VM instance with ID {vm_instance_id} not found in database")

    # Check if VM instance has VirtualBox UUID
    if not vm_instance.vbox_uuid:
        log.debug(f"VM instance '{vm_instance.instance_name}' has no VirtualBox UUID - needs initial import")
        return True

    # Verify VM instance exists in VirtualBox using UUID
    if not VirtualBoxVM.verify_vm_exists_by_uuid(vm_instance.vbox_uuid):
        log.warning(f"VM instance '{vm_instance.instance_name}' (UUID: {vm_instance.vbox_uuid}) missing from VirtualBox")

        # Perform automatic cleanup
        context_info = f" (experiment: {experiment_id})" if experiment_id else ""
        log.info(f"Automatically removing orphaned VM instance '{vm_instance.instance_name}' from database{context_info}")

        try:
            with VmApi() as api:
                api.delete_vm_instance(vm_instance_id)
            log.info(f"Successfully cleaned up missing VM instance '{vm_instance.instance_name}' from database")
            return False  # VM instance was missing and cleaned up
        except (OSError, DatabaseError) as e:
            log.error(f"Failed to cleanup missing VM instance '{vm_instance.instance_name}': {e}")
            raise VMError(log, f"Failed to cleanup missing VM instance: {e}") from e

    log.debug(f"VM instance '{vm_instance.instance_name}' verified as ready in VirtualBox")
    return True


# ==========================================
# PHASE 4: OPTIMIZED EXPERIMENT WORKFLOW
# ==========================================

async def ensure_vm_ready_for_experiment(vm_id: str, experiment_id: str, environment_ulid: str = None, experiment_run_ulid: str | None = None, preserve_experiment_snapshot: bool = False, interrupt_event: threading.Event | None = None, test_mode: bool = False) -> str:
    """
    OPTIMIZED VM preparation using instance management for concurrent experiments!

    This function now uses the VM instance system to support multiple concurrent
    experiments with the same environment, including smart reuse and dynamic port allocation.

    Args:
        vm_id: VM database ID (from environment)
        experiment_id: Unique experiment identifier (for instance naming)
        environment_ulid: Environment identifier for context
        experiment_run_ulid: Experiment run ID for stage tracking and instance assignment
        preserve_experiment_snapshot: Whether to create experiment-specific snapshot
        interrupt_event: Optional event to check for user interruption
        test_mode: Skip VM integrity verification in test/development mode

    Returns:
        VM instance ID ready for experiment (not the source VM ID!)

    Raises:
        VMError: If VM preparation fails
    """
    import time
    start_time = time.time()

    from adare.backend.vm.instance_manager import allocate_vm_instance_for_experiment
    from adare.backend.vm.snapshot_manager import (
        create_base_snapshot_for_instance,
        restore_instance_to_base_snapshot,
    )

    log.info(f"Starting OPTIMIZED VM instance preparation for experiment {experiment_id}")
    log.debug(f"ensure_vm_ready_for_experiment called with vm_id={vm_id}, experiment_id={experiment_id}, experiment_run_ulid={experiment_run_ulid}")
    log.debug(f"Performance tracking - function entry at {time.time():.3f}")

    # Check for interruption before starting
    if interrupt_event and interrupt_event.is_set():
        log.info("VM preparation cancelled before starting due to interrupt")
        return None

    # Step 0: Verify VM exists and cleanup if missing (experiment-scoped)
    log.debug("Step 0 - Verifying VM exists and cleaning up if missing")
    try:
        vm_is_available = verify_and_cleanup_vm_for_experiment(vm_id, experiment_id)
        if not vm_is_available:
            # VM was missing and cleaned up - cannot proceed
            raise VMError(log, f"VM with ID {vm_id} was missing from VirtualBox and has been removed from database. Cannot proceed with experiment.")
        log.debug("VM verification passed - VM is available")
    except Exception as e:
        log.error(f"VM verification failed: {e}")
        raise

    # Step 1: Allocate VM instance (reuse existing or create new)
    log.debug(f"Step 1 - Starting VM instance allocation for vm_id={vm_id}")
    try:
        if experiment_run_ulid:
            log.debug(f"Allocating instance with experiment_run_ulid={experiment_run_ulid}")
            vm_instance = await allocate_vm_instance_for_experiment(vm_id, experiment_run_ulid)
        else:
            # Fallback for non-experiment use cases
            import ulid
            temp_run_id = str(ulid.ULID())
            log.debug(f"Allocating instance with temp_run_id={temp_run_id}")
            vm_instance = await allocate_vm_instance_for_experiment(vm_id, temp_run_id)

        log.info(f"Allocated VM instance: {vm_instance.instance_name} on port {vm_instance.websocket_port}")
        log.debug(f"VM instance details - ID={vm_instance.id}, status={vm_instance.status}, vbox_uuid={vm_instance.vbox_uuid}")
    except Exception as e:
        log.error(f"Failed to allocate VM instance: {e}")
        import traceback
        log.debug(f"VM instance allocation traceback: {traceback.format_exc()}")
        raise

    # Step 2: Ensure source VM is ready in VirtualBox (if this is a new instance)
    source_vm = vm_database.get_vm_by_id(vm_id)
    if not source_vm:
        raise VMError(log, f"Source VM with ID {vm_id} not found in database")

    # Detect hypervisor type to skip VirtualBox-specific snapshot operations for QEMU
    is_qemu = (source_vm.hypervisor == 'qemu')
    log.debug(f"Source VM hypervisor: {source_vm.hypervisor} (is_qemu={is_qemu})")

    # Check if this is a reused instance or new instance
    # VirtualBox uses vbox_uuid, QEMU uses check via identifier_strategy
    is_reused = False
    if vm_instance.vbox_uuid:
        is_reused = True
    elif is_qemu:
        # QEMU check - verify if instance exists in libvirt
        from adare.hypervisor.base.identifier_strategy import get_identifier_strategy
        try:
            strategy = get_identifier_strategy('qemu')
            identifier = strategy.get_identifier(vm_instance)
            if identifier and strategy.verify_exists(identifier):
                is_reused = True
        except Exception as e:
            log.warning(f"Failed to verify QEMU instance existence: {e}")

    if is_reused:
        # Reused instance - VM already exists in VirtualBox
        log.info(f"Reusing existing VM instance: {vm_instance.instance_name}")

        # Check if instance has a base snapshot, create if missing (VirtualBox only)
        if not is_qemu and not vm_instance.base_snapshot_name:
            log.info(f"VM instance '{vm_instance.instance_name}' missing base snapshot - creating it now")
            if experiment_run_ulid:
                with StageCtxManager(VMSnapshotCreateStage(), experiment_run_ulid, interrupt_event):
                    snapshot_success = create_base_snapshot_for_instance(vm_instance, silent=False)
            else:
                snapshot_success = create_base_snapshot_for_instance(vm_instance, silent=False)

            if not snapshot_success:
                log.warning(f"Failed to create base snapshot for reused instance {vm_instance.instance_name}")
            else:
                # Refresh instance data to get updated snapshot name
                from adare.database.api.vm import VmApi
                with VmApi() as api:
                    vm_instance = api.get_vm_instance_by_id(vm_instance.id)
        elif is_qemu:
            log.debug("QEMU instance - skipping snapshot creation (uses overlay disks)")

        # Restore instance to clean state (only if base snapshot exists, VirtualBox only)
        if not is_qemu and vm_instance.base_snapshot_name:
            if experiment_run_ulid:
                with StageCtxManager(VMSnapshotRestoreStage(), experiment_run_ulid, interrupt_event):
                    restore_success = restore_instance_to_base_snapshot(
                        vm_instance,  # Pass VM instance record
                        silent=False,
                        interrupt_event=interrupt_event,
                        timeout=180
                    )
            else:
                restore_success = restore_instance_to_base_snapshot(
                    vm_instance,
                    silent=False,
                    interrupt_event=interrupt_event,
                    timeout=180
                )

            if interrupt_event and interrupt_event.is_set():
                log.info("VM instance preparation interrupted during restore")
                return None

            if not restore_success:
                log.warning(f"Failed to restore VM instance '{vm_instance.instance_name}' to clean state - will continue anyway")
        elif not is_qemu and not vm_instance.base_snapshot_name:
            log.warning(f"VM instance '{vm_instance.instance_name}' has no base snapshot available - cannot restore to clean state")
        elif is_qemu:
            log.debug("QEMU instance - skipping snapshot restoration (uses overlay disks)")

    else:
        # New instance - need to import from source VM
        log.info(f"Creating new VM instance: {vm_instance.instance_name}")

        # Verify source VM integrity (skip in test mode)
        await verify_vm_integrity(vm_id, experiment_run_ulid, interrupt_event, test_mode=test_mode)

        if interrupt_event and interrupt_event.is_set():
            log.info("VM integrity verification was interrupted")
            return None

        # Import VM instance with unique name
        # Stage management handled by hypervisor-specific prepare_vm_for_experiment()
        if experiment_run_ulid:
            from adare.types.stages import VMDiskPreparationStage
            # Wrap in disk prep stage as parent
            with StageCtxManager(VMDiskPreparationStage(), experiment_run_ulid, interrupt_event):
                # Wrap in import stage
                with StageCtxManager(VMImportStage(), experiment_run_ulid, interrupt_event):
                    vm_instance = await _import_vm_instance(vm_instance, source_vm, environment_ulid)
        else:
            vm_instance = await _import_vm_instance(vm_instance, source_vm, environment_ulid)

        if interrupt_event and interrupt_event.is_set():
            log.info("VM instance import was interrupted")
            return None

        # Create base snapshot for this instance (VirtualBox only)
        if not is_qemu:
            if experiment_run_ulid:
                with StageCtxManager(VMSnapshotCreateStage(), experiment_run_ulid, interrupt_event):
                    success = create_base_snapshot_for_instance(vm_instance, silent=False)
            else:
                success = create_base_snapshot_for_instance(vm_instance, silent=False)

            if not success:
                log.warning(f"Failed to create base snapshot for instance {vm_instance.instance_name}")
        else:
            log.info("QEMU VM - skipping VirtualBox-style snapshot creation (uses overlay disks instead)")

    total_time = time.time() - start_time
    log.info(f"VM instance preparation completed in {total_time:.1f} seconds!")
    log.info(f"Instance: {vm_instance.instance_name}, Port: {vm_instance.websocket_port}")
    log.debug(f"Performance tracking - function exit at {time.time():.3f}, total duration: {total_time:.3f}s")

    # Verify the instance exists before returning
    log.debug(f"Verifying instance exists before returning ID: {vm_instance.id}")
    from adare.database.api.vm import VmApi
    with VmApi() as api:
        verification_instance = api.get_vm_instance_by_id(vm_instance.id)
        if not verification_instance:
            log.error(f"CRITICAL - Instance {vm_instance.id} was created but cannot be retrieved!")
            raise VMError(log, f"Instance {vm_instance.id} was created but cannot be retrieved from database")
        log.debug(f"Instance verification successful: {verification_instance.instance_name}")

    log.info(f"Returning VM instance ID: {vm_instance.id}")
    return vm_instance.id  # Return instance ID, not source VM ID


async def _import_vm_instance(vm_instance, source_vm, environment_ulid: str = None):
    """
    Import a VM instance using the appropriate hypervisor manager.

    Args:
        vm_instance: VmInstance database record
        source_vm: Source VM database record
        environment_ulid: Environment identifier for context

    Returns:
        Updated VmInstance with hypervisor-specific identifiers
    """
    from adare.database.api.vm import VmApi
    from adare.hypervisor import get_hypervisor_manager

    # Get hypervisor type from source VM (default to virtualbox for backwards compatibility)
    hypervisor = getattr(source_vm, 'hypervisor', 'virtualbox')

    log.info(f"Importing VM instance '{vm_instance.instance_name}' using {hypervisor} hypervisor...")

    # Get appropriate hypervisor manager using factory pattern
    manager = get_hypervisor_manager(hypervisor)
    vm_file_path = Path(source_vm.file)

    # Import VM with unique instance name
    vm_obj = await manager.import_vm_async(
        vm_file_path,
        vm_instance.instance_name,
        environment_ulid=environment_ulid
    )

    # Update instance with hypervisor-specific identifiers
    update_fields = {
        'base_snapshot_name': f"{vm_instance.instance_name}_base"
    }

    # VirtualBox-specific: store vbox_uuid
    if hypervisor == 'virtualbox':
        vbox_uuid = vm_obj.get_vm_uuid()
        update_fields['vbox_uuid'] = vbox_uuid
        log.info(f"Successfully imported VirtualBox VM instance '{vm_instance.instance_name}' with UUID: {vbox_uuid}")
    elif hypervisor == 'qemu':
        # QEMU VMs don't use vbox_uuid field (remains None)
        log.info(f"Successfully imported QEMU VM instance '{vm_instance.instance_name}'")

    with VmApi() as api:
        api.update_vm_instance(vm_instance.id, **update_fields)

    # Return updated instance
    with VmApi() as api:
        return api.get_vm_instance_by_id(vm_instance.id)


async def release_vm_instance_for_experiment(vm_instance_id: str):
    """
    Release a VM instance when an experiment completes.

    Args:
        vm_instance_id: VM instance ID to release
    """
    from adare.backend.vm.instance_manager import release_vm_instance
    await release_vm_instance(vm_instance_id)


async def cleanup_vm_instances_for_experiment(experiment_run_id: str):
    """
    Clean up all VM instances used by an experiment run.

    Args:
        experiment_run_id: Experiment run ID
    """
    from adare.backend.vm.instance_manager import cleanup_vm_instance
    from adare.database.api.vm import VmApi
    from adare.database.models.global_models import VmInstance

    with VmApi() as api:
        instances = api._session.query(VmInstance).filter_by(
            current_experiment_run_id=experiment_run_id
        ).all()

        for instance in instances:
            log.info(f"Cleaning up VM instance for experiment {experiment_run_id}: {instance.instance_name}")
            await cleanup_vm_instance(instance.id, force=True)


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


def clear_all_vms(force: bool = False) -> dict:
    """
    Clear all VMs from the system.

    Args:
        force: If True, force deletion even if VMs are in use

    Returns:
        Dictionary with deletion results
    """
    log.info("Starting VM cleanup - removing ALL VMs")

    results = vm_database.delete_all_vms(force=force)

    if results['deleted_count'] > 0:
        log.info(f"Successfully cleared {results['deleted_count']} VMs")
        for vm_name in results['deleted_vms']:
            log.info(f"   - {vm_name}")

    if results['failed_count'] > 0:
        log.error(f"Failed to delete {results['failed_count']} VMs")
        for error in results['failed_vms']:
            log.error(f"   - {error}")

    if results['deleted_count'] == 0 and results['failed_count'] == 0:
        log.info("No VMs found to delete")

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
    log.info(f"Starting VM cleanup for environment: {environment_ulid}")

    results = vm_database.delete_vms_by_environment(environment_ulid, force=force)

    if results['deleted_count'] > 0:
        log.info(f"Successfully cleared {results['deleted_count']} VMs for environment {environment_ulid}")
        for vm_name in results['deleted_vms']:
            log.info(f"   - {vm_name}")

    if results['failed_count'] > 0:
        log.error(f"Failed to delete {results['failed_count']} VMs")
        for error in results['failed_vms']:
            log.error(f"   - {error}")

    if results['deleted_count'] == 0 and results['failed_count'] == 0:
        log.info(f"No VMs found for environment {environment_ulid}")

    return results


def list_all_vms() -> list[dict]:
    """
    List all VMs in the system.

    Returns:
        List of VM information dictionaries
    """
    return vm_database.get_all_vms(fields=['id', 'name', 'description', 'hash', 'hypervisor'])


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
    except (VMError, OSError, ImportError) as e:
        log.debug(f"Could not get snapshot info for VM {vm_id}: {e}")

    return {
        'id': vm.id,
        'name': vm.name,
        'file': vm.file,
        'hash': vm.hash,
        'description': vm.description,
        'use_snapshots': getattr(vm, 'use_snapshots', False),
        'snapshots': snapshot_info
    }


def _is_vm_managed(vm_file_path: Path) -> bool:
    """
    Check if a VM file is managed (in VMS_DIR) or external.

    Args:
        vm_file_path: Path to VM file

    Returns:
        True if VM is in managed storage, False if external
    """
    from adare.config.configdirectory import VMS_DIR
    try:
        # Check if vm_file_path is relative to VMS_DIR
        vm_file_path.resolve().relative_to(VMS_DIR.resolve())
        return True
    except ValueError:
        # Path is not relative to VMS_DIR - it's external
        return False

