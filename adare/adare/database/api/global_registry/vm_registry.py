"""
Global VM Registry API.

This module provides database operations for the global VM registry,
which stores VMs that can be shared across multiple projects.
"""

import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func

from adare.config.configdirectory import APPDATA_DIR, VMS_DIR
from adare.database.api.base import EnhancedDatabaseApi
from adare.database.models.global_registry import (
    GlobalVm,
    ResourceUsage,
    ResourceSnapshot,
    GlobalResourceMetadata
)
from adare.database.exceptions import (
    DatabaseError,
    EntityNotFoundError,
    ValidationError
)

log = logging.getLogger(__name__)


class VmRegistryApi(EnhancedDatabaseApi):
    """
    Database API for global VM registry operations.

    Manages VMs that are stored globally and can be referenced by multiple projects.
    Provides usage tracking, snapshot management, and resource cleanup.
    """

    def __init__(self):
        """Initialize VM registry API with global VM registry database."""
        vm_registry_path = APPDATA_DIR / 'vm_registry.db'
        super().__init__(db_path=vm_registry_path)
        self._ensure_vm_storage_directory()
        self._ensure_registry_metadata()

    def _ensure_vm_storage_directory(self):
        """Ensure the global VM storage directory exists."""
        try:
            VMS_DIR.mkdir(parents=True, exist_ok=True)
            log.debug(f"VM storage directory ensured at: {VMS_DIR}")
        except OSError as e:
            log.error(f"Failed to create VM storage directory: {e}")
            raise DatabaseError(f"Cannot create VM storage directory: {e}")

    def _ensure_registry_metadata(self):
        """Ensure registry metadata exists and is up to date."""
        with self:
            metadata = self._session.query(GlobalResourceMetadata).first()
            if not metadata:
                metadata = GlobalResourceMetadata(
                    registry_version="1.0.0",
                    auto_cleanup_enabled=True,
                    cleanup_threshold_days=30,
                    max_vm_size_gb=50
                )
                self._session.add(metadata)
                self._session.commit()
                log.info("Created global VM registry metadata")

    def create_vm(self, name: str, file_path: Path, file_hash: str,
                  description: str = '', os_platform: str = '', os_type: str = '',
                  os_distribution: str = '', os_version: str = '', os_language: str = '',
                  os_architecture: str = 'x86_64', created_by: str = None) -> GlobalVm:
        """
        Create a new VM in the global registry.

        Args:
            name: Unique VM name
            file_path: Path to VM file (will be moved to global storage)
            file_hash: SHA256 hash of VM file
            description: VM description
            os_platform: OS platform (windows, linux, macos)
            os_type: OS type (workstation, server, embedded)
            os_distribution: OS distribution (ubuntu, windows10, etc.)
            os_version: OS version (22.04, 10.0.19041, etc.)
            os_language: OS language (en-US, de-DE, etc.)
            os_architecture: Architecture (x86_64, arm64, i386)
            created_by: User who created the VM

        Returns:
            Created GlobalVm instance

        Raises:
            ValidationError: If VM name or hash already exists
            DatabaseError: If database operation fails
        """
        with self:
            # Check for existing VM with same name or hash
            existing_vm = self._session.query(GlobalVm).filter(
                (GlobalVm.name == name) | (GlobalVm.hash == file_hash)
            ).first()

            if existing_vm:
                if existing_vm.name == name:
                    raise ValidationError(f"VM with name '{name}' already exists")
                else:
                    raise ValidationError(f"VM with hash '{file_hash}' already exists")

            # Move VM file to global storage if not already there
            global_vm_path = self._move_vm_to_global_storage(file_path, name)

            # Get file size
            try:
                file_size = global_vm_path.stat().st_size
            except OSError:
                file_size = None
                log.warning(f"Could not get file size for VM {name}")

            # Create VM record
            vm = GlobalVm(
                name=name,
                file=str(global_vm_path.relative_to(VMS_DIR)),  # Store relative path
                hash=file_hash,
                description=description,
                os_platform=os_platform,
                os_type=os_type,
                os_distribution=os_distribution,
                os_version=os_version,
                os_language=os_language,
                os_architecture=os_architecture,
                created_by=created_by,
                file_size_bytes=file_size
            )

            self._session.add(vm)
            self._session.flush()  # Get ID

            log.info(f"Created global VM: {name} ({file_hash[:8]})")
            return vm

    def _move_vm_to_global_storage(self, source_path: Path, vm_name: str) -> Path:
        """
        Move VM file to global storage location.

        Args:
            source_path: Current path of VM file
            vm_name: Name of VM (used for file naming)

        Returns:
            Path to VM file in global storage

        Raises:
            DatabaseError: If file operation fails
        """
        source_path = Path(source_path)

        # Generate target filename
        target_filename = f"{vm_name}{source_path.suffix}"
        target_path = VMS_DIR / target_filename

        # Check if source is already in global storage
        try:
            if source_path.resolve().is_relative_to(VMS_DIR.resolve()):
                log.debug(f"VM file already in global storage: {source_path}")
                return source_path
        except ValueError:
            pass  # Not in global storage, need to move

        # Move file to global storage
        try:
            if source_path.exists():
                # Ensure target directory exists
                target_path.parent.mkdir(parents=True, exist_ok=True)

                # Move file
                source_path.rename(target_path)
                log.info(f"Moved VM file from {source_path} to {target_path}")
            else:
                log.warning(f"Source VM file not found: {source_path}")
                # Create empty file as placeholder
                target_path.touch()

            return target_path

        except OSError as e:
            log.error(f"Failed to move VM file to global storage: {e}")
            raise DatabaseError(f"Cannot move VM file to global storage: {e}")

    def get_vm_by_id(self, vm_id: str) -> Optional[GlobalVm]:
        """Get VM by ID."""
        with self:
            return self.get_by_ulid(GlobalVm, vm_id)

    def get_vm_by_name(self, name: str) -> Optional[GlobalVm]:
        """Get VM by name."""
        with self:
            return self._session.query(GlobalVm).filter(GlobalVm.name == name).first()

    def get_vm_by_hash(self, file_hash: str) -> Optional[GlobalVm]:
        """Get VM by file hash."""
        with self:
            return self._session.query(GlobalVm).filter(GlobalVm.hash == file_hash).first()

    def get_all_vms(self, include_usage_stats: bool = False) -> List[GlobalVm]:
        """
        Get all VMs in the registry.

        Args:
            include_usage_stats: If True, eagerly load usage statistics

        Returns:
            List of GlobalVm instances
        """
        with self:
            query = self._session.query(GlobalVm)

            if include_usage_stats:
                # This would require additional queries to calculate usage stats
                pass  # TODO: Implement usage stats loading

            return query.order_by(GlobalVm.name).all()

    def update_vm(self, vm_id: str, **kwargs) -> GlobalVm:
        """
        Update VM metadata.

        Args:
            vm_id: VM ID
            **kwargs: Fields to update

        Returns:
            Updated GlobalVm instance

        Raises:
            EntityNotFoundError: If VM not found
        """
        with self:
            vm = self.get_by_ulid_or_404(GlobalVm, vm_id)

            # Update allowed fields
            allowed_fields = {
                'description', 'os_platform', 'os_type', 'os_distribution',
                'os_version', 'os_language', 'os_architecture', 'os_details'
            }

            for key, value in kwargs.items():
                if key in allowed_fields:
                    setattr(vm, key, value)
                else:
                    log.warning(f"Ignoring update to non-updateable field: {key}")

            vm.updated_at = datetime.utcnow()
            self._session.commit()

            log.info(f"Updated VM {vm.name} (ID: {vm_id})")
            return vm

    def delete_vm(self, vm_id: str, force: bool = False) -> bool:
        """
        Delete VM from registry and storage.

        Args:
            vm_id: VM ID
            force: If True, delete even if VM is in use

        Returns:
            True if deleted successfully

        Raises:
            EntityNotFoundError: If VM not found
            ValidationError: If VM is in use and force=False
        """
        with self:
            vm = self.get_by_ulid_or_404(GlobalVm, vm_id)

            # Check usage if not forcing
            if not force:
                usage_count = self._session.query(ResourceUsage).filter(
                    ResourceUsage.resource_type == 'vm',
                    ResourceUsage.resource_id == vm_id
                ).count()

                if usage_count > 0:
                    raise ValidationError(
                        f"VM '{vm.name}' is used by {usage_count} project(s). "
                        f"Use force=True to delete anyway."
                    )

            # Delete physical file
            try:
                vm_file_path = vm.full_file_path
                if vm_file_path.exists():
                    vm_file_path.unlink()
                    log.info(f"Deleted VM file: {vm_file_path}")
            except OSError as e:
                log.warning(f"Failed to delete VM file {vm.file}: {e}")

            # Delete usage records
            self._session.query(ResourceUsage).filter(
                ResourceUsage.resource_type == 'vm',
                ResourceUsage.resource_id == vm_id
            ).delete()

            # Delete snapshots
            self._session.query(ResourceSnapshot).filter(
                ResourceSnapshot.vm_id == vm_id
            ).delete()

            # Delete VM record
            self._session.delete(vm)
            self._session.commit()

            log.info(f"Deleted VM {vm.name} (ID: {vm_id})")
            return True

    def track_vm_usage(self, vm_id: str, project_path: str, project_name: str = None,
                      alias_name: str = None, usage_notes: str = None) -> ResourceUsage:
        """
        Track usage of a VM by a project.

        Args:
            vm_id: VM ID
            project_path: Absolute path to project
            project_name: Project name (for convenience)
            alias_name: Project-specific alias for the VM
            usage_notes: Project-specific notes

        Returns:
            ResourceUsage instance

        Raises:
            EntityNotFoundError: If VM not found
        """
        with self:
            # Verify VM exists
            vm = self.get_by_ulid_or_404(GlobalVm, vm_id)

            # Get or create usage record
            usage, created = self.get_or_create(
                ResourceUsage,
                defaults={
                    'project_name': project_name,
                    'alias_name': alias_name,
                    'usage_notes': usage_notes,
                    'usage_count': 1
                },
                resource_type='vm',
                resource_id=vm_id,
                project_path=project_path
            )

            if not created:
                # Update existing usage
                usage.last_used = datetime.utcnow()
                usage.usage_count += 1
                if alias_name:
                    usage.alias_name = alias_name
                if usage_notes:
                    usage.usage_notes = usage_notes

            # Update VM usage stats
            vm.usage_count = self._session.query(ResourceUsage).filter(
                ResourceUsage.resource_type == 'vm',
                ResourceUsage.resource_id == vm_id
            ).count()
            vm.last_used = datetime.utcnow()

            self._session.commit()

            action = "Created" if created else "Updated"
            log.info(f"{action} VM usage tracking: {vm.name} -> {project_name or project_path}")

            return usage

    def stop_vm_usage(self, vm_id: str, project_path: str) -> bool:
        """
        Stop tracking VM usage by a project.

        Args:
            vm_id: VM ID
            project_path: Project path

        Returns:
            True if usage was removed
        """
        with self:
            usage = self._session.query(ResourceUsage).filter(
                ResourceUsage.resource_type == 'vm',
                ResourceUsage.resource_id == vm_id,
                ResourceUsage.project_path == project_path
            ).first()

            if usage:
                self._session.delete(usage)

                # Update VM usage count
                vm = self.get_by_ulid(GlobalVm, vm_id)
                if vm:
                    vm.usage_count = self._session.query(ResourceUsage).filter(
                        ResourceUsage.resource_type == 'vm',
                        ResourceUsage.resource_id == vm_id
                    ).count()

                self._session.commit()
                log.info(f"Stopped VM usage tracking: {vm_id} -> {project_path}")
                return True

            return False

    def get_vm_usage(self, vm_id: str) -> List[ResourceUsage]:
        """
        Get all usage records for a VM.

        Args:
            vm_id: VM ID

        Returns:
            List of ResourceUsage instances
        """
        with self:
            return self._session.query(ResourceUsage).filter(
                ResourceUsage.resource_type == 'vm',
                ResourceUsage.resource_id == vm_id
            ).order_by(ResourceUsage.last_used.desc()).all()

    def get_project_vms(self, project_path: str) -> List[Dict[str, Any]]:
        """
        Get all VMs used by a specific project.

        Args:
            project_path: Project path

        Returns:
            List of dicts with VM and usage information
        """
        with self:
            # Query VMs with their usage info for this project
            results = self._session.query(GlobalVm, ResourceUsage).join(
                ResourceUsage,
                (ResourceUsage.resource_type == 'vm') &
                (ResourceUsage.resource_id == GlobalVm.id)
            ).filter(
                ResourceUsage.project_path == project_path
            ).all()

            return [
                {
                    'vm': vm,
                    'usage': usage,
                    'alias': usage.alias_name or vm.name,
                    'last_used': usage.last_used,
                    'usage_count': usage.usage_count
                }
                for vm, usage in results
            ]

    def cleanup_unused_vms(self, threshold_days: int = 30, dry_run: bool = True) -> Dict[str, Any]:
        """
        Clean up VMs that haven't been used recently.

        Args:
            threshold_days: Remove VMs unused for this many days
            dry_run: If True, don't actually delete anything

        Returns:
            Dict with cleanup results
        """
        from datetime import timedelta

        cutoff_date = datetime.utcnow() - timedelta(days=threshold_days)

        with self:
            # Find VMs that are either never used or haven't been used recently
            unused_vms = self._session.query(GlobalVm).filter(
                (GlobalVm.last_used.is_(None)) |
                (GlobalVm.last_used < cutoff_date)
            ).filter(
                GlobalVm.usage_count == 0
            ).all()

            results = {
                'found_unused': len(unused_vms),
                'deleted': 0,
                'failed': 0,
                'dry_run': dry_run,
                'vm_list': [vm.name for vm in unused_vms]
            }

            if not dry_run:
                for vm in unused_vms:
                    try:
                        self.delete_vm(vm.id, force=True)
                        results['deleted'] += 1
                    except Exception as e:
                        log.error(f"Failed to delete unused VM {vm.name}: {e}")
                        results['failed'] += 1

            log.info(f"VM cleanup: found {results['found_unused']} unused VMs")
            return results

    def get_registry_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the VM registry.

        Returns:
            Dict with registry statistics
        """
        with self:
            total_vms = self._session.query(GlobalVm).count()
            total_usage = self._session.query(ResourceUsage).filter(
                ResourceUsage.resource_type == 'vm'
            ).count()

            # Calculate total storage used
            total_size = self._session.query(func.sum(GlobalVm.file_size_bytes)).scalar() or 0

            # Get top used VMs
            top_vms = self._session.query(GlobalVm).order_by(
                GlobalVm.usage_count.desc()
            ).limit(5).all()

            return {
                'total_vms': total_vms,
                'total_projects_using': total_usage,
                'total_storage_bytes': total_size,
                'total_storage_gb': round(total_size / (1024**3), 2),
                'top_used_vms': [
                    {'name': vm.name, 'usage_count': vm.usage_count}
                    for vm in top_vms
                ]
            }