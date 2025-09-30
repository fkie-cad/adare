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
import shutil
import os

log = logging.getLogger(__name__)


class VMLifecycleManager:
    """Manages the complete lifecycle of VirtualBox VMs for experiments."""
    
    def __init__(self):
        self.vbox_manager = VirtualBoxManager()

    async def _ensure_vm_runtime_ready(self, context: ExperimentRunCtx):
        """Ensure project VM runtime directory is ready with up-to-date adarevm and adarelib."""
        # Use project-level vm_runtime directory instead of creating per-experiment copies
        vm_runtime_dir = context.project_directory.vm_runtime
        adarevm_target = vm_runtime_dir / 'adarevm'
        adarelib_target = vm_runtime_dir / 'adarelib'

        # Use global sources
        adarevm_source = context.adarevm
        adarelib_source = context.adarelib

        # Check if we need to copy/update files
        needs_update = False

        if not vm_runtime_dir.exists():
            log.info("CLAUDE: Creating project VM runtime directory for first time")
            needs_update = True
        elif not adarevm_target.exists() or not adarelib_target.exists():
            log.info("CLAUDE: Project VM runtime directory incomplete, updating")
            needs_update = True
        else:
            # Check if source files are newer than target
            adarevm_source_time = self._get_latest_mtime(adarevm_source)
            adarelib_source_time = self._get_latest_mtime(adarelib_source)
            adarevm_target_time = self._get_latest_mtime(adarevm_target)
            adarelib_target_time = self._get_latest_mtime(adarelib_target)

            if (adarevm_source_time > adarevm_target_time or
                adarelib_source_time > adarelib_target_time):
                log.info("CLAUDE: Source files newer than cached runtime, updating")
                needs_update = True

        if needs_update:
            # Create/recreate VM runtime directory
            if vm_runtime_dir.exists():
                shutil.rmtree(vm_runtime_dir)
            vm_runtime_dir.mkdir(parents=True)

            # Copy adarevm
            log.info(f"CLAUDE: Copying adarevm from {adarevm_source} to {adarevm_target}")
            shutil.copytree(adarevm_source, adarevm_target, dirs_exist_ok=True)

            # Copy adarelib
            log.info(f"CLAUDE: Copying adarelib from {adarelib_source} to {adarelib_target}")
            shutil.copytree(adarelib_source, adarelib_target, dirs_exist_ok=True)

            log.info("CLAUDE: Project VM runtime directory ready")
        else:
            log.info("CLAUDE: Project VM runtime directory up-to-date")

    def _get_latest_mtime(self, directory: Path) -> float:
        """Get the latest modification time in a directory tree."""
        if not directory.exists():
            return 0.0

        latest = 0.0
        for root, dirs, files in os.walk(directory):
            # Skip __pycache__ directories
            dirs[:] = [d for d in dirs if d != '__pycache__']

            for file in files:
                if file.endswith('.pyc'):
                    continue
                file_path = Path(root) / file
                try:
                    mtime = file_path.stat().st_mtime
                    latest = max(latest, mtime)
                except (OSError, PermissionError):
                    continue
        return latest


    async def create_and_prepare_vm(self, context: ExperimentRunCtx):
        """Create and prepare VM for experiment with snapshots and shared folders."""
        # Get VM ID from environment (file operations already done during environment load)
        env_data = environment_database.get_environment_by_ulid(context.environment_ulid, fields=['vm_id'])
        vm_id = env_data['vm_id'] if env_data else None
        if not vm_id:
            raise LoggedException(log, "No VM associated with environment. Did you load the environment properly?")
        
        # Prepare VM instance for experiment (includes port allocation and VM reuse)
        from adare.backend.vm.commands import ensure_vm_ready_for_experiment
        from adare.database.api.vm import VmApi

        log.info("CLAUDE: Starting VM instance preparation for experiment (with dynamic port allocation)")

        # Use shorter experiment ID for VM instance naming (first 8 chars of ULID)
        short_experiment_id = context.experiment_run_ulid[:8]
        log.debug(f"CLAUDE: VM preparation - vm_id={vm_id}, short_experiment_id={short_experiment_id}, experiment_run_ulid={context.experiment_run_ulid}")

        # Add timeout to VM instance allocation
        import asyncio
        vm_instance_id = await asyncio.wait_for(
            ensure_vm_ready_for_experiment(
                vm_id=vm_id,
                experiment_id=short_experiment_id,  # Use shorter ID for naming
                environment_ulid=context.environment_ulid,
                experiment_run_ulid=context.experiment_run_ulid,
                preserve_experiment_snapshot=context.config.preserve_snapshot,
                interrupt_event=context.user_interrupt_event
            ),
            timeout=120  # 2 minute timeout
        )
        log.info(f"CLAUDE: VM instance allocation completed successfully, instance_id={vm_instance_id}")

        # Check if VM preparation was interrupted - return early if so
        if vm_instance_id is None:
            log.info("VM instance preparation was interrupted - returning early")
            return

        # Get the prepared VM instance from database
        log.debug(f"CLAUDE: Attempting to fetch VM instance with ID: {vm_instance_id}")
        try:
            with VmApi() as api:
                vm_instance = api.get_vm_instance_by_id(vm_instance_id)
                if not vm_instance:
                    # Try to debug what instances exist
                    log.error(f"CLAUDE: VM instance {vm_instance_id} not found! Checking database...")
                    all_instances = api.get_all_vm_instances()
                    log.error(f"CLAUDE: Found {len(all_instances)} total instances in database:")
                    for inst in all_instances:
                        log.error(f"CLAUDE:   - {inst.id}: {inst.instance_name} (status: {inst.status})")

                    # Check if ID format is correct
                    log.error(f"CLAUDE: Problematic ID: '{vm_instance_id}' (length: {len(vm_instance_id)}, type: {type(vm_instance_id)})")

                    raise LoggedException(log, f"VM instance with ID {vm_instance_id} not found after preparation")

                log.debug(f"CLAUDE: Successfully found VM instance: {vm_instance.instance_name}")
        except Exception as e:
            log.error(f"CLAUDE: Error fetching VM instance: {e}")
            import traceback
            log.debug(f"CLAUDE: Fetch VM instance traceback: {traceback.format_exc()}")
            raise

        # Update experiment run with VM instance ID
        experiment_database.update_experiment_run_vm_instance(
            context.config.project_path,
            context.experiment_run_ulid,
            vm_instance_id
        )

        # Use the instance name and port from the allocated instance
        context.vm_name = vm_instance.instance_name
        context.config.websocket_port = vm_instance.websocket_port

        # Validate that the port was properly allocated
        if context.config.websocket_port is None:
            raise LoggedException(log, f"VM instance {vm_instance.instance_name} has no websocket port allocated")

        log.info(f"Using VM instance: {context.vm_name} on port {context.config.websocket_port}")
        
        # Setup VM runtime directory with smart copying
        await self._ensure_vm_runtime_ready(context)

        # Setup shared directories configuration
        shared_root = Path(SHARE_POINT_VM[context.guest_platform])
        context.config.shared_directories = {
            'run': {'host': context.experiment_run_directory.path, 'vm': shared_root / 'run'},
            'adare': {'host': context.project_directory.vm_runtime, 'vm': shared_root / 'app'},
            'experiment': {'host': context.experiment_directory.path, 'vm': shared_root / 'experiment'},
            'shared': {'host': context.experiment_directory.shared, 'vm': shared_root / 'shared'},
        }
        
        # Create VirtualBox VM instance using the instance name and UUID
        from adare.config import get_vm_credentials
        username, password = get_vm_credentials(context.guest_platform)
        context.vm = VirtualBoxVM(
            vm_name=context.vm_name,  # Use the VM instance name
            guest_os=context.guest_platform,
            manager=self.vbox_manager,
            username=username,
            password=password,
            cpus=context.config.vm_cpus,
            ram=context.config.vm_memory
        )

        # VM instance is already prepared with snapshots - verify it exists and cleanup if missing
        with StageCtxManager(VMCreateStage(), context.experiment_run_ulid, event=context.user_interrupt_event):
            # Import the VM instance verification function
            from adare.backend.vm.commands import verify_and_cleanup_vm_instance_for_experiment
            from adare.database.api.vm import VmApi

            # First verify and cleanup VM instance if missing from VirtualBox
            try:
                vm_instance_is_available = verify_and_cleanup_vm_instance_for_experiment(
                    vm_instance.id,
                    context.experiment_run_ulid
                )
                if not vm_instance_is_available:
                    # VM instance was missing and cleaned up - need to allocate a new one
                    log.info(f"VM instance was cleaned up, allocating a new instance for the experiment")

                    # Re-allocate a new VM instance for this experiment
                    from adare.backend.vm.instance_manager import allocate_vm_instance_for_experiment

                    # Get VM ID from environment (same as original allocation)
                    env_data = environment_database.get_environment_by_ulid(context.environment_ulid, fields=['vm_id'])
                    vm_id = env_data['vm_id'] if env_data else None
                    if not vm_id:
                        raise LoggedException(log, "No VM associated with environment after cleanup")

                    # Allocate new instance
                    new_vm_instance = await allocate_vm_instance_for_experiment(vm_id, context.experiment_run_ulid)
                    if not new_vm_instance:
                        raise LoggedException(log, "Failed to allocate new VM instance after cleanup")

                    # Update the experiment run with new VM instance ID
                    experiment_database.update_experiment_run_vm_instance(
                        context.config.project_path,
                        context.experiment_run_ulid,
                        new_vm_instance.id
                    )

                    # Update context with new instance information
                    vm_instance = new_vm_instance
                    context.vm_name = vm_instance.instance_name
                    context.config.websocket_port = vm_instance.websocket_port

                    # Validate that the port was properly allocated
                    if context.config.websocket_port is None:
                        raise LoggedException(log, f"New VM instance {vm_instance.instance_name} has no websocket port allocated")

                    log.info(f"Successfully allocated new VM instance after cleanup: {context.vm_name} on port {context.config.websocket_port}")

                    # New instance needs to be imported to VirtualBox if it doesn't have a UUID
                    if not vm_instance.vbox_uuid:
                        log.info(f"New VM instance '{vm_instance.instance_name}' needs to be imported to VirtualBox")

                        # Get source VM for import
                        source_vm = vm_database.get_vm_by_id(vm_id)
                        if not source_vm:
                            raise LoggedException(log, f"Source VM with ID {vm_id} not found for import")

                        # Verify source VM integrity
                        from adare.backend.vm.commands import verify_vm_integrity
                        await verify_vm_integrity(vm_id, context.experiment_run_ulid, context.user_interrupt_event)

                        # Import VM instance to VirtualBox with proper stage management
                        with StageCtxManager(VMImportStage(), context.experiment_run_ulid, context.user_interrupt_event):
                            log.info(f"Importing new VM instance '{vm_instance.instance_name}' to VirtualBox...")

                            # Import using VirtualBox manager directly (inline implementation)
                            from adare.virtualbox.api import VirtualBoxManager

                            manager = VirtualBoxManager()
                            vm_file_path = Path(source_vm.file)

                            # Import VM with unique instance name
                            vbox_vm = await manager.import_vm_async(
                                vm_file_path,
                                vm_instance.instance_name,
                                environment_ulid=context.environment_ulid
                            )

                            # Update instance with VirtualBox UUID
                            vbox_uuid = vbox_vm.get_vm_uuid()
                            with VmApi() as api:
                                api.update_vm_instance(
                                    vm_instance.id,
                                    vbox_uuid=vbox_uuid,
                                    base_snapshot_name=f"{vm_instance.instance_name}_base"
                                )

                            log.info(f"Successfully imported VM instance '{vm_instance.instance_name}' with UUID: {vbox_uuid}")

                            # Return updated instance
                            with VmApi() as api:
                                vm_instance = api.get_vm_instance_by_id(vm_instance.id)

                        # Create base snapshot for the new instance
                        with StageCtxManager(VMSnapshotCreateStage(), context.experiment_run_ulid, context.user_interrupt_event):
                            from adare.backend.vm.snapshot_manager import create_base_snapshot_for_instance
                            snapshot_success = create_base_snapshot_for_instance(vm_instance, silent=False)
                            if not snapshot_success:
                                log.warning(f"Failed to create base snapshot for new instance {vm_instance.instance_name}")
                            else:
                                log.info(f"Successfully created base snapshot for new instance {vm_instance.instance_name}")

                        log.info(f"Successfully imported and prepared new VM instance: {vm_instance.instance_name}")
            except Exception as e:
                log.error(f"VM instance verification failed: {e}")
                raise LoggedException(log, f"VM instance verification failed: {e}")

            # Final verification that VM instance exists in VirtualBox
            if not vm_instance.vbox_uuid or not VirtualBoxVM.verify_vm_exists_by_uuid(vm_instance.vbox_uuid):
                raise LoggedException(log, f"VM instance '{context.vm_name}' was not properly prepared - missing from VirtualBox")
            log.info(f"Using prepared VM instance '{context.vm_name}' with snapshots (UUID: {vm_instance.vbox_uuid})")

        # Setup shared folders - remove all existing and add fresh ones
        if not context.stop_event.is_set():
            log.info("CLAUDE: Setting up shared folders for VM")

            # Remove all existing shared folders to prevent conflicts
            log.debug("CLAUDE: Removing all existing shared folders to prevent conflicts")
            await context.vm.remove_all_shared_folders(stop_event=context.user_interrupt_event)

            # Add the new shared folders for this experiment
            log.info(f"CLAUDE: Adding {len(context.config.shared_directories)} shared folders to VirtualBox config")
            for name, paths in context.config.shared_directories.items():
                log.debug(f"CLAUDE: Adding shared folder '{name}': host={paths['host']} -> vm={paths['vm']}")
                return_code = await context.vm.add_shared_folder(name, host_path=paths['host'], stop_event=context.user_interrupt_event)

                if return_code != 0:
                    raise LoggedException(log, f"CLAUDE: Failed to add shared folder '{name}' to VirtualBox (return code: {return_code})")

            log.info("CLAUDE: All shared folders added to VirtualBox successfully")

        # Update experiment run with VM-specific data
        if not context.stop_event.is_set():
            context.experiment_run_ulid = experiment_database.update_experiment_run(
                context.experiment_run_ulid,
                context.experiment_run_directory
            )

        # Add port forwarding for the websocket server
        if not context.stop_event.is_set():
            # Clean up any existing 'adarevm' port forwarding rule first
            await context.vm.remove_port_forwarding(
                name='adarevm',
                stop_event=context.user_interrupt_event,
                silent=True
            )

            # Add port forwarding: host uses allocated unique port, guest always uses 18765
            # Validate port is allocated before attempting port forwarding
            if context.config.websocket_port is None:
                raise LoggedException(log, "Cannot set up port forwarding: no websocket port allocated")

            await context.vm.add_port_forwarding(
                name='adarevm',
                protocol='tcp',
                host_port=context.config.websocket_port,  # Unique allocated port
                guest_port=18765,  # Always use 18765 in guest VM
                stop_event=context.user_interrupt_event
            )
            log.info(f'added port forwarding for websocket server: host:{context.config.websocket_port} -> guest:18765')

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
            # Verify all shared folders exist in VirtualBox config before mounting
            log.info("CLAUDE: Verifying shared folders exist in VirtualBox config before mounting")
            existing_folders = await context.vm.list_shared_folders(stop_event=context.user_interrupt_event, silent=True)
            log.debug(f"CLAUDE: Found {len(existing_folders)} shared folders in VirtualBox config: {list(existing_folders.keys())}")

            folders = {
                name: paths['vm'] for name, paths in context.config.shared_directories.items()
            }

            # Check that all required folders exist
            missing_folders = [name for name in folders.keys() if name not in existing_folders]
            if missing_folders:
                raise LoggedException(
                    log,
                    f"CLAUDE: Cannot mount shared folders - the following folders are not configured in VirtualBox: {missing_folders}. "
                    f"Expected folders: {list(folders.keys())}, Found: {list(existing_folders.keys())}"
                )

            log.info(f"CLAUDE: All {len(folders)} required shared folders exist in VirtualBox, proceeding with mount")
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

            # Clean up port forwarding before releasing VM instance
            if context.vm:
                log.info('Cleaning up port forwarding rules before VM instance release')
                await context.vm.remove_port_forwarding(
                    name='adarevm',
                    stop_event=event,
                    silent=True
                )

            # Release VM instance for reuse by other experiments
            log.info('Releasing VM instance for reuse by future experiments')
            await self._release_vm_instance(context)

    async def _release_vm_instance(self, context: ExperimentRunCtx):
        """Release the VM instance used by this experiment."""
        try:
            # Get the VM instance ID from the experiment run
            from adare.database.api.experiment import ExperimentApi
            from adare.database.models.project_models import ExperimentRun

            with ExperimentApi(context.config.project_path) as api:
                experiment_run = api._session.query(ExperimentRun).filter(
                    ExperimentRun.id == context.experiment_run_ulid
                ).first()

            if experiment_run and experiment_run.vm_instance_id:
                from adare.backend.vm.commands import release_vm_instance_for_experiment
                await release_vm_instance_for_experiment(experiment_run.vm_instance_id)
                log.info(f"Released VM instance {experiment_run.vm_instance_id} for reuse")
            else:
                log.warning("No VM instance ID found in experiment run - cannot release")
        except Exception as e:
            log.error(f"Failed to release VM instance: {e}")


    async def _create_experiment_snapshot(self, context: ExperimentRunCtx, event: threading.Event):
        """Create a snapshot of the final experiment state."""
        if context.vm and context.experiment_run_ulid:
            # Import snapshot manager for creating snapshot
            from adare.backend.vm.snapshot_manager import SnapshotManager

            # Get VM instance from database to create snapshot
            try:
                from adare.database.api.vm import VmApi
                from adare.database.api.experiment import ExperimentApi
                from adare.database.models.project_models import ExperimentRun

                # Get the VM instance ID from the experiment run
                with ExperimentApi(context.config.project_path) as api:
                    experiment_run = api._session.query(ExperimentRun).filter(
                        ExperimentRun.id == context.experiment_run_ulid
                    ).first()

                if not experiment_run or not experiment_run.vm_instance_id:
                    log.warning('No VM instance ID found in experiment run - cannot create experiment snapshot')
                    return

                # Get the VM instance
                with VmApi() as api:
                    vm_instance = api.get_vm_instance_by_id(experiment_run.vm_instance_id)

                if vm_instance and vm_instance.vbox_uuid:
                    snapshot_manager = SnapshotManager()

                    # Create new experiment snapshot with current state
                    with StageCtxManager(VMExperimentSnapshotStage(), context.experiment_run_ulid, event=event):
                        created_snapshot = snapshot_manager.create_experiment_snapshot_for_instance(
                            vm_instance,
                            context.experiment_run_ulid,
                            description=f"Final state snapshot for experiment {context.experiment_run_ulid}",
                            silent=False
                        )

                    if created_snapshot:
                        log.info(f'Created experiment snapshot: {created_snapshot}')
                    else:
                        log.warning('Failed to create experiment snapshot')
                else:
                    log.warning('VM instance not found or missing UUID - cannot create experiment snapshot')

            except Exception as e:
                log.warning(f'Error creating experiment snapshot: {e}')

    async def _cleanup_experiment_snapshot(self, context: ExperimentRunCtx):
        """Clean up experiment-specific snapshots."""
        if context.vm and context.experiment_run_ulid:
            # Import snapshot manager for cleanup
            from adare.backend.vm.snapshot_manager import SnapshotManager

            # Get VM instance from database to delete snapshot
            try:
                from adare.database.api.vm import VmApi
                from adare.database.api.experiment import ExperimentApi
                from adare.database.models.project_models import ExperimentRun

                # Get the VM instance ID from the experiment run
                with ExperimentApi(context.config.project_path) as api:
                    experiment_run = api._session.query(ExperimentRun).filter(
                        ExperimentRun.id == context.experiment_run_ulid
                    ).first()

                if not experiment_run or not experiment_run.vm_instance_id:
                    log.warning('No VM instance ID found in experiment run - cannot cleanup experiment snapshot')
                    return

                # Get the VM instance
                with VmApi() as api:
                    vm_instance = api.get_vm_instance_by_id(experiment_run.vm_instance_id)

                if vm_instance and vm_instance.vbox_uuid:
                    snapshot_manager = SnapshotManager()

                    # Generate the experiment snapshot name (same logic as in create_experiment_snapshot_for_instance)
                    exp_snapshot_name = f"adare_exp_{context.experiment_run_ulid[:8]}"

                    # Delete only the experiment-specific snapshot
                    success = snapshot_manager.delete_instance_snapshot(vm_instance, exp_snapshot_name, silent=True)
                    if success:
                        log.info(f'Successfully cleaned up experiment snapshot: {exp_snapshot_name}')
                    else:
                        log.warning(f'Failed to cleanup experiment snapshot: {exp_snapshot_name} (may not exist)')
                else:
                    log.warning('VM instance not found or missing UUID - cannot cleanup experiment snapshot')

            except Exception as e:
                log.warning(f'Error during snapshot cleanup: {e}')
