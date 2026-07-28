"""
VM instance management mixin.

Provides CRUD operations for VM instances, which represent running
or previously-run copies of VM templates.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import joinedload

from adare.database.models.global_models import Vm, VmInstance

from .exceptions import VMLoadError, VMNotFoundError

log = logging.getLogger(__name__)


class VmInstanceMixin:
    """Mixin providing VM instance management operations."""

    def create_vm_instance(self, vm_id: str, instance_name: str, experiment_run_id: str,
                          websocket_port: int, status: str = 'active') -> VmInstance:
        """
        Create a new VM instance entry in the database.

        Args:
            vm_id: Source VM ID
            instance_name: Unique name for the instance
            experiment_run_id: Experiment run ID
            websocket_port: Allocated websocket port
            status: Instance status (default: 'active')

        Returns:
            Created VmInstance

        Raises:
            VMLoadError: If creation fails
        """
        instance = VmInstance(
            vm_id=vm_id,
            instance_name=instance_name,
            current_experiment_run_id=experiment_run_id,
            websocket_port=websocket_port,
            status=status,
            created_at=datetime.now(UTC),
            last_used_at=datetime.now(UTC)
        )

        try:
            with self:
                self._session.add(instance)
                self._session.commit()
                self._session.refresh(instance)

                # Eagerly load the VM relationship before detaching
                instance = self._session.query(VmInstance).options(
                    joinedload(VmInstance.vm).joinedload(Vm.osinfo)
                ).filter_by(id=instance.id).first()

                if instance:
                    self._session.expunge(instance)

                log.info(f"Created VM instance: {instance_name} (ID: {instance.id})")
                return instance
        except IntegrityError:
            # Let a unique-constraint violation (instance_name or the active
            # websocket_port index) reach reserve_port_atomically() unwrapped
            # so it can roll back and retry the next candidate port/name.
            raise
        except SQLAlchemyError as e:
            self._session.rollback()
            raise VMLoadError(log, f"Database error while creating VM instance: {e}") from e

    def get_vm_instance_by_id(self, instance_id: str) -> VmInstance | None:
        """
        Get a VM instance by ID.

        Args:
            instance_id: VM instance ID

        Returns:
            VmInstance or None if not found
        """
        with self:
            instance = self._session.query(VmInstance).options(
                joinedload(VmInstance.vm).joinedload(Vm.osinfo)
            ).filter_by(id=instance_id).first()
            if instance:
                self._session.expunge(instance)
            return instance

    def get_vm_instances_for_vm(self, vm_id: str, status: str = None) -> list[VmInstance]:
        """
        Get all VM instances for a source VM.

        Args:
            vm_id: Source VM ID
            status: Optional status filter

        Returns:
            List of VmInstance objects
        """
        with self:
            query = self._session.query(VmInstance).options(
                joinedload(VmInstance.vm).joinedload(Vm.osinfo)
            ).filter_by(vm_id=vm_id)
            if status:
                query = query.filter_by(status=status)
            instances = query.all()
            # Expunge objects from session to make them detached
            for instance in instances:
                self._session.expunge(instance)
            return instances

    def get_all_vm_instances(self) -> list[VmInstance]:
        """
        Get all VM instances.

        Returns:
            List of all VmInstance objects
        """
        with self:
            instances = self._session.query(VmInstance).options(
                joinedload(VmInstance.vm).joinedload(Vm.osinfo)
            ).all()
            # Expunge objects from session to make them detached
            for instance in instances:
                self._session.expunge(instance)
            return instances

    def get_old_vm_instances(self, cutoff_date, status: str = None) -> list[VmInstance]:
        """
        Get VM instances older than cutoff date.

        Args:
            cutoff_date: Datetime cutoff for last_used_at
            status: Optional status filter

        Returns:
            List of old VmInstance objects
        """
        with self:
            query = self._session.query(VmInstance).options(
                joinedload(VmInstance.vm).joinedload(Vm.osinfo)
            ).filter(VmInstance.last_used_at < cutoff_date)
            if status:
                query = query.filter_by(status=status)
            instances = query.all()
            # Expunge objects from session to make them detached
            for instance in instances:
                self._session.expunge(instance)
            return instances

    def update_vm_instance(self, instance_id: str, **kwargs):
        """
        Update a VM instance.

        Args:
            instance_id: VM instance ID
            **kwargs: Fields to update
        """
        try:
            with self:
                instance = self._session.query(VmInstance).filter_by(id=instance_id).first()
                if not instance:
                    raise VMNotFoundError(log, f"VM instance with ID {instance_id} not found")

                for key, value in kwargs.items():
                    if hasattr(instance, key):
                        setattr(instance, key, value)

                self._session.commit()
                log.info(f"Updated VM instance {instance.instance_name}: {kwargs}")
        except SQLAlchemyError as e:
            self._session.rollback()
            raise VMLoadError(log, f"Database error while updating VM instance: {e}") from e

    def claim_available_vm_instance(self, instance_id: str, experiment_run_id: str,
                                     websocket_port: int) -> bool:
        """
        Atomically claim an available VM instance for an experiment.

        Performs a single conditional UPDATE (status='available' -> 'active')
        so that two processes racing to reuse the same instance cannot both
        succeed: whichever commits first flips the row, and the loser's WHERE
        clause no longer matches.

        Args:
            instance_id: VM instance ID to claim
            experiment_run_id: Experiment run ID claiming the instance
            websocket_port: Freshly allocated websocket port for the instance

        Returns:
            True if this call claimed the instance, False if it was no longer available
        """
        try:
            with self:
                updated_count = self._session.query(VmInstance).filter_by(
                    id=instance_id, status='available'
                ).update({
                    'status': 'active',
                    'current_experiment_run_id': experiment_run_id,
                    'websocket_port': websocket_port,
                    'last_used_at': datetime.now(UTC)
                }, synchronize_session=False)

                self._session.commit()

                claimed = updated_count == 1
                if claimed:
                    log.info(f"Claimed VM instance {instance_id} for experiment {experiment_run_id}")
                else:
                    log.info(f"Failed to claim VM instance {instance_id} - no longer available")
                return claimed
        except IntegrityError:
            # A port collision on the reuse-claim path — let it surface
            # unwrapped so the caller's retry-over-ports loop can catch it.
            self._session.rollback()
            raise
        except SQLAlchemyError as e:
            self._session.rollback()
            raise VMLoadError(log, f"Database error while claiming VM instance: {e}") from e

    def delete_vm_instance(self, instance_id: str) -> bool:
        """
        Delete a VM instance from the database.

        Args:
            instance_id: VM instance ID

        Returns:
            True if deleted successfully

        Raises:
            VMNotFoundError: If instance not found
        """
        with self:
            instance = self._session.query(VmInstance).filter_by(id=instance_id).first()
            if not instance:
                raise VMNotFoundError(log, f"VM instance with ID {instance_id} not found")

            instance_name = instance.instance_name
            self._session.delete(instance)
            self._session.commit()
            log.info(f"Successfully deleted VM instance '{instance_name}' (ID: {instance_id})")
            return True

    def get_vm_instance_by_name(self, instance_name: str) -> VmInstance | None:
        """
        Get a VM instance by name.

        Args:
            instance_name: VM instance name

        Returns:
            VmInstance or None if not found
        """
        with self:
            instance = self._session.query(VmInstance).options(
                joinedload(VmInstance.vm).joinedload(Vm.osinfo)
            ).filter_by(instance_name=instance_name).first()
            if instance:
                self._session.expunge(instance)
            return instance

    def get_websocket_port_for_instance(self, instance_name: str) -> int | None:
        """
        Get the WebSocket port for an active VM instance by name.

        Args:
            instance_name: VM instance name

        Returns:
            WebSocket port number if instance is active and has a port, None otherwise
        """
        try:
            instance = self.get_vm_instance_by_name(instance_name)
            if not instance:
                log.warning(f"VM instance '{instance_name}' not found")
                return None

            if instance.status != 'active':
                log.warning(f"VM instance '{instance_name}' is not active (status: {instance.status})")
                return None

            if instance.websocket_port is None:
                log.warning(f"VM instance '{instance_name}' has no WebSocket port allocated")
                return None

            log.info(f"Found WebSocket port {instance.websocket_port} for instance '{instance_name}'")
            return instance.websocket_port

        except SQLAlchemyError as e:
            log.error(f"Error looking up WebSocket port for instance '{instance_name}': {e}")
            return None
