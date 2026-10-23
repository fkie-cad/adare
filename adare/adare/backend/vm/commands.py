"""
VM command operations.

High-level VM operations for CLI and other interfaces.
"""

import contextlib
import logging
import threading
from pathlib import Path

from adare.backend.experiment.stagectxmanager import StageCtxManager
from adare.backend.vm import database as vm_database
from adare.backend.vm.exceptions import VMError
from adare.backend.vm.manager import VMFileManager
from adare.database.exceptions import DatabaseError
from adare.helperfunctions.digest_cache import fresh_cached_sha256, record_file_sha256
from adare.hypervisor.virtualbox.vm import VirtualBoxVM
from adare.types.environment import EnvironmentMetadata
from adare.types.stages import (
    VMDiskPreparationStage,
    VMImportStage,
    VMIntegrityVerificationStage,
    VMSnapshotCreateStage,
    VMSnapshotRestoreStage,
)

log = logging.getLogger(__name__)


def _integrity_cache_file(vm_file_path: Path) -> Path:
    """Where the run-time integrity check caches a disk's verified digest."""
    import hashlib

    from adare.config.configdirectory import STATE_DIR

    key = hashlib.sha256(str(vm_file_path.resolve()).encode()).hexdigest()
    return STATE_DIR / 'disk-digests' / f'{key}.json'


async def verify_vm_integrity(
    vm_id: str,
    experiment_run_ulid: str | None = None,
    interrupt_event: threading.Event | None = None,
    test_mode: bool = False,
) -> None:
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

    # Recipe recovery advantage: if the cached disk of a recipe-built VM is
    # missing, rebuild it from the recipe instead of hard-failing (a baked disk
    # cannot recover from a missing file). The rebuilt disk is then verified
    # normally below via its recorded Vm.hash.
    is_recipe = getattr(vm_record, 'build_source', 'baked') == 'recipe'
    if is_recipe and not vm_file_path.exists():
        log.warning(f"Cached recipe disk missing for VM '{vm_record.name}'; attempting rebuild from recipe...")
        from adare.backend.vm.recipe import rebuild_recipe_vm_by_id

        rebuilt_id = rebuild_recipe_vm_by_id(vm_id)
        if rebuilt_id:
            rebuilt_record = vm_database.get_vm_by_id(rebuilt_id)
            if rebuilt_record:
                vm_record = rebuilt_record
                vm_file_path = Path(vm_record.file)
                log.info(f"Rebuilt recipe disk for VM '{vm_record.name}' at {vm_file_path}")

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
                    "Use 'adare environment load' without --no-copy to copy the VM to managed storage",
                ],
            )
        raise ExperimentIntegrityError(
            log,
            f"VM file not found: {vm_file_path}",
            possible_solutions=[
                "Check if VM file was moved or deleted",
                "Re-import VM with correct file path",
                "Verify file system permissions",
            ],
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
                    "Ensure VM import creates base disk with -base suffix",
                ],
            )

        # Full hash only when the disk changed since it was last verified; the
        # cache entry lives in ADARE's state directory (never beside a user's
        # --no-copy disk) and is keyed by size/mtime/ctime/inode -- ctime cannot
        # be set back after an in-place edit.
        cache_file = _integrity_cache_file(vm_file_path)
        current_hash = fresh_cached_sha256(vm_file_path, cache_file)
        if current_hash is None:
            stat_before = vm_file_path.stat()
            try:
                current_hash = await vm_manager.calculate_file_hash_async(
                    vm_file_path, silent=True, interrupt_event=interrupt_event
                )
            except InterruptedError:
                log.info(f"VM integrity verification interrupted by user for {vm_record.name}")
                return  # Return gracefully, let the stage manager handle the interruption status
            if current_hash == vm_record.hash:
                record_file_sha256(vm_file_path, current_hash, cache_file=cache_file, st=stat_before)
        else:
            log.info(f"VM disk unchanged since its last full verification: {vm_record.name}")

        if current_hash != vm_record.hash:
            from adare.backend.experiment.exceptions import ExperimentIntegrityError

            raise ExperimentIntegrityError(
                log,
                f"VM file integrity check failed for '{vm_record.name}'. File has been modified since import.",
                possible_solutions=[
                    "Re-import VM from original source",
                    "Check for unauthorized file modifications",
                    "Verify VM file hasn't been corrupted",
                ],
            )

        log.info(f"VM integrity verification passed: {vm_record.name}")

    # Run with stage context if experiment run provided
    if experiment_run_ulid:
        with StageCtxManager(VMIntegrityVerificationStage(), experiment_run_ulid, interrupt_event):
            await verify_in_stage()
    else:
        await verify_in_stage()


def load_vm(
    vm_file: Path,
    name: str = None,
    description: str = '',
    os_platform: str = '',
    os_type: str = '',
    os_distribution: str = '',
    os_version: str = '',
    os_language: str = '',
    os_architecture: str = 'x86_64',
    force: bool = False,
) -> str:
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
        silent=False,
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
        return [
            {'id': vm.id, 'name': vm.name, 'description': vm.description, 'file': vm.file, 'hash': vm.hash}
            for vm in vms
        ]


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
            instances = api.get_vm_instances_for_vm(vm_id)
            if instances:
                log.info(f"Found {len(instances)} VM instances to delete for '{vm.name}'")
                from adare.backend.vm.instance_manager import cleanup_vm_instance
                from adare.hypervisor.exceptions import InstanceStateException

                for instance in instances:
                    try:
                        await cleanup_vm_instance(instance.id)
                        log.info(f"Deleted VM instance: {instance.instance_name}")
                    except (VMError, OSError, InstanceStateException) as inst_error:
                        log.warning(f"Failed to delete instance {instance.instance_name}: {inst_error}")
                        if not force:
                            raise VMError(log, f"Failed to delete VM instance: {inst_error}") from inst_error

        # Delete from database (cascade will remove instances)
        deleted = vm_database.delete_vm(vm_id)
        if deleted and getattr(vm, 'hypervisor', None) == 'qemu':
            from adare.hypervisor.qemu.run_resources import remove_vm_templates

            remove_vm_templates(str(vm_id), str(getattr(vm, 'hash', '')))
        return deleted

    except (VMError, OSError, DatabaseError) as e:
        if not force:
            raise VMError(log, f"Failed to delete VM {vm_id}: {e}") from e
        log.warning(f"Failed to delete VM {vm_id}: {e} (continuing due to force=True)")
        return False


# ==========================================
# PHASE 2: UUID-BASED VM VERIFICATION
# ==========================================


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
        log.warning(
            f"VM instance '{vm_instance.instance_name}' (UUID: {vm_instance.vbox_uuid}) missing from VirtualBox"
        )

        # Perform automatic cleanup
        context_info = f" (experiment: {experiment_id})" if experiment_id else ""
        log.info(
            f"Automatically removing orphaned VM instance '{vm_instance.instance_name}' from database{context_info}"
        )

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


async def ensure_vm_ready_for_experiment(
    vm_id: str,
    environment_ulid: str = None,
    experiment_run_ulid: str | None = None,
    interrupt_event: threading.Event | None = None,
    test_mode: bool = False,
    machine_key: str | None = None,
) -> str | None:
    """
    Prepare the VM instance an experiment run boots.

    QEMU: a run-scoped instance (port reservation + name) whose disk is a
    throwaway overlay on the read-only environment disk, created later by the
    lifecycle strategy -- nothing is copied here. VirtualBox: a pooled instance,
    reused and restored to its base snapshot, or imported on first use.

    Args:
        vm_id: VM database ID (from environment)
        environment_ulid: Environment identifier for context
        experiment_run_ulid: Experiment run ID for stage tracking and instance assignment
        interrupt_event: Optional event to check for user interruption
        test_mode: Skip VM integrity verification in test/development mode
        machine_key: Machine of a multi-machine run (keeps its instance name distinct)

    Returns:
        VM instance ID ready for experiment (not the source VM ID!), or None if interrupted

    Raises:
        VMError: If VM preparation fails
    """
    import time

    import ulid

    from adare.backend.vm.instance_manager import allocate_vm_instance_for_experiment
    from adare.backend.vm.snapshot_manager import create_base_snapshot_for_instance
    from adare.database.api.vm import VmApi

    if interrupt_event and interrupt_event.is_set():
        log.info("VM preparation cancelled before starting due to interrupt")
        return None

    with VmApi() as vm_api:
        source_vm = vm_api.get_vm_by_id(vm_id)
    if not source_vm:
        raise VMError(log, f"Source VM with ID {vm_id} not found in database")
    if source_vm.hypervisor == 'qemu':
        return await _prepare_qemu_run_instance(source_vm, experiment_run_ulid, machine_key, interrupt_event, test_mode)

    start_time = time.time()
    vm_instance = await allocate_vm_instance_for_experiment(vm_id, experiment_run_ulid or str(ulid.ULID()))
    log.info(f"Allocated VM instance: {vm_instance.instance_name} on port {vm_instance.websocket_port}")

    if vm_instance.vbox_uuid:
        log.info(f"Reusing existing VM instance: {vm_instance.instance_name}")
        if not await _restore_pooled_instance(vm_instance, experiment_run_ulid, interrupt_event):
            return None
    else:
        log.info(f"Creating new VM instance: {vm_instance.instance_name}")
        await verify_vm_integrity(vm_id, experiment_run_ulid, interrupt_event, test_mode=test_mode)
        if interrupt_event and interrupt_event.is_set():
            log.info("VM integrity verification was interrupted")
            return None

        with (
            _optional_stage(VMDiskPreparationStage(), experiment_run_ulid, interrupt_event),
            _optional_stage(VMImportStage(), experiment_run_ulid, interrupt_event),
        ):
            vm_instance = await _import_vm_instance(vm_instance, source_vm, environment_ulid)
        if interrupt_event and interrupt_event.is_set():
            log.info("VM instance import was interrupted")
            return None

        with _optional_stage(VMSnapshotCreateStage(), experiment_run_ulid, interrupt_event):
            if not create_base_snapshot_for_instance(vm_instance, silent=False):
                log.warning(f"Failed to create base snapshot for instance {vm_instance.instance_name}")

    log.info(
        f"VM instance {vm_instance.instance_name} (port {vm_instance.websocket_port}) "
        f"ready in {time.time() - start_time:.1f}s"
    )
    instance_id: str = vm_instance.id
    return instance_id


def _optional_stage(stage, experiment_run_ulid: str | None, interrupt_event: threading.Event | None):
    """The stage's context manager when there is a run to report it on, else a no-op."""
    if not experiment_run_ulid:
        return contextlib.nullcontext()
    return StageCtxManager(stage, experiment_run_ulid, interrupt_event)


async def _restore_pooled_instance(
    vm_instance, experiment_run_ulid: str | None, interrupt_event: threading.Event | None
) -> bool:
    """Bring a reused VirtualBox instance back to its base snapshot (taking one if missing).

    Returns:
        False if interrupted.
    """
    from adare.backend.vm.snapshot_manager import create_base_snapshot_for_instance, restore_instance_to_base_snapshot
    from adare.database.api.vm import VmApi

    if not vm_instance.base_snapshot_name:
        log.info(f"VM instance '{vm_instance.instance_name}' missing base snapshot - creating it now")
        with _optional_stage(VMSnapshotCreateStage(), experiment_run_ulid, interrupt_event):
            created = create_base_snapshot_for_instance(vm_instance, silent=False)
        if not created:
            log.warning(
                f"VM instance '{vm_instance.instance_name}' has no base snapshot - cannot restore to clean state"
            )
            return True
        with VmApi() as api:
            vm_instance = api.get_vm_instance_by_id(vm_instance.id)

    with _optional_stage(VMSnapshotRestoreStage(), experiment_run_ulid, interrupt_event):
        restored = restore_instance_to_base_snapshot(
            vm_instance, silent=False, interrupt_event=interrupt_event, timeout=180
        )
    if interrupt_event and interrupt_event.is_set():
        log.info("VM instance preparation interrupted during restore")
        return False
    if not restored:
        log.warning(
            f"Failed to restore VM instance '{vm_instance.instance_name}' to clean state - will continue anyway"
        )
    return True


async def _prepare_qemu_run_instance(
    source_vm,
    experiment_run_ulid: str | None,
    machine_key: str | None,
    interrupt_event: threading.Event | None,
    test_mode: bool,
) -> str | None:
    """Verify the environment disk and reserve this run's QEMU instance."""
    import ulid

    from adare.backend.vm.run_instances import allocate_qemu_run_instance, reconcile_instances

    # Crashed runs leave rows (holding ports) and run files behind; reap them first.
    report = await reconcile_instances()
    if not report.empty:
        log.info(f"Reclaimed leftovers of crashed runs: {report}")

    await verify_vm_integrity(str(source_vm.id), experiment_run_ulid, interrupt_event, test_mode=test_mode)
    if interrupt_event and interrupt_event.is_set():
        log.info("VM integrity verification was interrupted")
        return None

    instance = allocate_qemu_run_instance(source_vm, experiment_run_ulid or str(ulid.ULID()), machine_key)
    instance_id: str = instance.id
    return instance_id


async def _import_vm_instance(vm_instance, source_vm, environment_ulid: str | None = None):
    """Import the source VM into VirtualBox as this pooled instance and record its UUID.

    Returns:
        The updated VmInstance
    """
    from adare.database.api.vm import VmApi
    from adare.hypervisor import get_hypervisor_manager

    log.info(f"Importing VM instance '{vm_instance.instance_name}'...")
    manager = get_hypervisor_manager('virtualbox')
    vm_obj = await manager.import_vm_async(
        Path(source_vm.file), vm_instance.instance_name, environment_ulid=environment_ulid
    )
    vbox_uuid = vm_obj.get_vm_uuid()
    log.info(f"Imported VM instance '{vm_instance.instance_name}' with UUID: {vbox_uuid}")

    with VmApi() as api:
        api.update_vm_instance(
            vm_instance.id, base_snapshot_name=f"{vm_instance.instance_name}_base", vbox_uuid=vbox_uuid
        )
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
        instances = api._session.query(VmInstance).filter_by(current_experiment_run_id=experiment_run_id).all()

        for instance in instances:
            log.info(f"Cleaning up VM instance for experiment {experiment_run_id}: {instance.instance_name}")
            await cleanup_vm_instance(instance.id, force=True)


def _reimport_missing_vm(vm_record, vm_path: Path, project_path: Path, environment_metadata: EnvironmentMetadata):
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
        silent=False,
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

    # Registered VMs are templates: snapshots exist only on (VirtualBox) instances.
    snapshot_info: dict = {}

    return {
        'id': vm.id,
        'name': vm.name,
        'file': vm.file,
        'hash': vm.hash,
        'description': vm.description,
        'use_snapshots': getattr(vm, 'use_snapshots', False),
        'snapshots': snapshot_info,
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
