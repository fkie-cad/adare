"""
VM Instance Manager for concurrent experiment support.

Manages the lifecycle of VM instances with smart reuse logic to optimize
resource usage while enabling multiple experiments to run concurrently.
"""

import logging
import threading
from datetime import datetime, timedelta
from typing import Optional, List
from pathlib import Path

from adare.database.models.global_models import VmInstance
from adare.backend.vm.port_manager import allocate_websocket_port
from adare.backend.vm.exceptions import VMError
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
        log.debug(f"CLAUDE: find_available_instance called for vm_id={vm_id}")
        from adare.database.api.vm import VmApi

        try:
            with VmApi() as api:
                instances = api.get_vm_instances_for_vm(vm_id, status='available')
                log.debug(f"CLAUDE: Found {len(instances)} available instances for vm_id={vm_id}")

                if instances:
                    # Return the most recently used available instance
                    instances.sort(key=lambda x: x.last_used_at, reverse=True)
                    selected = instances[0]
                    log.debug(f"CLAUDE: Selected available instance: {selected.instance_name} (last used: {selected.last_used_at})")
                    return selected

                log.debug(f"CLAUDE: No available instances found for vm_id={vm_id}")
                return None
        except Exception as e:
            log.error(f"CLAUDE: Error in find_available_instance: {e}")
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

                # Clean up VirtualBox VM if it exists
                if oldest.vbox_uuid:
                    try:
                        await self._cleanup_virtualbox_instance(oldest)
                    except Exception as e:
                        log.warning(f"Failed to cleanup VirtualBox instance {oldest.instance_name}: {e}")

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
        log.debug(f"CLAUDE: create_new_instance called - vm_id={vm_id}, experiment_run_id={experiment_run_id}")
        from adare.database.api.vm import VmApi
        import adare.backend.vm.database as vm_database

        # Note: We're already inside the lock from allocate_instance_for_experiment

        try:
            # Check if we need to cleanup old instances first
            current_count = self.get_instance_count_for_vm(vm_id)
            log.debug(f"CLAUDE: Current instance count for vm_id={vm_id}: {current_count}/{self.MAX_INSTANCES_PER_VM}")

            if current_count >= self.MAX_INSTANCES_PER_VM:
                log.info(f"CLAUDE: VM {vm_id} has {current_count} instances, cleaning up oldest available")
                cleanup_success = await self.cleanup_oldest_available_instance(vm_id)
                if not cleanup_success:
                    # If no available instances to cleanup, we're at capacity
                    raise VMError(log, f"VM {vm_id} at maximum instance capacity ({self.MAX_INSTANCES_PER_VM}) with all instances active")
                log.debug(f"CLAUDE: Cleanup completed, proceeding with new instance creation")

            # Get source VM
            log.debug(f"CLAUDE: Fetching source VM record for vm_id={vm_id}")
            vm_record = vm_database.get_vm_by_id(vm_id)
            if not vm_record:
                raise VMError(log, f"Source VM {vm_id} not found")

            log.debug(f"CLAUDE: Source VM found: {vm_record.name}")

            # Generate unique instance name before port allocation
            instance_name = self._generate_instance_name(vm_record.name, experiment_run_id)
            log.debug(f"CLAUDE: Generated instance name: {instance_name}")

            # Atomically allocate port and create instance record in single transaction
            log.debug(f"CLAUDE: Atomically reserving port and creating VM instance record")
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
                log.info(f"CLAUDE: Atomically created VM instance: {instance_name} on port {websocket_port} (ID: {instance_id})")

            # Verify the instance can be retrieved from database after commit
            log.debug(f"CLAUDE: Verifying instance {instance_id} can be retrieved from database")
            with VmApi() as api:
                verification = api.get_vm_instance_by_id(instance_id)
                if verification:
                    log.debug(f"CLAUDE: Instance verification successful - port {verification.websocket_port} atomically reserved")
                    return verification  # Return the fresh instance from verification
                else:
                    log.error(f"CLAUDE: Instance {instance_id} not retrievable after creation and commit")
                    # Debug: Check what instances exist
                    all_instances = api.get_all_vm_instances()
                    log.error(f"CLAUDE: Total instances in DB: {len(all_instances)}")
                    for inst in all_instances[-3:]:  # Show last 3 instances
                        log.error(f"CLAUDE:   Recent instance: {inst.id} - {inst.instance_name}")
                    raise VMError(log, f"Database consistency error: created instance {instance_id} but cannot retrieve it")

        except VMError:
            # Re-raise VMErrors as-is to preserve specific error handling
            raise
        except Exception as e:
            log.error(f"CLAUDE: Error in create_new_instance: {e}")
            import traceback
            log.debug(f"CLAUDE: create_new_instance traceback: {traceback.format_exc()}")
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

        # Validate that base snapshot exists before reusing
        if instance.base_snapshot_name and instance.vbox_uuid:
            snapshot_exists = verify_instance_base_snapshot_exists(instance)
            if not snapshot_exists:
                log.warning(f"Base snapshot '{instance.base_snapshot_name}' not found for instance {instance.instance_name} - will need recreation")
                # Reset snapshot info to trigger recreation
                with VmApi() as api:
                    api.update_vm_instance(
                        instance.id,
                        base_snapshot_name=None
                    )

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
                last_used_at=datetime.utcnow()
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
        log.debug(f"CLAUDE: allocate_instance_for_experiment called - vm_id={vm_id}, experiment_run_id={experiment_run_id}")

        # Add timeout to lock acquisition
        import threading
        import time
        lock_acquired = False
        start_time = time.time()

        try:
            # Try to acquire lock with timeout
            log.debug(f"CLAUDE: Attempting to acquire instance manager lock")
            lock_acquired = self._lock.acquire(timeout=30)  # 30 second timeout
            if not lock_acquired:
                raise VMError(log, "Timeout acquiring instance manager lock after 30 seconds")

            log.debug(f"CLAUDE: Lock acquired in {time.time() - start_time:.2f}s")

            # Synchronize database instance states with VirtualBox before allocation
            log.debug(f"CLAUDE: Synchronizing instance states before allocation for vm_id={vm_id}")
            sync_count = await self.sync_instance_states(vm_id)
            if sync_count > 0:
                log.info(f"CLAUDE: Synchronized {sync_count} instance states before allocation")

            # First try to find available instance for reuse
            log.debug(f"CLAUDE: Searching for available instances for vm_id={vm_id}")
            available_instance = self.find_available_instance(vm_id)

            if available_instance:
                log.info(f"CLAUDE: Found available instance for reuse: {available_instance.instance_name}")
                return await self.reuse_instance(available_instance, experiment_run_id)
            else:
                log.info(f"CLAUDE: No available instances found, creating new instance")
                return await self.create_new_instance(vm_id, experiment_run_id)

        except Exception as e:
            log.error(f"CLAUDE: Error in allocate_instance_for_experiment: {e}")
            raise
        finally:
            if lock_acquired:
                self._lock.release()
                log.debug(f"CLAUDE: Released instance manager lock after {time.time() - start_time:.2f}s total")

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
                last_used_at=datetime.utcnow()
            )

    async def cleanup_instance(self, instance_id: str):
        """
        Clean up a specific VM instance.

        Args:
            instance_id: VM instance ID to cleanup

        Raises:
            VMError: If instance is actually running in VirtualBox
        """
        from adare.database.api.vm import VmApi

        with VmApi() as api:
            instance = api.get_vm_instance_by_id(instance_id)
            if not instance:
                log.warning(f"VM instance {instance_id} not found for cleanup")
                return

            # Check actual VirtualBox state before removal
            vbox_state = self._get_virtualbox_vm_state(instance)

            if vbox_state in ["running", "paused"]:
                raise VMError(log, f"Cannot remove running VM instance {instance.instance_name} (ID: {instance_id}). Stop the VM first.")

            # If VM is stopped or doesn't exist in VirtualBox, safe to remove
            log.info(f"Cleaning up VM instance: {instance.instance_name} (ID: {instance_id})")

            # Clean up VirtualBox VM if it exists
            if instance.vbox_uuid:
                try:
                    await self._cleanup_virtualbox_instance(instance)
                except Exception as e:
                    log.warning(f"Failed to cleanup VirtualBox instance {instance.instance_name}: {e}")

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

        cutoff_date = datetime.utcnow() - timedelta(days=age_days)

        with VmApi() as api:
            old_instances = api.get_old_vm_instances(cutoff_date, status='available')

            for instance in old_instances:
                log.info(f"Cleaning up old instance: {instance.instance_name} (age: {(datetime.utcnow() - instance.last_used_at).days} days)")
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
                except VMError as e:
                    # Instance is running, skip it
                    log.warning(f"Skipped running instance {instance.instance_name} (ID: {instance.id})")
                except Exception as e:
                    log.warning(f"Failed to remove instance {instance.id}: {e}")

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
            from adare.virtualbox.api import VirtualBoxVM
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

                # Determine if running by checking VirtualBox state
                vbox_state = self._get_virtualbox_vm_state(instance)
                is_running = vbox_state in ["running", "paused"]

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

    def _get_virtualbox_vm_state(self, instance: VmInstance) -> str:
        """
        Get the actual VirtualBox state for a VM instance.

        Args:
            instance: VmInstance to check

        Returns:
            VirtualBox VM state ('running', 'poweroff', 'not_found', etc.)
        """
        if not instance.vbox_uuid:
            log.debug(f"CLAUDE: Instance {instance.instance_name} has no VirtualBox UUID")
            return "not_found"

        try:
            from adare.virtualbox.api import VirtualBoxVM

            # Get VM name from UUID
            vm_name = VirtualBoxVM.get_vm_name_by_uuid(instance.vbox_uuid)
            if not vm_name:
                log.debug(f"CLAUDE: VirtualBox VM not found for UUID: {instance.vbox_uuid}")
                return "not_found"

            # Create temporary VirtualBox VM instance to check state
            from adare.virtualbox.manager import VirtualBoxManager
            manager = VirtualBoxManager()
            vbox_vm = VirtualBoxVM(vm_name, "", manager, "dummy", "dummy")

            # Get current state
            state = vbox_vm._get_state(raise_on_missing=False)
            log.debug(f"CLAUDE: VirtualBox state for {instance.instance_name}: {state}")
            return state

        except Exception as e:
            log.warning(f"CLAUDE: Error checking VirtualBox state for {instance.instance_name}: {e}")
            return "error"

    async def sync_instance_states(self, vm_id: str) -> int:
        """
        Synchronize database instance states with actual VirtualBox VM states.

        Args:
            vm_id: Source VM ID to sync instances for

        Returns:
            Number of instances updated
        """
        log.debug(f"CLAUDE: Syncing instance states for vm_id={vm_id}")
        from adare.database.api.vm import VmApi

        updated_count = 0

        try:
            with VmApi() as api:
                # Get all instances for this VM
                instances = api.get_vm_instances_for_vm(vm_id)
                log.debug(f"CLAUDE: Found {len(instances)} instances to sync for vm_id={vm_id}")

                for instance in instances:
                    current_db_status = instance.status
                    vbox_state = self._get_virtualbox_vm_state(instance)

                    # Determine correct database status based on VirtualBox state
                    new_db_status = None

                    if vbox_state in ["not_found", "error"]:
                        # VM doesn't exist in VirtualBox - mark as available for cleanup/reuse
                        if current_db_status != "available":
                            new_db_status = "available"
                            log.info(f"CLAUDE: VM instance {instance.instance_name} not found in VirtualBox, marking as available")

                    elif vbox_state in ["poweroff", "aborted", "saved"]:
                        # VM is stopped - mark as available for reuse
                        if current_db_status != "available":
                            new_db_status = "available"
                            log.info(f"CLAUDE: VM instance {instance.instance_name} is stopped ({vbox_state}), marking as available")

                    elif vbox_state in ["running", "paused"]:
                        # VM is running - should be active, but only update if it has no experiment assigned
                        if current_db_status == "available" and not instance.current_experiment_run_id:
                            # This case might indicate a VM that was started manually
                            log.warning(f"CLAUDE: VM instance {instance.instance_name} is running but marked as available - keeping available status")
                        # Otherwise, leave status as-is since it might be legitimately active

                    # Update database if status needs to change
                    if new_db_status and new_db_status != current_db_status:
                        api.update_vm_instance(
                            instance.id,
                            status=new_db_status,
                            last_used_at=datetime.utcnow()
                        )
                        updated_count += 1
                        log.info(f"CLAUDE: Updated instance {instance.instance_name} status: {current_db_status} -> {new_db_status}")

                log.info(f"CLAUDE: Synchronized {updated_count} instance states for vm_id={vm_id}")
                return updated_count

        except Exception as e:
            log.error(f"CLAUDE: Error syncing instance states for vm_id={vm_id}: {e}")
            import traceback
            log.debug(f"CLAUDE: sync_instance_states traceback: {traceback.format_exc()}")
            return 0

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

    async def _cleanup_virtualbox_instance(self, instance: VmInstance):
        """
        Clean up VirtualBox VM for an instance.

        Args:
            instance: VmInstance to cleanup
        """
        from adare.virtualbox.api import VirtualBoxVM, VirtualBoxManager

        if not instance.vbox_uuid:
            return

        # Get VM name from UUID
        vm_name = VirtualBoxVM.get_vm_name_by_uuid(instance.vbox_uuid)
        if not vm_name:
            log.warning(f"VirtualBox VM not found for UUID: {instance.vbox_uuid}")
            return

        # Create VirtualBox VM instance and remove it
        manager = VirtualBoxManager()
        vbox_vm = VirtualBoxVM(vm_name, "", manager, "dummy", "dummy")
        await vbox_vm.remove()

        log.info(f"Cleaned up VirtualBox VM: {vm_name}")


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