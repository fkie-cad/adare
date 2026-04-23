"""
VM core CRUD operations.

Provides create, read, update, delete operations for VM records
and OS info entries.
"""

import logging
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from adare.config.configdirectory import VMS_DIR
from adare.database.models.global_models import OsInfo, Vm

from .exceptions import VMLoadError, VMNameConflictError, VMNotFoundError

log = logging.getLogger(__name__)


class VmCrudMixin:
    """Mixin providing core VM CRUD operations."""

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
            project_path: Project path
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
            log.info("Skipping write-protection for external VM file (user-managed)")
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
        except OSError as e:
            raise VMLoadError(log, f"File system error creating VM '{name}': {e}")

    def get_vm_by_name(self, name: str) -> Vm | None:
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

    def get_vm_by_hash(self, file_hash: str) -> Vm | None:
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

    def get_vm_by_id(self, vm_id: str) -> Vm | None:
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

    def get_all_vms(self) -> list[Vm]:
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

        vm_path = Path(vm.file)
        try:
            vm_path.resolve().relative_to(VMS_DIR.resolve())
            return False  # Managed
        except ValueError:
            return True  # External

    def get_available_vms(self) -> list[Vm]:
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
