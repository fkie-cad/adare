"""
Libguestfs file transfer strategy.

Uses the guestfish CLI to transfer files to/from stopped QEMU VM disks.
Files are copied before boot and artifacts retrieved after shutdown.
This is the fallback mode when virtiofsd is unavailable on Linux,
or when explicitly requested via QEMU_LIBGUESTFS=true.
"""
import json as json_module
import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from adare.hypervisor.exceptions import HypervisorException
from adare.hypervisor.qemu.file_transfer.base import FileTransferStrategy
from adare.hypervisor.qemu.file_transfer.shares import build_config_json
from adare.hypervisor.qemu.guestfish_client import GuestfishClient

log = logging.getLogger(__name__)


class LibguestfsStrategy(FileTransferStrategy):
    """File transfer via guestfish CLI on stopped VM disks.

    Requires VM to be stopped for both upload and download operations.
    Uses the GuestfishClient for all disk interactions.
    """

    @property
    def setup_description(self) -> str:
        return "Copying files to disk via Libguestfs"

    @property
    def post_boot_description(self) -> str:
        return ""

    @property
    def retrieval_description(self) -> str:
        return "Extracting from disk via Libguestfs"

    @property
    def has_post_boot_transfer(self) -> bool:
        return False

    def __init__(self, guestfish_client: GuestfishClient | None = None):
        self.guestfish = guestfish_client or GuestfishClient()

    async def setup(self, context: Any) -> None:
        """Copy files to stopped VM disk via guestfish before boot.

        Ensures VM is stopped, validates disk integrity, builds a file
        manifest, and copies everything in a single guestfish session.

        Args:
            context: ExperimentRunCtx containing directories and VM
        """
        log.info("Using libguestfs mode for file transfer")

        # Ensure VM is stopped (required for libguestfs)
        vm_state = context.vm.get_state()
        if vm_state == "running":
            log.info("Stopping VM for libguestfs file transfer")
            await context.vm.stop()
        elif vm_state != "poweroff":
            raise HypervisorException(
                f"VM in unexpected state '{vm_state}'. "
                f"Expected 'poweroff' or 'running'."
            )

        # Disable virtiofs in config to prevent snapshot migration errors
        context.vm.config.virtiofs_enabled = False
        context.vm.config.virtiofs_shares = []
        context.vm._save_vm_config()
        log.info("Disabled virtiofs in VM config (required for snapshots)")

        disk_path = context.vm.config.disk_path

        if not Path(disk_path).exists():
            raise HypervisorException(
                f"Disk image not found: {disk_path}\n"
                "Ensure VM overlay was created successfully."
            )

        log.debug(f"Preparing to copy files to disk: {disk_path}")
        self._validate_overlay_chain(disk_path)

        files_to_copy = _build_file_transfer_manifest(context)

        # Write config.json for adarevm (tools/data path discovery)
        is_windows = 'windows' in context.guest_platform.lower()
        run_dir = context.experiment_run_directory.path
        config_data = build_config_json(
            is_windows=is_windows,
            installation_mode=context.config.installation_mode,
        )
        with open(run_dir / 'config.json', 'w') as f:
            json_module.dump(config_data, f, indent=2)
        log.debug(f"Wrote config.json to {run_dir / 'config.json'}")

        files_to_copy.append({
            'source': str(run_dir / 'config.json'),
            'dest': 'run/config.json',
        })

        log.info(f"Transferring {len(files_to_copy)} files to VM disk via libguestfs")

        self._copy_files_to_disk(
            disk_path=disk_path,
            files_to_copy=files_to_copy,
            target_base_dir="/adare",
        )
        log.info("File transfer to VM completed successfully")

    async def post_boot_transfer(self, context: Any) -> None:
        """No-op for libguestfs -- all files were placed before boot."""
        pass

    async def retrieve_artifacts(self, context: Any) -> None:
        """Retrieve artifacts and logs from stopped VM disk via guestfish.

        Builds a batch retrieval spec and executes it in a single guestfish
        session to minimise disk-mount overhead.

        Args:
            context: ExperimentRunCtx
        """
        disk_path = context.vm.config.disk_path

        log.info(f"Artifact retrieval - using disk path: {disk_path}")
        log.debug(f"Disk exists: {Path(disk_path).exists()}")

        self._log_disk_info(disk_path)

        if not Path(disk_path).exists():
            log.warning(
                f"Disk image not found at {disk_path}. "
                f"Skipping artifact retrieval - experiment may have failed very early."
            )
            return

        retrieval_specs = [
            {
                'guest_path': '/adare/run/artifacts',
                'host_path': context.experiment_run_directory.path / 'artifacts',
                'type': 'directory',
                'optional': True,
                'name': 'artifacts',
            },
            {
                'guest_path': '/adare/run/logs/adarevm.log',
                'host_path': context.experiment_run_directory.log_directory / 'adarevm.log',
                'type': 'file',
                'optional': True,
                'name': 'adarevm.log',
            },
            {
                'guest_path': '/adare/run/logs/adarevmstartup.log',
                'host_path': context.experiment_run_directory.log_directory / 'adarevmstartup.log',
                'type': 'file',
                'optional': True,
                'name': 'adarevmstartup.log',
            },
            {
                'guest_path': '/adare/run/logs/scheduled_task_error.log',
                'host_path': context.experiment_run_directory.log_directory / 'scheduled_task_error.log',
                'type': 'file',
                'optional': True,
                'name': 'scheduled_task_error.log',
            },
        ]

        log.info(
            "Retrieving artifacts and logs in single guestfish session "
            "(batched operation)"
        )

        results = self._batch_retrieve_files_from_disk(disk_path, retrieval_specs)

        if results['retrieved']:
            log.info(f"Successfully retrieved: {', '.join(results['retrieved'])}")
        if results['missing']:
            log.info(f"Not found in guest (skipped): {', '.join(results['missing'])}")

        log.info("Artifact and log retrieval completed")

    def requires_vm_stop_for_retrieval(self) -> bool:
        """Libguestfs requires VM to be stopped for disk access."""
        return True

    # ---------------------------------------------------------------
    # Private helpers
    # ---------------------------------------------------------------

    def _validate_overlay_chain(self, disk_path: str) -> None:
        """Validate overlay backing chain integrity.

        Detects overlay chaining (overlay backed by overlay) which would
        cause data from previous runs to accumulate.

        Args:
            disk_path: Path to overlay disk image

        Raises:
            HypervisorException: If overlay chain detected
        """
        try:
            result = subprocess.run(
                ['qemu-img', 'info', '--output=json', disk_path],
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode != 0:
                return

            disk_info = json_module.loads(result.stdout)

            if 'backing-filename' not in disk_info:
                log.debug("Standalone disk (no backing file)")
                return

            backing_file = disk_info['backing-filename']
            log.debug(
                f"Overlay disk detected with backing file: {backing_file}"
            )

            # Resolve relative paths
            disk_dir = Path(disk_path).parent
            backing_path = (
                Path(backing_file) if Path(backing_file).is_absolute()
                else disk_dir / backing_file
            )

            if not backing_path.exists():
                log.warning(
                    f"Backing file not found at expected location:\n"
                    f"  Backing file (from qcow2): {backing_file}\n"
                    f"  Resolved path: {backing_path}\n"
                    f"  This may cause libguestfs to fail."
                )
                return

            log.debug(f"Backing file verified: {backing_path}")

            # Reject overlay-backed-by-overlay
            if '-overlay-' in str(backing_file):
                raise HypervisorException(
                    f"OVERLAY CHAIN DETECTED - refusing to proceed.\n"
                    f"The overlay disk's backing file is itself an overlay:\n"
                    f"  Current overlay: {disk_path}\n"
                    f"  Backing file (also overlay!): {backing_file}\n\n"
                    f"This indicates a bug where overlay paths were persisted to config.\n"
                    f"Logs and data from previous runs would accumulate in this chain.\n\n"
                    f"To fix: Delete the orphaned overlay files and re-run.\n"
                    f"Overlay files are located in: {disk_dir}\n"
                    f"Pattern: *-overlay-*.qcow2"
                )

            # Check one level deeper
            backing_info_result = subprocess.run(
                ['qemu-img', 'info', '--output=json', str(backing_path)],
                capture_output=True,
                text=True,
                check=False,
            )
            if backing_info_result.returncode == 0:
                backing_info = json_module.loads(backing_info_result.stdout)
                if 'backing-filename' in backing_info:
                    nested = backing_info['backing-filename']
                    log.debug(f"Base disk has backing file: {nested}")

        except HypervisorException:
            raise
        except json_module.JSONDecodeError as e:
            log.warning(f"Failed to parse qemu-img output: {e}")
        except FileNotFoundError:
            log.warning("qemu-img not found - skipping disk validation")
        except subprocess.SubprocessError as e:
            log.warning(f"Failed to inspect disk image: {e}")

    def _log_disk_info(self, disk_path: str) -> None:
        """Log disk information for diagnostics."""
        try:
            result = subprocess.run(
                ['qemu-img', 'info', '--output=json', disk_path],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                disk_info = json_module.loads(result.stdout)
                if 'backing-filename' in disk_info:
                    log.info(
                        f"Disk is overlay, backing file: "
                        f"{disk_info['backing-filename']}"
                    )
                else:
                    log.info("Disk is standalone (no backing file)")
                log.debug(
                    f"Disk format: {disk_info.get('format', 'unknown')}"
                )
        except (json_module.JSONDecodeError, FileNotFoundError, subprocess.SubprocessError) as e:
            log.warning(f"Failed to inspect disk: {e}")

    def _copy_files_to_disk(
        self,
        disk_path: str,
        files_to_copy: list[dict[str, str]],
        target_base_dir: str = "/adare",
    ) -> None:
        """Copy files to guest disk using guestfish CLI.

        Args:
            disk_path: Absolute path to VM disk image (qcow2)
            files_to_copy: List of dicts with 'source' and 'dest' keys
            target_base_dir: Base directory in guest

        Raises:
            HypervisorException: If any operation fails
        """
        if not Path(disk_path).exists():
            raise HypervisorException(
                f"VM disk not found at {disk_path}. "
                f"Ensure the VM has been created before transferring files."
            )

        for file_spec in files_to_copy:
            source_path = Path(file_spec['source'])
            if not source_path.exists():
                raise HypervisorException(
                    f"Source file/directory not found: {source_path}"
                )

        log.info(
            f"Mounting guest disk {disk_path} via guestfish for file transfer"
        )

        commands: list[str] = []

        # Create base and runtime directories
        commands.extend(['mkdir-p', target_base_dir, ':'])
        commands.extend(['mkdir-p', f'{target_base_dir}/run/logs', ':'])
        commands.extend(['mkdir-p', f'{target_base_dir}/run/artifacts', ':'])
        commands.extend(['mkdir-p', f'{target_base_dir}/vm', ':'])

        # Collect parent directories
        parent_dirs: set[str] = set()

        def resolve_guest_dest(dest: str) -> str:
            if re.match(r'^[a-zA-Z]:[\\/]', dest):
                return dest[2:].replace('\\', '/')
            if dest.startswith('/'):
                return dest
            return f"{target_base_dir}/{dest}"

        for file_spec in files_to_copy:
            dest_full = resolve_guest_dest(file_spec['dest'])
            parent = str(Path(dest_full).parent)
            parent_dirs.add(parent)

        for parent_dir in sorted(parent_dirs, key=lambda p: len(p.split('/'))):
            if parent_dir != target_base_dir:
                commands.extend(['mkdir-p', parent_dir, ':'])

        for file_spec in files_to_copy:
            source_path = file_spec['source']
            dest_full = resolve_guest_dest(file_spec['dest'])
            dest_parent = str(Path(dest_full).parent)

            log.info(f"Copying {source_path} -> {dest_full}")
            commands.extend(['copy-in', source_path, dest_parent, ':'])

        # Remove trailing colon
        if commands and commands[-1] == ':':
            commands = commands[:-1]

        returncode, stdout, stderr = self.guestfish.run_command(
            disk_path, commands, readonly=False,
        )

        if returncode != 0:
            raise HypervisorException(
                f"Failed to copy files to guest disk.\n"
                f"Guestfish error: {stderr}\n"
                f"Disk: {disk_path}\n\n"
                f"Troubleshooting:\n"
                f"  1. For Windows VMs: Disable Fast Startup in "
                f"Control Panel > Power Options\n"
                f"  2. Ensure VM was shut down cleanly "
                f"(not hibernated or forced off)\n"
                f"  3. Run with verbose logging: "
                f"export LIBGUESTFS_DEBUG=1 LIBGUESTFS_TRACE=1\n"
                f"  4. Test filesystem detection: "
                f"guestfish --ro --format=qcow2 -a {disk_path} "
                f": run : list-filesystems\n"
                f"  5. Mount manually: guestfish --rw --format=qcow2 "
                f"-a {disk_path} : run : mount /dev/sdaX /\n"
                f"  6. Check backing file: qemu-img info {disk_path}\n"
                f"  7. Verify libguestfs: libguestfs-test-tool"
            )

        log.info(f"Successfully copied {len(files_to_copy)} items to guest disk")

    def _batch_retrieve_files_from_disk(
        self,
        disk_path: str,
        retrieval_specs: list[dict[str, Any]],
    ) -> dict[str, list[str]]:
        """Retrieve multiple files/directories in a single guestfish session.

        Args:
            disk_path: Path to guest disk image (qcow2)
            retrieval_specs: List of retrieval specifications

        Returns:
            Dict with 'retrieved' and 'missing' lists

        Raises:
            HypervisorException: If disk not found or mount fails
        """
        if not Path(disk_path).exists():
            raise HypervisorException(f"VM disk not found at {disk_path}")

        log.info(
            f"Starting batched retrieval of {len(retrieval_specs)} "
            f"paths via single guestfish session"
        )

        # Create host destination directories
        for spec in retrieval_specs:
            try:
                spec['host_path'].parent.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                log.warning(
                    f"Failed to create directory {spec['host_path'].parent}: {e}"
                )

        # Detect root filesystem once
        try:
            root_device, _ = self.guestfish.detect_root_filesystem(disk_path)
            log.debug(
                f"Using root filesystem for batch retrieval: "
                f"{root_device}"
            )
        except HypervisorException:
            log.error("Failed to detect root filesystem")
            raise

        # Build script
        script_content = self._generate_retrieval_script(
            root_device, retrieval_specs,
        )

        if not script_content:
            log.warning("No retrieval specs provided or script generation failed")
            return {'retrieved': [], 'missing': []}

        log.debug(f"Guestfish script:\n{script_content}")

        script_fd = None
        script_path = None
        try:
            script_fd, script_path = tempfile.mkstemp(
                suffix='.guestfish', text=True,
            )
            with os.fdopen(script_fd, 'w') as f:
                f.write(script_content)
                script_fd = None

            log.debug(f"Wrote guestfish script to {script_path}")

            cmd = [
                'guestfish', '--ro', '--format=qcow2',
                '-a', disk_path, '-f', script_path,
            ]

            log.debug(f"Executing: {' '.join(cmd)}")

            result = subprocess.run(
                cmd, capture_output=True, text=True, check=False,
            )

            if result.returncode != 0:
                if (
                    'could not' in result.stderr.lower()
                    or 'cannot' in result.stderr.lower()
                ):
                    log.error(
                        f"Guestfish failed to mount disk: {result.stderr}\n"
                        f"This may indicate a corrupted overlay backing chain."
                    )
                    raise HypervisorException(
                        f"Failed to mount guest disk via guestfish: "
                        f"{result.stderr}"
                    )
                log.debug(
                    f"Guestfish completed with returncode "
                    f"{result.returncode}: {result.stderr}"
                )

            # Analyse which files were actually created
            results: dict[str, list[str]] = {'retrieved': [], 'missing': []}

            for spec in retrieval_specs:
                host_path = spec['host_path']
                name = spec['name']
                optional = spec['optional']

                if spec['type'] == 'directory':
                    quirky_path = (
                        host_path.parent / Path(spec['guest_path']).name
                    )
                    if quirky_path.exists():
                        if quirky_path != host_path:
                            if host_path.exists():
                                shutil.rmtree(host_path)
                            shutil.move(str(quirky_path), str(host_path))
                        results['retrieved'].append(name)
                    elif host_path.exists():
                        results['retrieved'].append(name)
                    else:
                        results['missing'].append(name)
                        if optional:
                            log.info(
                                f"Optional path {name} not found in guest "
                                f"(normal if experiment didn't produce it)"
                            )
                        else:
                            log.warning(
                                f"Required path {name} not found in guest: "
                                f"{spec['guest_path']}"
                            )
                else:
                    if host_path.exists():
                        results['retrieved'].append(name)
                    else:
                        results['missing'].append(name)
                        if optional:
                            log.debug(
                                f"Optional file {name} not found in guest"
                            )
                        else:
                            log.warning(
                                f"Required file {name} not found in guest: "
                                f"{spec['guest_path']}"
                            )

            return results

        finally:
            if script_fd is not None:
                try:
                    os.close(script_fd)
                except OSError:
                    pass
            if script_path and Path(script_path).exists():
                try:
                    Path(script_path).unlink()
                except OSError as e:
                    log.warning(
                        f"Failed to clean up temp script {script_path}: {e}"
                    )

    def _generate_retrieval_script(
        self,
        root_device: str,
        retrieval_specs: list[dict[str, Any]],
    ) -> str:
        """Generate guestfish script for batched file retrieval.

        Args:
            root_device: Root filesystem device (e.g. /dev/sda4)
            retrieval_specs: List of retrieval specifications

        Returns:
            Guestfish script content as string (empty if nothing to do)
        """
        script_lines = [
            'run',
            f'mount {root_device} /',
        ]

        for spec in retrieval_specs:
            guest_path = spec['guest_path']
            host_path = spec['host_path']
            file_type = spec['type']
            prefix = '-'  # optional marker to continue on error

            if file_type == 'file':
                script_lines.append(f"{prefix}download {guest_path} {host_path}")
            elif file_type == 'directory':
                script_lines.append(
                    f"{prefix}copy-out {guest_path} {host_path.parent}"
                )

        if len(script_lines) <= 2:  # Only run and mount
            return ""

        return '\n'.join(script_lines)


def _build_file_transfer_manifest(context: Any) -> list[dict[str, str]]:
    """Build list of {source, dest} dicts for file transfer.

    Used by both libguestfs and QGA strategies to determine which files
    need to be transferred to the guest VM.

    Args:
        context: ExperimentRunCtx containing directories and VM

    Returns:
        List of dicts with 'source' (host path) and 'dest' (guest relative path)
    """
    wheels_dir = context.project_directory.vm_runtime / 'wheels'
    adarelib_wheels = list(wheels_dir.glob('adarelib-*.whl'))
    adarevm_wheels = list(wheels_dir.glob('adarevm-*.whl'))
    wheels_available = bool(adarelib_wheels and adarevm_wheels)

    files_to_copy: list[dict[str, str]] = []

    if context.experiment_directory:
        files_to_copy.append({
            'source': str(context.experiment_directory.playbookfile),
            'dest': 'playbook.yml',
        })

    if wheels_available:
        log.info("Using wheel installation mode for QEMU - copying wheels")
        adarelib_wheel = adarelib_wheels[0]
        adarevm_wheel = adarevm_wheels[0]
        files_to_copy.extend([
            {
                'source': str(adarevm_wheel),
                'dest': f'vm/wheels/{adarevm_wheel.name}',
            },
            {
                'source': str(adarelib_wheel),
                'dest': f'vm/wheels/{adarelib_wheel.name}',
            },
        ])
    else:
        log.info(
            "Using editable installation mode for QEMU (no wheels found)"
        )
        adarelib_src = context.project_directory.vm_runtime / 'adarelib'
        adarevm_src = context.project_directory.vm_runtime / 'adarevm'

        if not adarelib_src.exists():
            raise HypervisorException(
                f"adarelib source not found at {adarelib_src}. "
                f"Run 'adare experiment load' first."
            )
        if not adarevm_src.exists():
            raise HypervisorException(
                f"adarevm source not found at {adarevm_src}. "
                f"Run 'adare experiment load' first."
            )

        files_to_copy.extend([
            {'source': str(adarevm_src), 'dest': 'vm/adarevm'},
            {'source': str(adarelib_src), 'dest': 'vm/adarelib'},
        ])

    # Project-level shared directory
    if context.project_directory.shared.exists():
        log.info(
            f"Adding shared project directory to transfer: "
            f"{context.project_directory.shared}"
        )
        files_to_copy.append({
            'source': str(context.project_directory.shared),
            'dest': 'project_shared',
        })

    # Experiment-level shared directory
    if (
        context.experiment_directory
        and context.experiment_directory.shared.exists()
    ):
        log.info(
            f"Adding shared experiment directory to transfer: "
            f"{context.experiment_directory.shared}"
        )
        files_to_copy.append({
            'source': str(context.experiment_directory.shared),
            'dest': 'shared',
        })

    # User-defined shared directories (fallback copy)
    if (
        hasattr(context.config, 'shared_directories')
        and context.config.shared_directories
    ):
        for name, details in context.config.shared_directories.items():
            host_path = details.get('host')
            vm_path = details.get('vm')
            if host_path and vm_path:
                files_to_copy.append({
                    'source': str(host_path),
                    'dest': str(vm_path),
                })

    return files_to_copy
