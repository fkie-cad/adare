"""
VM Snapshot Management System.

High-level snapshot management for fast experiment setup using VirtualBox snapshots.
Provides base snapshot creation, experiment snapshots, and cleanup utilities.
"""

from pathlib import Path
from typing import Optional, List
import logging
from datetime import datetime, timedelta

from adare.virtualbox.api import VirtualBoxVM, VirtualBoxManager
from adare.backend.vm import database as vm_database
from adare.backend.vm.exceptions import VMError
from adarelib.constants import VMStatus
from adare.database.api.vm import VmApi
from adare.database.models.experiment import VmSnapshot

log = logging.getLogger(__name__)


# ==========================================
# PHASE 3: SNAPSHOT MANAGEMENT SYSTEM
# ==========================================

class SnapshotManager:
    """
    High-level manager for VM snapshots enabling fast experiment setup.
    """
    
    def __init__(self, vbox_manager: VirtualBoxManager = None):
        self.vbox_manager = vbox_manager or VirtualBoxManager()
    
    def create_base_snapshot(self, vm_record, snapshot_name: str = None, 
                           description: str = None, silent: bool = False) -> bool:
        """
        Create a clean base snapshot for a VM.
        
        Args:
            vm_record: VM database record with vbox_uuid
            snapshot_name: Name for the snapshot (auto-generated if None)
            description: Snapshot description
            silent: Suppress logging
            
        Returns:
            True if snapshot created successfully
        """
        if not vm_record.vbox_uuid:
            raise VMError(log, f"VM '{vm_record.name}' has no VirtualBox UUID")
        
        # Generate snapshot name if not provided
        if not snapshot_name:
            snapshot_name = f"adare_base_{vm_record.hash[:8]}"
        
        if not description:
            description = f"Adare base snapshot for {vm_record.name}"
        
        # Get VirtualBox VM instance
        vm_name = self._get_vm_name_by_uuid(vm_record.vbox_uuid)
        if not vm_name:
            raise VMError(log, f"VM with UUID {vm_record.vbox_uuid} not found in VirtualBox")
        
        vbox_vm = VirtualBoxVM(
            vm_name=vm_name,
            guest_os="",  # Will be populated from VBox info
            manager=self.vbox_manager
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
                
                # Track snapshot in database
                self._track_snapshot_in_db(
                    vm_record.id, 
                    snapshot_name, 
                    "base", 
                    None, 
                    description
                )
                
                log.info(f"Created base snapshot '{snapshot_name}' for VM '{vm_record.name}'")
                return True
            else:
                log.error(f"Failed to create base snapshot '{snapshot_name}' for VM '{vm_record.name}'")
                return False
                
        except Exception as e:
            log.error(f"Error creating base snapshot for VM '{vm_record.name}': {e}")
            return False
    
    def restore_base_snapshot(self, vm_record, silent: bool = False) -> bool:
        """
        Restore VM to its clean base snapshot.
        
        Args:
            vm_record: VM database record
            silent: Suppress logging
            
        Returns:
            True if restored successfully
        """
        if not vm_record.base_snapshot_name:
            raise VMError(log, f"VM '{vm_record.name}' has no base snapshot configured")
        
        # Get VirtualBox VM instance
        vm_name = self._get_vm_name_by_uuid(vm_record.vbox_uuid)
        if not vm_name:
            raise VMError(log, f"VM with UUID {vm_record.vbox_uuid} not found in VirtualBox")
        
        vbox_vm = VirtualBoxVM(
            vm_name=vm_name,
            guest_os="",
            manager=self.vbox_manager
        )
        
        try:
            # Restore to base snapshot
            result = vbox_vm.restore_snapshot(
                snapshot_name=vm_record.base_snapshot_name,
                silent=silent
            )
            
            if result:
                log.info(f"Restored VM '{vm_record.name}' to base snapshot '{vm_record.base_snapshot_name}'")
                return True
            else:
                log.error(f"Failed to restore VM '{vm_record.name}' to base snapshot")
                return False
                
        except Exception as e:
            log.error(f"Error restoring base snapshot for VM '{vm_record.name}': {e}")
            return False
    
    def create_experiment_snapshot(self, vm_record, experiment_id: str, 
                                 description: str = None, silent: bool = False) -> Optional[str]:
        """
        Create a snapshot for a specific experiment.
        
        Args:
            vm_record: VM database record
            experiment_id: Unique experiment identifier
            description: Snapshot description
            silent: Suppress logging
            
        Returns:
            Snapshot name if created successfully, None otherwise
        """
        snapshot_name = f"adare_exp_{experiment_id[:8]}"
        
        if not description:
            description = f"Adare experiment snapshot for {experiment_id}"
        
        # Get VirtualBox VM instance
        vm_name = self._get_vm_name_by_uuid(vm_record.vbox_uuid)
        if not vm_name:
            raise VMError(log, f"VM with UUID {vm_record.vbox_uuid} not found in VirtualBox")
        
        vbox_vm = VirtualBoxVM(
            vm_name=vm_name,
            guest_os="",
            manager=self.vbox_manager
        )
        
        try:
            # Create experiment snapshot
            result = vbox_vm.create_snapshot(
                snapshot_name=snapshot_name,
                description=description,
                silent=silent
            )
            
            if result == 0:  # Success
                # Track snapshot in database
                self._track_snapshot_in_db(
                    vm_record.id,
                    snapshot_name,
                    "experiment",
                    experiment_id,
                    description
                )
                
                log.info(f"Created experiment snapshot '{snapshot_name}' for VM '{vm_record.name}'")
                return snapshot_name
            else:
                log.error(f"Failed to create experiment snapshot for VM '{vm_record.name}'")
                return None
                
        except Exception as e:
            log.error(f"Error creating experiment snapshot for VM '{vm_record.name}': {e}")
            return None
    
    def check_base_snapshot_exists(self, vm_record) -> bool:
        """
        Check if base snapshot exists for a VM.
        
        Args:
            vm_record: VM database record
            
        Returns:
            True if base snapshot exists and is accessible
        """
        if not vm_record.base_snapshot_name or not vm_record.vbox_uuid:
            return False
        
        # Get VirtualBox VM instance
        vm_name = self._get_vm_name_by_uuid(vm_record.vbox_uuid)
        if not vm_name:
            return False
        
        vbox_vm = VirtualBoxVM(
            vm_name=vm_name,
            guest_os="",
            manager=self.vbox_manager
        )
        
        try:
            return vbox_vm.snapshot_exists(vm_record.base_snapshot_name)
        except Exception as e:
            log.debug(f"Error checking base snapshot for VM '{vm_record.name}': {e}")
            return False
    
    def cleanup_experiment_snapshots(self, vm_record, keep_recent: int = 5, 
                                   older_than_days: int = 7) -> int:
        """
        Clean up old experiment snapshots to save space.
        
        Args:
            vm_record: VM database record
            keep_recent: Number of recent snapshots to keep
            older_than_days: Delete snapshots older than this many days
            
        Returns:
            Number of snapshots deleted
        """
        if not vm_record.vbox_uuid:
            return 0
        
        # Get experiment snapshots from database
        with VmApi() as api:
            # This would need a new method to get snapshots by VM and type
            experiment_snapshots = self._get_experiment_snapshots_for_vm(vm_record.id)
        
        deleted_count = 0
        cutoff_date = datetime.utcnow() - timedelta(days=older_than_days)
        
        # Sort by creation date (newest first)
        experiment_snapshots.sort(key=lambda s: s.created_at, reverse=True)
        
        # Skip the most recent ones
        snapshots_to_check = experiment_snapshots[keep_recent:]
        
        for snapshot in snapshots_to_check:
            if snapshot.created_at < cutoff_date:
                if self._delete_snapshot(vm_record, snapshot.snapshot_name):
                    deleted_count += 1
        
        log.info(f"Cleaned up {deleted_count} old experiment snapshots for VM '{vm_record.name}'")
        return deleted_count
    
    def get_snapshot_info(self, vm_record) -> dict:
        """
        Get information about VM snapshots.
        
        Args:
            vm_record: VM database record
            
        Returns:
            Dictionary with snapshot information
        """
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
        """Track snapshot creation in database."""
        with VmApi() as api:
            api.create_snapshot_record(
                vm_id=vm_id,
                snapshot_name=snapshot_name,
                snapshot_type=snapshot_type,
                experiment_id=experiment_id,
                description=description
            )
    
    def _get_experiment_snapshots_for_vm(self, vm_id: str) -> List:
        """Get experiment snapshots from database for a VM."""
        with VmApi() as api:
            return api.get_snapshots_for_vm(vm_id, snapshot_type="experiment")
    
    def _delete_snapshot(self, vm_record, snapshot_name: str) -> bool:
        """Delete a snapshot from VirtualBox and database."""
        if not vm_record.vbox_uuid:
            log.warning(f"VM '{vm_record.name}' has no VirtualBox UUID - cannot delete snapshot")
            return False
        
        # Get VirtualBox VM instance
        vm_name = self._get_vm_name_by_uuid(vm_record.vbox_uuid)
        if not vm_name:
            log.warning(f"VM with UUID {vm_record.vbox_uuid} not found in VirtualBox")
            return False
        
        vbox_vm = VirtualBoxVM(
            vm_name=vm_name,
            guest_os="",
            manager=self.vbox_manager
        )
        
        try:
            # First check if snapshot exists
            if not vbox_vm.snapshot_exists(snapshot_name):
                log.info(f"Snapshot '{snapshot_name}' does not exist for VM '{vm_record.name}' - nothing to delete")
                return True
            
            # Delete the snapshot from VirtualBox
            success = vbox_vm.delete_snapshot(snapshot_name, silent=False)
            
            if success:
                # Remove snapshot record from database
                try:
                    with VmApi() as api:
                        api.delete_snapshot_record(vm_record.id, snapshot_name)
                    log.info(f"Deleted snapshot '{snapshot_name}' for VM '{vm_record.name}'")
                except Exception as db_error:
                    log.warning(f"Snapshot deleted from VirtualBox but failed to remove from database: {db_error}")
                return True
            else:
                log.error(f"Failed to delete snapshot '{snapshot_name}' for VM '{vm_record.name}'")
                return False
                
        except Exception as e:
            log.error(f"Error deleting snapshot '{snapshot_name}' for VM '{vm_record.name}': {e}")
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


def restore_vm_to_base_snapshot(vm_record, silent: bool = False) -> bool:
    """
    Convenience function to restore VM to base snapshot.
    
    Args:
        vm_record: VM database record
        silent: Suppress logging
        
    Returns:
        True if restored successfully
    """
    manager = SnapshotManager()
    return manager.restore_base_snapshot(vm_record, silent=silent)


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
    
    # Create VirtualBox VM instance and check snapshot
    vbox_vm = VirtualBoxVM(
        vm_name=vm_name,
        guest_os="",
        manager=VirtualBoxManager()
    )
    
    try:
        return vbox_vm.snapshot_exists(snapshot_name)
    except Exception as e:
        log.debug(f"Error checking snapshot '{snapshot_name}' for UUID {vbox_uuid}: {e}")
        return False