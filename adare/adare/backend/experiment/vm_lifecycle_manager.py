from pathlib import Path
from datetime import datetime, timezone
import threading
import logging

from adare.backend.experiment.stagectxmanager import StageCtxManager
from adare.types.stages import (
    VMCreateStage, VMRunStage, VMWaitTillReadyStage, VMMountSharedDirectoriesStage,
    VMStopStage, VMDestroyStage, VMExperimentSnapshotStage
)
from adare.backend.experiment.runctx import ExperimentRunCtx
from adare.exceptions import LoggedException
from adare.config import SHARE_POINT_VM
from adare.virtualbox.api import VirtualBoxVM, VirtualBoxManager
import adare.backend.experiment.database as experiment_database
import adare.backend.environment.database as environment_database
import adare.backend.vm.database as vm_database

log = logging.getLogger(__name__)


class VMLifecycleManager:
    """Manages the complete lifecycle of VirtualBox VMs for experiments."""
    
    def __init__(self):
        self.vbox_manager = VirtualBoxManager()
    
    async def create_and_prepare_vm(self, context: ExperimentRunCtx):
        """Create and prepare VM for experiment with snapshots and shared folders."""
        # Get VM ID from environment (file operations already done during environment load)
        env_data = environment_database.get_environment_by_ulid(context.environment_ulid, fields=['vm_id'])
        vm_id = env_data['vm_id'] if env_data else None
        if not vm_id:
            raise LoggedException(log, "No VM associated with environment. Did you load the environment properly?")
        
        # Only handle VirtualBox import and snapshots (fast operations)
        from adare.backend.vm.commands import ensure_vm_ready_for_experiment
        
        log.info("Preparing VM for experiment (VirtualBox import and snapshots only)")
        vm_id = await ensure_vm_ready_for_experiment(
            vm_id=vm_id,
            experiment_id=context.experiment_run_ulid,
            environment_ulid=context.environment_ulid,
            experiment_run_ulid=context.experiment_run_ulid,
            preserve_experiment_snapshot=context.config.preserve_snapshot
        )
        
        # Get the prepared VM from database to use its actual VirtualBox name
        vm_record = vm_database.get_vm_by_id(vm_id)
        if not vm_record:
            raise LoggedException(log, f"VM with ID {vm_id} not found after preparation")
        
        # Use the actual VM name from database (not experiment-specific name)
        context.vm_name = vm_record.name
        
        # Setup shared directories configuration
        shared_root = Path(SHARE_POINT_VM[context.guest_platform])
        context.config.shared_directories = {
            'run': {'host': context.experiment_run_directory.path, 'vm': shared_root / 'run'},
            'adare': {'host': context.adarevm.parent, 'vm': shared_root / 'app'},
            'experiment': {'host': context.experiment_directory.path, 'vm': shared_root / 'experiment'},
            'testfunctions': {'host': context.project_directory.testfunctions, 'vm': shared_root / 'testfunctions'},
            'shared': {'host': context.project_directory.shared, 'vm': shared_root / 'shared'},
        }
        
        # Create VirtualBox VM instance
        context.vm = VirtualBoxVM(
            vm_name=context.vm_name,  # Use the actual VM name from database
            guest_os=context.guest_platform,
            manager=self.vbox_manager,
            cpus=context.config.vm_cpus,
            ram=context.config.vm_memory
        )

        # VM is already prepared with snapshots - just verify it exists in VirtualBox
        with StageCtxManager(VMCreateStage(), context.experiment_run_ulid, event=context.user_interrupt_event):
            if not VirtualBoxVM.verify_vm_exists_by_uuid(vm_record.vbox_uuid):
                raise LoggedException(log, f"VM '{context.vm_name}' was not properly prepared - missing from VirtualBox")
            log.info(f"Using prepared VM '{context.vm_name}' with snapshots (UUID: {vm_record.vbox_uuid})")

        # Setup shared folders - simple cleanup and add
        if not context.stop_event.is_set():
            # First clean up any existing shared folders to avoid conflicts
            await context.vm.clean_shared_folders({}, stop_event=context.user_interrupt_event)
            
            # Now add the new shared folders
            for name, paths in context.config.shared_directories.items():
                await context.vm.add_shared_folder(name, host_path=paths['host'], stop_event=context.user_interrupt_event)

        # Update experiment run with VM-specific data
        if not context.stop_event.is_set():
            context.experiment_run_ulid = experiment_database.update_experiment_run(
                context.experiment_run_ulid,
                context.experiment_run_directory
            )

        # Add port forwarding for the websocket server
        if not context.stop_event.is_set():
            await context.vm.add_port_forwarding(
                name='adarevm',
                protocol='tcp',
                host_port=context.config.websocket_port,
                guest_port=context.config.websocket_port,
                stop_event=context.user_interrupt_event
            )
            log.info(f'added port forwarding for websocket server on port {context.config.websocket_port}')

        context.timestamp_before_vm_start = datetime.now(timezone.utc)

    async def start_vm(self, context: ExperimentRunCtx):
        """Start the virtual machine."""
        with StageCtxManager(VMRunStage(), context.experiment_run_ulid, event=context.user_interrupt_event):
            await context.vm.start(stop_event=context.user_interrupt_event)
            
            # Set video mode hint to default resolution after VM starts
            if not context.stop_event.is_set():
                width, height = context.config.vm_resolution
                await context.vm.set_video_mode_hint(
                    width=width, 
                    height=height,
                    stop_event=context.user_interrupt_event
                )

    async def wait_until_ready(self, context: ExperimentRunCtx):
        """Wait until VM is fully booted and ready."""
        with StageCtxManager(VMWaitTillReadyStage(), context.experiment_run_ulid, event=context.user_interrupt_event):
            log.info('waiting until VM is ready')
            if not await context.vm.wait_until_fully_booted(timeout=360, stop_event=context.user_interrupt_event):
                raise LoggedException(log, 'VM did not become ready in time')
            log.info('VM is ready')

    async def mount_shared_directories(self, context: ExperimentRunCtx):
        """Mount all configured shared directories in the VM."""
        with StageCtxManager(VMMountSharedDirectoriesStage(), context.experiment_run_ulid, event=context.user_interrupt_event):
            folders = {
                name: paths['vm'] for name, paths in context.config.shared_directories.items()
            }
            await context.vm.mount_multiple_shared_folders(
                folders=folders,
                stop_event=context.user_interrupt_event
            )

    async def stop_vm(self, context: ExperimentRunCtx, post_interrupt: bool = False):
        """Stop the virtual machine."""
        event = None if post_interrupt else context.user_interrupt_event
        with StageCtxManager(VMStopStage(), context.experiment_run_ulid, event=event):
            log.info('stopping virtualbox virtual machine')
            if context.vm:
                await context.vm.stop()

    async def cleanup_vm(self, context: ExperimentRunCtx, post_interrupt: bool = False):
        """Cleanup VM resources and handle experiment snapshots."""
        event = None if post_interrupt else context.user_interrupt_event
        with StageCtxManager(VMDestroyStage(), context.experiment_run_ulid, event=event):
            if context.config.preserve_snapshot:
                log.info('Creating experiment snapshot (--preserve-snapshot enabled)')
                await self._create_experiment_snapshot(context, event)
            else:
                log.info('Cleaning up experiment snapshot (default behavior)')
                await self._cleanup_experiment_snapshot(context)
            
            # Keep the VM running - do NOT destroy it
            log.info('VM preserved for future experiments')

    async def _create_experiment_snapshot(self, context: ExperimentRunCtx, event: threading.Event):
        """Create a snapshot of the final experiment state."""
        if context.vm and context.experiment_run_ulid:
            # Import snapshot manager for creating snapshot
            from adare.backend.vm.snapshot_manager import SnapshotManager
            
            # Get VM record from database to create snapshot
            try:
                from adare.database.api.vm import VmApi
                with VmApi() as api:
                    vm_records = api.get_all_vms()
                    vm_record = None
                    for record in vm_records:
                        if record.name == context.vm_name:
                            vm_record = record
                            break
                
                if vm_record and vm_record.vbox_uuid:
                    snapshot_manager = SnapshotManager()
                    
                    # Create new experiment snapshot with current state
                    with StageCtxManager(VMExperimentSnapshotStage(), context.experiment_run_ulid, event=event):
                        created_snapshot = snapshot_manager.create_experiment_snapshot(
                            vm_record, 
                            context.experiment_run_ulid,
                            description=f"Final state snapshot for experiment {context.experiment_run_ulid}",
                            silent=False
                        )
                    
                    if created_snapshot:
                        log.info(f'Created experiment snapshot: {created_snapshot}')
                    else:
                        log.warning('Failed to create experiment snapshot')
                else:
                    log.warning('VM record not found or missing UUID - cannot create experiment snapshot')
                    
            except Exception as e:
                log.warning(f'Error creating experiment snapshot: {e}')

    async def _cleanup_experiment_snapshot(self, context: ExperimentRunCtx):
        """Clean up experiment-specific snapshots."""
        if context.vm and context.experiment_run_ulid:
            # Import snapshot manager for cleanup
            from adare.backend.vm.snapshot_manager import SnapshotManager
            
            # Get VM record from database to access snapshot management
            try:
                # Get the VM ID from the database using the VM name
                from adare.database.api.vm import VmApi
                with VmApi() as api:
                    vm_records = api.get_all_vms()
                    vm_record = None
                    for record in vm_records:
                        if record.name == context.vm_name:
                            vm_record = record
                            break
                
                if vm_record and vm_record.vbox_uuid:
                    snapshot_manager = SnapshotManager()
                    
                    # Generate the experiment snapshot name (same logic as in create_experiment_snapshot)
                    exp_snapshot_name = f"adare_exp_{context.experiment_run_ulid[:8]}"
                    
                    # Delete only the experiment-specific snapshot
                    success = snapshot_manager._delete_snapshot(vm_record, exp_snapshot_name)
                    if success:
                        log.info(f'Successfully cleaned up experiment snapshot: {exp_snapshot_name}')
                    else:
                        log.warning(f'Failed to cleanup experiment snapshot: {exp_snapshot_name} (may not exist)')
                else:
                    log.warning('VM record not found or missing UUID - cannot cleanup experiment snapshot')
                    
            except Exception as e:
                log.warning(f'Error during snapshot cleanup: {e}')