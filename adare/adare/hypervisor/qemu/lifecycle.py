"""
QEMU-specific VM lifecycle strategy.

This module implements the QEMU lifecycle strategy using libguestfs for file
transfer. Files must be copied to the disk image before boot and retrieved
after shutdown, as QEMU doesn't support live shared folders like VirtualBox.
"""
from pathlib import Path
import logging
import asyncio
from typing import List, Dict

from adare.hypervisor.base.lifecycle import AbstractVMLifecycleStrategy
from adare.hypervisor.qemu import QEMUVM, QEMUManager
from adare.hypervisor.exceptions import HypervisorException
from adare.exceptions import LoggedException
from adare.config import get_vm_credentials

log = logging.getLogger(__name__)


class QEMULifecycleStrategy(AbstractVMLifecycleStrategy):
    """
    QEMU-specific lifecycle strategy using libguestfs.

    QEMU uses libguestfs to transfer files to/from the VM. This requires:
    1. VM must be stopped to mount disk with libguestfs
    2. Files are copied to disk before boot
    3. Artifacts are retrieved after shutdown
    """

    def __init__(self):
        self.qemu_manager = QEMUManager()

    def _copy_files_to_disk_via_libguestfs(
        self,
        disk_path: str,
        files_to_copy: List[Dict[str, str]],
        target_base_dir: str = "/adare"
    ) -> None:
        """
        Copy files to guest disk using libguestfs.

        Args:
            disk_path: Absolute path to VM disk image (qcow2)
            files_to_copy: List of dicts with 'source' (host path) and 'dest' (guest relative path)
            target_base_dir: Base directory in guest where files will be placed

        Raises:
            HypervisorException: If any operation fails
        """
        # Import check
        try:
            import guestfs
        except ImportError:
            raise HypervisorException(
                "libguestfs Python bindings not available. "
                "Install with: sudo apt install python3-guestfs (Ubuntu/Debian) "
                "or sudo dnf install python3-libguestfs (Fedora/RHEL)"
            )

        # Verify disk file exists
        if not Path(disk_path).exists():
            raise HypervisorException(
                f"VM disk not found at {disk_path}. "
                f"Ensure the VM has been created before transferring files."
            )

        log.info(f"Mounting guest disk {disk_path} via libguestfs for file transfer")

        g = None
        try:
            # Initialize libguestfs handle
            g = guestfs.GuestFS(python_return_dict=True)

            # Add disk with WRITE access (readonly=0)
            log.debug(f"Adding disk {disk_path} with write access")
            g.add_drive_opts(disk_path, readonly=0)

            # Launch guestfs appliance
            log.debug("Launching libguestfs appliance")
            g.launch()

            # Inspect OS and get root filesystem
            log.debug("Inspecting guest OS")
            roots = g.inspect_os()
            if not roots:
                raise HypervisorException(
                    f"No operating system found in VM disk {disk_path}. "
                    f"Ensure the VM has been properly installed."
                )

            root = roots[0]
            log.debug(f"Detected OS root: {root}")

            # Get and mount filesystems
            log.debug("Mounting guest filesystems")
            mps = g.inspect_get_mountpoints(root)

            # Sort by mountpoint length to mount / before /usr, /boot, etc.
            for mountpoint, device in sorted(mps.items(), key=lambda x: len(x[0])):
                try:
                    log.debug(f"Mounting {device} on {mountpoint}")
                    g.mount(device, mountpoint)  # Read-write mount
                except RuntimeError as e:
                    # Some filesystems may fail to mount (e.g., swap, EFI)
                    log.warning(f"Could not mount {device} on {mountpoint}: {e}")

            # Create base target directory if it doesn't exist
            log.debug(f"Creating base directory {target_base_dir}")
            try:
                g.mkdir_p(target_base_dir)
            except RuntimeError as e:
                raise HypervisorException(
                    f"Failed to create directory {target_base_dir} in guest: {e}"
                )

            # Copy each file/directory
            for file_spec in files_to_copy:
                source_path = Path(file_spec['source'])
                dest_relative = file_spec['dest']
                dest_full = f"{target_base_dir}/{dest_relative}"

                # Verify source exists on host
                if not source_path.exists():
                    raise HypervisorException(
                        f"Source file/directory not found: {source_path}"
                    )

                # Create parent directory in guest
                dest_parent = str(Path(dest_full).parent)
                try:
                    g.mkdir_p(dest_parent)
                except RuntimeError as e:
                    raise HypervisorException(
                        f"Failed to create parent directory {dest_parent} in guest: {e}"
                    )

                # Copy file or directory
                if source_path.is_file():
                    log.info(f"Copying file {source_path} -> {dest_full}")
                    try:
                        g.upload(str(source_path), dest_full)
                    except RuntimeError as e:
                        raise HypervisorException(
                            f"Failed to upload {source_path} to {dest_full}: {e}"
                        )

                elif source_path.is_dir():
                    log.info(f"Copying directory {source_path} -> {dest_full}")
                    try:
                        # Create destination directory first
                        g.mkdir_p(dest_full)

                        # Copy each item in the directory
                        for item in source_path.iterdir():
                            item_dest = f"{dest_full}/{item.name}"
                            if item.is_file():
                                g.upload(str(item), item_dest)
                            elif item.is_dir():
                                # For nested directories, use copy_in
                                g.copy_in(str(item), dest_full)
                    except RuntimeError as e:
                        raise HypervisorException(
                            f"Failed to copy directory {source_path} to {dest_full}: {e}"
                        )

            # Sync and unmount
            log.debug("Syncing filesystems")
            g.sync()

            log.debug("Unmounting filesystems")
            g.umount_all()

        except HypervisorException:
            # Re-raise our own exceptions
            raise
        except Exception as e:
            # Catch any unexpected errors and wrap them
            raise HypervisorException(
                f"Unexpected error during libguestfs file transfer: {e}"
            )
        finally:
            # Always close the handle
            if g is not None:
                try:
                    g.close()
                    log.debug("Closed libguestfs handle")
                except:
                    pass  # Ignore errors during cleanup

        log.info(f"Successfully copied {len(files_to_copy)} items to guest disk")

    def _copy_artifacts_from_disk_via_libguestfs(
        self,
        disk_path: str,
        source_path: str,
        destination_path: Path
    ) -> None:
        """
        Copy artifacts from guest disk using libguestfs.

        Args:
            disk_path: Absolute path to VM disk image (qcow2)
            source_path: Path in guest filesystem (e.g., "/adare/run/artifacts")
            destination_path: Path on host where artifacts should be copied

        Raises:
            HypervisorException: If critical operations fail
        """
        # Import check
        try:
            import guestfs
        except ImportError:
            raise HypervisorException(
                "libguestfs Python bindings not available. "
                "Install with: sudo apt install python3-guestfs (Ubuntu/Debian) "
                "or sudo dnf install python3-libguestfs (Fedora/RHEL)"
            )

        # Verify disk file exists
        if not Path(disk_path).exists():
            raise HypervisorException(
                f"VM disk not found at {disk_path}"
            )

        log.info(f"Mounting guest disk {disk_path} via libguestfs to retrieve artifacts")

        # Create destination directory on host
        try:
            destination_path.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise HypervisorException(
                f"Failed to create destination directory {destination_path}: {e}"
            )

        g = None
        try:
            # Initialize libguestfs handle
            g = guestfs.GuestFS(python_return_dict=True)

            # Add disk with READ-ONLY access (readonly=1)
            log.debug(f"Adding disk {disk_path} with read-only access")
            g.add_drive_opts(disk_path, readonly=1)

            # Launch guestfs appliance
            log.debug("Launching libguestfs appliance")
            g.launch()

            # Inspect OS and get root filesystem
            log.debug("Inspecting guest OS")
            roots = g.inspect_os()
            if not roots:
                raise HypervisorException(
                    f"No operating system found in VM disk {disk_path}"
                )

            root = roots[0]
            log.debug(f"Detected OS root: {root}")

            # Get and mount filesystems (read-only)
            log.debug("Mounting guest filesystems (read-only)")
            mps = g.inspect_get_mountpoints(root)

            # Sort by mountpoint length
            for mountpoint, device in sorted(mps.items(), key=lambda x: len(x[0])):
                try:
                    log.debug(f"Mounting {device} on {mountpoint} (read-only)")
                    g.mount_ro(device, mountpoint)  # Read-only mount
                except RuntimeError as e:
                    log.warning(f"Could not mount {device} on {mountpoint}: {e}")

            # Check if source path exists
            try:
                exists = g.exists(source_path)
            except RuntimeError as e:
                raise HypervisorException(
                    f"Failed to check if {source_path} exists: {e}"
                )

            if not exists:
                # This is not necessarily an error - experiments may not produce artifacts
                log.warning(
                    f"Artifact path {source_path} does not exist in guest. "
                    f"This may be normal if the experiment did not produce artifacts."
                )
                # Don't raise exception, just return early
                return

            # Check if it's a directory or file
            try:
                is_dir = g.is_dir(source_path)
            except RuntimeError as e:
                raise HypervisorException(
                    f"Failed to determine if {source_path} is a directory: {e}"
                )

            # Copy artifacts
            if is_dir:
                log.info(f"Copying artifact directory {source_path} -> {destination_path}")
                try:
                    # copy_out() copies directory contents to parent
                    # We want to copy the directory itself
                    # So we copy its contents to the destination
                    g.copy_out(source_path, str(destination_path.parent))

                    # copy_out will create source_path name in parent
                    # We may need to rename it
                    source_name = Path(source_path).name
                    copied_dir = destination_path.parent / source_name
                    if copied_dir != destination_path:
                        import shutil
                        shutil.move(str(copied_dir), str(destination_path))

                except RuntimeError as e:
                    raise HypervisorException(
                        f"Failed to copy artifacts from {source_path}: {e}"
                    )
            else:
                # Single file
                log.info(f"Copying artifact file {source_path} -> {destination_path}")
                try:
                    g.download(source_path, str(destination_path))
                except RuntimeError as e:
                    raise HypervisorException(
                        f"Failed to download artifact file {source_path}: {e}"
                    )

            # Unmount (read-only, no sync needed)
            log.debug("Unmounting filesystems")
            g.umount_all()

        except HypervisorException:
            raise
        except Exception as e:
            raise HypervisorException(
                f"Unexpected error during artifact retrieval: {e}"
            )
        finally:
            # Always close the handle
            if g is not None:
                try:
                    g.close()
                    log.debug("Closed libguestfs handle")
                except:
                    pass

        log.info(f"Successfully retrieved artifacts from {source_path}")

    async def prepare_vm_for_experiment(self, context):
        """
        Create QEMU VM instance and allocate resources.

        Args:
            context: ExperimentRunCtx with vm_name and guest_platform already set
        """
        # Create QEMU VM instance
        username, password = get_vm_credentials(context.guest_platform)
        context.vm = QEMUVM(
            vm_name=context.vm_name,
            guest_os=context.guest_platform,
            manager=self.qemu_manager,
            username=username,
            password=password,
            cpus=context.config.vm_cpus,
            ram=context.config.vm_memory
        )
        log.info(f"Created QEMU VM instance: {context.vm_name}")

    async def setup_file_transfer(self, context):
        """
        Use libguestfs to place files on stopped VM disk.

        This method:
        1. Ensures VM is stopped
        2. Uses libguestfs to mount the disk image
        3. Copies playbook, wheels, and other files to /adare/ directory
        4. Unmounts and closes libguestfs

        Args:
            context: ExperimentRunCtx containing directories and VM
        """
        # Ensure VM is stopped (required for libguestfs)
        vm_state = context.vm.get_state()
        if vm_state == "running":
            log.info("Stopping VM for libguestfs file transfer")
            await context.vm.stop()
        elif vm_state != "poweroff":
            raise HypervisorException(
                f"VM in unexpected state '{vm_state}'. Expected 'poweroff' or 'running'."
            )

        # Get disk path from VM configuration
        disk_path = context.vm.config.disk_path

        # Find wheel files
        wheels_dir = context.project_directory.vm_runtime / 'wheels'
        adarelib_wheels = list(wheels_dir.glob('adarelib-*.whl'))
        adarevm_wheels = list(wheels_dir.glob('adarevm-*.whl'))

        if not adarelib_wheels:
            raise HypervisorException(
                f"adarelib wheel not found in {wheels_dir}. Run 'adare experiment load' first."
            )
        if not adarevm_wheels:
            raise HypervisorException(
                f"adarevm wheel not found in {wheels_dir}. Run 'adare experiment load' first."
            )

        adarelib_wheel = adarelib_wheels[0]
        adarevm_wheel = adarevm_wheels[0]

        # Build file manifest
        files_to_copy = [
            {'source': str(context.experiment_directory.playbookfile), 'dest': 'playbook.yml'},
            {'source': str(adarevm_wheel), 'dest': f'wheels/{adarevm_wheel.name}'},
            {'source': str(adarelib_wheel), 'dest': f'wheels/{adarelib_wheel.name}'}
        ]

        log.info(f"Transferring {len(files_to_copy)} files to VM disk via libguestfs")

        # Copy files using libguestfs
        self._copy_files_to_disk_via_libguestfs(
            disk_path=disk_path,
            files_to_copy=files_to_copy,
            target_base_dir="/adare"
        )

        log.info("File transfer to VM completed successfully")

    async def start_and_initialize_vm(self, context):
        """
        Start QEMU VM (files already on disk from setup_file_transfer).

        Args:
            context: ExperimentRunCtx containing VM
        """
        # Start the VM
        await context.vm.start(stop_event=context.user_interrupt_event)

        # Wait until VM is fully booted and guest agent is ready
        log.info('Waiting until VM is ready (QEMU Guest Agent)')
        if not await context.vm.wait_until_fully_booted(timeout=360, stop_event=context.user_interrupt_event):
            raise LoggedException(log, 'VM did not become ready in time')
        log.info('VM is ready')

    async def retrieve_artifacts(self, context):
        """
        Stop VM and use libguestfs to retrieve artifacts.

        For QEMU, artifacts must be explicitly copied from the disk after
        the experiment completes, as there are no shared folders.

        Args:
            context: ExperimentRunCtx
        """
        # Stop VM first (required for libguestfs)
        log.info("Stopping VM to retrieve artifacts via libguestfs")
        await context.vm.stop()

        # Get disk path from VM configuration
        disk_path = context.vm.config.disk_path

        # Define artifact paths
        # Guest: /adare/run/artifacts
        # Host: <run_directory>/artifacts
        guest_artifact_path = "/adare/run/artifacts"
        host_artifact_path = context.experiment_run_directory.path / 'artifacts'

        log.info(f"Retrieving artifacts from {guest_artifact_path} to {host_artifact_path}")

        # Copy artifacts using libguestfs
        self._copy_artifacts_from_disk_via_libguestfs(
            disk_path=disk_path,
            source_path=guest_artifact_path,
            destination_path=host_artifact_path
        )

        log.info("Artifact retrieval completed successfully")

    async def cleanup_vm(self, context, post_interrupt: bool = False):
        """
        Cleanup QEMU VM resources.

        Args:
            context: ExperimentRunCtx
            post_interrupt: True if cleaning up after interrupt
        """
        # QEMU cleanup is simpler than VirtualBox - no shared folders or port forwarding to clean up
        log.debug("QEMU VM cleanup completed")
