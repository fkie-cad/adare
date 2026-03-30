"""
VirtualBox-specific VM lifecycle strategy.

This module implements the VirtualBox lifecycle strategy using shared folders
for file transfer. Files are accessible to the guest while the VM is running.
"""
from pathlib import Path
import logging
import asyncio

from adare.hypervisor.base.lifecycle import AbstractVMLifecycleStrategy
from adare.hypervisor.virtualbox import VirtualBoxVM, VirtualBoxManager
from adare.types.stages import VMCreateStage
from adare.backend.experiment.stagectxmanager import StageCtxManager
from adare.exceptions import LoggedException
from adare.config import SHARE_POINT_VM, get_vm_credentials
import adare.backend.environment.database as environment_database
import adare.backend.experiment.database as experiment_database
import adare.backend.vm.database as vm_database

log = logging.getLogger(__name__)


class VirtualBoxLifecycleStrategy(AbstractVMLifecycleStrategy):
    """
    VirtualBox-specific lifecycle strategy using shared folders.

    VirtualBox uses shared folders for file transfer, which are configured
    before VM start and mounted after boot. Files are immediately accessible
    to both host and guest without explicit copying.
    """

    def __init__(self):
        self.vbox_manager = VirtualBoxManager()

    async def prepare_vm_for_experiment(self, context):
        """
        Create VirtualBox VM instance and allocate resources.

        This method is called by VMLifecycleManager.create_and_prepare_vm()
        after common VM instance allocation is complete. It creates the
        VirtualBox-specific VM object.

        Args:
            context: ExperimentRunCtx with vm_name and guest_platform already set
        """
        # Create VirtualBox VM instance using the allocated instance name
        username, password = get_vm_credentials(context.guest_platform)
        context.vm = VirtualBoxVM(
            vm_name=context.vm_name,
            guest_os=context.guest_platform,
            manager=self.vbox_manager,
            username=username,
            password=password,
            executables=self.vbox_manager.executables,
            cpus=context.config.vm_cpus,
            ram=context.config.vm_memory
        )
        log.info(f"Created VirtualBox VM instance: {context.vm_name}")

    async def setup_networking(self, context):
        """
        Setup port forwarding for WebSocket communication.

        Configures port forwarding from host to guest VM for adarevm WebSocket server.
        The guest always uses port 18765, while the host uses a dynamically allocated port.

        Args:
            context: ExperimentRunCtx containing configuration
        """
        # Clean up any existing 'adarevm' port forwarding rule first
        await context.vm.remove_port_forwarding(
            name='adarevm',
            stop_event=context.user_interrupt_event,
            silent=True
        )

        # Add port forwarding: host uses allocated unique port, guest always uses 18765
        if context.config.websocket_port is None:
            raise LoggedException(log, "Cannot set up port forwarding: no websocket port allocated")

        await context.vm.add_port_forwarding(
            name='adarevm',
            protocol='tcp',
            host_port=context.config.websocket_port,
            guest_port=18765,
            stop_event=context.user_interrupt_event
        )
        log.info(f'Added port forwarding for websocket server: host:{context.config.websocket_port} -> guest:18765')

    async def setup_file_transfer(self, context):
        """
        Configure VirtualBox shared folders for file transfer.

        Sets up shared directories for:
        - run: experiment run directory
        - adare: adarevm/adarelib runtime
        - experiment: experiment configuration
        - project_shared: project-level shared files (if exists)
        - shared: experiment-level shared files (if exists)

        Args:
            context: ExperimentRunCtx containing directories
        """
        # Setup shared directories configuration
        shared_root = Path(SHARE_POINT_VM[context.guest_platform])
        context.config.shared_directories = {
            'run': {'host': context.experiment_run_directory.path, 'vm': shared_root / 'run'},
            'adare': {'host': context.project_directory.vm_runtime, 'vm': shared_root / 'vm'},
            'experiment': {'host': context.experiment_directory.path, 'vm': shared_root / 'experiment'},
        }

        # Add project-level shared directory if it exists
        if context.project_directory.shared.exists():
            context.config.shared_directories['project_shared'] = {
                'host': context.project_directory.shared,
                'vm': shared_root / 'project_shared'
            }

        # Add experiment-level shared directory if it exists
        if context.experiment_directory.shared.exists():
            context.config.shared_directories['shared'] = {
                'host': context.experiment_directory.shared,
                'vm': shared_root / 'shared'
            }

        # Remove all existing shared folders to prevent conflicts
        log.debug("Removing all existing shared folders to prevent conflicts")
        await context.vm.remove_all_shared_folders(stop_event=context.user_interrupt_event)

        # Add the new shared folders for this experiment
        log.info(f"Adding {len(context.config.shared_directories)} shared folders to VirtualBox config")
        for name, paths in context.config.shared_directories.items():
            log.debug(f"Adding shared folder '{name}': host={paths['host']} -> vm={paths['vm']}")
            return_code = await context.vm.add_shared_folder(
                name,
                host_path=paths['host'],
                stop_event=context.user_interrupt_event
            )

            if return_code != 0:
                raise LoggedException(
                    log,
                    f"Failed to add shared folder '{name}' to VirtualBox (return code: {return_code})"
                )

        log.info("All shared folders added to VirtualBox successfully")

    async def start_and_initialize_vm(self, context):
        """
        Start VirtualBox VM and mount shared folders.

        VirtualBox shared folders must be mounted after the VM boots.

        Args:
            context: ExperimentRunCtx containing VM
        """
        from adare.types.stages import VMStartStage, VMGuestAgentWaitStage, VMMountSharedDirectoriesStage
        from adare.backend.experiment.stagectxmanager import StageCtxManager

        # Stage 1: Start VM
        with StageCtxManager(
            VMStartStage(),
            context.experiment_run_ulid,
            context.user_interrupt_event
        ):
            # Start the VM
            await context.vm.start(stop_event=context.user_interrupt_event)

            # Set video mode hint to default resolution after VM starts
            if not context.stop_event.is_set():
                width, height = context.config.vm_resolution
                await context.vm.set_video_mode_hint(
                    width=width,
                    height=height,
                    stop_event=context.user_interrupt_event
                )

        # Stage 2: Wait for guest agent
        with StageCtxManager(
            VMGuestAgentWaitStage(),
            context.experiment_run_ulid,
            context.user_interrupt_event
        ):
            # Wait until VM is fully booted and ready
            log.info('Waiting until VM is ready')
            if not await context.vm.wait_until_fully_booted(timeout=360, stop_event=context.user_interrupt_event):
                raise LoggedException(log, 'VM did not become ready in time')
            log.info('VM is ready')

            # Allow grace period for guest agent to fully stabilize
            grace_period = 3  # seconds
            log.debug(f"Allowing {grace_period}s grace period for guest agent to fully stabilize")
            await asyncio.sleep(grace_period)

        # Stage 3: Mount shared directories (VirtualBox-specific)
        with StageCtxManager(
            VMMountSharedDirectoriesStage(),
            context.experiment_run_ulid,
            context.user_interrupt_event
        ):
            # Mount shared directories in the VM
            log.info("Verifying shared folders exist in VirtualBox config before mounting")
            existing_folders = await context.vm.list_shared_folders(stop_event=context.user_interrupt_event, silent=True)
            log.debug(f"Found {len(existing_folders)} shared folders in VirtualBox config: {list(existing_folders.keys())}")

            folders = {
                name: paths['vm'] for name, paths in context.config.shared_directories.items()
            }

            # Check that all required folders exist
            missing_folders = [name for name in folders.keys() if name not in existing_folders]
            if missing_folders:
                raise LoggedException(
                    log,
                    f"Cannot mount shared folders - the following folders are not configured in VirtualBox: {missing_folders}. "
                    f"Expected folders: {list(folders.keys())}, Found: {list(existing_folders.keys())}"
                )

            log.info(f"All {len(folders)} required shared folders exist in VirtualBox, proceeding with mount")
            await context.vm.mount_multiple_shared_folders(
                folders=folders,
                stop_event=context.user_interrupt_event
            )

    async def retrieve_artifacts(self, context, post_interrupt: bool = False, force_stop: bool = False):
        """
        Retrieve artifacts and logs from VirtualBox VM.

        For VirtualBox, this is a no-op because artifacts and logs are already on
        the host via shared folders. The experiment run directory (including the
        logs subdirectory) is mounted as a shared folder, so all files written
        there are immediately accessible from the host.

        Args:
            context: ExperimentRunCtx
            post_interrupt: If True, we're in post-interrupt cleanup (ignored for VirtualBox)
            force_stop: Unused for VirtualBox (VM stop is handled separately)
        """
        # No-op: artifacts and logs already on host via shared folders
        log.debug("VirtualBox: Artifacts and logs already on host via shared folders, no retrieval needed")

    async def cleanup_vm(self, context, post_interrupt: bool = False):
        """
        Cleanup VirtualBox VM resources.

        Handles:
        - Port forwarding cleanup
        - Experiment snapshots (if requested)

        Args:
            context: ExperimentRunCtx
            post_interrupt: True if cleaning up after interrupt
        """
        # Clean up port forwarding before releasing VM instance
        if context.vm:
            event = None if post_interrupt else context.user_interrupt_event
            log.info('Cleaning up port forwarding rules before VM instance release')
            await context.vm.remove_port_forwarding(
                name='adarevm',
                stop_event=event,
                silent=True
            )
