"""
QGA file transfer strategy.

Uses QEMU Guest Agent guest-file-* operations to transfer files to/from
running QEMU guests. Used on macOS where virtiofsd and guestfish are
both unavailable.

Files are transferred after boot (QGA requires a running VM) and
artifacts are retrieved before VM shutdown.
"""
import asyncio
import logging
from pathlib import Path
from typing import Any

from adare.hypervisor.exceptions import HypervisorException
from adare.hypervisor.qemu.file_transfer.base import FileTransferStrategy

log = logging.getLogger(__name__)


class QGAStrategy(FileTransferStrategy):
    """File transfer via QEMU Guest Agent guest-file-* operations.

    QGA requires a running VM, so setup only builds the manifest and
    disables virtiofs config. Actual upload happens in post_boot_transfer().
    """

    async def setup(self, context: Any) -> None:
        """Prepare for deferred QGA file transfer.

        Disables virtiofs config and builds the file manifest. The actual
        file upload is deferred to post_boot_transfer() since QGA needs
        the VM to be running.

        Args:
            context: ExperimentRunCtx containing directories and VM
        """
        log.info("Using QGA mode for file transfer (deferred to after boot)")

        # Disable virtiofs (same as libguestfs mode)
        context.vm.config.virtiofs_enabled = False
        context.vm.config.virtiofs_shares = []
        context.vm._save_vm_config()
        log.info("Disabled virtiofs in VM config (QGA mode)")

        # Create run directory structure on host (for artifact retrieval later)
        run_dir = context.experiment_run_directory.path
        (run_dir / 'logs').mkdir(parents=True, exist_ok=True)
        (run_dir / 'artifacts').mkdir(parents=True, exist_ok=True)

        # Build manifest and store on context for post-boot transfer
        from adare.hypervisor.qemu.file_transfer.libguestfs_strategy import (
            _build_file_transfer_manifest,
        )

        context._qga_file_manifest = _build_file_transfer_manifest(context)
        log.info(
            f"Built QGA file transfer manifest: "
            f"{len(context._qga_file_manifest)} items "
            f"(will transfer after VM boot)"
        )

    async def post_boot_transfer(self, context: Any) -> None:
        """Upload files to running VM via QGA guest-file-* operations.

        Iterates over the manifest built in setup() and uploads each
        file/directory via QGAFileTransfer.

        Args:
            context: ExperimentRunCtx containing VM
        """
        from adare.hypervisor.qemu.qga_file_transfer import QGAFileTransfer
        from adare.types.stages import VMFileTransferSetupStage
        from adare.backend.experiment.stagectxmanager import StageCtxManager

        with StageCtxManager(
            VMFileTransferSetupStage(),
            context.experiment_run_ulid,
            context.user_interrupt_event,
        ):
            # Wait for guest OS to stabilize after boot — the boot readiness
            # check only verifies guest-exec works, but services/disk I/O may
            # still be settling, causing file operations to time out.
            stabilization_delay = 5
            log.info(
                f"Waiting {stabilization_delay}s for guest OS to stabilize "
                f"before QGA file transfer..."
            )
            await asyncio.sleep(stabilization_delay)

            is_windows = 'windows' in context.guest_platform.lower()
            transferor = QGAFileTransfer(context.vm)
            manifest = getattr(context, '_qga_file_manifest', [])
            base = 'C:\\adare' if is_windows else '/adare'

            log.info(f"Transferring {len(manifest)} items to VM via QGA")

            # Create base directories
            await transferor.mkdir_p(base)
            await transferor.mkdir_p(
                f"{base}\\run\\logs" if is_windows else f"{base}/run/logs"
            )
            await transferor.mkdir_p(
                f"{base}\\run\\artifacts" if is_windows
                else f"{base}/run/artifacts"
            )
            await transferor.mkdir_p(
                f"{base}\\vm" if is_windows else f"{base}/vm"
            )

            for item in manifest:
                source = Path(item['source'])
                dest_relative = item['dest']

                if is_windows:
                    guest_dest = (
                        f"{base}\\{dest_relative.replace('/', '\\')}"
                    )
                else:
                    guest_dest = f"{base}/{dest_relative}"

                if source.is_dir():
                    log.info(
                        f"Uploading directory {source.name} -> {guest_dest}"
                    )
                    await transferor.upload_directory(source, guest_dest)
                else:
                    if is_windows:
                        parent = '\\'.join(
                            guest_dest.replace('/', '\\').split('\\')[:-1]
                        )
                    else:
                        parent = str(Path(guest_dest).parent)
                    await transferor.mkdir_p(parent)
                    log.info(
                        f"Uploading file {source.name} -> {guest_dest}"
                    )
                    await transferor.upload_file(source, guest_dest)

            log.info("QGA file transfer completed")

    async def retrieve_artifacts(self, context: Any) -> None:
        """Retrieve artifacts and logs from running VM via QGA.

        Must be called BEFORE vm.stop() since QGA needs a running VM.

        Args:
            context: ExperimentRunCtx
        """
        from adare.hypervisor.qemu.qga_file_transfer import QGAFileTransfer

        log.info("Retrieving artifacts via QGA (before VM stop)")

        transferor = QGAFileTransfer(context.vm)
        is_windows = 'windows' in context.guest_platform.lower()
        base = 'C:\\adare' if is_windows else '/adare'
        sep = '\\' if is_windows else '/'

        retrieval_specs = [
            {
                'guest_path': f'{base}{sep}run{sep}artifacts',
                'host_path': context.experiment_run_directory.path / 'artifacts',
                'type': 'directory',
                'name': 'artifacts',
            },
            {
                'guest_path': f'{base}{sep}run{sep}logs{sep}adarevm.log',
                'host_path': context.experiment_run_directory.log_directory / 'adarevm.log',
                'type': 'file',
                'name': 'adarevm.log',
            },
            {
                'guest_path': f'{base}{sep}run{sep}logs{sep}adarevmstartup.log',
                'host_path': context.experiment_run_directory.log_directory / 'adarevmstartup.log',
                'type': 'file',
                'name': 'adarevmstartup.log',
            },
            {
                'guest_path': f'{base}{sep}run{sep}logs{sep}scheduled_task_error.log',
                'host_path': context.experiment_run_directory.log_directory / 'scheduled_task_error.log',
                'type': 'file',
                'name': 'scheduled_task_error.log',
            },
        ]

        retrieved = []
        missing = []

        for spec in retrieval_specs:
            guest_path = spec['guest_path']
            host_path = spec['host_path']
            name = spec['name']

            if not await transferor.file_exists(guest_path):
                missing.append(name)
                continue

            try:
                if spec['type'] == 'directory':
                    await transferor.download_directory(guest_path, host_path)
                else:
                    await transferor.download_file(guest_path, host_path)
                retrieved.append(name)
            except HypervisorException as e:
                log.warning(f"Failed to retrieve {name} via QGA: {e}")
                missing.append(name)

        if retrieved:
            log.info(f"Retrieved via QGA: {', '.join(retrieved)}")
        if missing:
            log.info(f"Not found in guest (skipped): {', '.join(missing)}")

    def requires_vm_stop_for_retrieval(self) -> bool:
        """QGA requires running VM -- do NOT stop before retrieval."""
        return False
