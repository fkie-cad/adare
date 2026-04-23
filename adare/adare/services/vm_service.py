"""
VM Service - Business logic for VM operations.

This service handles all VM-related operations and returns Result[T] objects
that can be consumed by any frontend (CLI, Web UI, REST API).
"""

import logging

from adare.backend.vm.commands import (
    clear_all_vms as backend_clear_all_vms,
)
from adare.backend.vm.commands import (
    clear_vms_by_environment as backend_clear_vms_by_environment,
)
from adare.backend.vm.commands import (
    load_vm as backend_load_vm,
)
from adare.backend.vm.exceptions import VMError
from adare.core.dto.vm import (
    VmClearResult,
    VmInfo,
    VmInstanceCleanupResult,
    VmInstanceInfo,
    VmInstanceListItem,
    VmInstanceUsage,
    VmListItem,
    VmLoadRequest,
    VmSnapshotInfo,
    VmTestRequest,
    VmTestResult,
)
from adare.core.result import Result
from adare.database.api.vm import (
    VmApi,
    VMLoadError,
    VMNameConflictError,
    VMNotFoundError,
    VMValidationError,
)

log = logging.getLogger(__name__)


class VMService:
    """
    Service for VM management operations.

    All methods return Result[T] objects for consistent error handling
    across different frontends.
    """

    # =========================================================================
    # VM Management
    # =========================================================================

    def load(self, request: VmLoadRequest) -> Result[VmInfo]:
        """
        Load a VM from file into the system.

        Args:
            request: VmLoadRequest with file path and options

        Returns:
            Result[VmInfo] with loaded VM info on success,
            or error information on failure.
        """
        try:
            vm_id = backend_load_vm(
                vm_file=request.file_path,
                name=request.name,
                description=request.description,
                os_platform=request.os_platform,
                os_type=request.os_type,
                os_distribution=request.os_distribution,
                os_version=request.os_version,
                os_language=request.os_language,
                os_architecture=request.os_architecture,
                force=request.force
            )

            # Get the loaded VM info
            vm_info = self.get_by_id(vm_id)
            if vm_info.success:
                # Add next steps
                vm_info.data.next_steps = [
                    'Create an environment that uses this VM',
                    f'View VM details with: adare vm info {vm_info.data.name}',
                ]
                vm_info.data.tip = f'VM "{vm_info.data.name}" is ready for use in environments'

            return vm_info

        except VMValidationError as e:
            return Result.from_exception(e)
        except VMLoadError as e:
            return Result.from_exception(e)
        except VMNameConflictError as e:
            return Result.from_exception(e)
        except VMError as e:
            return Result.from_exception(e)

    def list_all(self) -> Result[list[VmListItem]]:
        """
        List all VMs in the system.

        Returns:
            Result[List[VmListItem]] with all VMs.
        """
        try:
            with VmApi() as api:
                vms = api.get_all_vms()

                items = []
                for vm in vms:
                    os_platform = None
                    if hasattr(vm, 'osinfo') and vm.osinfo:
                        os_platform = vm.osinfo.platform

                    # Count instances for this VM
                    instance_count = len(api.get_vm_instances_for_vm(vm.id))

                    items.append(VmListItem(
                        id=vm.id,
                        name=vm.name,
                        description=vm.description or "",
                        file_hash=vm.hash[:16] + "..." if vm.hash else "",
                        hypervisor=vm.hypervisor or "virtualbox",
                        os_platform=os_platform,
                        instance_count=instance_count,
                    ))

                return Result.ok(items)

        except VMNotFoundError as e:
            return Result.from_exception(e)

    def get_by_id(self, vm_id: str) -> Result[VmInfo]:
        """
        Get a VM by its ID.

        Args:
            vm_id: VM database ID

        Returns:
            Result[VmInfo] with VM data, or error if not found.
        """
        try:
            with VmApi() as api:
                vm = api.get_vm_by_id(vm_id)

                if not vm:
                    return Result.fail(
                        code="VMNotFoundError",
                        message=f'VM with ID {vm_id} not found',
                        solutions=[
                            'Use `adare vm list` to see available VMs',
                            'Check if the VM ID is correct',
                        ]
                    )

                # Extract OS info
                os_platform = None
                os_type = None
                os_distribution = None
                os_version = None
                os_language = None
                os_architecture = None

                if hasattr(vm, 'osinfo') and vm.osinfo:
                    os_platform = vm.osinfo.platform
                    os_type = vm.osinfo.os
                    os_distribution = vm.osinfo.distribution
                    os_version = vm.osinfo.version
                    os_language = vm.osinfo.language
                    os_architecture = vm.osinfo.architecture

                # Count instances
                instance_count = len(api.get_vm_instances_for_vm(vm.id))

                # Check if external
                is_external = api.is_vm_external(vm.id)

                return Result.ok(VmInfo(
                    id=vm.id,
                    name=vm.name,
                    file_path=vm.file,
                    file_hash=vm.hash,
                    description=vm.description or "",
                    hypervisor=vm.hypervisor or "virtualbox",
                    use_snapshots=getattr(vm, 'use_snapshots', True),
                    os_platform=os_platform,
                    os_type=os_type,
                    os_distribution=os_distribution,
                    os_version=os_version,
                    os_language=os_language,
                    os_architecture=os_architecture,
                    instance_count=instance_count,
                    is_external=is_external,
                ))

        except VMNotFoundError as e:
            return Result.from_exception(e)

    def get_by_name(self, name: str) -> Result[VmInfo]:
        """
        Get a VM by its name.

        Args:
            name: VM name

        Returns:
            Result[VmInfo] with VM data, or error if not found.
        """
        try:
            with VmApi() as api:
                vm = api.get_vm_by_name(name)

                if not vm:
                    return Result.fail(
                        code="VMNotFoundError",
                        message=f'VM with name "{name}" not found',
                        solutions=[
                            'Use `adare vm list` to see available VMs',
                            'Check if the VM name is spelled correctly',
                        ]
                    )

                return self.get_by_id(vm.id)

        except VMNotFoundError as e:
            return Result.from_exception(e)

    def delete(self, vm_id: str, force: bool = False) -> Result[None]:
        """
        Delete a VM from the system.

        Args:
            vm_id: VM database ID
            force: Force deletion even if VM has instances

        Returns:
            Result[None] on success, or error information on failure.
        """
        try:
            with VmApi() as api:
                vm = api.get_vm_by_id(vm_id)
                if not vm:
                    return Result.fail(
                        code="VMNotFoundError",
                        message=f'VM with ID {vm_id} not found',
                        solutions=[
                            'Use `adare vm list` to see available VMs',
                        ]
                    )

                # Check for instances
                instances = api.get_vm_instances_for_vm(vm_id)
                if instances and not force:
                    return Result.fail(
                        code="VMHasInstancesError",
                        message=f'VM "{vm.name}" has {len(instances)} active instances',
                        solutions=[
                            'Use --force to delete VM and all its instances',
                            'Remove instances first with `adare vm instance remove`',
                        ]
                    )

                api.delete_vm(vm_id)
                return Result.ok(None)

        except VMNotFoundError as e:
            return Result.from_exception(e)
        except VMError as e:
            return Result.from_exception(e)

    def clear_all(self, force: bool = False) -> Result[VmClearResult]:
        """
        Clear all VMs from the system.

        Args:
            force: Force deletion even if VMs are in use

        Returns:
            Result[VmClearResult] with deletion results.
        """
        try:
            results = backend_clear_all_vms(force=force)

            return Result.ok(VmClearResult(
                deleted_count=results['deleted_count'],
                deleted_vms=results['deleted_vms'],
                failed_count=results['failed_count'],
                failed_vms=results['failed_vms'],
            ))

        except VMError as e:
            return Result.from_exception(e)

    def clear_by_environment(self, environment_ulid: str, force: bool = False) -> Result[VmClearResult]:
        """
        Clear all VMs associated with a specific environment.

        Args:
            environment_ulid: Environment ULID
            force: Force deletion even if VMs are in use

        Returns:
            Result[VmClearResult] with deletion results.
        """
        try:
            results = backend_clear_vms_by_environment(environment_ulid, force=force)

            return Result.ok(VmClearResult(
                deleted_count=results['deleted_count'],
                deleted_vms=results['deleted_vms'],
                failed_count=results['failed_count'],
                failed_vms=results['failed_vms'],
            ))

        except VMError as e:
            return Result.from_exception(e)

    # =========================================================================
    # VM Instance Management
    # =========================================================================

    def list_instances(self, vm_id: str | None = None) -> Result[list[VmInstanceListItem]]:
        """
        List all VM instances, optionally filtered by VM.

        Args:
            vm_id: Optional VM ID to filter instances

        Returns:
            Result[List[VmInstanceListItem]] with all instances.
        """
        try:
            with VmApi() as api:
                if vm_id:
                    instances = api.get_vm_instances_for_vm(vm_id)
                else:
                    instances = api.get_all_vm_instances()

                items = []
                for instance in instances:
                    vm_name = instance.vm.name if instance.vm else "Unknown"
                    hypervisor = instance.vm.hypervisor if instance.vm else "virtualbox"

                    items.append(VmInstanceListItem(
                        id=instance.id,
                        vm_name=vm_name,
                        instance_name=instance.instance_name,
                        status=instance.status,
                        websocket_port=instance.websocket_port,
                        hypervisor=hypervisor,
                    ))

                return Result.ok(items)

        except VMNotFoundError as e:
            return Result.from_exception(e)

    def get_instance_by_id(self, instance_id: str) -> Result[VmInstanceInfo]:
        """
        Get a VM instance by its ID.

        Args:
            instance_id: VM instance ID

        Returns:
            Result[VmInstanceInfo] with instance data, or error if not found.
        """
        try:
            with VmApi() as api:
                instance = api.get_vm_instance_by_id(instance_id)

                if not instance:
                    return Result.fail(
                        code="VmInstanceNotFoundError",
                        message=f'VM instance with ID {instance_id} not found',
                        solutions=[
                            'Use `adare vm instance list` to see available instances',
                            'Check if the instance ID is correct',
                        ]
                    )

                vm_name = instance.vm.name if instance.vm else "Unknown"
                hypervisor = instance.vm.hypervisor if instance.vm else "virtualbox"

                return Result.ok(VmInstanceInfo(
                    id=instance.id,
                    vm_id=instance.vm_id,
                    vm_name=vm_name,
                    instance_name=instance.instance_name,
                    status=instance.status,
                    websocket_port=instance.websocket_port,
                    vbox_uuid=instance.vbox_uuid,
                    base_snapshot_name=instance.base_snapshot_name,
                    current_experiment_run_id=instance.current_experiment_run_id,
                    created_at=instance.created_at,
                    last_used_at=instance.last_used_at,
                    hypervisor=hypervisor,
                ))

        except VMNotFoundError as e:
            return Result.from_exception(e)

    async def remove_instance(self, instance_id: str) -> Result[None]:
        """
        Remove a specific VM instance.

        Args:
            instance_id: VM instance ID

        Returns:
            Result[None] on success, or error information on failure.
        """
        from adare.backend.vm.instance_manager import cleanup_vm_instance

        try:
            await cleanup_vm_instance(instance_id)
            return Result.ok(None)

        except VMNotFoundError as e:
            return Result.from_exception(e)
        except VMError as e:
            return Result.from_exception(e)

    async def remove_all_stopped_instances(self) -> Result[VmInstanceCleanupResult]:
        """
        Remove all stopped VM instances.

        Returns:
            Result[VmInstanceCleanupResult] with cleanup results.
        """
        from adare.backend.vm.instance_manager import remove_all_instances

        try:
            removed_instances = await remove_all_instances()

            return Result.ok(VmInstanceCleanupResult(
                removed_count=len(removed_instances),
                removed_instances=removed_instances,
                failed_count=0,
                failed_instances=[],
            ))

        except VMError as e:
            return Result.from_exception(e)

    def get_instance_usage(self) -> Result[VmInstanceUsage]:
        """
        Get VM instance usage statistics.

        Returns:
            Result[VmInstanceUsage] with usage statistics.
        """
        try:
            with VmApi() as api:
                instances = api.get_all_vm_instances()

                total = len(instances)
                active = sum(1 for i in instances if i.status == 'active')
                available = sum(1 for i in instances if i.status == 'available')
                stopped = sum(1 for i in instances if i.status == 'stopped')

                # Count by VM
                by_vm = {}
                for instance in instances:
                    vm_name = instance.vm.name if instance.vm else "Unknown"
                    by_vm[vm_name] = by_vm.get(vm_name, 0) + 1

                return Result.ok(VmInstanceUsage(
                    total_instances=total,
                    active_instances=active,
                    available_instances=available,
                    stopped_instances=stopped,
                    instances_by_vm=by_vm,
                ))

        except VMNotFoundError as e:
            return Result.from_exception(e)

    # =========================================================================
    # VM Snapshot Management
    # =========================================================================

    def list_snapshots(self, instance_id: str | None = None) -> Result[list[VmSnapshotInfo]]:
        """
        List all snapshots, optionally filtered by VM instance.

        Args:
            instance_id: Optional VM instance ID to filter snapshots

        Returns:
            Result[List[VmSnapshotInfo]] with all snapshots.
        """
        try:
            with VmApi() as api:
                if instance_id:
                    snapshots = api.get_snapshots_for_instance(instance_id)
                else:
                    # Get all snapshots by iterating through instances
                    snapshots = []
                    instances = api.get_all_vm_instances()
                    for instance in instances:
                        instance_snapshots = api.get_snapshots_for_instance(instance.id)
                        snapshots.extend(instance_snapshots)

                items = []
                for snapshot in snapshots:
                    items.append(VmSnapshotInfo(
                        id=snapshot.id,
                        name=snapshot.name,
                        snapshot_type=snapshot.snapshot_type or "unknown",
                        description=snapshot.description,
                        created_at=snapshot.created_at,
                        vm_id=snapshot.vm_id,
                        vm_instance_id=snapshot.vm_instance_id,
                        vbox_uuid=snapshot.vbox_uuid,
                    ))

                return Result.ok(items)

        except VMNotFoundError as e:
            return Result.from_exception(e)

    def delete_snapshot(self, instance_id: str, snapshot_name: str) -> Result[None]:
        """
        Delete a snapshot from a VM instance.

        Args:
            instance_id: VM instance ID
            snapshot_name: Name of the snapshot to delete

        Returns:
            Result[None] on success, or error information on failure.
        """
        try:
            from adare.backend.vm.snapshot_manager import SnapshotManager

            with VmApi() as api:
                instance = api.get_vm_instance_by_id(instance_id)
                if not instance:
                    return Result.fail(
                        code="VmInstanceNotFoundError",
                        message=f'VM instance with ID {instance_id} not found',
                        solutions=[
                            'Use `adare vm instance list` to see available instances',
                        ]
                    )

                # Get the parent VM record
                vm_record = api.get_vm_by_id(instance.vm_id)
                if not vm_record:
                    return Result.fail(
                        code="VMNotFoundError",
                        message=f'Parent VM with ID {instance.vm_id} not found',
                        solutions=[
                            'The VM may have been deleted',
                        ]
                    )

            # Delete the snapshot using snapshot manager
            snapshot_manager = SnapshotManager()
            success, msg = snapshot_manager._delete_snapshot(vm_record, snapshot_name)

            if success:
                return Result.ok(None)
            return Result.fail(
                code="SnapshotDeleteError",
                message=f'Failed to delete snapshot "{snapshot_name}": {msg}',
                solutions=[
                    'Check if the snapshot exists',
                    'Ensure the VM is not running',
                ]
            )

        except VMNotFoundError as e:
            return Result.from_exception(e)
        except VMError as e:
            return Result.from_exception(e)

    # =========================================================================
    # VM Testing
    # =========================================================================

    async def test_ova(self, request: VmTestRequest) -> Result[VmTestResult]:
        """
        Test OVA file compatibility with ADARE.

        Args:
            request: VmTestRequest with OVA file path and test options

        Returns:
            Result[VmTestResult] with test results.
        """
        from adare.backend.experiment.commands import ova_test

        try:
            success = await ova_test(
                ova_file_path=request.ova_file_path,
                guest_platform=request.guest_platform,
                verbose=request.verbose,
                vm_cleanup_mode=request.vm_cleanup_mode
            )

            if success:
                return Result.ok(VmTestResult(
                    success=True,
                    ova_file=str(request.ova_file_path),
                    guest_platform=request.guest_platform,
                    message='VM test completed successfully! OVA file is compatible with ADARE.'
                ))
            return Result.ok(VmTestResult(
                success=False,
                ova_file=str(request.ova_file_path),
                guest_platform=request.guest_platform,
                message='VM test failed! OVA file may not be compatible with ADARE.'
            ))

        except VMError as e:
            return Result.from_exception(e)
        except FileNotFoundError:
            return Result.fail(
                code="OVAFileNotFoundError",
                message=f'OVA file not found: {request.ova_file_path}',
                solutions=[
                    'Check if the file path is correct',
                    'Ensure the OVA file exists at the specified location',
                ]
            )
