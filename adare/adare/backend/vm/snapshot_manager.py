"""
VM Snapshot Management System.

High-level snapshot management for fast experiment setup using VirtualBox snapshots.
Provides base snapshot creation, experiment snapshots, and cleanup utilities.
"""

from pathlib import Path
from typing import Optional, List
import logging
from datetime import datetime, timedelta

from adare.hypervisor.virtualbox.vm import VirtualBoxVM
from adare.hypervisor.virtualbox.manager import VirtualBoxManager
from adare.hypervisor.qemu.vm import QEMUVM
from adare.hypervisor.qemu.manager import QEMUManager
from adare.hypervisor.exceptions import VMNotFoundException
from adare.backend.vm import database as vm_database
from adare.backend.vm.exceptions import VMError
from adarelib.constants import VMStatus
from adare.database.api.vm import VmApi
from adare.database.models.global_models import VmSnapshot

log = logging.getLogger(__name__)


class SnapshotManager:
    """
    High-level manager for VM snapshots enabling fast experiment setup.
    """
    
    def __init__(self, vbox_manager: VirtualBoxManager = None):
        self.vbox_manager = vbox_manager or VirtualBoxManager()
    
    def create_base_snapshot(self, vm_record, snapshot_name: str = None,
                           description: str = None, silent: bool = False) -> bool:
        """
        DEPRECATED: Vm records no longer track VirtualBox UUIDs.
        Use create_base_snapshot_for_instance() instead for VmInstance records.

        Args:
            vm_record: VM database record (abstract template)
            snapshot_name: Name for the snapshot (auto-generated if None)
            description: Snapshot description
            silent: Suppress logging

        Returns:
            False - this function is deprecated
        """
        log.error("create_base_snapshot is deprecated - Vm records don't track VirtualBox state")
        log.error("Use create_base_snapshot_for_instance() for VmInstance records instead")
        return False

        if False and not vm_record.vbox_uuid:
            # Attempt to recover the UUID by looking it up in VirtualBox
            log.warning(f"VM '{vm_record.name}' has no VirtualBox UUID - attempting to retrieve it")
            try:
                recovered_uuid = VirtualBoxVM.get_vm_uuid_by_name(vm_record.name)
                if recovered_uuid:
                    # Update the database with the recovered UUID
                    with VmApi() as api:
                        success = api.update_vm_uuid_and_snapshot_info(
                            vm_record.id,
                            vbox_uuid=recovered_uuid,
                            base_snapshot_name=vm_record.base_snapshot_name,
                            use_snapshots=vm_record.use_snapshots if hasattr(vm_record, 'use_snapshots') else True
                        )
                    if success:
                        log.info(f"Successfully recovered VirtualBox UUID for VM '{vm_record.name}': {recovered_uuid}")
                        # Update the vm_record object for the rest of this function
                        vm_record.vbox_uuid = recovered_uuid
                    else:
                        log.error(f"Failed to update recovered UUID in database for VM '{vm_record.name}'")
                        raise VMError(log, f"VM '{vm_record.name}' has no VirtualBox UUID and recovery failed")
                else:
                    raise VMError(log, f"VM '{vm_record.name}' has no VirtualBox UUID and could not be found in VirtualBox")
            except Exception as e:
                log.error(f"Failed to recover UUID for VM '{vm_record.name}': {e}")
                raise VMError(log, f"VM '{vm_record.name}' has no VirtualBox UUID and recovery failed: {e}")
        
        # Generate snapshot name if not provided
        if not snapshot_name:
            snapshot_name = f"adare_base_{vm_record.hash[:8]}"
        
        if not description:
            description = f"Adare base snapshot for {vm_record.name}"
        
        # Get VirtualBox VM instance
        vm_name = self._get_vm_name_by_uuid(vm_record.vbox_uuid)
        if not vm_name:
            raise VMError(log, f"VM with UUID {vm_record.vbox_uuid} not found in VirtualBox")
        
        # Get OS platform for credentials
        from adare.config import get_vm_credentials
        platform = getattr(vm_record.osinfo, 'platform', 'linux') if hasattr(vm_record, 'osinfo') and vm_record.osinfo else 'linux'
        username, password = get_vm_credentials(platform)

        vbox_vm = VirtualBoxVM(
            vm_name=vm_name,
            guest_os=platform,
            manager=self.vbox_manager,
            username=username,
            password=password,
            executables=self.vbox_manager.executables
        )

        try:
            # Create the snapshot
            result = vbox_vm.create_snapshot(
                snapshot_name=snapshot_name,
                description=description,
                silent=silent
            )
            
            if result == 0:  # Success
                # Update database record with snapshot info
                with VmApi() as api:
                    api.update_vm_uuid_and_snapshot_info(
                        vm_record.id,
                        vm_record.vbox_uuid,
                        base_snapshot_name=snapshot_name,
                        use_snapshots=True
                    )

                # DEPRECATED: This tracks snapshot on VM template which is wrong
                # Snapshots should only be tracked on VM instances
                log.warning("Snapshot tracking on VM templates is deprecated - use instance-based snapshots")
                
                log.info(f"Created base snapshot '{snapshot_name}' for VM '{vm_record.name}'")
                return True
            else:
                log.error(f"Failed to create base snapshot '{snapshot_name}' for VM '{vm_record.name}'")
                return False
                
        except Exception as e:
            log.error(f"Error creating base snapshot for VM '{vm_record.name}': {e}")
            return False
    
    def restore_base_snapshot(self, vm_record, silent: bool = False,
                             interrupt_event: Optional['threading.Event'] = None,
                             timeout: int = 120) -> bool:
        """
        DEPRECATED: Vm records no longer track VirtualBox UUIDs.
        Use restore_base_snapshot_for_instance() instead for VmInstance records.

        Args:
            vm_record: VM database record (abstract template)
            silent: Suppress logging
            interrupt_event: Event to check for user interruption
            timeout: Timeout in seconds for the operation (default: 120)

        Returns:
            False - this function is deprecated
        """
        log.error("restore_base_snapshot is deprecated - Vm records don't track VirtualBox state")
        log.error("Use restore_base_snapshot_for_instance() for VmInstance records instead")
        return False

        import threading

        if False and not vm_record.base_snapshot_name:
            raise VMError(log, f"VM '{vm_record.name}' has no base snapshot configured")

        # Check for interruption before starting
        if interrupt_event and interrupt_event.is_set():
            log.info(f"CLAUDE: Snapshot restore cancelled before starting for VM '{vm_record.name}'")
            return False

        # Get VirtualBox VM instance
        vm_name = self._get_vm_name_by_uuid(vm_record.vbox_uuid)
        if not vm_name:
            raise VMError(log, f"VM with UUID {vm_record.vbox_uuid} not found in VirtualBox")

        # Get OS platform for credentials
        from adare.config import get_vm_credentials
        platform = getattr(vm_record.osinfo, 'platform', 'linux') if hasattr(vm_record, 'osinfo') and vm_record.osinfo else 'linux'
        username, password = get_vm_credentials(platform)

        vbox_vm = VirtualBoxVM(
            vm_name=vm_name,
            guest_os=platform,
            manager=self.vbox_manager,
            username=username,
            password=password,
            executables=self.vbox_manager.executables
        )

        try:
            # Add detailed logging for debugging hanging issues
            log.info(f"CLAUDE: Starting snapshot restore for VM '{vm_record.name}' to '{vm_record.base_snapshot_name}' (timeout: {timeout}s)")

            # Restore to base snapshot with interrupt support
            result = vbox_vm.restore_snapshot(
                snapshot_name=vm_record.base_snapshot_name,
                silent=silent,
                stop_event=interrupt_event
            )

            # Check for interruption after operation
            if interrupt_event and interrupt_event.is_set():
                log.info(f"CLAUDE: Snapshot restore interrupted for VM '{vm_record.name}'")
                return False

            if result:
                log.info(f"CLAUDE: Successfully restored VM '{vm_record.name}' to base snapshot '{vm_record.base_snapshot_name}'")
                return True
            else:
                log.error(f"CLAUDE: Failed to restore VM '{vm_record.name}' to base snapshot - VBoxManage returned failure")
                return False

        except InterruptedError:
            log.info(f"CLAUDE: Snapshot restore operation interrupted for VM '{vm_record.name}'")
            return False
        except Exception as e:
            # Provide more specific error information
            if "timeout" in str(e).lower():
                log.error(f"CLAUDE: Snapshot restore timed out after {timeout}s for VM '{vm_record.name}': {e}")
            else:
                log.error(f"CLAUDE: Error restoring base snapshot for VM '{vm_record.name}': {e}")
            return False
    
    def create_experiment_snapshot_for_instance(self, vm_instance, experiment_id: str,
                                              description: str = None, silent: bool = False) -> Optional[str]:
        """
        Create a snapshot for a specific experiment on a VM instance.

        Args:
            vm_instance: VmInstance database record with vbox_uuid
            experiment_id: Unique experiment identifier
            description: Snapshot description
            silent: Suppress logging

        Returns:
            Snapshot name if created successfully, None otherwise
        """
        # Generate snapshot name
        snapshot_name = f"adare_exp_{experiment_id[:8]}"

        if not description:
            description = f"Adare experiment snapshot for {experiment_id}"

        # Get hypervisor-appropriate VM object
        try:
            vm_obj = self._get_vm_object(vm_instance)
        except (VMError, VMNotFoundException) as e:
            log.error(f"Failed to get VM object: {e}")
            return None

        # Ensure QEMU VMs are stopped
        if not self._ensure_vm_stopped_for_qemu(vm_obj, vm_instance, "experiment snapshot creation"):
            return None

        try:
            # Create experiment snapshot
            result = vm_obj.create_snapshot(
                snapshot_name=snapshot_name,
                description=description,
                silent=silent
            )

            if result == 0:  # Success
                # Track snapshot in database
                self._track_instance_snapshot_in_db(
                    vm_instance.id,
                    snapshot_name,
                    "experiment",
                    experiment_id,
                    description
                )

                log.info(f"Created experiment snapshot '{snapshot_name}' for VM instance '{vm_instance.instance_name}'")
                return snapshot_name
            else:
                log.error(f"Failed to create experiment snapshot '{snapshot_name}' for VM instance '{vm_instance.instance_name}'")
                return None

        except VMNotFoundException as e:
            log.error(f"VM not found: {e}")
            return None
        except OSError as e:
            log.error(f"File system error during snapshot creation: {e}")
            return None
    
    def check_base_snapshot_exists(self, vm_record) -> bool:
        """
        DEPRECATED: Vm records no longer track VirtualBox UUIDs.
        Use check_base_snapshot_exists_for_instance() instead for VmInstance records.

        Args:
            vm_record: VM database record (abstract template)

        Returns:
            False - this function is deprecated
        """
        log.error("check_base_snapshot_exists is deprecated - Vm records don't track VirtualBox state")
        return False

        if False and (not vm_record.base_snapshot_name or not vm_record.vbox_uuid):
            return False
        
        # Get VirtualBox VM instance
        vm_name = self._get_vm_name_by_uuid(vm_record.vbox_uuid)
        if not vm_name:
            return False
        
        # Get OS platform for credentials
        from adare.config import get_vm_credentials
        platform = getattr(vm_record.osinfo, 'platform', 'linux') if hasattr(vm_record, 'osinfo') and vm_record.osinfo else 'linux'
        username, password = get_vm_credentials(platform)

        vbox_vm = VirtualBoxVM(
            vm_name=vm_name,
            guest_os=platform,
            manager=self.vbox_manager,
            username=username,
            password=password,
            executables=self.vbox_manager.executables
        )

        try:
            return vbox_vm.snapshot_exists(vm_record.base_snapshot_name)
        except Exception as e:
            log.debug(f"Error checking base snapshot for VM '{vm_record.name}': {e}")
            return False
    
    def get_snapshot_info(self, vm_record) -> dict:
        """
        DEPRECATED: Vm records no longer track VirtualBox UUIDs.
        Use get_snapshot_info_for_instance() instead for VmInstance records.

        Args:
            vm_record: VM database record (abstract template)

        Returns:
            Empty dictionary - this function is deprecated
        """
        log.warning("get_snapshot_info is deprecated - Vm records don't track VirtualBox state")
        return {"base_snapshot": {"name": None, "exists": False}, "experiment_snapshots": [], "total_snapshots": 0}

        info = {
            "base_snapshot": {
                "name": vm_record.base_snapshot_name,
                "exists": False
            },
            "experiment_snapshots": [],
            "total_snapshots": 0
        }
        
        if vm_record.base_snapshot_name:
            info["base_snapshot"]["exists"] = self.check_base_snapshot_exists(vm_record)
        
        # Get experiment snapshots from database
        experiment_snapshots = self._get_experiment_snapshots_for_vm(vm_record.id)
        info["experiment_snapshots"] = [
            {
                "name": s.snapshot_name,
                "experiment_id": s.experiment_id,
                "created_at": s.created_at,
                "description": s.description
            }
            for s in experiment_snapshots
        ]
        info["total_snapshots"] = len(experiment_snapshots) + (1 if info["base_snapshot"]["exists"] else 0)
        
        return info
    
    # Private helper methods
    
    def _get_vm_name_by_uuid(self, vbox_uuid: str) -> Optional[str]:
        """Get VM name from VirtualBox using UUID."""
        return VirtualBoxVM.get_vm_name_by_uuid(vbox_uuid)
    
    def _track_snapshot_in_db(self, vm_id: str, snapshot_name: str, snapshot_type: str,
                             experiment_id: Optional[str], description: str):
        """
        DEPRECATED: Track snapshot creation in database for VM templates.
        Use _track_instance_snapshot_in_db instead.
        """
        log.error("_track_snapshot_in_db is deprecated - VM templates don't have snapshots. Use _track_instance_snapshot_in_db instead.")

    def _get_experiment_snapshots_for_vm(self, vm_id: str) -> List:
        """
        DEPRECATED: Get experiment snapshots from database for a VM template.
        Use get_snapshots_for_instance instead.
        """
        log.warning("_get_experiment_snapshots_for_vm is deprecated - VM templates don't have snapshots.")
        return []
    
    def _delete_snapshot(self, vm_record, snapshot_name: str) -> tuple[bool, str]:
        """
        DEPRECATED: Delete a snapshot from VirtualBox and database for VM templates.
        Use instance-based snapshot deletion instead.
        """
        log.error(f"_delete_snapshot is deprecated - VM templates don't have snapshots. Use instance-based snapshot deletion.")
        return False, "VM templates don't have snapshots - use instance-based snapshots"

    # Instance-specific snapshot methods

    def _get_vm_object(self, vm_instance):
        """
        Get appropriate VM object (VirtualBoxVM or QEMUVM) based on hypervisor type.

        Args:
            vm_instance: VmInstance database record with vm relationship

        Returns:
            VirtualBoxVM or QEMUVM instance configured for the VM

        Raises:
            VMError: If hypervisor unsupported or VM not found
            VMNotFoundException: If VM doesn't exist in hypervisor
        """
        from adare.config import get_vm_credentials

        # Get hypervisor type from source VM
        hypervisor = vm_instance.vm.hypervisor

        if hypervisor == 'virtualbox':
            # VirtualBox: use vbox_uuid to get VM
            if not vm_instance.vbox_uuid:
                raise VMError(log, f"VirtualBox VM instance '{vm_instance.instance_name}' has no vbox_uuid")

            vm_name = self._get_vm_name_by_uuid(vm_instance.vbox_uuid)
            if not vm_name:
                raise VMError(log, f"VirtualBox VM with UUID {vm_instance.vbox_uuid} not found")

            platform = getattr(vm_instance.vm.osinfo, 'platform', 'linux') if hasattr(vm_instance.vm, 'osinfo') and vm_instance.vm.osinfo else 'linux'
            username, password = get_vm_credentials(platform)

            return VirtualBoxVM(
                vm_name=vm_name,
                guest_os=platform,
                manager=self.vbox_manager,
                username=username,
                password=password,
                executables=self.vbox_manager.executables
            )

        elif hypervisor == 'qemu':
            # QEMU: use instance_name to load VM config
            try:
                qemu_vm = QEMUVM.get_vm_by_name(
                    vm_name=vm_instance.instance_name,
                    manager=QEMUManager()
                )
                return qemu_vm
            except VMNotFoundException as e:
                raise VMError(log, f"QEMU VM instance '{vm_instance.instance_name}' not found: {e}")

        else:
            raise VMError(log, f"Unsupported hypervisor: {hypervisor}")

    def _ensure_vm_stopped_for_qemu(self, vm_obj, vm_instance, operation_name: str) -> bool:
        """
        Ensure QEMU VM is stopped before snapshot operation.
        VirtualBox VMs can snapshot while running, so this only affects QEMU.

        Args:
            vm_obj: QEMUVM or VirtualBoxVM instance
            vm_instance: VmInstance database record
            operation_name: Name of operation for error messages

        Returns:
            True if VM is in correct state, False if operation should abort
        """
        hypervisor = vm_instance.vm.hypervisor

        if hypervisor != 'qemu':
            return True  # VirtualBox: no state check needed

        try:
            state = vm_obj.get_state()
            if state != 'poweroff':
                log.error(
                    f"QEMU VM must be stopped for {operation_name}. "
                    f"Current state: {state}. Stop the VM first with: adare vm stop {vm_instance.instance_name}"
                )
                return False
            return True
        except OSError as e:
            log.error(f"Error checking VM state for {operation_name}: {e}")
            return False

    def create_base_snapshot_for_instance(self, vm_instance, snapshot_name: str = None,
                                        description: str = None, silent: bool = False) -> bool:
        """
        Create a clean base snapshot for a VM instance.

        Args:
            vm_instance: VmInstance database record with vbox_uuid
            snapshot_name: Name for the snapshot (auto-generated if None)
            description: Snapshot description
            silent: Suppress logging

        Returns:
            True if snapshot created successfully
        """
        # Generate snapshot name if not provided
        if not snapshot_name:
            snapshot_name = f"{vm_instance.instance_name}_base"

        if not description:
            description = f"Adare base snapshot for instance {vm_instance.instance_name}"

        # Get hypervisor-appropriate VM object
        try:
            vm_obj = self._get_vm_object(vm_instance)
        except (VMError, VMNotFoundException) as e:
            log.error(f"Failed to get VM object: {e}")
            return False

        # Ensure QEMU VMs are stopped
        if not self._ensure_vm_stopped_for_qemu(vm_obj, vm_instance, "snapshot creation"):
            return False

        try:
            # Create the snapshot
            result = vm_obj.create_snapshot(
                snapshot_name=snapshot_name,
                description=description,
                silent=silent
            )

            if result == 0:  # Success
                # Update instance record with snapshot info
                from adare.database.api.vm import VmApi
                with VmApi() as api:
                    api.update_vm_instance(
                        vm_instance.id,
                        base_snapshot_name=snapshot_name,
                        use_snapshots=True
                    )

                # Track snapshot in database
                self._track_instance_snapshot_in_db(
                    vm_instance.id,
                    snapshot_name,
                    "base",
                    None,
                    description
                )

                log.info(f"Created base snapshot '{snapshot_name}' for VM instance '{vm_instance.instance_name}'")
                return True
            else:
                log.error(f"Failed to create base snapshot '{snapshot_name}' for VM instance '{vm_instance.instance_name}'")
                return False

        except VMNotFoundException as e:
            log.error(f"VM not found: {e}")
            return False
        except OSError as e:
            log.error(f"File system error during snapshot creation: {e}")
            return False

    def restore_instance_to_base_snapshot(self, vm_instance, silent: bool = False,
                                        interrupt_event: Optional['threading.Event'] = None,
                                        timeout: int = 120) -> bool:
        """
        Restore VM instance to its clean base snapshot.

        Args:
            vm_instance: VmInstance database record
            silent: Suppress logging
            interrupt_event: Event to check for user interruption
            timeout: Timeout in seconds for the operation (default: 120)

        Returns:
            True if restored successfully
        """
        import threading

        if not vm_instance.base_snapshot_name:
            log.error(f"VM instance '{vm_instance.instance_name}' has no base snapshot configured")
            return False

        # Check for interruption before starting
        if interrupt_event and interrupt_event.is_set():
            log.info(f"CLAUDE: Snapshot restore cancelled before starting for VM instance '{vm_instance.instance_name}'")
            return False

        # Get hypervisor-appropriate VM object
        try:
            vm_obj = self._get_vm_object(vm_instance)
        except (VMError, VMNotFoundException) as e:
            log.error(f"Failed to get VM object: {e}")
            return False

        # Ensure QEMU VMs are stopped
        if not self._ensure_vm_stopped_for_qemu(vm_obj, vm_instance, "snapshot restore"):
            return False

        try:
            # Add detailed logging for debugging hanging issues
            log.info(f"CLAUDE: Starting snapshot restore for VM instance '{vm_instance.instance_name}' to '{vm_instance.base_snapshot_name}' (timeout: {timeout}s)")

            # Restore to base snapshot with interrupt support
            result = vm_obj.restore_snapshot(
                snapshot_name=vm_instance.base_snapshot_name,
                silent=silent,
                stop_event=interrupt_event
            )

            # Check for interruption after operation
            if interrupt_event and interrupt_event.is_set():
                log.info(f"CLAUDE: Snapshot restore interrupted for VM instance '{vm_instance.instance_name}'")
                return False

            if result:
                log.info(f"CLAUDE: Successfully restored VM instance '{vm_instance.instance_name}' to base snapshot '{vm_instance.base_snapshot_name}'")
                return True
            else:
                log.error(f"CLAUDE: Failed to restore VM instance '{vm_instance.instance_name}' to base snapshot - VBoxManage returned failure")
                return False

        except InterruptedError:
            log.info(f"CLAUDE: Snapshot restore operation interrupted for VM instance '{vm_instance.instance_name}'")
            return False
        except VMNotFoundException as e:
            log.error(f"VM or snapshot not found: {e}")
            return False
        except OSError as e:
            log.error(f"File system error during restore: {e}")
            return False

    def check_instance_base_snapshot_exists(self, vm_instance) -> bool:
        """
        Check if base snapshot exists for a VM instance.

        Args:
            vm_instance: VmInstance database record

        Returns:
            True if base snapshot exists and is accessible
        """
        if not vm_instance.base_snapshot_name:
            return False

        try:
            vm_obj = self._get_vm_object(vm_instance)
            return vm_obj.snapshot_exists(vm_instance.base_snapshot_name)
        except (VMError, VMNotFoundException) as e:
            log.debug(f"Error checking base snapshot: {e}")
            return False

    def _track_instance_snapshot_in_db(self, vm_instance_id: str, snapshot_name: str, snapshot_type: str,
                                     experiment_id: Optional[str], description: str):
        """Track instance snapshot creation in database."""
        from adare.database.api.vm import VmApi
        with VmApi() as api:
            api.create_instance_snapshot_record(
                vm_instance_id=vm_instance_id,
                snapshot_name=snapshot_name,
                snapshot_type=snapshot_type,
                experiment_id=experiment_id,
                description=description
            )

    def delete_instance_snapshot(self, vm_instance, snapshot_name: str, silent: bool = False) -> bool:
        """
        Delete a snapshot from a VM instance.

        Args:
            vm_instance: VmInstance database record with vbox_uuid
            snapshot_name: Name of the snapshot to delete
            silent: Suppress logging

        Returns:
            True if snapshot deleted successfully

        Raises:
            VMError: If attempting to delete a base snapshot
        """
        # Protect base snapshots from deletion
        if vm_instance.base_snapshot_name and snapshot_name == vm_instance.base_snapshot_name:
            raise VMError(log, f"Cannot delete base snapshot '{snapshot_name}' - base snapshots are protected from deletion")

        # Get hypervisor-appropriate VM object
        try:
            vm_obj = self._get_vm_object(vm_instance)
        except (VMError, VMNotFoundException) as e:
            log.error(f"Failed to get VM object: {e}")
            return False

        # Ensure QEMU VMs are stopped
        if not self._ensure_vm_stopped_for_qemu(vm_obj, vm_instance, "snapshot deletion"):
            return False

        try:
            # Delete the snapshot
            result = vm_obj.delete_snapshot(
                snapshot_name=snapshot_name,
                silent=silent
            )

            if result:  # Success
                # Remove snapshot record from database
                from adare.database.api.vm import VmApi
                with VmApi() as api:
                    api.delete_instance_snapshot_record(
                        vm_instance_id=vm_instance.id,
                        snapshot_name=snapshot_name
                    )

                log.info(f"Deleted snapshot '{snapshot_name}' from VM instance '{vm_instance.instance_name}'")
                return True
            else:
                log.error(f"Failed to delete snapshot '{snapshot_name}' from VM instance '{vm_instance.instance_name}'")
                return False

        except VMError:
            raise
        except VMNotFoundException as e:
            log.error(f"VM or snapshot not found: {e}")
            return False
        except OSError as e:
            log.error(f"File system error during deletion: {e}")
            return False


# Convenience functions for direct use

def create_base_snapshot_for_vm(vm_record, silent: bool = False) -> bool:
    """
    Convenience function to create base snapshot for a VM.
    
    Args:
        vm_record: VM database record
        silent: Suppress logging
        
    Returns:
        True if snapshot created successfully
    """
    manager = SnapshotManager()
    return manager.create_base_snapshot(vm_record, silent=silent)


def restore_vm_to_base_snapshot(vm_record, silent: bool = False,
                                interrupt_event: Optional['threading.Event'] = None,
                                timeout: int = 120) -> bool:
    """
    Convenience function to restore VM to base snapshot.

    Args:
        vm_record: VM database record
        silent: Suppress logging
        interrupt_event: Event to check for user interruption
        timeout: Timeout in seconds for the operation (default: 120)

    Returns:
        True if restored successfully
    """
    import threading
    manager = SnapshotManager()
    return manager.restore_base_snapshot(vm_record, silent=silent,
                                       interrupt_event=interrupt_event,
                                       timeout=timeout)


def verify_base_snapshot_exists(vm_record) -> bool:
    """
    Convenience function to check if base snapshot exists.
    
    Args:
        vm_record: VM database record
        
    Returns:
        True if base snapshot exists
    """
    manager = SnapshotManager()
    return manager.check_base_snapshot_exists(vm_record)


def check_snapshot_exists_by_uuid(vbox_uuid: str, snapshot_name: str) -> bool:
    """
    Direct function to check if snapshot exists using UUID and name.
    
    Args:
        vbox_uuid: VirtualBox VM UUID
        snapshot_name: Snapshot name to check
        
    Returns:
        True if snapshot exists
    """
    # Get VM name from UUID
    vm_name = VirtualBoxVM.get_vm_name_by_uuid(vbox_uuid)
    if not vm_name:
        return False
    
    # Create VirtualBox VM instance and check snapshot (no credentials needed for snapshot check)
    manager = VirtualBoxManager()
    vbox_vm = VirtualBoxVM(
        vm_name=vm_name,
        guest_os="",
        manager=manager,
        username="dummy",
        password="dummy",
        executables=manager.executables
    )

    try:
        return vbox_vm.snapshot_exists(snapshot_name)
    except Exception as e:
        log.debug(f"Error checking snapshot '{snapshot_name}' for UUID {vbox_uuid}: {e}")
        return False


# Instance-aware convenience functions

def create_base_snapshot_for_instance(vm_instance, silent: bool = False) -> bool:
    """
    Convenience function to create base snapshot for a VM instance.

    Args:
        vm_instance: VmInstance database record
        silent: Suppress logging

    Returns:
        True if snapshot created successfully
    """
    manager = SnapshotManager()
    return manager.create_base_snapshot_for_instance(vm_instance, silent=silent)


def restore_instance_to_base_snapshot(vm_instance, silent: bool = False,
                                    interrupt_event: Optional['threading.Event'] = None,
                                    timeout: int = 120) -> bool:
    """
    Convenience function to restore VM instance to base snapshot.

    Args:
        vm_instance: VmInstance database record
        silent: Suppress logging
        interrupt_event: Event to check for user interruption
        timeout: Timeout in seconds for the operation (default: 120)

    Returns:
        True if restored successfully
    """
    import threading
    manager = SnapshotManager()
    return manager.restore_instance_to_base_snapshot(vm_instance, silent=silent,
                                                   interrupt_event=interrupt_event,
                                                   timeout=timeout)


def verify_instance_base_snapshot_exists(vm_instance) -> bool:
    """
    Convenience function to check if base snapshot exists for VM instance.

    Args:
        vm_instance: VmInstance database record

    Returns:
        True if base snapshot exists
    """
    manager = SnapshotManager()
    return manager.check_instance_base_snapshot_exists(vm_instance)