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
from pathlib import Path
from typing import Any, Dict, List

from adare.hypervisor.exceptions import HypervisorException
from adare.hypervisor.qemu.file_transfer.base import FileTransferStrategy

log = logging.getLogger(__name__)


class VirtioFSStrategy(FileTransferStrategy):
    """File transfer via virtio-fs shared directories.

    This is the default (and fastest) file transfer mode. Files are shared
    directly between host and guest via virtio-fs filesystem devices, so
    no copying is needed -- the guest reads/writes the host directories.
    """

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
        config_data = _build_config_json(
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
        from adare.types.stages import VMMountVirtioFSStage
        from adare.backend.experiment.stagectxmanager import StageCtxManager

        is_windows = 'windows' in context.guest_platform.lower()

        with StageCtxManager(
            VMMountVirtioFSStage(),
            context.experiment_run_ulid,
            context.user_interrupt_event,
        ):
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
    ) -> List[Dict[str, Any]]:
        """Build the list of virtio-fs share specifications.

        Args:
            context: ExperimentRunCtx
            is_windows: True for Windows guests
            base_mount: Base mount path in guest (e.g. /adare or C:\\adare)

        Returns:
            List of share dicts with tag, host_path, guest_mount, readonly keys
        """
        virtiofs_shares: List[Dict[str, Any]] = []

        # 1. Run directory -- experiment run artifacts and logs
        run_dir = context.experiment_run_directory.path
        (run_dir / 'logs').mkdir(parents=True, exist_ok=True)
        (run_dir / 'artifacts').mkdir(parents=True, exist_ok=True)

        # Copy playbook.yml to run directory for easy guest access
        if context.experiment_directory:
            shutil.copy2(
                context.experiment_directory.playbookfile,
                run_dir / 'playbook.yml',
            )
            log.debug(f"Copied playbook to {run_dir / 'playbook.yml'}")

        virtiofs_shares.append({
            'tag': 'run',
            'host_path': str(run_dir),
            'guest_mount': f'{base_mount}\\run' if is_windows else f'{base_mount}/run',
            'readonly': False,
        })

        # 2. VM runtime -- adarevm/adarelib wheels or source
        vm_runtime_dir = context.project_directory.vm_runtime
        if not vm_runtime_dir.exists():
            raise HypervisorException(
                f"VM runtime directory not found at {vm_runtime_dir}. "
                f"Run 'adare experiment load' first."
            )
        virtiofs_shares.append({
            'tag': 'vm',
            'host_path': str(vm_runtime_dir),
            'guest_mount': f'{base_mount}\\vm' if is_windows else f'{base_mount}/vm',
            'readonly': True,
        })

        # 3. Experiment directory (optional)
        if context.experiment_directory:
            experiment_dir = context.experiment_directory.path
            virtiofs_shares.append({
                'tag': 'experiment',
                'host_path': str(experiment_dir),
                'guest_mount': (
                    f'{base_mount}\\experiment' if is_windows
                    else f'{base_mount}/experiment'
                ),
                'readonly': True,
            })

        # 4. Project shared directory (optional)
        if context.project_directory.shared.exists():
            virtiofs_shares.append({
                'tag': 'project_shared',
                'host_path': str(context.project_directory.shared),
                'guest_mount': (
                    f'{base_mount}\\project_shared' if is_windows
                    else f'{base_mount}/project_shared'
                ),
                'readonly': True,
            })

        # 5. Experiment shared directory (optional)
        if (
            context.experiment_directory
            and context.experiment_directory.shared.exists()
        ):
            virtiofs_shares.append({
                'tag': 'shared',
                'host_path': str(context.experiment_directory.shared),
                'guest_mount': (
                    f'{base_mount}\\shared' if is_windows
                    else f'{base_mount}/shared'
                ),
                'readonly': True,
            })

        # 6. User-defined shared directories
        if (
            hasattr(context.config, 'shared_directories')
            and context.config.shared_directories
        ):
            log.info(
                f"Configuring {len(context.config.shared_directories)} "
                f"user-defined shared directories"
            )
            for name, details in context.config.shared_directories.items():
                host_path = details.get('host')
                vm_path = details.get('vm')
                if host_path and vm_path:
                    virtiofs_shares.append({
                        'tag': name,
                        'host_path': str(host_path),
                        'guest_mount': str(vm_path),
                        'readonly': False,
                    })

        return virtiofs_shares

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


def _build_config_json(
    is_windows: bool,
    installation_mode: str = "wheel",
) -> Dict[str, Any]:
    """Build config.json content for adarevm with mount paths.

    Args:
        is_windows: True if guest is Windows
        installation_mode: "wheel" (pip) or "editable" (Poetry)

    Returns:
        Dictionary with config.json contents
    """
    if is_windows:
        return {
            "tools_paths": [
                "C:\\adare\\project_shared\\tools",
                "C:\\adare\\shared\\tools",
            ],
            "data_paths": [
                "C:\\adare\\project_shared\\data",
                "C:\\adare\\shared\\data",
            ],
            "logfile": "C:\\adare\\run\\logs\\adarevm.log",
            "installation_mode": installation_mode,
        }
    return {
        "tools_paths": [
            "/adare/project_shared/tools",
            "/adare/shared/tools",
        ],
        "data_paths": [
            "/adare/project_shared/data",
            "/adare/shared/data",
        ],
        "logfile": "/adare/run/logs/adarevm.log",
        "installation_mode": installation_mode,
    }
