"""
VM snapshot management mixin.

Provides CRUD operations for VM snapshot records, including
both deprecated VM-level snapshots and current instance-level snapshots.
"""

import logging
import warnings

from adare.database.models.global_models import VmSnapshot

log = logging.getLogger(__name__)


class VmSnapshotMixin:
    """Mixin providing VM snapshot management operations."""

    def create_snapshot_record(self, vm_instance_id: str, snapshot_name: str, snapshot_type: str,
                              experiment_id: str = None, description: str = None) -> bool:
        """
        DEPRECATED: Use create_instance_snapshot_record instead.
        This method is kept for backward compatibility but will be removed.

        Args:
            vm_instance_id: VM instance database ID (formerly vm_id - now uses instance)
            snapshot_name: Name of the snapshot
            snapshot_type: Type of snapshot (base, experiment, backup)
            experiment_id: Associated experiment ID (if applicable)
            description: Snapshot description

        Returns:
            True if created successfully
        """
        log.warning("create_snapshot_record is deprecated - use create_instance_snapshot_record instead")
        return self.create_instance_snapshot_record(
            vm_instance_id=vm_instance_id,
            snapshot_name=snapshot_name,
            snapshot_type=snapshot_type,
            experiment_id=experiment_id,
            description=description
        )

    def get_snapshots_for_vm(self, vm_id: str, snapshot_type: str = None) -> list:
        """
        DEPRECATED: This method gets snapshots for VM templates which is incorrect.
        Use get_snapshots_for_instance instead.

        Args:
            vm_id: VM database ID (template - snapshots don't belong to templates)
            snapshot_type: Filter by snapshot type (optional)

        Raises:
            NotImplementedError: Always - VMs (templates) don't have snapshots
        """
        warnings.warn(
            "get_snapshots_for_vm is deprecated - use get_snapshots_for_instance instead",
            DeprecationWarning,
            stacklevel=2
        )
        raise NotImplementedError(
            "get_snapshots_for_vm is deprecated - VMs (templates) don't have snapshots. "
            "Use get_snapshots_for_instance instead."
        )

    def delete_snapshot_record(self, vm_id: str, snapshot_name: str) -> bool:
        """
        DEPRECATED: This method deletes snapshots from VM templates which is incorrect.
        Use delete_instance_snapshot_record instead.

        Args:
            vm_id: VM database ID (template - snapshots don't belong to templates)
            snapshot_name: Name of the snapshot to delete

        Raises:
            NotImplementedError: Always - snapshots are managed per-instance, not per-template
        """
        raise NotImplementedError(
            "delete_snapshot_record is deprecated - VMs (templates) don't have snapshots. "
            "Snapshots are managed per-instance. Use delete_instance_snapshot_record instead."
        )

    def create_instance_snapshot_record(self, vm_instance_id: str, snapshot_name: str, snapshot_type: str,
                                      experiment_id: str = None, description: str = None) -> bool:
        """
        Create a snapshot record for a VM instance in the database.

        Args:
            vm_instance_id: VM instance database ID
            snapshot_name: Name of the snapshot
            snapshot_type: Type of snapshot (base, experiment, backup)
            experiment_id: Associated experiment ID (if applicable)
            description: Snapshot description

        Returns:
            True if created successfully
        """
        with self:
            snapshot_record = VmSnapshot(
                vm_instance_id=vm_instance_id,
                name=snapshot_name,
                snapshot_type=snapshot_type,
                description=description
            )

            self._session.add(snapshot_record)
            self._session.commit()
            log.debug(f"Created instance snapshot record '{snapshot_name}' (type: {snapshot_type}) for VM instance {vm_instance_id}")
            return True

    def get_snapshots_for_instance(self, vm_instance_id: str, snapshot_type: str = None) -> list[VmSnapshot]:
        """
        Get all snapshots for a VM instance.

        Args:
            vm_instance_id: VM instance ID
            snapshot_type: Optional filter by snapshot type

        Returns:
            List of VmSnapshot records
        """
        with self:
            query = self._session.query(VmSnapshot).filter_by(vm_instance_id=vm_instance_id)
            snapshots = query.all()

            # Detach from session
            for snapshot in snapshots:
                self._session.expunge(snapshot)

            return snapshots

    def delete_instance_snapshot_record(self, vm_instance_id: str, snapshot_name: str) -> bool:
        """
        Delete a snapshot record for a VM instance from the database.

        Args:
            vm_instance_id: VM instance database ID
            snapshot_name: Name of the snapshot to delete

        Returns:
            True if deleted successfully (or didn't exist)
        """
        with self:
            snapshot = self._session.query(VmSnapshot).filter_by(
                vm_instance_id=vm_instance_id,
                name=snapshot_name
            ).first()

            if snapshot:
                self._session.delete(snapshot)
                self._session.commit()
                log.debug(f"Deleted snapshot record '{snapshot_name}' for VM instance {vm_instance_id}")
            else:
                log.debug(f"Snapshot record '{snapshot_name}' not found for VM instance {vm_instance_id} - nothing to delete")

            return True
