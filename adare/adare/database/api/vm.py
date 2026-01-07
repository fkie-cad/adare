"""
Database API for VM management.

This module provides functions for managing VMs in both global and project scopes,
including loading, validation, and database operations.
"""

# external imports
from pathlib import Path
from typing import List, Optional

# internal imports
from adare.database.api.base import GlobalDatabaseApi
from adare.database.models.global_models import Vm, OsInfo
from adare.exceptions import LoggedErrorException
from adare.helperfunctions.file.hash import file_sha256_with_progress
from adare.helperfunctions.file.validation import validate_tarfile_with_progress
from adare.config.configdirectory import VMS_DIR
from adare.validators.vm_validators import VMValidatorFactory

# configure logging
import logging
log = logging.getLogger(__name__)


class VMNotFoundError(LoggedErrorException):
    """VM not found in database or filesystem."""
    pass


class VMValidationError(LoggedErrorException):
    """VM validation failed."""
    pass


class VMLoadError(LoggedErrorException):
    """Failed to load VM into database."""
    pass


class VMNameConflictError(LoggedErrorException):
    """VM name already exists in database."""
    pass


class VmApi(GlobalDatabaseApi):
    """
    Database API for global VM management operations.

    Handles globally shared VMs with validation and loading capabilities.
    All VMs are now stored in the global database and shared across projects.
    """

    def __init__(self):
        super().__init__()
        self._start_session()
        # VM table is automatically created by GlobalDatabaseApi
    
    def create_osinfo(self, platform: str = '', os: str = '', distribution: str = '', 
                     version: str = '', language: str = '', architecture: str = 'x86_64') -> OsInfo:
        """
        Create a new OSInfo entry in the database.
        
        Args:
            platform: OS platform (windows, linux, etc.)
            os: OS type
            distribution: OS distribution
            version: OS version
            language: OS language
            architecture: Architecture (default: x86_64)
            
        Returns:
            Created OSInfo instance
            
        Raises:
            VMLoadError: If OSInfo creation fails
        """
        from sqlalchemy.exc import SQLAlchemyError

        osinfo = OsInfo(
            platform=platform,
            os=os,
            distribution=distribution,
            version=version,
            language=language,
            architecture=architecture
        )

        with self:
            self._session.add(osinfo)
            self._session.flush()  # Get ID without committing
            osinfo_id = osinfo.id
            log.info(f"Successfully created OSInfo (ID: {osinfo_id})")
            # Detach before returning
            self._session.expunge(osinfo)
            return osinfo
        # Context manager commits on successful exit
    
    def create_vm(self, project_path: Path, name: str, file_path: Path, file_hash: str, description: str = '',
                  os_platform: str = '', os_type: str = '', os_distribution: str = '',
                  os_version: str = '', os_language: str = '', os_architecture: str = 'x86_64',
                  silent: bool = False, no_copy: bool = False, hypervisor: str = 'virtualbox',
                  force: bool = False) -> Vm:
        """
        Create a new VM entry in the database with file operations.

        Args:
            name: Unique name for the VM
            file_path: Path to the VM file (OVA for VirtualBox, qcow2 for QEMU, etc.)
            file_hash: SHA256 hash of the VM file
            description: Optional description
            os_platform: OS platform (windows, linux, etc.)
            os_type: OS type
            os_distribution: OS distribution
            os_version: OS version
            os_language: OS language
            os_architecture: Architecture (default: x86_64)
            silent: If True, suppress progress bars
            no_copy: If True, reference file at original location instead of copying
            hypervisor: Hypervisor type ('virtualbox', 'qemu') - default: 'virtualbox'
            force: If True, overwrite existing VM with same name but different hash

        Returns:
            Created VM instance

        Raises:
            ValidationError: If validation fails
            VMLoadError: If VM creation fails
            VMNameConflictError: If VM name exists with different hash and force=False
        """
        # Validate and process VM file
        self.validate_vm_file(file_path, name, quiet=silent, hypervisor=hypervisor)

        # Check for existing VMs by name and hash BEFORE file operations
        existing_vm_by_name = self.get_vm_by_name(name)
        existing_vm_by_hash = self.get_vm_by_hash(file_hash)

        # Scenario 1: Name and Hash both match (same VM)
        if existing_vm_by_name and existing_vm_by_hash and existing_vm_by_name.id == existing_vm_by_hash.id:
            if force:
                log.info(f"VM '{name}' exists with matching hash - updating metadata due to --force")
                return self._update_vm_metadata(
                    existing_vm_by_name.id, description, os_platform, os_type,
                    os_distribution, os_version, os_language, os_architecture, hypervisor
                )
            else:
                log.info(f"VM '{name}' already exists with matching hash - returning existing VM")
                return existing_vm_by_name

        # Scenario 2: Name matches but hash differs (VM updated)
        if existing_vm_by_name and (not existing_vm_by_hash or existing_vm_by_name.id != existing_vm_by_hash.id):
            if force:
                log.info(f"VM '{name}' exists with different hash - updating to new version due to --force")
                return self._update_vm_file_and_metadata(
                    existing_vm_by_name.id, existing_vm_by_name.name, file_path, file_hash,
                    description, os_platform, os_type, os_distribution, os_version,
                    os_language, os_architecture, no_copy, silent, hypervisor, project_path
                )
            else:
                raise VMNameConflictError(
                    log,
                    f"VM with name '{name}' already exists but has different hash.\n"
                    f"Existing hash: {existing_vm_by_name.hash[:16]}...\n"
                    f"New hash: {file_hash[:16]}...",
                    possible_solutions=[
                        "Use --force flag to update the existing VM to the new version",
                        "Use a different VM name",
                        "Delete the existing VM first"
                    ]
                )

        # Scenario 3: Hash matches but name differs (hash-based deduplication)
        if existing_vm_by_hash and (not existing_vm_by_name or existing_vm_by_hash.id != existing_vm_by_name.id):
            log.warning(f"VM file already exists with name '{existing_vm_by_hash.name}' - returning existing VM")
            return existing_vm_by_hash

        # No conflicts - proceed with normal creation
        # CLAUDE: Copy file to storage location OR use original path
        if no_copy:
            log.info(f"Using --no-copy mode: storing reference to {file_path}")
            target_file_path = file_path.resolve()  # Store absolute path

            # Don't attempt write-protection for external files
            log.info(f"Skipping write-protection for external VM file (user-managed)")
        else:
            # Copy VM file to storage location
            target_file_path = self._copy_vm_file(file_path, project_path, name, silent=silent)
        
        # Create both OsInfo and VM in same transaction to prevent orphaned records
        try:
            with self:
                # Create OSInfo inline
                osinfo = OsInfo(
                    platform=os_platform,
                    os=os_type,
                    distribution=os_distribution,
                    version=os_version,
                    language=os_language,
                    architecture=os_architecture
                )
                self._session.add(osinfo)
                self._session.flush()  # Get ID without committing

                # Create VM with OSInfo relationship
                vm = Vm(
                    name=name,
                    file=str(target_file_path),
                    hash=file_hash,
                    description=description,
                    osinfo_id=osinfo.id,
                    hypervisor=hypervisor
                )
                self._session.add(vm)
                # Both commit together on context exit
                self._session.flush()
                vm_id = vm.id
                log.info(f"Successfully created VM '{name}' (ID: {vm_id})")

            # Return a new instance by querying it back to avoid session issues
            return self.get_vm_by_name(name)
        except SQLAlchemyError as e:
            raise VMLoadError(log, f"Database error creating VM '{name}': {e}")
        except (OSError, IOError) as e:
            raise VMLoadError(log, f"File system error creating VM '{name}': {e}")
    
    
    def get_vm_by_name(self, name: str) -> Optional[Vm]:
        """
        Get VM by name.
        
        Args:
            name: VM name
            
        Returns:
            VM instance or None if not found
        """
        from sqlalchemy.orm import joinedload
        with self:
            vm = self._session.query(Vm).options(joinedload(Vm.osinfo)).filter_by(name=name).first()
            if vm:
                self._session.expunge(vm)
            return vm
    
    def get_vm_by_hash(self, file_hash: str) -> Optional[Vm]:
        """
        Get VM by file hash.
        
        Args:
            file_hash: SHA256 hash of the VM file
            
        Returns:
            VM instance if found, None otherwise
        """
        from sqlalchemy.orm import joinedload
        with self:
            vm = self._session.query(Vm).options(joinedload(Vm.osinfo)).filter_by(hash=file_hash).first()
            if vm:
                self._session.expunge(vm)
            return vm
    
    def get_vm_by_id(self, vm_id: str) -> Optional[Vm]:
        """Get VM by database ID."""
        from sqlalchemy.orm import joinedload
        with self:
            vm = self._session.query(Vm).options(joinedload(Vm.osinfo)).filter(Vm.id == vm_id).first()
            if vm:
                self._session.expunge(vm)
            return vm

    def update_vm_name(self, vm_id: str, new_name: str) -> bool:
        """
        Update VM name in the database.
        
        Args:
            vm_id: VM database ID
            new_name: New name for the VM
            
        Returns:
            True if updated successfully
        """
        with self:
            vm = self._session.query(Vm).filter_by(id=vm_id).first()
            if not vm:
                log.error(f"VM with ID {vm_id} not found for name update")
                return False
            
            old_name = vm.name
            vm.name = new_name
            
            self._session.commit()
            log.debug(f"Updated VM name from '{old_name}' to '{new_name}'")
            return True
    
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
    
    def get_snapshots_for_vm(self, vm_id: str, snapshot_type: str = None) -> List:
        """
        DEPRECATED: This method gets snapshots for VM templates which is incorrect.
        Use get_snapshots_for_instance instead.

        Args:
            vm_id: VM database ID (template - snapshots don't belong to templates)
            snapshot_type: Filter by snapshot type (optional)

        Returns:
            Empty list (VMs don't have snapshots, instances do)
        """
        log.warning("get_snapshots_for_vm is deprecated - VMs (templates) don't have snapshots. Use get_snapshots_for_instance instead.")
        return []
    
    def delete_snapshot_record(self, vm_id: str, snapshot_name: str) -> bool:
        """
        DEPRECATED: This method deletes snapshots from VM templates which is incorrect.
        Use delete_instance_snapshot_record instead.

        Args:
            vm_id: VM database ID (template - snapshots don't belong to templates)
            snapshot_name: Name of the snapshot to delete

        Returns:
            False - operation not supported for VM templates
        """
        log.error("delete_snapshot_record is deprecated - VMs (templates) don't have snapshots. Use delete_instance_snapshot_record instead.")
        return False
    
    def get_all_vms(self) -> List[Vm]:
        """
        Get all VMs.

        Returns:
            List of VM instances
        """
        with self:
            from sqlalchemy.orm import joinedload
            vms = self._session.query(Vm).options(joinedload(Vm.osinfo)).all()
            # Expunge objects from session to make them detached
            for vm in vms:
                self._session.expunge(vm)
            return vms

    def is_vm_external(self, vm_id: str) -> bool:
        """
        Check if a VM is external (not in managed storage).

        Args:
            vm_id: VM database ID

        Returns:
            True if VM is external, False if managed
        """
        vm = self.get_vm_by_id(vm_id)
        if not vm:
            return False

        from adare.config.configdirectory import VMS_DIR
        vm_path = Path(vm.file)
        try:
            vm_path.resolve().relative_to(VMS_DIR.resolve())
            return False  # Managed
        except ValueError:
            return True  # External

    def get_available_vms(self) -> List[Vm]:
        """
        Get all VMs available for use.
        
        Returns:
            List of available VM instances
        """
        with self:
            from sqlalchemy.orm import joinedload
            vms = self._session.query(Vm).options(joinedload(Vm.osinfo)).all()
            # Expunge objects from session to make them detached
            for vm in vms:
                self._session.expunge(vm)
            return vms
    
    def delete_vm(self, vm_id: str) -> bool:
        """
        Delete VM from database.
        
        Args:
            vm_id: VM ID to delete
            
        Returns:
            True if deleted successfully
            
        Raises:
            VMNotFoundError: If VM not found
        """
        with self:
            vm = self._session.query(Vm).filter_by(id=vm_id).first()
            if not vm:
                raise VMNotFoundError(log, f"VM with id {vm_id} not found")
                
            self._session.delete(vm)
            self._session.commit()
            log.info(f"Successfully deleted VM '{vm.name}' (id: {vm_id})")
            return True
    
    
    def validate_vm_file(self, file_path: Path, name: str = None, quiet: bool = False, hypervisor: str = 'virtualbox') -> dict:
        """
        Validate VM file using hypervisor-specific validator.

        Args:
            file_path: Path to VM file
            name: Optional name for better error messages
            quiet: If True, suppress progress bars
            hypervisor: Hypervisor type ('virtualbox', 'qemu') - default: 'virtualbox'

        Returns:
            Dictionary with file_size and file_hash

        Raises:
            VMValidationError: If validation fails
        """
        # Get validator for this hypervisor
        validator = VMValidatorFactory.get_validator(hypervisor)

        # Check file extension
        file_ext = file_path.suffix.lower()
        supported = validator.get_supported_extensions()

        if file_ext not in supported:
            raise VMValidationError(
                log,
                f"VM file {file_path} has unsupported extension '{file_ext}' for hypervisor '{hypervisor}'.\n"
                f"Supported extensions for {hypervisor}: {', '.join(supported)}\n"
                f"If using QEMU, ensure environment YAML specifies: hypervisor: qemu"
            )

        # Delegate validation to hypervisor-specific validator
        validator.validate_file(file_path, name or file_path.stem, quiet=quiet)

        log.debug(f"Successfully validated {hypervisor} VM file: {file_path}")
    
    def _calculate_file_hash(self, file_path: Path, quiet: bool = False) -> str:
        """
        Calculate SHA256 hash of file with progress indication.
        
        Args:
            file_path: Path to file
            quiet: If True, suppress progress bar
            
        Returns:
            SHA256 hash string
        """
        return file_sha256_with_progress(
            file_path=file_path,
            description=f"Calculating hash for {file_path.name}",
            quiet=quiet
        )
    
    
    def _copy_vm_file(self, source_path: Path, project_path: Path, name: str, silent: bool = False) -> Path:
        """
        Copy VM file to global storage location.

        Args:
            source_path: Original VM file path
            project_path: Not used (VMs are global now)
            name: VM name
            silent: If True, suppress progress indicators

        Returns:
            Path to copied VM file

        Raises:
            VMLoadError: If file copying fails
        """
        try:
            # Use global VM directory instead of project-specific directory
            target_dir = VMS_DIR
            target_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate target filename with VM name
            target_filename = f"{name}{source_path.suffix}"
            target_path = target_dir / target_filename
            
            # Check if target already exists
            if target_path.exists():
                if target_path.samefile(source_path):
                    # Source and target are the same file, no need to copy
                    log.info(f"VM file already in target location: {target_path}")
                    return target_path
                else:
                    raise VMLoadError(log, f"Target VM file {target_path} already exists and is different from source {source_path}")
            
            log.info(f"Copying VM file to {target_path}")
            from adare.helperfunctions.file.copy import copy
            copy(
                src=source_path,
                dst=target_path,
                silent=silent
            )
            log.info(f"Successfully copied VM file to {target_path}")
            
            return target_path
            
        except Exception as e:
            raise VMLoadError(log, f"Failed to copy VM file: {e}")

    def _is_file_managed(self, file_path: Path) -> bool:
        """
        Check if a VM file is in managed storage (VMS_DIR).

        Args:
            file_path: Path to check

        Returns:
            True if file is in managed storage, False otherwise
        """
        try:
            file_path.resolve().relative_to(VMS_DIR.resolve())
            return True
        except ValueError:
            return False

    def _update_vm_metadata(self, vm_id: str, description: str = '', os_platform: str = '',
                           os_type: str = '', os_distribution: str = '', os_version: str = '',
                           os_language: str = '', os_architecture: str = 'x86_64',
                           hypervisor: str = 'virtualbox') -> Vm:
        """
        Update VM metadata without changing file or hash.

        Args:
            vm_id: ID of VM to update
            description: New description
            os_platform: OS platform
            os_type: OS type
            os_distribution: OS distribution
            os_version: OS version
            os_language: OS language
            os_architecture: Architecture
            hypervisor: Hypervisor type

        Returns:
            Updated VM instance

        Raises:
            VMLoadError: If update fails or VM not found
        """
        with self:
            # Re-fetch VM inside context to attach it to this session
            vm = self._session.query(Vm).filter_by(id=vm_id).first()
            if not vm:
                raise VMLoadError(log, f"VM with ID {vm_id} not found")

            # Update VM fields
            if description:
                vm.description = description
            if hypervisor:
                vm.hypervisor = hypervisor

            # Update or create OSInfo (inline - no separate transaction)
            if vm.osinfo_id:
                osinfo = self._session.query(OsInfo).filter_by(id=vm.osinfo_id).first()
                if osinfo:
                    osinfo.platform = os_platform
                    osinfo.os = os_type
                    osinfo.distribution = os_distribution
                    osinfo.version = os_version
                    osinfo.language = os_language
                    osinfo.architecture = os_architecture
            else:
                # Create new OSInfo inline
                osinfo = OsInfo(
                    platform=os_platform,
                    os=os_type,
                    distribution=os_distribution,
                    version=os_version,
                    language=os_language,
                    architecture=os_architecture
                )
                self._session.add(osinfo)
                self._session.flush()  # Get osinfo.id without committing
                vm.osinfo_id = osinfo.id

            log.info(f"Updated metadata for VM '{vm.name}' (ID: {vm_id})")
            # Commit happens automatically when context exits

        # Re-fetch and return detached object
        return self.get_vm_by_id(vm_id)

    def _update_vm_file_and_metadata(self, vm_id: str, vm_name: str, file_path: Path, file_hash: str,
                                     description: str = '', os_platform: str = '', os_type: str = '',
                                     os_distribution: str = '', os_version: str = '', os_language: str = '',
                                     os_architecture: str = 'x86_64', no_copy: bool = False,
                                     silent: bool = False, hypervisor: str = 'virtualbox',
                                     project_path: Path = None) -> Vm:
        """
        Update VM to point to new file with new hash, preserving VM ID and relationships.
        CRITICAL: We update the existing VM record rather than delete/recreate to preserve FK relationships.

        Args:
            vm_id: ID of VM to update
            vm_name: Name of VM (for file operations and logging)
            file_path: Path to new VM file
            file_hash: SHA256 hash of new VM file
            description: New description
            os_platform: OS platform
            os_type: OS type
            os_distribution: OS distribution
            os_version: OS version
            os_language: OS language
            os_architecture: Architecture
            no_copy: If True, reference file at original location
            silent: If True, suppress progress bars
            hypervisor: Hypervisor type
            project_path: Project path (not used for global VMs)

        Returns:
            Updated VM instance

        Raises:
            VMLoadError: If update fails or VM not found
        """
        # Variables to track old file info (will be set inside transaction)
        old_file_path = None
        old_is_managed = False

        # Determine new file location BEFORE database transaction
        if no_copy:
            log.info(f"Using --no-copy mode: storing reference to {file_path}")
            target_file_path = file_path.resolve()
        else:
            target_file_path = self._copy_vm_file(file_path, project_path, vm_name, silent=silent)

        with self:
            # Re-fetch VM inside context to attach it to this session
            vm = self._session.query(Vm).filter_by(id=vm_id).first()
            if not vm:
                raise VMLoadError(log, f"VM with ID {vm_id} not found")

            # Store old file info for cleanup after successful commit
            old_file_path = Path(vm.file)
            old_is_managed = self._is_file_managed(old_file_path)

            # Update VM fields
            vm.file = str(target_file_path)
            vm.hash = file_hash
            if description:
                vm.description = description
            vm.hypervisor = hypervisor

            # Update or create OSInfo (inline - no separate transaction)
            if vm.osinfo_id:
                osinfo = self._session.query(OsInfo).filter_by(id=vm.osinfo_id).first()
                if osinfo:
                    osinfo.platform = os_platform
                    osinfo.os = os_type
                    osinfo.distribution = os_distribution
                    osinfo.version = os_version
                    osinfo.language = os_language
                    osinfo.architecture = os_architecture
            else:
                # Create new OSInfo inline
                osinfo = OsInfo(
                    platform=os_platform,
                    os=os_type,
                    distribution=os_distribution,
                    version=os_version,
                    language=os_language,
                    architecture=os_architecture
                )
                self._session.add(osinfo)
                self._session.flush()  # Get osinfo.id without committing
                vm.osinfo_id = osinfo.id

            log.info(f"Updated VM '{vm.name}' to new file/hash (ID: {vm_id})")
            # Commit happens automatically when context exits

        # Clean up old VM file AFTER successful commit
        if old_file_path and old_is_managed and old_file_path.exists() and old_file_path != target_file_path:
            log.info(f"Removing old VM file from managed storage: {old_file_path}")
            try:
                old_file_path.unlink()
            except OSError as e:
                log.warning(f"Failed to remove old VM file {old_file_path}: {e}")

        # Re-fetch and return detached object
        return self.get_vm_by_id(vm_id)

    def suggest_similar_vms(self, vm_name: str, max_suggestions: int = 5):
        """
        Get VM suggestions based on name similarity.
        
        Args:
            vm_name: The VM name to find suggestions for
            max_suggestions: Maximum number of suggestions
            
        Returns:
            List of VMSuggestion objects
        """
        from adare.helperfunctions.vm_suggestions import suggest_similar_vm_names
        
        # Get all available VMs
        all_vms = self.get_all_vms()
        vm_names = [vm.name for vm in all_vms]
        
        # Get name-based suggestions
        suggestions = suggest_similar_vm_names(vm_name, vm_names, max_suggestions)
        
        # Fill in additional VM metadata for suggestions
        vm_lookup = {vm.name: vm for vm in all_vms}
        for suggestion in suggestions:
            if suggestion.name in vm_lookup:
                vm_obj = vm_lookup[suggestion.name]
                suggestion.description = vm_obj.description
        
        return suggestions

    # VM Instance Management Methods

    def create_vm_instance(self, vm_id: str, instance_name: str, experiment_run_id: str,
                          websocket_port: int, status: str = 'active') -> 'VmInstance':
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
        from adare.database.models.global_models import VmInstance
        from sqlalchemy.exc import SQLAlchemyError
        from datetime import datetime

        instance = VmInstance(
            vm_id=vm_id,
            instance_name=instance_name,
            current_experiment_run_id=experiment_run_id,
            websocket_port=websocket_port,
            status=status,
            created_at=datetime.utcnow(),
            last_used_at=datetime.utcnow()
        )

        try:
            with self:
                self._session.add(instance)
                self._session.commit()
                self._session.refresh(instance)

                # Eagerly load the VM relationship before detaching
                from sqlalchemy.orm import joinedload
                instance = self._session.query(VmInstance).options(
                    joinedload(VmInstance.vm).joinedload(Vm.osinfo)
                ).filter_by(id=instance.id).first()

                if instance:
                    self._session.expunge(instance)

                log.info(f"Created VM instance: {instance_name} (ID: {instance.id})")
                return instance
        except SQLAlchemyError as e:
            self._session.rollback()
            raise VMLoadError(log, f"Database error while creating VM instance: {e}")

    def get_vm_instance_by_id(self, instance_id: str) -> Optional['VmInstance']:
        """
        Get a VM instance by ID.

        Args:
            instance_id: VM instance ID

        Returns:
            VmInstance or None if not found
        """
        from adare.database.models.global_models import VmInstance
        from sqlalchemy.orm import joinedload

        with self:
            instance = self._session.query(VmInstance).options(
                joinedload(VmInstance.vm).joinedload(Vm.osinfo)
            ).filter_by(id=instance_id).first()
            if instance:
                self._session.expunge(instance)
            return instance

    def get_vm_instances_for_vm(self, vm_id: str, status: str = None) -> List['VmInstance']:
        """
        Get all VM instances for a source VM.

        Args:
            vm_id: Source VM ID
            status: Optional status filter

        Returns:
            List of VmInstance objects
        """
        from adare.database.models.global_models import VmInstance
        from sqlalchemy.orm import joinedload

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

    def get_all_vm_instances(self) -> List['VmInstance']:
        """
        Get all VM instances.

        Returns:
            List of all VmInstance objects
        """
        from adare.database.models.global_models import VmInstance
        from sqlalchemy.orm import joinedload

        with self:
            instances = self._session.query(VmInstance).options(
                joinedload(VmInstance.vm).joinedload(Vm.osinfo)
            ).all()
            # Expunge objects from session to make them detached
            for instance in instances:
                self._session.expunge(instance)
            return instances

    def get_old_vm_instances(self, cutoff_date, status: str = None) -> List['VmInstance']:
        """
        Get VM instances older than cutoff date.

        Args:
            cutoff_date: Datetime cutoff for last_used_at
            status: Optional status filter

        Returns:
            List of old VmInstance objects
        """
        from adare.database.models.global_models import VmInstance
        from sqlalchemy.orm import joinedload

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
        from adare.database.models.global_models import VmInstance
        from sqlalchemy.exc import SQLAlchemyError

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
            raise VMLoadError(log, f"Database error while updating VM instance: {e}")

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
        from adare.database.models.global_models import VmInstance

        with self:
            instance = self._session.query(VmInstance).filter_by(id=instance_id).first()
            if not instance:
                raise VMNotFoundError(log, f"VM instance with ID {instance_id} not found")

            instance_name = instance.instance_name
            self._session.delete(instance)
            self._session.commit()
            log.info(f"Successfully deleted VM instance '{instance_name}' (ID: {instance_id})")
            return True

    def get_vm_instance_by_name(self, instance_name: str) -> Optional['VmInstance']:
        """
        Get a VM instance by name.

        Args:
            instance_name: VM instance name

        Returns:
            VmInstance or None if not found
        """
        from adare.database.models.global_models import VmInstance
        from sqlalchemy.orm import joinedload

        with self:
            instance = self._session.query(VmInstance).options(
                joinedload(VmInstance.vm).joinedload(Vm.osinfo)
            ).filter_by(instance_name=instance_name).first()
            if instance:
                self._session.expunge(instance)
            return instance

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
        from adare.database.models.global_models import VmSnapshot

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

    def get_snapshots_for_instance(self, vm_instance_id: str, snapshot_type: str = None) -> List['VmSnapshot']:
        """
        Get all snapshots for a VM instance.

        Args:
            vm_instance_id: VM instance ID
            snapshot_type: Optional filter by snapshot type

        Returns:
            List of VmSnapshot records
        """
        from adare.database.models.global_models import VmSnapshot

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
        from adare.database.models.global_models import VmSnapshot

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

    def get_websocket_port_for_instance(self, instance_name: str) -> Optional[int]:
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

        except Exception as e:
            log.error(f"Error looking up WebSocket port for instance '{instance_name}': {e}")
            return None


def ensure_vm_directories():
    """
    Ensure VM storage directories exist.
    
    Creates the global VM directory if it doesn't exist.
    """
    VMS_DIR.mkdir(parents=True, exist_ok=True)
    log.info(f"Ensured global VM directory exists: {VMS_DIR}")


def load_vm_from_file(project_path: Path, file_path: Path, name: str = None, description: str = '',
                     os_platform: str = '', os_type: str = '', os_distribution: str = '',
                     os_version: str = '', os_language: str = '', os_architecture: str = 'x86_64',
                     silent: bool = False) -> Vm:
    """
    Load a VM from file into the database.

    Args:
        file_path: Path to VM file
        name: VM name (defaults to filename without extension)
        description: VM description
        os_platform: OS platform (windows, linux, etc.)
        os_type: OS type
        os_distribution: OS distribution
        os_version: OS version
        os_language: OS language
        os_architecture: Architecture (default: x86_64)
        silent: If True, suppress progress bars during validation

    Returns:
        Created VM instance

    Raises:
        VMLoadError: If loading fails
    """
    if not name:
        name = file_path.stem

    api = VMDatabaseApi()
    return api.create_vm(
        project_path=project_path,
        name=name,
        file_path=file_path,
        file_hash=api._calculate_file_hash(file_path, quiet=silent),
        description=description,
        os_platform=os_platform,
        os_type=os_type,
        os_distribution=os_distribution,
        os_version=os_version,
        os_language=os_language,
        os_architecture=os_architecture,
        silent=silent
    )


# Convenience alias for backward compatibility
VMDatabaseApi = VmApi