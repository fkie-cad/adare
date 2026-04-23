"""
VirtioFS file transfer strategy.

Uses virtio-fs shared directories for high-performance file sharing between
host and QEMU guest. Multiple shares are configured (run, vm, experiment, etc.)
and mounted inside the guest after boot.

Linux guests mount via `mount -t virtiofs {tag} /adare/{name}`.
Windows guests mount via `virtiofs.exe -t {tag} -m C:\\adare\\{name}`.
"""
import json
import logging
import shutil
from typing import Any

from adare.hypervisor.exceptions import HypervisorException
from adare.hypervisor.qemu.file_transfer.base import FileTransferStrategy
from adare.hypervisor.qemu.file_transfer.shares import build_config_json, build_share_list

log = logging.getLogger(__name__)


class VirtioFSStrategy(FileTransferStrategy):
    """File transfer via virtio-fs shared directories.

    This is the default (and fastest) file transfer mode. Files are shared
    directly between host and guest via virtio-fs filesystem devices, so
    no copying is needed -- the guest reads/writes the host directories.
    """

    @property
    def setup_description(self) -> str:
        return "Configuring VirtioFS shares"

    @property
    def post_boot_description(self) -> str:
        return "Mounting VirtioFS shares"

    @property
    def retrieval_description(self) -> str:
        return "Verifying VirtioFS shared files"

    async def setup(self, context: Any) -> None:
        """Create shared directories on host and configure VM for virtio-fs.

        Sets up multiple virtio-fs shares matching the VirtualBox shared folder
        pattern. Each share maps a host directory to a guest mount point.

        Args:
            context: ExperimentRunCtx containing directories and VM
        """
        log.info("Using virtio-fs mode for file transfer (multiple shares)")
        is_windows = 'windows' in context.guest_platform.lower()
        base_mount = 'C:\\adare' if is_windows else '/adare'

        log.info("Setting up multiple virtio-fs shared directories")

        virtiofs_shares = self._build_share_list(context, is_windows, base_mount)

        # Write config.json to run directory
        run_dir = context.experiment_run_directory.path
        config_data = build_config_json(
            is_windows=is_windows,
            installation_mode=context.config.installation_mode,
        )
        with open(run_dir / 'config.json', 'w') as f:
            json.dump(config_data, f, indent=2)
        log.debug(f"Wrote config.json to {run_dir / 'config.json'}")

        # Store shares in VM config for libvirt XML generation
        context.vm.config.virtiofs_enabled = True
        context.vm.config.virtiofs_shares = virtiofs_shares
        context.vm._save_vm_config()

        # Store in context for later use (mounting, artifact retrieval)
        context.virtiofs_shares = virtiofs_shares

        log.info(f"Configured {len(virtiofs_shares)} virtio-fs shares:")
        for share in virtiofs_shares:
            log.debug(f"  {share['tag']}: {share['host_path']} -> {share['guest_mount']}")

    async def post_boot_transfer(self, context: Any) -> None:
        """Mount virtio-fs shares inside the guest after boot.

        Linux: uses kernel virtiofs driver.
        Windows: uses virtiofs.exe from WinFsp.

        Args:
            context: ExperimentRunCtx containing VM
        """
        is_windows = 'windows' in context.guest_platform.lower()

        if is_windows:
            log.info("Mounting virtio-fs shares on Windows guest using virtiofs.exe")
            await self._mount_virtiofs_windows(context)
        else:
            await self._mount_virtiofs_linux(context)

    async def retrieve_artifacts(self, context: Any) -> None:
        """Verify artifacts are accessible from virtio-fs shared directories.

        With multi-share virtio-fs, the 'run' share points directly to
        context.experiment_run_directory.path, so artifacts are already
        in the correct location. This method verifies and logs what was found.

        Args:
            context: ExperimentRunCtx
        """
        log.info("Retrieving artifacts from virtio-fs shared directory")

        run_dir = context.experiment_run_directory.path
        retrieved = []
        missing = []

        # Check artifacts directory
        artifacts_dir = run_dir / 'artifacts'
        if artifacts_dir.exists() and any(artifacts_dir.iterdir()):
            artifact_count = len(list(artifacts_dir.iterdir()))
            retrieved.append(f'artifacts ({artifact_count} items)')
            log.debug(f"Found artifacts at {artifacts_dir}")
        else:
            missing.append('artifacts')

        # Check log files
        logs_dir = run_dir / 'logs'
        log_files = ['adarevm.log', 'adarevmstartup.log', 'scheduled_task_error.log']

        for log_file in log_files:
            log_path = logs_dir / log_file
            if log_path.exists():
                # Copy to log_directory if different from logs subdirectory
                log_dest = context.experiment_run_directory.log_directory
                if log_dest != logs_dir:
                    shutil.copy2(log_path, log_dest / log_file)
                    log.debug(f"Copied {log_file} to {log_dest}")
                retrieved.append(log_file)
            else:
                missing.append(log_file)

        if retrieved:
            log.info(f"Found in virtio-fs run share: {', '.join(retrieved)}")
        if missing:
            log.debug(f"Not found in virtio-fs run share (skipped): {', '.join(missing)}")

    def requires_vm_stop_for_retrieval(self) -> bool:
        """VirtioFS does not require VM stop -- artifacts are on host already."""
        return False

    # ---------------------------------------------------------------
    # Private helpers
    # ---------------------------------------------------------------

    def _build_share_list(
        self,
        context: Any,
        is_windows: bool,
        base_mount: str,
    ) -> list[dict[str, Any]]:
        """Build the list of virtio-fs share specifications.

        Delegates to the shared build_share_list() utility.
        """
        return build_share_list(context, is_windows, base_mount)

    async def _mount_virtiofs_linux(self, context: Any) -> None:
        """Mount multiple virtio-fs filesystems on Linux guest.

        Args:
            context: ExperimentRunCtx containing VM
        """
        shares = (
            getattr(context, 'virtiofs_shares', None)
            or context.vm.config.virtiofs_shares
        )
        if not shares:
            log.warning("No virtiofs shares configured, skipping mount")
            return

        log.info(f"Mounting {len(shares)} virtio-fs filesystems on Linux guest")

        # Create parent directory
        await context.vm.run_command(
            'sudo mkdir -p /adare && sudo chmod 755 /adare',
            stop_event=context.user_interrupt_event,
        )

        # Mount each share
        for share in shares:
            tag = share['tag']
            mount_point = share['guest_mount']

            mount_cmd = (
                f'sudo mkdir -p {mount_point} && '
                f'sudo mount -t virtiofs {tag} {mount_point} && '
                f'sudo chmod 777 {mount_point}'
            )

            result = await context.vm.run_command(
                mount_cmd,
                stop_event=context.user_interrupt_event,
            )

            if result.returncode != 0:
                log.warning(f"Failed to mount virtiofs '{tag}': {result.stderr}")
            else:
                log.debug(f"Mounted virtiofs '{tag}' to {mount_point}")

        # Verify mounts
        verify_result = await context.vm.run_command(
            'mount | grep virtiofs',
            stop_event=context.user_interrupt_event,
        )

        mounted_count = verify_result.stdout.count('virtiofs')
        if mounted_count >= len(shares):
            log.info(f"All {len(shares)} virtio-fs shares mounted successfully")
        else:
            log.warning(
                f"Only {mounted_count} of {len(shares)} virtio-fs shares mounted"
            )

    async def _mount_virtiofs_windows(self, context: Any) -> None:
        """Mount multiple virtio-fs shares on Windows guest using virtiofs.exe.

        Uses the QEMU Guest Agent to run virtiofs.exe in background for each
        share. The viofs service auto-mount is bypassed in favour of explicit
        per-share mounts to specific directories.

        Args:
            context: ExperimentRunCtx containing VM
        """
        shares = (
            getattr(context, 'virtiofs_shares', None)
            or context.vm.config.virtiofs_shares
        )
        if not shares:
            log.warning("No virtiofs shares configured, skipping Windows mount")
            return

        # Create base directory
        await context.vm.run_command(
            'New-Item -ItemType Directory -Path "C:\\adare" -Force | Out-Null',
            stop_event=context.user_interrupt_event,
        )

        for share in shares:
            tag = share['tag']
            mount_point = str(share['guest_mount']).replace('/', '\\')

            virtiofs_exe = r"C:\Program Files\VirtIO-Win\VioFS\virtiofs.exe"
            mount_cmd = f'"{virtiofs_exe}" -t {tag} -m {mount_point}'

            log.debug(
                f"Mounting virtio-fs share '{tag}' using run_as_user strategy"
            )

            result = await context.vm.run_command(
                mount_cmd,
                background=True,
                stop_event=context.user_interrupt_event,
                binary_is_filepath=True,
            )

            if result.returncode != 0:
                raise HypervisorException(
                    f"Failed to mount virtio-fs share '{tag}': {result.stderr}"
                )
            log.debug(f"Mounted virtio-fs share '{tag}' -> {mount_point}")
