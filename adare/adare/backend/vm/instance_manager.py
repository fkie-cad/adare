"""
VM Instance Manager for concurrent experiment support.

Manages the lifecycle of VM instances with smart reuse logic to optimize
resource usage while enabling multiple experiments to run concurrently.

Uses:
- Unit of Work pattern for atomic port allocation
- Identifier Strategy pattern for hypervisor-agnostic VM identification
- Specific exception types for better error handling
"""

import asyncio
import logging
import threading
from datetime import datetime, timedelta, UTC
from typing import Optional, List
from pathlib import Path

from adare.database.models.global_models import VmInstance
from adare.backend.vm.port_manager import reserve_port_atomically
from adare.backend.vm.exceptions import VMError
from adare.hypervisor.exceptions import (
    PortAllocationException,
    InstanceNotFoundException,
    InstanceStateException,
)
from adare.hypervisor.base.identifier_strategy import (
    get_identifier_strategy,
    get_vm_state as strategy_get_vm_state,
    verify_vm_exists,
)
from adarelib.constants import VMStatus
import ulid

log = logging.getLogger(__name__)


class VmInstanceManager:
    """
    Manages VM instances with smart reuse logic.

    Provides efficient VM instance allocation, reuse, and cleanup
    to support concurrent experiments while minimizing resource waste.
    """

    # Configuration
    MAX_INSTANCES_PER_VM = 5  # Maximum instances per source VM
    CLEANUP_AGE_DAYS = 7      # Age threshold for automatic cleanup

    def __init__(self):
        self._lock = threading.Lock()

    def find_available_instance(self, vm_id: str) -> Optional[VmInstance]:
        """
        Find an available VM instance for reuse.

        Args:
            vm_id: Source VM ID to find instances for

        Returns:
            Available VmInstance or None if none available
        """
        log.debug(f"find_available_instance called for vm_id={vm_id}")
        from adare.database.api.vm import VmApi

        try:
            with VmApi() as api:
                instances = api.get_vm_instances_for_vm(vm_id, status='available')
                log.debug(f"Found {len(instances)} available instances for vm_id={vm_id}")

                if instances:
                    # Return the most recently used available instance
                    instances.sort(key=lambda x: x.last_used_at, reverse=True)
                    selected = instances[0]
                    log.debug(f"Selected available instance: {selected.instance_name} (last used: {selected.last_used_at})")
                    return selected

                log.debug(f"No available instances found for vm_id={vm_id}")
                return None
        except Exception as e:
            log.error(f"Error in find_available_instance: {e}")
            raise

    def get_instance_count_for_vm(self, vm_id: str) -> int:
        """
        Get total number of instances for a source VM.

        Args:
            vm_id: Source VM ID

        Returns:
            Number of instances (all statuses)
        """
        from adare.database.api.vm import VmApi

        with VmApi() as api:
            instances = api.get_vm_instances_for_vm(vm_id)
            return len(instances)

    async def cleanup_oldest_available_instance(self, vm_id: str) -> bool:
        """
        Clean up the oldest available instance for a VM.

        Args:
            vm_id: Source VM ID

        Returns:
            True if an instance was cleaned up
        """
        from adare.database.api.vm import VmApi

        with VmApi() as api:
            instances = api.get_vm_instances_for_vm(vm_id, status='available')

            if instances:
                # Find oldest available instance
                oldest = min(instances, key=lambda x: x.last_used_at)
                log.info(f"Cleaning up oldest available instance: {oldest.instance_name}")

                # Clean up hypervisor VM
                await self._cleanup_hypervisor_instance(oldest)

                # Port deallocation handled automatically by database cleanup

                # Delete from database
                api.delete_vm_instance(oldest.id)
                return True

            return False

    async def create_new_instance(self, vm_id: str, experiment_run_id: str) -> VmInstance:
        """
        Create a new VM instance for an experiment.

        Args:
            vm_id: Source VM ID
            experiment_run_id: Experiment run ID

        Returns:
            Created VmInstance

        Raises:
            VMError: If instance creation fails
        """
        log.debug(f"create_new_instance called - vm_id={vm_id}, experiment_run_id={experiment_run_id}")
        from adare.database.api.vm import VmApi
        import adare.backend.vm.database as vm_database

        # Note: We're already inside the lock from allocate_instance_for_experiment

        try:
            # Check if we need to cleanup old instances first
            current_count = self.get_instance_count_for_vm(vm_id)
            log.debug(f"Current instance count for vm_id={vm_id}: {current_count}/{self.MAX_INSTANCES_PER_VM}")

            if current_count >= self.MAX_INSTANCES_PER_VM:
                log.info(f"VM {vm_id} has {current_count} instances, cleaning up oldest available")
                cleanup_success = await self.cleanup_oldest_available_instance(vm_id)
                if not cleanup_success:
                    # If no available instances to cleanup, we're at capacity
                    raise VMError(log, f"VM {vm_id} at maximum instance capacity ({self.MAX_INSTANCES_PER_VM}) with all instances active")
                log.debug(f"Cleanup completed, proceeding with new instance creation")

            # Get source VM
            log.debug(f"Fetching source VM record for vm_id={vm_id}")
            vm_record = vm_database.get_vm_by_id(vm_id)
            if not vm_record:
                raise VMError(log, f"Source VM {vm_id} not found")

            log.debug(f"Source VM found: {vm_record.name}")

            # Generate unique instance name before port allocation
            instance_name = self._generate_instance_name(vm_record.name, experiment_run_id)
            log.debug(f"Generated instance name: {instance_name}")

            # Atomically allocate port and create instance record in single transaction
            log.debug(f"Atomically reserving port and creating VM instance record")
            instance = None
            instance_id = None
            websocket_port = None

            with VmApi() as api:
                # Reserve port and create instance atomically to prevent race conditions
                websocket_port = reserve_port_atomically(
                    api_session=api,
                    vm_id=vm_id,
                    instance_name=instance_name,
                    experiment_run_id=experiment_run_id
                )

                if not websocket_port:
                    raise VMError(log, "No available websocket ports for new VM instance")

                # Get the created instance (it was created inside reserve_port_atomically)
                instance = api.get_vm_instance_by_name(instance_name)
                if not instance:
                    raise VMError(log, f"Failed to retrieve newly created instance {instance_name}")

                # Extract the ID while the instance is still attached to session
                instance_id = instance.id
                log.info(f"Atomically created VM instance: {instance_name} on port {websocket_port} (ID: {instance_id})")

            # Verify the instance can be retrieved from database after commit
            log.debug(f"Verifying instance {instance_id} can be retrieved from database")
            with VmApi() as api:
                verification = api.get_vm_instance_by_id(instance_id)
                if verification:
                    log.debug(f"Instance verification successful - port {verification.websocket_port} atomically reserved")
                    return verification  # Return the fresh instance from verification
                else:
                    log.error(f"Instance {instance_id} not retrievable after creation and commit")
                    # Debug: Check what instances exist
                    all_instances = api.get_all_vm_instances()
                    log.error(f"Total instances in DB: {len(all_instances)}")
                    for inst in all_instances[-3:]:  # Show last 3 instances
                        log.error(f"  Recent instance: {inst.id} - {inst.instance_name}")
                    raise VMError(log, f"Database consistency error: created instance {instance_id} but cannot retrieve it")

        except VMError:
            # Re-raise VMErrors as-is to preserve specific error handling
            raise
        except Exception as e:
            log.error(f"Error in create_new_instance: {e}")
            import traceback
            log.debug(f"create_new_instance traceback: {traceback.format_exc()}")
            raise

    async def reuse_instance(self, instance: VmInstance, experiment_run_id: str) -> VmInstance:
        """
        Reuse an existing available VM instance for a new experiment.

        Args:
            instance: Available VmInstance to reuse
            experiment_run_id: New experiment run ID

        Returns:
            Updated VmInstance
        """
        from adare.database.api.vm import VmApi
        from adare.backend.vm.snapshot_manager import verify_instance_base_snapshot_exists

        log.info(f"Reusing VM instance: {instance.instance_name} for experiment {experiment_run_id}")

        # Validate that base snapshot exists before reusing (VirtualBox only)
        if instance.base_snapshot_name and instance.vbox_uuid:
            # Only validate snapshots for VirtualBox instances
            with VmApi() as api:
                source_vm = api.get_vm_by_id(instance.vm_id)
                is_virtualbox = (source_vm and source_vm.hypervisor == 'virtualbox')

            if is_virtualbox:
                snapshot_exists = verify_instance_base_snapshot_exists(instance)
                if not snapshot_exists:
                    log.warning(f"Base snapshot '{instance.base_snapshot_name}' not found for instance {instance.instance_name} - will need recreation")
                    # Reset snapshot info to trigger recreation
                    with VmApi() as api:
                        api.update_vm_instance(
                            instance.id,
                            base_snapshot_name=None
                        )
            else:
                log.debug(f"Skipping snapshot validation for non-VirtualBox instance")

        # Allocate fresh websocket port for reused instance atomically
        from adare.backend.vm.port_manager import PORT_RANGE_START, PORT_RANGE_END

        with VmApi() as api:
            # Find available port within the same transaction to avoid race conditions
            active_instances = api.get_all_vm_instances()
            used_ports = set()

            for inst in active_instances:
                # Only consider active instances with allocated ports in our range
                if (inst.status == 'active' and
                    inst.websocket_port is not None and
                    PORT_RANGE_START <= inst.websocket_port <= PORT_RANGE_END):
                    used_ports.add(inst.websocket_port)

            # Find first available port
            websocket_port = None
            for port in range(PORT_RANGE_START, PORT_RANGE_END + 1):
                if port not in used_ports:
                    websocket_port = port
                    break

            if not websocket_port:
                raise VMError(log, f"No available websocket ports for reused instance {instance.instance_name}")

            log.info(f"Allocated fresh port {websocket_port} for reused instance {instance.instance_name}")

            # Update instance status, assignment, and new port atomically
            api.update_vm_instance(
                instance.id,
                status='active',
                current_experiment_run_id=experiment_run_id,
                websocket_port=websocket_port,
                last_used_at=datetime.now(UTC)
            )

        # Refresh instance data
        with VmApi() as api:
            return api.get_vm_instance_by_id(instance.id)

    async def allocate_instance_for_experiment(self, vm_id: str, experiment_run_id: str) -> VmInstance:
        """
        Allocate a VM instance for an experiment (reuse or create new).

        This is the main entry point for getting a VM instance for an experiment.

        Args:
            vm_id: Source VM ID
            experiment_run_id: Experiment run ID

        Returns:
            VmInstance ready for use
        """
        log.debug(f"allocate_instance_for_experiment called - vm_id={vm_id}, experiment_run_id={experiment_run_id}")

        # Add timeout to lock acquisition
        import threading
        import time
        lock_acquired = False
        start_time = time.time()

        try:
            # Try to acquire lock with timeout
            log.debug(f"Attempting to acquire instance manager lock")
            lock_acquired = self._lock.acquire(timeout=30)  # 30 second timeout
            if not lock_acquired:
                raise VMError(log, "Timeout acquiring instance manager lock after 30 seconds")

            log.debug(f"Lock acquired in {time.time() - start_time:.2f}s")

            # Synchronize database instance states with hypervisor (with stage visibility)
            from adare.backend.experiment.stagectxmanager import StageCtxManager
            from adare.types.stages import VMInstanceSyncStage
            from adare.database.api.vm import VmApi

            log.debug(f"Synchronizing instance states before allocation for vm_id={vm_id}")
            with VmApi() as api:
                instance_count = len(api.get_vm_instances_for_vm(vm_id))

            with StageCtxManager(
                VMInstanceSyncStage(),
                experiment_run_id,
                event=None  # No interrupt support at this level yet
            ) as stage_ctx:
                # Update sub-message to show count
                stage_ctx.stage.sub_msg = f"Checking {instance_count} instances"
                stage_ctx.set_status(stage_ctx.stage.status)

                sync_count = await self.sync_instance_states(vm_id)

                # Update message with result
                stage_ctx.stage.sub_msg = f"Synchronized {sync_count} instances"
                stage_ctx.set_status(stage_ctx.stage.status)

                if sync_count > 0:
                    log.info(f"Synchronized {sync_count} instance states before allocation")

            # First try to find available instance for reuse
            log.debug(f"Searching for available instances for vm_id={vm_id}")
            available_instance = self.find_available_instance(vm_id)

            if available_instance:
                log.info(f"Found available instance for reuse: {available_instance.instance_name}")
                return await self.reuse_instance(available_instance, experiment_run_id)
            else:
                log.info(f"No available instances found, creating new instance")
                return await self.create_new_instance(vm_id, experiment_run_id)

        except Exception as e:
            log.error(f"Error in allocate_instance_for_experiment: {e}")
            raise
        finally:
            if lock_acquired:
                self._lock.release()
                log.debug(f"Released instance manager lock after {time.time() - start_time:.2f}s total")

    async def release_instance(self, instance_id: str):
        """
        Release a VM instance when experiment completes.

        Args:
            instance_id: VM instance ID to release
        """
        from adare.database.api.vm import VmApi

        with VmApi() as api:
            instance = api.get_vm_instance_by_id(instance_id)
            if not instance:
                log.warning(f"VM instance {instance_id} not found for release")
                return

            log.info(f"Releasing VM instance: {instance.instance_name}")

            # Mark as available for reuse and clear websocket_port to free it
            api.update_vm_instance(
                instance_id,
                status='available',
                current_experiment_run_id=None,
                websocket_port=None,  # Clear port so it can be reallocated
                last_used_at=datetime.now(UTC)
            )

    async def cleanup_instance(self, instance_id: str):
        """
        Clean up a specific VM instance.

        Args:
            instance_id: VM instance ID to cleanup

        Raises:
            InstanceNotFoundException: If instance not found
            InstanceStateException: If instance is running and cannot be removed
        """
        from adare.database.api.vm import VmApi

        with VmApi() as api:
            instance = api.get_vm_instance_by_id(instance_id)
            if not instance:
                raise InstanceNotFoundException(instance_id)

            # Check actual hypervisor state before removal
            hypervisor_state = self._get_hypervisor_vm_state(instance)

            if hypervisor_state in ["running", "paused"]:
                raise InstanceStateException(
                    instance.instance_name,
                    current_state=hypervisor_state,
                    expected_states=["poweroff", "shutoff", "not_found"]
                )

            # If VM is stopped or doesn't exist in hypervisor, safe to remove
            log.info(f"Cleaning up VM instance: {instance.instance_name} (ID: {instance_id})")

            # Clean up hypervisor VM if it exists
            await self._cleanup_hypervisor_instance(instance)

            # Port deallocation handled automatically by database cleanup

            # Delete from database
            api.delete_vm_instance(instance_id)

    async def cleanup_old_instances(self, age_days: int = None):
        """
        Clean up old available instances based on age.

        Args:
            age_days: Age threshold in days (default: CLEANUP_AGE_DAYS)
        """
        from adare.database.api.vm import VmApi

        if age_days is None:
            age_days = self.CLEANUP_AGE_DAYS

        cutoff_date = datetime.now(UTC) - timedelta(days=age_days)

        with VmApi() as api:
            old_instances = api.get_old_vm_instances(cutoff_date, status='available')

            for instance in old_instances:
                log.info(f"Cleaning up old instance: {instance.instance_name} (age: {(datetime.now(UTC) - instance.last_used_at).days} days)")
                await self.cleanup_instance(instance.id)

    async def remove_all_instances(self):
        """
        Remove all stopped VM instances.

        Running instances will be skipped with a warning.

        Returns:
            List of removed instance IDs
        """
        from adare.database.api.vm import VmApi

        with VmApi() as api:
            # Get all instances
            all_instances = api.get_all_vm_instances()

            removed_instance_ids = []

            for instance in all_instances:
                log.info(f"Attempting to remove instance: {instance.instance_name} (ID: {instance.id})")
                try:
                    await self.cleanup_instance(instance.id)
                    removed_instance_ids.append(instance.id)
                except InstanceStateException as e:
                    # Instance is running, skip it
                    log.warning(f"Skipped running instance {instance.instance_name} (ID: {instance.id}): {e}")
                except InstanceNotFoundException as e:
                    # Instance already removed, log and continue
                    log.debug(f"Instance {instance.id} already removed: {e}")

            return removed_instance_ids

    def _get_instance_disk_usage(self, instance: VmInstance) -> float:
        """
        Get disk usage for a VM instance in GB.

        Args:
            instance: VmInstance to check

        Returns:
            Disk usage in GB, or 0 if cannot determine
        """
        if not instance.vbox_uuid:
            return 0.0

        try:
            from adare.hypervisor.virtualbox.vm import VirtualBoxVM
            import subprocess

            # Get VM name from UUID
            vm_name = VirtualBoxVM.get_vm_name_by_uuid(instance.vbox_uuid)
            if not vm_name:
                return 0.0

            # Get VM folder path from VirtualBox
            result = subprocess.run(
                ['VBoxManage', 'showvminfo', vm_name, '--machinereadable'],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode != 0:
                return 0.0

            # Parse output to find VM folder
            vm_folder = None
            for line in result.stdout.splitlines():
                if line.startswith('CfgFile='):
                    # CfgFile contains full path to .vbox file
                    cfg_file = line.split('=', 1)[1].strip('"')
                    vm_folder = Path(cfg_file).parent
                    break

            if not vm_folder or not vm_folder.exists():
                return 0.0

            # Calculate total size of VM folder
            total_size = 0
            for file_path in vm_folder.rglob('*'):
                if file_path.is_file():
                    total_size += file_path.stat().st_size

            # Convert to GB
            return total_size / (1024 ** 3)

        except Exception as e:
            log.debug(f"Could not determine disk usage for instance {instance.instance_name}: {e}")
            return 0.0

    def get_instance_stats(self) -> dict:
        """
        Get statistics about VM instances.

        Returns:
            Dictionary with instance statistics including disk usage
        """
        from adare.database.api.vm import VmApi

        with VmApi() as api:
            all_instances = api.get_all_vm_instances()

            # Calculate disk usage and running status
            total_disk_gb = 0.0
            instance_details = []

            for instance in all_instances:
                disk_gb = self._get_instance_disk_usage(instance)
                total_disk_gb += disk_gb

                # Determine if running by checking hypervisor state
                hypervisor_state = self._get_hypervisor_vm_state(instance)
                is_running = hypervisor_state in ["running", "paused"]

                instance_details.append({
                    'id': instance.id,
                    'name': instance.instance_name,
                    'disk_gb': disk_gb,
                    'is_running': is_running,
                    'vm_id': instance.vm_id
                })

            # Count running vs stopped
            running_count = sum(1 for i in instance_details if i['is_running'])
            stopped_count = len(instance_details) - running_count

            # Sort by disk usage for top consumers
            instance_details.sort(key=lambda x: x['disk_gb'], reverse=True)

            stats = {
                'total_instances': len(all_instances),
                'running_instances': running_count,
                'stopped_instances': stopped_count,
                'total_disk_gb': round(total_disk_gb, 2),
                'top_disk_consumers': instance_details[:10]  # Top 10 consumers
            }

            return stats

    def _get_hypervisor_vm_state(self, instance: VmInstance) -> str:
        """
        Get the actual hypervisor state for a VM instance using the identifier strategy.

        This method works for both VirtualBox and QEMU instances.

        Args:
            instance: VmInstance to check

        Returns:
            VM state ('running', 'poweroff', 'not_found', etc.)
        """
        # Load the VM relationship if needed
        from adare.database.api.vm import VmApi

        # Get the VM to determine hypervisor type
        vm = instance.vm
        if not vm:
            with VmApi() as api:
                vm = api.get_vm_by_id(instance.vm_id)

        if not vm:
            log.debug(f"Cannot determine hypervisor for instance {instance.instance_name}")
            return "error"

        # Use identifier strategy for hypervisor-agnostic state checking
        strategy = get_identifier_strategy(vm.hypervisor)
        identifier = strategy.get_identifier(instance)

        if not identifier:
            log.debug(f"Instance {instance.instance_name} has no hypervisor identifier")
            return "not_found"

        state = strategy.get_vm_state(identifier)
        log.debug(f"{vm.hypervisor} state for {instance.instance_name}: {state}")
        return state

    # Keep old method name as alias for backward compatibility
    def _get_virtualbox_vm_state(self, instance: VmInstance) -> str:
        """Alias for _get_hypervisor_vm_state for backward compatibility."""
        return self._get_hypervisor_vm_state(instance)

    async def _check_instance_state_async(self, instance: VmInstance) -> tuple[str, str, str]:
        """
        Asynchronously check hypervisor state for a single instance.

        Uses thread executor to run blocking libvirt calls in parallel without
        blocking the event loop. Each thread gets its own QEMUVM instance with
        isolated libvirt connection for thread-safety.

        Args:
            instance: VmInstance to check

        Returns:
            Tuple of (instance_id, current_db_status, hypervisor_state)
        """
        loop = asyncio.get_event_loop()

        # Run blocking libvirt call in thread executor
        # Each thread will create its own QEMUVM instance via get_vm_by_name()
        # which ensures isolated libvirt connections (thread-safe)
        hypervisor_state = await loop.run_in_executor(
            None,  # Uses default ThreadPoolExecutor
            self._get_hypervisor_vm_state,
            instance
        )

        return (instance.id, instance.status, hypervisor_state)

    async def sync_instance_states(self, vm_id: str) -> int:
        """
        Synchronize database instance states with actual hypervisor VM states.

        Uses parallel execution via asyncio.gather() to check multiple instances
        simultaneously, reducing sync time from O(n×5s) to O(5s) for n instances.

        Uses the identifier strategy pattern for hypervisor-agnostic state checking.

        Args:
            vm_id: Source VM ID to sync instances for

        Returns:
            Number of instances updated
        """
        log.info(f"===== PARALLEL VERSION EXECUTING ===== vm_id={vm_id}")
        log.debug(f"Syncing instance states for vm_id={vm_id}")
        from adare.database.api.vm import VmApi

        updated_count = 0

        with VmApi() as api:
            # Get all instances for this VM
            instances = api.get_vm_instances_for_vm(vm_id)
            log.debug(f"Found {len(instances)} instances to sync for vm_id={vm_id}")

            if not instances:
                return 0

            # Create parallel tasks for state checking
            log.debug(f"Starting parallel state checks for {len(instances)} instances")
            tasks = [
                self._check_instance_state_async(instance)
                for instance in instances
            ]

            # Execute all state checks in parallel
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results and batch update database
            updates_to_apply = []

            for result in results:
                if isinstance(result, Exception):
                    log.error(f"Error checking instance state: {result}")
                    continue

                instance_id, current_db_status, hypervisor_state = result

                # Determine correct database status based on hypervisor state
                new_db_status = None

                if hypervisor_state in ["not_found", "error"]:
                    # VM doesn't exist in hypervisor - mark as available for cleanup/reuse
                    if current_db_status != "available":
                        new_db_status = "available"
                        log.info(f"Instance {instance_id} not found in hypervisor, will mark as available")

                elif hypervisor_state in ["poweroff", "aborted", "saved", "shutoff"]:
                    # VM is stopped - mark as available for reuse
                    # Note: "shutoff" is the libvirt/QEMU state for powered off VMs
                    if current_db_status != "available":
                        new_db_status = "available"
                        log.info(f"Instance {instance_id} is stopped ({hypervisor_state}), will mark as available")

                elif hypervisor_state in ["running", "paused"]:
                    # VM is running - keep status as-is (might be legitimately active)
                    pass

                if new_db_status and new_db_status != current_db_status:
                    updates_to_apply.append((instance_id, new_db_status))

            # Apply all updates in batch
            for instance_id, new_status in updates_to_apply:
                api.update_vm_instance(
                    instance_id,
                    status=new_status,
                    last_used_at=datetime.now(UTC)
                )
                updated_count += 1
                log.info(f"Updated instance {instance_id} status to {new_status}")

            log.info(f"Synchronized {updated_count} instance states for vm_id={vm_id} (parallel mode)")
            return updated_count

    def _generate_instance_name(self, base_vm_name: str, experiment_run_id: str) -> str:
        """
        Generate a unique instance name for VirtualBox.

        Args:
            base_vm_name: Base VM name
            experiment_run_id: Experiment run ID

        Returns:
            Unique instance name
        """
        # Use first 8 characters of experiment run ID for uniqueness
        short_id = experiment_run_id[:8]
        return f"{base_vm_name}_exp_{short_id}"

    async def _cleanup_hypervisor_instance(self, instance: VmInstance):
        """
        Clean up hypervisor VM for an instance using the appropriate strategy.

        Args:
            instance: VmInstance to cleanup
        """
        from adare.database.api.vm import VmApi

        # Get the VM to determine hypervisor type
        vm = instance.vm
        if not vm:
            with VmApi() as api:
                vm = api.get_vm_by_id(instance.vm_id)

        if not vm:
            log.warning(f"Cannot determine hypervisor for instance {instance.instance_name}")
            return

        if vm.hypervisor == 'virtualbox':
            await self._cleanup_virtualbox_vm(instance)
        elif vm.hypervisor == 'qemu':
            await self._cleanup_qemu_vm(instance)
        else:
            log.warning(f"Unknown hypervisor '{vm.hypervisor}' for instance {instance.instance_name}")

    async def _cleanup_virtualbox_vm(self, instance: VmInstance):
        """Clean up VirtualBox VM for an instance."""
        if not instance.vbox_uuid:
            return

        try:
            from adare.hypervisor.virtualbox.vm import VirtualBoxVM
            from adare.hypervisor.virtualbox.manager import VirtualBoxManager

            # Get VM name from UUID
            vm_name = VirtualBoxVM.get_vm_name_by_uuid(instance.vbox_uuid)
            if not vm_name:
                log.warning(f"VirtualBox VM not found for UUID: {instance.vbox_uuid}")
                return

            # Create VirtualBox VM instance and remove it
            manager = VirtualBoxManager()
            vbox_vm = VirtualBoxVM(vm_name, "", manager, "dummy", "dummy", manager.executables)
            await vbox_vm.remove()

            log.info(f"Cleaned up VirtualBox VM: {vm_name}")
        except ImportError:
            log.warning("VirtualBox module not available for cleanup")

    async def _cleanup_qemu_vm(self, instance: VmInstance):
        """Clean up QEMU/libvirt VM for an instance."""
        try:
            from adare.hypervisor.qemu.utilities.uuid_registry import QEMUVMRegistry

            vm = QEMUVMRegistry.get_vm_by_name(instance.instance_name)
            if not vm:
                log.warning(f"QEMU VM not found: {instance.instance_name}")
                return

            await vm.remove()
            log.info(f"Cleaned up QEMU VM: {instance.instance_name}")
        except ImportError:
            log.warning("QEMU module not available for cleanup")

    # Keep old method name as alias for backward compatibility
    async def _cleanup_virtualbox_instance(self, instance: VmInstance):
        """Alias for _cleanup_hypervisor_instance for backward compatibility."""
        await self._cleanup_hypervisor_instance(instance)


# Global instance for system-wide VM instance management
_instance_manager = VmInstanceManager()


async def allocate_vm_instance_for_experiment(vm_id: str, experiment_run_id: str) -> VmInstance:
    """
    Allocate a VM instance for an experiment (main public interface).

    Args:
        vm_id: Source VM ID
        experiment_run_id: Experiment run ID

    Returns:
        VmInstance ready for use
    """
    return await _instance_manager.allocate_instance_for_experiment(vm_id, experiment_run_id)


async def release_vm_instance(instance_id: str):
    """
    Release a VM instance when experiment completes.

    Args:
        instance_id: VM instance ID to release
    """
    await _instance_manager.release_instance(instance_id)


async def cleanup_vm_instance(instance_id: str):
    """
    Clean up a specific VM instance.

    Args:
        instance_id: VM instance ID to cleanup

    Raises:
        VMError: If instance is actually running in VirtualBox
    """
    await _instance_manager.cleanup_instance(instance_id)


async def cleanup_old_vm_instances(age_days: int = None):
    """
    Clean up old available VM instances.

    Args:
        age_days: Age threshold in days
    """
    await _instance_manager.cleanup_old_instances(age_days)


async def remove_all_instances():
    """
    Remove all stopped VM instances.

    Running instances will be skipped with a warning.

    Returns:
        List of removed instance IDs
    """
    return await _instance_manager.remove_all_instances()


def get_vm_instance_stats() -> dict:
    """
    Get statistics about VM instances.

    Returns:
        Dictionary with instance statistics
    """
    return _instance_manager.get_instance_stats()