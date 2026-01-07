"""
QEMU VM - Main VM class with modular operations.

Implements AbstractVM for QEMU-specific VM management using:
- Direct QEMU command-line execution
- libguestfs for file operations when VM is stopped
- QEMU Guest Agent for runtime command execution
- qcow2 internal snapshots
"""
import asyncio
import json
import logging
import os
import platform
import re
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

from adarelib.constants import StatusEnum

from adare.hypervisor.base.vm import AbstractVM
from adare.hypervisor.exceptions import (
    VMImportException,
    VMAlreadyRunningException,
    VMNotFoundException,
    HypervisorException,
    VMStartException
)
from adare.hypervisor.qemu.manager import QEMUManager
from adare.hypervisor.qemu.mixins.commands import CommandExecutionMixin
from adare.hypervisor.qemu.mixins.snapshots import SnapshotMixin
from adare.hypervisor.qemu.mixins.networking import NetworkingMixin
from adare.hypervisor.qemu.models import QEMUVMConfig, CommandResult
from adare.hypervisor.qemu.libvirt_stderr_redirect import (
    LibvirtStderrRedirect,
    get_experiment_log_file
)

log = logging.getLogger(__name__)


class QEMUVM(CommandExecutionMixin, SnapshotMixin, NetworkingMixin, AbstractVM):
    """
    QEMU VM management class with modular operations.
    Inherits from mixins for command execution, snapshots, and networking.
    """

    def __init__(
        self,
        vm_name: str,
        guest_os: str,
        manager: 'QEMUManager',
        username: str,
        password: str,
        executables: 'ExecutableManager',
        cpus: int = 2,
        ram: int = 2048,
        machine: str = 'pc',
        accel: str = 'kvm',
        drive_format: str = 'qcow2',
        disk_path: Optional[str] = None
    ):
        self.vm_name = vm_name
        self.guest_os = guest_os
        self.username = username
        self.password = password
        self.cpus = cpus
        self.ram = ram
        self.machine = machine
        self.accel = accel
        self.drive_format = drive_format
        self.host_os = platform.system().lower()
        self.manager = manager
        self.executables = executables  # Store executable manager
        self._background_pids = []
        self._command_queue = []
        self._qemu_process = None  # Running QEMU process
        self._external_disk_path = disk_path  # Optional external disk path for --no-copy mode

        # libvirt integration
        self._libvirt_conn = None  # Lazy initialization - will use manager's connection
        self._libvirt_domain = None  # libvirt domain object

        # PATH discovery cache
        self._cached_guest_path = None  # Cached PATH from guest discovery
        self._path_discovery_attempted = False  # Track if we've tried discovery to prevent retries

        # Screen resolution tracking for coordinate normalization (USB tablet uses 0-32767 range)
        self._screen_width = None   # Current screen width in pixels
        self._screen_height = None  # Current screen height in pixels
        self._resolution_last_updated = None  # Timestamp of last resolution update

        # Load or create VM config
        self.config = self._load_or_create_vm_config()

        log.debug(f"CLAUDE: Initialized QEMUVM for '{self.vm_name}' ({self.guest_os})")

    @staticmethod
    def _detect_disk_format_static(file_path: Path, qemu_img_exe: str = 'qemu-img') -> str:
        """
        Detect disk image format using qemu-img info (static version).

        Args:
            file_path: Path to disk image file
            qemu_img_exe: Path to qemu-img executable

        Returns:
            Format string (e.g., 'qcow2', 'vmdk', 'vdi', 'raw', 'vpc')
            Returns 'ova' for OVA files (special marker indicating extraction needed)

        Raises:
            HypervisorException: If format detection fails
        """
        # For OVA files, need to extract first to detect disk format
        if str(file_path).endswith('.ova'):
            log.debug(f"CLAUDE: OVA file detected, will need extraction: {file_path}")
            return 'ova'

        # Use qemu-img info with JSON output
        args = [qemu_img_exe, 'info', '--output=json', str(file_path)]

        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                check=False
            )

            if result.returncode != 0:
                raise HypervisorException(
                    f"Failed to detect disk format for {file_path}: {result.stderr}"
                )

            info = json.loads(result.stdout)
            disk_format = info.get('format', 'unknown')

            log.debug(f"CLAUDE: Detected disk format: {disk_format} for {file_path}")
            return disk_format

        except json.JSONDecodeError as e:
            raise HypervisorException(
                f"Failed to parse qemu-img info output: {e}"
            )
        except FileNotFoundError:
            raise HypervisorException(
                f"qemu-img executable not found. Please install QEMU tools."
            )
        except Exception as e:
            raise HypervisorException(
                f"Error detecting disk format: {e}"
            )

    def _detect_disk_format(self, file_path: Path) -> str:
        """
        Detect disk image format using qemu-img info (instance method wrapper).

        Args:
            file_path: Path to disk image file

        Returns:
            Format string (e.g., 'qcow2', 'vmdk', 'vdi', 'raw', 'vpc')
            Returns 'ova' for OVA files (special marker indicating extraction needed)

        Raises:
            HypervisorException: If format detection fails
        """
        return self._detect_disk_format_static(file_path, self.executables.qemu_img)

    def _get_vm_config_path(self) -> Path:
        """Get path to VM configuration JSON file."""
        # Store VM configs in ~/.adare/qemu/vms/
        config_dir = Path.home() / '.adare' / 'qemu' / 'vms'
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / f"{self.vm_name}.json"

    def _load_or_create_vm_config(self) -> QEMUVMConfig:
        """Load VM config from JSON or create new one."""
        config_path = self._get_vm_config_path()

        if config_path.exists():
            log.debug(f"CLAUDE: Loading VM config from {config_path}")
            with open(config_path, 'r') as f:
                data = json.load(f)
            return QEMUVMConfig.from_dict(data)
        else:
            log.debug(f"CLAUDE: Creating new VM config for '{self.vm_name}'")
            # Create new config
            vm_uuid = str(uuid.uuid4())

            # Determine disk path: use external path if provided, otherwise use managed storage
            if self._external_disk_path:
                disk_path = self._external_disk_path
                log.debug(f"CLAUDE: Using external disk path for --no-copy mode: {disk_path}")
            else:
                disk_dir = Path.home() / '.adare' / 'qemu' / 'disks'
                disk_dir.mkdir(parents=True, exist_ok=True)
                disk_path = str(disk_dir / f"{self.vm_name}.qcow2")
                log.debug(f"CLAUDE: Using managed disk path: {disk_path}")

            # Socket paths
            runtime_dir = Path.home() / '.adare' / 'qemu' / 'run'
            runtime_dir.mkdir(parents=True, exist_ok=True)
            qmp_socket = str(runtime_dir / f"{self.vm_name}.qmp")
            qga_socket = str(runtime_dir / f"{self.vm_name}.qga")
            pid_file = str(runtime_dir / f"{self.vm_name}.pid")

            # Validate socket path lengths (Unix sockets have ~108 character limit)
            for name, path in [("QMP", qmp_socket), ("Guest Agent", qga_socket)]:
                if len(path) > 107:
                    raise ValueError(f"{name} socket path too long ({len(path)} > 107 chars): {path}")

            config = QEMUVMConfig(
                vm_name=self.vm_name,
                uuid=vm_uuid,
                guest_os=self.guest_os,
                disk_path=disk_path,
                cpus=self.cpus,
                ram=self.ram,
                machine=self.machine,
                accel=self.accel,
                drive_format=self.drive_format,
                network='user',
                qmp_socket_path=qmp_socket,
                guest_agent_socket_path=qga_socket,
                pid_file_path=pid_file
            )

            self._save_vm_config_obj(config)
            return config

    def _save_vm_config(self):
        """Save current VM config to JSON file."""
        self._save_vm_config_obj(self.config)

    def _save_vm_config_obj(self, config: QEMUVMConfig):
        """
        Save VM config object to JSON file.

        IMPORTANT: This method ensures that overlay paths are NEVER persisted to the
        config file. If the current disk_path is an overlay, we substitute it with
        the original disk path to prevent overlay chaining on subsequent runs.
        """
        config_path = self._get_vm_config_path()

        # Create a copy of config dict to avoid modifying the in-memory config
        config_dict = config.to_dict()

        # CRITICAL: Don't persist overlay paths - they cause chaining bugs
        # If disk_path contains '-overlay-', substitute with the original path
        disk_path = config_dict.get('disk_path', '')
        if '-overlay-' in disk_path:
            # Determine the original disk path to persist instead
            if self._external_disk_path:
                # External qcow2: use the original path
                original_path = self._external_disk_path
                log.debug(f"CLAUDE: Config save: replacing overlay path with external: {original_path}")
            else:
                # Managed VM: use the base disk path (without -base suffix for config)
                # The original config disk_path format is: /path/to/VM-name.qcow2
                # Strip overlay suffix and -base to get back to original format
                stripped = self._strip_overlay_suffixes(Path(disk_path).stem)
                stripped = stripped.replace('-base', '')
                original_path = str(Path(disk_path).parent / f"{stripped}{Path(disk_path).suffix}")
                log.debug(f"CLAUDE: Config save: replacing overlay path with original: {original_path}")

            config_dict['disk_path'] = original_path

        log.debug(f"CLAUDE: Saving VM config to {config_path}")
        with open(config_path, 'w') as f:
            json.dump(config_dict, f, indent=2)

    def get_base_disk_path(self) -> str:
        """
        Get path for immutable base disk.

        The base disk is never modified after creation. It serves as the
        backing file for experiment-specific overlays.

        Returns:
            Path with -base suffix: /path/to/disk-base.qcow2
        """
        current_disk = Path(self.config.disk_path)
        return str(current_disk.parent / f"{current_disk.stem}-base{current_disk.suffix}")

    def _get_true_base_disk(self) -> str:
        """
        Get the TRUE base disk path, ignoring any overlay paths in config.

        This method ensures we ALWAYS use the original base disk (never an overlay)
        when creating new overlays. This prevents overlay chaining which causes
        logs/data from previous runs to accumulate.

        Priority:
        1. For external qcow2 (--no-copy mode): Use the original external path
        2. For managed VMs: Use the -base.qcow2 file

        Returns:
            Absolute path to the true base disk

        Raises:
            HypervisorException: If no valid base disk can be found
        """
        # Priority 1: External qcow2 (--no-copy mode)
        # self._external_disk_path is set at init and NEVER changes
        if self._external_disk_path:
            external_path = Path(self._external_disk_path)
            if external_path.exists():
                log.debug(f"CLAUDE: True base disk (external): {external_path}")
                return str(external_path)
            else:
                raise HypervisorException(
                    f"External disk not found: {external_path}\n"
                    f"The original qcow2 file may have been moved or deleted."
                )

        # Priority 2: Managed VM with -base suffix
        # Look for the base disk that was created during import/conversion
        base_disk_path = self.get_base_disk_path()
        if Path(base_disk_path).exists():
            log.debug(f"CLAUDE: True base disk (managed): {base_disk_path}")
            return base_disk_path

        # Fallback: Try to find base by stripping overlay suffixes from config path
        # This handles edge cases where config.disk_path might be an overlay
        current_disk = Path(self.config.disk_path)
        stripped_stem = self._strip_overlay_suffixes(current_disk.stem)
        stripped_stem = stripped_stem.replace('-base', '')  # Also strip -base if present

        # Look for base disk with stripped name
        potential_base = current_disk.parent / f"{stripped_stem}-base{current_disk.suffix}"
        if potential_base.exists():
            log.debug(f"CLAUDE: True base disk (fallback): {potential_base}")
            return str(potential_base)

        # Last resort: check if stripped path exists as standalone qcow2
        potential_standalone = current_disk.parent / f"{stripped_stem}{current_disk.suffix}"
        if potential_standalone.exists() and '-overlay-' not in str(potential_standalone):
            log.debug(f"CLAUDE: True base disk (standalone): {potential_standalone}")
            return str(potential_standalone)

        raise HypervisorException(
            f"Cannot find base disk for VM '{self.vm_name}'.\n"
            f"Checked:\n"
            f"  - External path: {self._external_disk_path}\n"
            f"  - Base disk path: {base_disk_path}\n"
            f"  - Fallback base: {potential_base}\n"
            f"Please ensure the VM has been properly imported."
        )

    @staticmethod
    def _strip_overlay_suffixes(filename_stem: str) -> str:
        """
        Strip all -overlay-{ULID} patterns from a filename stem.

        This prevents filename length explosion when overlays are chained.
        Each ULID is 26 uppercase alphanumeric characters.

        Args:
            filename_stem: Filename without extension (e.g., "VM-name-overlay-01ABC...")

        Returns:
            Cleaned filename stem with all overlay suffixes removed

        Examples:
            >>> _strip_overlay_suffixes("VM-name-overlay-01KDK1XEYYBCSSS33BFD72Q3VV")
            "VM-name"
            >>> _strip_overlay_suffixes("VM-name-overlay-01ABC...-overlay-01DEF...")
            "VM-name"
        """
        # Strip all -overlay-{ULID} patterns (ULID = 26 uppercase alphanumeric chars)
        cleaned = re.sub(r'-overlay-[0-9A-Z]{26}', '', filename_stem)
        log.debug(f"CLAUDE: Stripped overlay suffixes: '{filename_stem}' => '{cleaned}'")
        return cleaned

    def get_overlay_disk_path(self, experiment_id: str) -> str:
        """
        Get path for experiment-specific overlay disk.

        Always derives overlay name from the base VM name by stripping ALL
        -overlay-{ULID} suffixes to prevent filename length explosion from
        chaining overlay names.

        This ensures overlays remain under the ext4 255-character filename limit
        by using a regex pattern to strip all overlay suffixes: -overlay-[0-9A-Z]{26}

        Args:
            experiment_id: Unique experiment ID (ULID - 26 alphanumeric characters)

        Returns:
            Path like: /path/to/VM-name-overlay-{exp_id}.qcow2

        Raises:
            HypervisorException: If generated filename exceeds 255 characters

        Examples:
            Base: ADARE-Ubuntu-24.04_exp_01KDK1XE-base.qcow2
            Overlay: ADARE-Ubuntu-24.04_exp_01KDK1XE-overlay-01KDKGR211GPRRSC0NGX8GWZMH.qcow2
            (72 characters - well within 255 limit)
        """
        # First, try to get the base disk path (normal case)
        base_disk_path = self.get_base_disk_path()
        base_disk = Path(base_disk_path)

        # Check if base disk exists (managed/converted case)
        if base_disk.exists():
            # Base disk format: VM-name-base.qcow2
            # Extract VM name by removing -base suffix
            vm_name_part = base_disk.stem.replace('-base', '')

            # Strip any overlay suffixes that may have leaked into base name
            # This handles edge cases where base disk was created from overlay
            vm_name_part = self._strip_overlay_suffixes(vm_name_part)

            overlay_name = f"{vm_name_part}-overlay-{experiment_id}{base_disk.suffix}"

            # Validate filename length (ext4 limit: 255 characters)
            if len(overlay_name) > 255:
                raise HypervisorException(
                    f"Overlay filename exceeds 255 character limit: {len(overlay_name)} chars\n"
                    f"Filename: {overlay_name}\n"
                    f"This should not happen with ULID-based naming. Please report this bug."
                )

            log.debug(f"CLAUDE: Generated overlay name (managed case): {overlay_name}")
            return str(base_disk.parent / overlay_name)

        # External qcow2 case: base disk doesn't exist, use config.disk_path directly
        # This handles --no-copy mode where source qcow2 is used without conversion
        current_disk = Path(self.config.disk_path)
        if current_disk.exists() and current_disk.suffix == '.qcow2':
            # Use the original disk name (without -overlay or -base suffix)
            # Strip ALL -overlay-{ULID} patterns to get clean VM name
            vm_name_part = current_disk.stem

            # First strip all overlay suffixes (handles chained overlays)
            vm_name_part = self._strip_overlay_suffixes(vm_name_part)

            # Then strip -base suffix if present
            if '-base' in vm_name_part:
                vm_name_part = vm_name_part.replace('-base', '')

            overlay_name = f"{vm_name_part}-overlay-{experiment_id}{current_disk.suffix}"

            # Validate filename length (ext4 limit: 255 characters)
            if len(overlay_name) > 255:
                raise HypervisorException(
                    f"Overlay filename exceeds 255 character limit: {len(overlay_name)} chars\n"
                    f"Filename: {overlay_name}\n"
                    f"Base VM name may be too long. Consider using a shorter VM name."
                )

            log.debug(f"CLAUDE: Generated overlay name (external case): {overlay_name}")
            return str(current_disk.parent / overlay_name)

        # Fallback: should not reach here, but use safe overlay generation
        # This maintains backward compatibility if we missed an edge case
        vm_name_part = self._strip_overlay_suffixes(current_disk.stem)
        vm_name_part = vm_name_part.replace('-base', '')  # Also strip base if present
        overlay_name = f"{vm_name_part}-overlay-{experiment_id}{current_disk.suffix}"

        # Validate filename length (ext4 limit: 255 characters)
        if len(overlay_name) > 255:
            log.warning(
                f"CLAUDE: Fallback overlay name exceeds 255 chars ({len(overlay_name)}): {overlay_name}"
            )
            # Truncate base name to fit within limit
            # 255 - len("-overlay-{26-char-ULID}.qcow2") = 255 - 36 = 219
            max_base_length = 219  # 255 - 36
            if len(vm_name_part) > max_base_length:
                vm_name_part = vm_name_part[:max_base_length]
                overlay_name = f"{vm_name_part}-overlay-{experiment_id}{current_disk.suffix}"
                log.warning(f"CLAUDE: Truncated base name to: {vm_name_part}")

        log.debug(f"CLAUDE: Generated overlay name (fallback case): {overlay_name}")
        return str(current_disk.parent / overlay_name)

    async def create_overlay_disk(self, experiment_id: str) -> str:
        """
        Create qcow2 overlay backed by immutable base disk.

        This creates a new overlay that captures all modifications while
        leaving the base disk untouched. The overlay is deleted after
        experiment completion.

        IMPORTANT: This method always uses the TRUE base disk (via _get_true_base_disk()),
        never an existing overlay. This prevents overlay chaining where logs/data from
        previous runs accumulate.

        Args:
            experiment_id: Unique ID for this experiment

        Returns:
            Path to created overlay disk

        Raises:
            HypervisorException: If overlay creation fails
        """
        # CRITICAL: Always use the TRUE base disk, never an overlay
        # This prevents overlay chaining which causes logs to accumulate
        base_disk = self._get_true_base_disk()
        log.debug(f"CLAUDE: Using true base disk for overlay: {base_disk}")

        # Clean up orphaned overlays from previous crashed runs BEFORE creating new one
        # This ensures we don't leave stale overlays that could confuse the system
        await self._cleanup_orphaned_overlays(experiment_id)

        # Create overlay path with experiment ID
        overlay_path = self.get_overlay_disk_path(experiment_id)

        # Calculate relative path from overlay to base disk for libguestfs compatibility
        # Libguestfs may mount the disk in a different context, so relative paths work better
        overlay_dir = Path(overlay_path).parent
        base_path = Path(base_disk)

        if overlay_dir == base_path.parent:
            # Same directory - use just filename (most common case)
            backing_file = base_path.name
        else:
            # Different directories - use relative path
            backing_file = os.path.relpath(base_disk, overlay_dir)

        log.debug(f"CLAUDE: Base disk absolute path: {base_disk}")
        log.debug(f"CLAUDE: Backing file relative path: {backing_file}")

        # Build qemu-img command to create backing file
        qemu_img = self.executables.qemu_img
        args = [
            qemu_img,
            'create',
            '-f', 'qcow2',
            '-F', 'qcow2',  # Backing file format
            '-b', backing_file,  # Backing file (relative path for libguestfs compatibility)
            overlay_path      # New overlay
        ]

        log.debug(f"CLAUDE: Creating overlay disk backed by {backing_file}")
        log.debug(f"CLAUDE: Command: {' '.join(args)}")

        # Execute qemu-img create
        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise HypervisorException(
                f"Failed to create overlay disk: {stderr.decode()}"
            )

        log.debug(f"CLAUDE: Successfully created overlay: {overlay_path}")
        return overlay_path

    async def _cleanup_orphaned_overlays(self, current_experiment_id: str) -> None:
        """
        Clean up orphaned overlay disks from previous crashed runs.

        This method finds and deletes overlay files that were left behind when
        previous experiment runs crashed before cleanup could occur.

        Only deletes overlays that:
        1. Match this VM's naming pattern (VM-name-overlay-*.qcow2)
        2. Are NOT the current experiment's overlay
        3. Are NOT the base disk

        Args:
            current_experiment_id: ID of current experiment (will NOT be deleted)
        """
        try:
            # Get the base disk to determine the overlay directory and naming pattern
            base_disk = self._get_true_base_disk()
            base_path = Path(base_disk)
            overlay_dir = base_path.parent

            # Determine the VM name part for matching overlays
            if self._external_disk_path:
                # External qcow2: use the original filename stem
                vm_name_stem = Path(self._external_disk_path).stem
            else:
                # Managed VM: strip -base suffix
                vm_name_stem = base_path.stem.replace('-base', '')

            # Strip any overlay suffixes that might have leaked into the stem
            vm_name_stem = self._strip_overlay_suffixes(vm_name_stem)

            # Find all overlays matching this VM's pattern
            overlay_pattern = f"{vm_name_stem}-overlay-*.qcow2"
            orphan_overlays = list(overlay_dir.glob(overlay_pattern))

            # Get the path for current experiment's overlay (should NOT be deleted)
            current_overlay_path = Path(self.get_overlay_disk_path(current_experiment_id))

            # Delete orphaned overlays
            deleted_count = 0
            for overlay in orphan_overlays:
                # Skip current experiment's overlay
                if overlay == current_overlay_path:
                    continue

                # Skip the base disk (shouldn't match pattern, but be safe)
                if overlay == base_path:
                    continue

                # Delete orphaned overlay
                try:
                    overlay.unlink()
                    deleted_count += 1
                    log.info(f"CLAUDE: Deleted orphaned overlay: {overlay.name}")
                except OSError as e:
                    log.warning(f"CLAUDE: Failed to delete orphaned overlay {overlay}: {e}")

            if deleted_count > 0:
                log.info(f"CLAUDE: Cleaned up {deleted_count} orphaned overlay(s)")

        except HypervisorException as e:
            # If we can't determine base disk, log warning but don't fail
            log.warning(f"CLAUDE: Could not clean orphaned overlays: {e}")

    async def cleanup_overlay_disk(self, experiment_id: str) -> None:
        """
        Delete experiment overlay disk.

        This removes the overlay file, leaving the base disk intact.
        The next experiment will create a fresh overlay from the base.

        Args:
            experiment_id: Unique ID for this experiment
        """
        overlay_path = self.get_overlay_disk_path(experiment_id)

        if Path(overlay_path).exists():
            try:
                os.remove(overlay_path)
                log.debug(f"CLAUDE: Deleted overlay disk: {overlay_path}")
            except OSError as e:
                log.warning(f"CLAUDE: Failed to delete overlay {overlay_path}: {e}")
        else:
            log.debug(f"CLAUDE: Overlay already deleted: {overlay_path}")

    async def create(
        self,
        ctx_manager=None,
        stop_event=None,
        log_file: Optional[Path] = None,
        silent: bool = False
    ) -> int:
        """
        Create a new QEMU VM disk.

        Args:
            ctx_manager: Optional context manager for status updates
            stop_event: Optional threading event to signal cancellation
            log_file: Optional path to log file
            silent: If True, suppress log output

        Returns:
            Return code (0 for success, non-zero for failure)
        """
        async def _create_async():
            if not silent:
                log.debug(f"CLAUDE: Creating QEMU VM '{self.vm_name}' with "
                        f"{self.cpus} CPUs, {self.ram}MB RAM")

            qemu_img_exe = self.executables.qemu_img

            # Create qcow2 disk (default 50GB)
            disk_path = self.config.disk_path
            args = [qemu_img_exe, 'create', '-f', 'qcow2', disk_path, '50G']

            returncode, stdout, stderr = await self._execute_streaming_command_async(
                args,
                log_file=log_file,
                stop_event=stop_event,
                silent=silent,
                ctx_manager=ctx_manager,
                operation_name="disk creation"
            )

            if returncode == 0:
                if not silent:
                    log.debug(f"CLAUDE: VM '{self.vm_name}' disk created at {disk_path}")
                # Save config
                self._save_vm_config()
            else:
                log.error(f"CLAUDE: Failed to create VM disk: {stderr}")

            return returncode

        return await self.manager.run_async(_create_async)

    def _get_libvirt_connection(self):
        """Get libvirt connection from manager (lazy initialization)."""
        if not self._libvirt_conn:
            self._libvirt_conn = self.manager.libvirt_conn
        return self._libvirt_conn

    def _define_libvirt_domain(self):
        """
        Define libvirt domain from XML configuration.

        Creates a libvirt domain definition that makes the VM visible in
        virsh and virt-manager while preserving all ADARE functionality.

        Returns:
            libvirt.virDomain: Domain object

        Raises:
            HypervisorException: If domain definition fails
        """
        from adare.hypervisor.qemu.libvirt_xml import generate_domain_xml
        import libvirt

        log.debug(f"CLAUDE: Defining libvirt domain for VM: {self.vm_name}")

        # Generate XML domain definition
        xml = generate_domain_xml(
            self.config,
            display_enabled=self.config.display_enabled,
            vnc_port=self.config.vnc_port
        )

        log.debug(f"CLAUDE: Generated libvirt XML for {self.vm_name}")

        # Get libvirt connection
        conn = self._get_libvirt_connection()

        if not conn:
            raise HypervisorException(
                "libvirt connection not available. Ensure libvirtd is running and "
                "libvirt integration is enabled in config."
            )

        # Check if domain already exists
        log_file = get_experiment_log_file()
        try:
            with LibvirtStderrRedirect(log_file=log_file, suppress_console=True):
                existing_domain = conn.lookupByName(self.vm_name)
                log.debug(f"CLAUDE: Domain '{self.vm_name}' already exists, undefining...")
                # Undefine existing domain (will redefine with new XML)
                if existing_domain.isActive():
                    log.warning(f"CLAUDE: Domain '{self.vm_name}' is running, destroying first...")
                    existing_domain.destroy()
                existing_domain.undefine()
        except libvirt.libvirtError as e:
            # Domain doesn't exist, which is fine
            if 'Domain not found' not in str(e):
                log.warning(f"CLAUDE: Error checking for existing domain: {e}")

        # Define the domain
        try:
            with LibvirtStderrRedirect(log_file=log_file, suppress_console=True):
                domain = conn.defineXML(xml)
            log.debug(f"CLAUDE: Defined libvirt domain '{self.vm_name}' (visible in virsh/virt-manager)")

            # Update config with libvirt domain name
            self.config.libvirt_domain_name = self.vm_name
            self._save_vm_config()

            return domain

        except libvirt.libvirtError as e:
            raise HypervisorException(
                f"Failed to define libvirt domain '{self.vm_name}': {e}"
            )

    def _build_qemu_command(self) -> List[str]:
        """
        Build QEMU command line for starting VM.

        Returns:
            List of command arguments
        """
        qemu_system_exe = self.executables.qemu_system

        cmd = [
            qemu_system_exe,
            '-name', self.vm_name,
            '-machine', f"{self.machine},accel={self.accel}",
            '-cpu', 'host',
            '-smp', str(self.cpus),
            '-m', str(self.ram),
            '-drive', f"file={self.config.disk_path},format={self.drive_format},if=virtio",
            # '-display', 'none',  # Headless
            '-daemonize',  # Run as daemon
            '-pidfile', self.config.pid_file_path
        ]

        # Add QEMU debug log if configured
        if self.config.qemu_debug_log_path:
            cmd.extend(['-D', self.config.qemu_debug_log_path])
            cmd.extend(['-d', 'guest_errors,cpu_reset,unimp'])

        # Add serial console redirect if configured
        if self.config.serial_console_log_path:
            cmd.extend([
                '-chardev', f'file,id=serial0,path={self.config.serial_console_log_path}',
                '-serial', 'chardev:serial0'
            ])

        # Add QMP monitor socket
        cmd.extend([
            '-qmp', f"unix:{self.config.qmp_socket_path},server=on,wait=off"
        ])

        # Add QEMU Guest Agent socket
        cmd.extend([
            '-chardev', f"socket,path={self.config.guest_agent_socket_path},server=on,wait=off,id=qga0",
            '-device', 'virtio-serial',
            '-device', 'virtserialport,chardev=qga0,name=org.qemu.guest_agent.0'
        ])

        # Add network with port forwarding
        netdev_args = f"user,id=net0"

        # Add port forwarding rules
        for name, rule in self.config.port_forwarding_rules.items():
            protocol = rule['protocol']
            host_port = rule['host_port']
            guest_port = rule['guest_port']
            host_ip = rule.get('host_ip', '')
            guest_ip = rule.get('guest_ip', '')

            hostfwd = f"{protocol}:{host_ip}:{host_port}-{guest_ip}:{guest_port}" if host_ip else f"{protocol}::{host_port}-:{guest_port}"
            netdev_args += f",hostfwd={hostfwd}"

        cmd.extend(['-netdev', netdev_args])
        cmd.extend(['-device', 'virtio-net-pci,netdev=net0'])

        log.debug(f"CLAUDE: QEMU command: {' '.join(cmd)}")
        return cmd

    async def start(
        self,
        ctx_manager=None,
        raise_if_running: bool = False,
        stop_event=None,
        log_file: Optional[Path] = None,
        silent: bool = False
    ) -> int:
        """
        Start the QEMU VM via libvirt.

        Creates libvirt domain definition and starts the VM, making it
        visible in virsh and virt-manager.

        Args:
            ctx_manager: Optional context manager for status updates
            raise_if_running: If True, raise exception if VM already running
            stop_event: Optional threading event to signal cancellation
            log_file: Optional path to log file
            silent: If True, suppress log output

        Returns:
            Return code (0 for success)

        Raises:
            VMStartException: If VM fails to start or state cannot be verified
            VMAlreadyRunningException: If VM is already running and raise_if_running=True
            HypervisorException: If libvirt domain definition fails
        """
        async def _start_async():
            import libvirt

            # Check if disk exists
            if not os.path.exists(self.config.disk_path):
                raise VMStartException(f"VM disk not found at {self.config.disk_path}")

            # Clean up any stale socket files before starting
            for socket_path in [self.config.qmp_socket_path, self.config.guest_agent_socket_path]:
                if os.path.exists(socket_path):
                    try:
                        os.remove(socket_path)
                        log.debug(f"CLAUDE: Removed stale socket: {socket_path}")
                    except OSError as e:
                        log.warning(f"CLAUDE: Could not remove stale socket {socket_path}: {e}")

            # CRITICAL: Always redefine libvirt domain on each start
            # This ensures the domain XML contains the current overlay disk path,
            # preventing "Cannot access storage file" errors on subsequent runs
            # where the previous overlay was deleted during cleanup.
            try:
                self._libvirt_domain = self._define_libvirt_domain()
            except HypervisorException:
                raise  # Re-raise specific hypervisor exceptions
            except libvirt.libvirtError as e:
                raise VMStartException(f"Failed to define libvirt domain: {e}")
            except OSError as e:
                raise VMStartException(f"OS error defining libvirt domain: {e}")

            # Check current state
            try:
                state, _ = self._libvirt_domain.state()
                if state == libvirt.VIR_DOMAIN_RUNNING:
                    message = f"VM '{self.vm_name}' is already running."
                    if raise_if_running:
                        raise VMAlreadyRunningException(message)
                    if not silent:
                        log.debug(f"CLAUDE: {message}")
                    return 0
            except libvirt.libvirtError as e:
                log.warning(f"CLAUDE: Could not check domain state: {e}")

            if not silent:
                log.debug(f"CLAUDE: Starting QEMU VM '{self.vm_name}' via libvirt")

            # Get experiment log file for stderr capture
            log_file = get_experiment_log_file()

            # Start the domain with stderr redirection to capture C library errors
            try:
                with LibvirtStderrRedirect(log_file=log_file, suppress_console=True):
                    self._libvirt_domain.create()

                # Give libvirt a moment to transition state
                await asyncio.sleep(1)

                # CRITICAL: Validate VM actually started
                # libvirt may fail silently and print to stderr instead of raising exception
                try:
                    is_active = self._libvirt_domain.isActive()
                    state, _ = self._libvirt_domain.state()

                    if not is_active or state != libvirt.VIR_DOMAIN_RUNNING:
                        raise VMStartException(
                            f"VM '{self.vm_name}' failed to start. "
                            f"Domain state: {state}, Active: {is_active}. "
                            f"Check experiment log for libvirt errors."
                        )
                except libvirt.libvirtError as e:
                    raise VMStartException(
                        f"Cannot verify VM state after start attempt: {e}"
                    )

                if not silent:
                    log.debug(f"CLAUDE: VM '{self.vm_name}' started successfully")
                return 0

            except VMStartException:
                raise  # Re-raise our own exception
            except VMAlreadyRunningException:
                raise  # Re-raise already running exception
            except libvirt.libvirtError as e:
                if "already running" in str(e).lower():
                    message = f"VM '{self.vm_name}' is already running."
                    if raise_if_running:
                        raise VMAlreadyRunningException(message)
                    if not silent:
                        log.debug(f"CLAUDE: {message}")
                    return 0
                else:
                    raise VMStartException(f"Failed to start VM via libvirt: {e}")
            except OSError as e:
                raise VMStartException(f"OS error during VM start: {e}")

        return await self.manager.run_async(_start_async)

    async def stop(
        self,
        ctx_manager=None,
        log_file: Optional[Path] = None,
        silent: bool = False,
        force: bool = False,
        timeout: int = 60
    ) -> int:
        """
        Stop the QEMU VM gracefully via libvirt.

        Args:
            ctx_manager: Optional context manager for status updates
            log_file: Optional path to log file
            silent: If True, suppress log output
            force: If True, force immediate shutdown (equivalent to pulling power)
            timeout: Timeout in seconds for graceful shutdown

        Returns:
            Return code (0 for success, non-zero for failure)
        """
        async def _stop_async():
            import libvirt

            if not silent:
                log.debug(f"CLAUDE: Stopping QEMU VM '{self.vm_name}' via libvirt")

            log_file_path = get_experiment_log_file()

            # Check if domain exists
            if not self._libvirt_domain:
                try:
                    with LibvirtStderrRedirect(log_file=log_file_path, suppress_console=True):
                        conn = self._get_libvirt_connection()
                        self._libvirt_domain = conn.lookupByName(self.vm_name)
                except libvirt.libvirtError:
                    if not silent:
                        log.debug(f"CLAUDE: VM '{self.vm_name}' is not defined in libvirt")
                    return 0

            # Check current state
            try:
                with LibvirtStderrRedirect(log_file=log_file_path, suppress_console=True):
                    state, _ = self._libvirt_domain.state()
                if state == libvirt.VIR_DOMAIN_SHUTOFF:
                    if not silent:
                        log.debug(f"CLAUDE: VM '{self.vm_name}' is already stopped")
                    return 0
            except libvirt.libvirtError as e:
                log.warning(f"CLAUDE: Could not check domain state: {e}")

            # Stop the domain
            try:
                with LibvirtStderrRedirect(log_file=log_file_path, suppress_console=True):
                    if force:
                        # Force stop (equivalent to virsh destroy)
                        if not silent:
                            log.debug(f"CLAUDE: Force stopping VM '{self.vm_name}'")
                        self._libvirt_domain.destroy()
                    else:
                        # Graceful shutdown (equivalent to virsh shutdown)
                        if not silent:
                            log.debug(f"CLAUDE: Gracefully shutting down VM '{self.vm_name}'")
                        self._libvirt_domain.shutdown()

                        # Wait for VM to stop with timeout
                        for _ in range(timeout):
                            await asyncio.sleep(1)
                            try:
                                state, _ = self._libvirt_domain.state()
                                if state == libvirt.VIR_DOMAIN_SHUTOFF:
                                    if not silent:
                                        log.debug(f"CLAUDE: VM '{self.vm_name}' stopped gracefully")
                                    return 0
                            except libvirt.libvirtError:
                                # Domain might have been destroyed
                                break

                        # Timeout - force stop
                        log.warning("CLAUDE: Graceful shutdown timed out, forcing stop")
                        self._libvirt_domain.destroy()

                if not silent:
                    log.debug(f"CLAUDE: VM '{self.vm_name}' stopped")
                return 0

            except libvirt.libvirtError as e:
                if "not running" in str(e).lower() or "not active" in str(e).lower():
                    if not silent:
                        log.debug(f"CLAUDE: VM '{self.vm_name}' is already stopped")
                    return 0
                else:
                    log.error(f"CLAUDE: Failed to stop VM via libvirt: {e}")
                    return 1
            except Exception as e:
                log.error(f"CLAUDE: Error stopping VM: {e}")
                return 1

        return await self.manager.run_async(_stop_async)

    async def destroy(
        self,
        ctx_manager=None,
        stop_event=None,
        log_file: Optional[Path] = None,
        silent: bool = False
    ) -> int:
        """
        Destroy the QEMU VM (undefine libvirt domain, delete disk and config).

        Args:
            ctx_manager: Optional context manager for status updates
            stop_event: Optional threading event to signal cancellation
            log_file: Optional path to log file
            silent: If True, suppress log output

        Returns:
            Return code (0 for success, non-zero for failure)
        """
        async def _destroy_async():
            import libvirt

            if not silent:
                log.debug(f"CLAUDE: Destroying QEMU VM '{self.vm_name}'")

            # Stop VM if running
            if self.get_state() == "running":
                await self.stop(silent=silent, force=True)

            log_file_path = get_experiment_log_file()

            # Undefine libvirt domain (removes from virsh list)
            if self._libvirt_domain:
                try:
                    with LibvirtStderrRedirect(log_file=log_file_path, suppress_console=True):
                        self._libvirt_domain.undefine()
                    if not silent:
                        log.debug(f"CLAUDE: Undefined libvirt domain '{self.vm_name}'")
                except libvirt.libvirtError as e:
                    log.warning(f"CLAUDE: Could not undefine libvirt domain: {e}")
                self._libvirt_domain = None
            else:
                # Try to lookup and undefine if it exists
                try:
                    with LibvirtStderrRedirect(log_file=log_file_path, suppress_console=True):
                        conn = self._get_libvirt_connection()
                        domain = conn.lookupByName(self.vm_name)
                        domain.undefine()
                    if not silent:
                        log.debug(f"CLAUDE: Undefined libvirt domain '{self.vm_name}'")
                except libvirt.libvirtError:
                    pass  # Domain doesn't exist, which is fine

            # Delete disk
            if os.path.exists(self.config.disk_path):
                try:
                    os.remove(self.config.disk_path)
                    if not silent:
                        log.debug(f"CLAUDE: Deleted VM disk: {self.config.disk_path}")
                except Exception as e:
                    log.error(f"CLAUDE: Error deleting disk: {e}")

            # Delete config
            config_path = self._get_vm_config_path()
            if config_path.exists():
                try:
                    os.remove(config_path)
                    if not silent:
                        log.debug(f"CLAUDE: Deleted VM config: {config_path}")
                except Exception as e:
                    log.error(f"CLAUDE: Error deleting config: {e}")

            # Clean up sockets
            for socket_path in [self.config.qmp_socket_path, self.config.guest_agent_socket_path]:
                if os.path.exists(socket_path):
                    try:
                        os.remove(socket_path)
                    except:
                        pass

            if not silent:
                log.debug(f"CLAUDE: VM '{self.vm_name}' destroyed")

            return 0

        return await self.manager.run_async(_destroy_async)

    def get_state(self) -> str:
        """
        Get the current state of the VM via libvirt.

        Returns:
            "running", "poweroff", "paused", or "unknown"
        """
        import libvirt

        try:
            log_file = get_experiment_log_file()

            # Try to get domain state from libvirt
            if not self._libvirt_domain:
                conn = self._get_libvirt_connection()
                if conn:
                    try:
                        with LibvirtStderrRedirect(log_file=log_file, suppress_console=True):
                            self._libvirt_domain = conn.lookupByName(self.vm_name)
                    except libvirt.libvirtError:
                        # Domain not defined in libvirt
                        return "poweroff"
                else:
                    # No libvirt connection
                    return "unknown"

            # Get domain state
            with LibvirtStderrRedirect(log_file=log_file, suppress_console=True):
                state, _ = self._libvirt_domain.state()

            # Map libvirt states to ADARE states
            state_map = {
                libvirt.VIR_DOMAIN_RUNNING: 'running',
                libvirt.VIR_DOMAIN_BLOCKED: 'running',
                libvirt.VIR_DOMAIN_PAUSED: 'paused',
                libvirt.VIR_DOMAIN_SHUTDOWN: 'poweroff',
                libvirt.VIR_DOMAIN_SHUTOFF: 'poweroff',
                libvirt.VIR_DOMAIN_CRASHED: 'poweroff',
                libvirt.VIR_DOMAIN_PMSUSPENDED: 'paused'
            }

            return state_map.get(state, 'unknown')

        except libvirt.libvirtError as e:
            log.debug(f"CLAUDE: Could not get VM state from libvirt: {e}")
            return "unknown"
        except Exception as e:
            log.warning(f"CLAUDE: Error getting VM state: {e}")
            return "unknown"

    def vm_exists(self) -> bool:
        """
        Check if the VM exists (disk file exists).

        Returns:
            True if VM exists, False otherwise
        """
        return os.path.exists(self.config.disk_path)

    @classmethod
    def get_vm_by_name(cls, vm_name: str, manager=None) -> 'QEMUVM':
        """
        Get a VM instance by name.

        Args:
            vm_name: Name of the VM
            manager: Optional QEMUManager instance

        Returns:
            QEMUVM instance

        Raises:
            VMNotFoundException: If VM config not found
        """
        from adare.config import get_vm_credentials

        if manager is None:
            manager = QEMUManager()

        # Check if config exists
        config_dir = Path.home() / '.adare' / 'qemu' / 'vms'
        config_path = config_dir / f"{vm_name}.json"

        if not config_path.exists():
            raise VMNotFoundException(f"QEMU VM '{vm_name}' not found")

        # Load config
        with open(config_path, 'r') as f:
            data = json.load(f)

        guest_os = data.get('guest_os', 'linux')
        username, password = get_vm_credentials(guest_os)

        # Create VM instance
        vm = cls(
            vm_name=vm_name,
            guest_os=guest_os,
            manager=manager,
            username=username,
            password=password,
            executables=manager.executables,
            cpus=data.get('cpus', 2),
            ram=data.get('ram', 2048),
            machine=data.get('machine', 'pc'),
            accel=data.get('accel', 'kvm'),
            drive_format=data.get('drive_format', 'qcow2')
        )

        return vm

    @property
    def vm_identifier(self) -> str:
        """
        Get VM identifier (name for QEMU).

        Returns:
            VM name
        """
        return self.vm_name

    async def run_command(
        self,
        command: str,
        background: bool = False,
        silent: bool = False,
        stop_event: Optional[threading.Event] = None,
        cwd: Optional[str] = None,
        admin: bool = False,
        **kwargs
    ) -> CommandResult:
        """
        Run a command in the guest VM via QEMU Guest Agent.

        Args:
            command: Command to execute
            background: If True, don't wait for completion
            silent: If True, suppress log output
            stop_event: Optional event to signal cancellation
            cwd: Optional working directory
            admin: If True, run with elevated privileges (sudo on Linux, RunAs on Windows)
            **kwargs: Additional arguments

        Returns:
            CommandResult with returncode, stdout, stderr
        """
        if not silent:
            log.debug(f"CLAUDE: Executing command in VM '{self.vm_name}': {command}")

        returncode, stdout, stderr = await self._execute_guest_command_via_agent(
            command,
            background=background,
            stop_event=stop_event,
            admin=admin
        )

        return CommandResult(
            returncode=returncode,
            stdout=stdout,
            stderr=stderr
        )

    async def wait_until_fully_booted(
        self,
        timeout: int = 300,
        ctx_manager=None,
        stop_event=None,
        skip_x11_discovery: bool = False
    ) -> bool:
        """
        Wait until VM is fully booted and guest agent is responsive.

        Tests both guest-ping (connectivity) and guest-exec (command execution)
        to ensure VM is truly ready for setup commands.

        Args:
            timeout: Timeout in seconds
            ctx_manager: Optional context manager for status updates
            stop_event: Optional event to signal cancellation
            skip_x11_discovery: If True, skip X11 environment discovery (for host-based GUI mode)

        Returns:
            True if VM is booted and ready, False if timeout
        """
        log.debug(f"CLAUDE: Waiting for VM '{self.vm_name}' to boot (timeout: {timeout}s)")

        start_time = time.time()
        ping_successful = False
        retry_delay = 0.5  # Start with short delay for quick boots
        max_retry_delay = 5.0  # Max delay between retries

        while time.time() - start_time < timeout:
            if stop_event and stop_event.is_set():
                log.debug("CLAUDE: Stop event detected")
                return False

            # Check if guest agent socket exists
            if not os.path.exists(self.config.guest_agent_socket_path):
                log.debug(f"CLAUDE: Guest agent socket not found yet: {self.config.guest_agent_socket_path}")
                await asyncio.sleep(retry_delay)
                # Increase delay for next iteration (exponential backoff)
                retry_delay = min(retry_delay * 1.5, max_retry_delay)
                continue

            try:
                # Phase 1: Test basic connectivity with guest-ping
                if not ping_successful:
                    ping_cmd = {"execute": "guest-ping"}
                    response = await self._send_qga_command_via_libvirt(ping_cmd)

                    if 'return' in response:
                        log.debug(f"CLAUDE: Guest agent is responsive (guest-ping successful)")
                        ping_successful = True
                        retry_delay = 0.5  # Reset delay after success
                    elif 'error' in response:
                        # Check if error is retriable (socket not ready, connection issues)
                        error_desc = response.get('error', {}).get('desc', '')
                        if 'OS error' in error_desc or 'Connection' in error_desc or 'Socket not found' in error_desc:
                            log.debug(f"CLAUDE: guest-ping failed (retriable): {error_desc}")
                            await asyncio.sleep(retry_delay)
                            retry_delay = min(retry_delay * 1.5, max_retry_delay)
                            continue
                        else:
                            log.debug(f"CLAUDE: guest-ping failed: {response}")
                            await asyncio.sleep(retry_delay)
                            retry_delay = min(retry_delay * 1.5, max_retry_delay)
                            continue
                    else:
                        log.debug(f"CLAUDE: guest-ping returned unexpected response: {response}")
                        await asyncio.sleep(retry_delay)
                        retry_delay = min(retry_delay * 1.5, max_retry_delay)
                        continue

                # Phase 2: Test actual command execution with guest-exec
                # This validates that the guest-exec subsystem is ready
                log.debug("CLAUDE: Testing guest-exec capability")

                # Determine test command based on guest OS
                if 'windows' in self.guest_os.lower():
                    test_path = 'cmd.exe'
                    test_args = ['/c', 'echo', 'Ready']
                else:
                    test_path = '/bin/echo'
                    test_args = ['Ready']

                exec_cmd = {
                    "execute": "guest-exec",
                    "arguments": {
                        "path": test_path,
                        "arg": test_args,
                        "capture-output": True
                    }
                }

                exec_response = await self._send_qga_command_via_libvirt(exec_cmd)

                if 'error' in exec_response:
                    error_desc = exec_response.get('error', {}).get('desc', '')
                    log.debug(f"CLAUDE: guest-exec test failed: {error_desc}")
                    # Treat as retriable - socket might not be fully ready
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 1.5, max_retry_delay)
                    continue

                # Get PID from exec response
                pid = exec_response.get('return', {}).get('pid')
                if not pid:
                    log.debug("CLAUDE: guest-exec returned no PID")
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 1.5, max_retry_delay)
                    continue

                # Wait for test command to complete (max 10s)
                test_timeout = 10
                test_start = time.time()

                while time.time() - test_start < test_timeout:
                    status_cmd = {
                        "execute": "guest-exec-status",
                        "arguments": {"pid": pid}
                    }

                    status_response = await self._send_qga_command_via_libvirt(status_cmd)

                    if 'error' in status_response:
                        log.debug(f"CLAUDE: guest-exec-status failed: {status_response['error']}")
                        break

                    status_data = status_response.get('return', {})
                    if status_data.get('exited', False):
                        returncode = status_data.get('exitcode', -1)

                        if returncode == 0:
                            log.debug(f"CLAUDE: VM '{self.vm_name}' is fully booted and guest-exec is functional")

                            # Phase 3: Discover and cache guest PATH environment
                            log.debug("CLAUDE: Discovering guest PATH environment")
                            await self._discover_and_cache_guest_path()

                            # Phase 4: Discover and cache X11 authorization for GUI automation (Linux only)
                            if skip_x11_discovery:
                                log.debug("CLAUDE: Skipping X11 discovery - using host-based GUI automation")
                            elif 'windows' not in self.guest_os.lower():
                                log.debug("CLAUDE: Discovering X11 authorization for GUI automation")
                                xauthority = await self._discover_and_cache_xauthority()
                                if not xauthority:
                                    raise RuntimeError(
                                        "XAUTHORITY not found - X11 environment required for GUI automation. "
                                        "Ensure the VM has an active X11 session (not headless). "
                                    )
                                log.debug(f"CLAUDE: X11 authorization configured with XAUTHORITY={xauthority}")
                            else:
                                log.debug("CLAUDE: Skipping X11 detection for Windows guest")

                            return True
                        else:
                            log.warning(f"CLAUDE: guest-exec test returned non-zero: {returncode}")
                            break

                    await asyncio.sleep(0.5)

                # Test command didn't complete in time, try again
                log.debug("CLAUDE: guest-exec test timed out, retrying")

            except asyncio.TimeoutError:
                log.debug("CLAUDE: Timeout during boot check")
            except OSError as e:
                log.debug(f"CLAUDE: OS error during boot check: {e}")
            except ConnectionError as e:
                log.debug(f"CLAUDE: Connection error during boot check: {e}")

            await asyncio.sleep(2)

        log.warning(f"CLAUDE: Timeout waiting for VM '{self.vm_name}' to boot")
        return False

    async def _discover_and_cache_guest_path(self):
        """
        Discover guest PATH environment and cache it for future command execution.

        Called once after VM is fully booted and guest agent is responsive.
        Failures are non-fatal - the system will fall back to hardcoded PATH.

        This method:
        1. Checks if discovery was already attempted (prevents retry on failure)
        2. Calls _discover_guest_path() to query PATH from guest OS
        3. Caches successful result in _cached_guest_path instance variable
        4. Logs warning on failure but doesn't raise exceptions
        """
        if self._path_discovery_attempted:
            return  # Already tried, don't retry

        self._path_discovery_attempted = True

        discovered_path = await self._discover_guest_path()

        if discovered_path:
            self._cached_guest_path = discovered_path
            log.debug(f"CLAUDE: Cached guest PATH: {discovered_path[:100]}...")
        else:
            log.warning("CLAUDE: PATH discovery failed, will use hardcoded fallback")

    async def create_from_ovf_or_ova(
        self,
        file_path: Path,
        silent: bool = False,
        try_extract: bool = True
    ) -> Tuple[int, str]:
        """
        Create VM from OVF/OVA file by converting disk to qcow2.

        For --no-copy mode with qcow2 source: skips conversion entirely.
        For --no-copy mode with non-qcow2 source: converts in-place next to original file.

        Args:
            file_path: Path to OVF/OVA file or disk image
            silent: If True, suppress log output
            try_extract: If True, try to extract OVA

        Returns:
            Tuple of (return_code, output_message)
        """
        log.debug(f"CLAUDE: Importing QEMU VM from {file_path}")

        qemu_img_exe = self.executables.qemu_img

        # For OVA, extract first
        if str(file_path).endswith('.ova') and try_extract:
            # Extract OVA (it's a tar file)
            import tarfile
            extract_dir = file_path.parent / f"{file_path.stem}_extracted"
            extract_dir.mkdir(exist_ok=True)

            with tarfile.open(file_path) as tar:
                tar.extractall(extract_dir)

            # Find VMDK or VDI file
            disk_files = list(extract_dir.glob('*.vmdk')) + list(extract_dir.glob('*.vdi'))
            if not disk_files:
                return 1, "No disk file found in OVA"

            source_disk = disk_files[0]
        else:
            # Assume it's already a disk file
            source_disk = file_path

        # Use base disk path (immutable) instead of regular disk path
        # This ensures the converted disk becomes the base for overlays
        dest_disk = self.get_base_disk_path()
        log.debug(f"CLAUDE: Conversion target is base disk: {dest_disk}")

        # Detect source disk format for --no-copy optimization
        try:
            source_format = self._detect_disk_format(source_disk)
            log.debug(f"CLAUDE: Detected source disk format: {source_format}")
        except HypervisorException as e:
            log.warning(f"CLAUDE: Could not detect source format, will attempt conversion: {e}")
            source_format = 'unknown'

        # Check if conversion can be skipped (--no-copy mode with qcow2 source)
        if source_format == 'qcow2' and self._external_disk_path:
            # Check if source and dest are the same file (--no-copy with existing qcow2)
            if Path(source_disk).resolve() == Path(dest_disk).resolve():
                log.debug(f"CLAUDE: Source is already qcow2 at target location, skipping conversion")
                self._save_vm_config()
                return 0, "VM imported successfully (no conversion needed)"

        # Validate write permissions for external disk path before conversion
        if self._external_disk_path:
            dest_path = Path(dest_disk)
            if dest_path.exists():
                # Check if file is writable
                if not os.access(dest_disk, os.W_OK):
                    return 1, (
                        f"External disk is not writable: {dest_disk}\n"
                        f"QEMU requires write access for snapshot operations.\n"
                        f"Please ensure the file has write permissions."
                    )
            else:
                # Check if parent directory is writable
                parent_dir = dest_path.parent
                if not parent_dir.exists():
                    return 1, f"Parent directory does not exist: {parent_dir}"
                if not os.access(parent_dir, os.W_OK):
                    return 1, (
                        f"Parent directory is not writable: {parent_dir}\n"
                        f"Cannot create converted qcow2 file for external VM.\n"
                        f"Please ensure directory has write permissions."
                    )

        # Convert to qcow2
        log.debug(f"CLAUDE: Converting {source_format} disk to qcow2 at {dest_disk}")
        args = [qemu_img_exe, 'convert', '-O', 'qcow2', str(source_disk), dest_disk]

        try:
            result = subprocess.run(args, capture_output=True, text=True, check=False)

            if result.returncode == 0:
                log.debug(f"CLAUDE: Successfully converted disk to {dest_disk}")
                self._save_vm_config()
                return 0, f"VM imported successfully"
            else:
                error_msg = f"Failed to convert {source_format} to qcow2: {result.stderr}"
                if self._external_disk_path:
                    error_msg += "\nConsider loading without --no-copy to use managed storage."
                return result.returncode, error_msg

        except Exception as e:
            error_msg = f"Conversion error: {str(e)}"
            if self._external_disk_path:
                error_msg += "\nConsider loading without --no-copy to use managed storage."
            return 1, error_msg

    def queue_command(self, command: str, description: str = None):
        """Queue a command for later execution."""
        self._command_queue.append({'command': command, 'description': description})

    async def execute_queued_commands(
        self,
        ctx_manager=None,
        stop_event=None,
        log_file=None,
        silent=False
    ):
        """Execute all queued commands."""
        for cmd_info in self._command_queue:
            command = cmd_info['command']
            result = await self.run_command(command, silent=silent, stop_event=stop_event)
            if result.returncode != 0:
                log.error(f"CLAUDE: Queued command failed: {command}")

        self._command_queue.clear()

    def cleanup_background_processes(self):
        """Clean up background processes (no-op for QEMU, processes managed by guest agent)."""
        self._background_pids.clear()

    # QMP Methods for Host-Based GUI Automation

    async def _send_qmp_command(self, command: dict) -> dict:
        """
        Send command to QEMU Monitor Protocol (QMP) via libvirt API.

        Args:
            command: QMP command dictionary

        Returns:
            Response dictionary
        """
        async def _qmp_async():
            import libvirt
            import libvirt_qemu
            try:
                if not self._libvirt_domain:
                    return {"error": {"desc": "Domain not defined"}}

                cmd_json = json.dumps(command)
                log.debug(f"CLAUDE: Sending QMP command: {command.get('execute', 'unknown')}")

                log_file = get_experiment_log_file()
                with LibvirtStderrRedirect(log_file=log_file, suppress_console=True):
                    result = libvirt_qemu.qemuMonitorCommand(
                        self._libvirt_domain,
                        cmd_json,
                        0  # flags (0 = default QMP mode)
                    )

                response = json.loads(result)

                # Log detailed response for debugging
                if 'error' in response:
                    log.error(f"CLAUDE: QMP command failed - Command: {command.get('execute')}, Error: {response['error']}")
                elif 'return' not in response:
                    log.warning(f"CLAUDE: QMP response missing 'return' key: {response}")
                else:
                    log.debug(f"CLAUDE: QMP response: {response}")

                return response

            except libvirt.libvirtError as e:
                log.error(f"CLAUDE: Libvirt error sending QMP command: {e}")
                return {"error": {"desc": f"Libvirt error: {e}"}}
            except json.JSONDecodeError as e:
                log.error(f"CLAUDE: Failed to parse QMP response: {e}, Raw: {result if 'result' in locals() else 'N/A'}")
                return {"error": {"desc": f"Invalid JSON: {e}"}}
            except Exception as e:
                log.error(f"CLAUDE: Unexpected QMP error: {e}", exc_info=True)
                return {"error": {"desc": f"Error: {e}"}}

        return await self.manager.run_async(_qmp_async)

    async def send_qmp_screenshot(self, output_path: str) -> bool:
        """
        Capture screenshot via QMP screendump command.

        Args:
            output_path: Path where screenshot will be saved (PPM format)

        Returns:
            True if successful, False otherwise
        """
        command = {
            "execute": "screendump",
            "arguments": {"filename": output_path}
        }
        response = await self._send_qmp_command(command)
        return 'return' in response

    async def send_qmp_mouse_click(self, x: int, y: int, button: str = 'left') -> bool:
        """
        Execute mouse click via QMP input-send-event command.

        Sends position, press, and release as separate commands for reliable execution.
        Automatically normalizes pixel coordinates to QEMU USB tablet range (0-32767).

        Args:
            x: X coordinate in pixels
            y: Y coordinate in pixels
            button: Button type ('left', 'right', 'middle')

        Returns:
            True if successful, False otherwise

        Raises:
            RuntimeError: If screen resolution is not yet known
        """
        # Normalize coordinates for USB tablet device
        norm_x, norm_y = self._normalize_coordinates(x, y)

        # Map button names to QMP button strings
        button_map = {'left': 'left', 'right': 'right', 'middle': 'middle', 'double': 'left'}
        qmp_button = button_map.get(button, 'left')

        # Step 1: Move mouse to position
        move_command = {
            "execute": "input-send-event",
            "arguments": {
                "events": [
                    {"type": "abs", "data": {"axis": "x", "value": norm_x}},
                    {"type": "abs", "data": {"axis": "y", "value": norm_y}}
                ]
            }
        }
        move_response = await self._send_qmp_command(move_command)

        if 'error' in move_response:
            log.error(f"CLAUDE: QMP mouse move failed: {move_response.get('error')}")
            return False

        await asyncio.sleep(0.01)

        # Step 2: Press button
        press_command = {
            "execute": "input-send-event",
            "arguments": {
                "events": [
                    {"type": "btn", "data": {"button": qmp_button, "down": True}}
                ]
            }
        }
        press_response = await self._send_qmp_command(press_command)

        if 'error' in press_response:
            log.error(f"CLAUDE: QMP button press failed: {press_response.get('error')}")
            return False

        await asyncio.sleep(0.05)  # Hold button down briefly

        # Step 3: Release button
        release_command = {
            "execute": "input-send-event",
            "arguments": {
                "events": [
                    {"type": "btn", "data": {"button": qmp_button, "down": False}}
                ]
            }
        }
        release_response = await self._send_qmp_command(release_command)

        if 'error' in release_response:
            log.error(f"CLAUDE: QMP button release failed: {release_response.get('error')}")
            return False

        return all('return' in r for r in [move_response, press_response, release_response])

    async def send_qmp_mouse_drag(self, x1: int, y1: int, x2: int, y2: int) -> bool:
        """
        Execute drag operation via QMP input-send-event command.

        Sends position and button events separately for reliable execution.
        Automatically normalizes pixel coordinates to QEMU USB tablet range (0-32767).

        Args:
            x1: Start X coordinate in pixels
            y1: Start Y coordinate in pixels
            x2: End X coordinate in pixels
            y2: End Y coordinate in pixels

        Returns:
            True if successful, False otherwise

        Raises:
            RuntimeError: If screen resolution is not yet known
        """
        # Normalize both start and end coordinates
        norm_x1, norm_y1 = self._normalize_coordinates(x1, y1)
        norm_x2, norm_y2 = self._normalize_coordinates(x2, y2)

        # Step 1: Move to start position
        move_start_command = {
            "execute": "input-send-event",
            "arguments": {
                "events": [
                    {"type": "abs", "data": {"axis": "x", "value": norm_x1}},
                    {"type": "abs", "data": {"axis": "y", "value": norm_y1}}
                ]
            }
        }
        response1 = await self._send_qmp_command(move_start_command)
        if 'error' in response1:
            log.error(f"CLAUDE: QMP drag move to start failed: {response1.get('error')}")
            return False

        await asyncio.sleep(0.01)

        # Step 2: Press left button
        press_command = {
            "execute": "input-send-event",
            "arguments": {
                "events": [
                    {"type": "btn", "data": {"button": "left", "down": True}}
                ]
            }
        }
        response2 = await self._send_qmp_command(press_command)
        if 'error' in response2:
            log.error(f"CLAUDE: QMP drag button press failed: {response2.get('error')}")
            return False

        await asyncio.sleep(0.01)

        # Step 3: Move to end position (while holding button)
        move_end_command = {
            "execute": "input-send-event",
            "arguments": {
                "events": [
                    {"type": "abs", "data": {"axis": "x", "value": norm_x2}},
                    {"type": "abs", "data": {"axis": "y", "value": norm_y2}}
                ]
            }
        }
        response3 = await self._send_qmp_command(move_end_command)
        if 'error' in response3:
            log.error(f"CLAUDE: QMP drag move to end failed: {response3.get('error')}")
            return False

        await asyncio.sleep(0.01)

        # Step 4: Release button
        release_command = {
            "execute": "input-send-event",
            "arguments": {
                "events": [
                    {"type": "btn", "data": {"button": "left", "down": False}}
                ]
            }
        }
        response4 = await self._send_qmp_command(release_command)
        if 'error' in response4:
            log.error(f"CLAUDE: QMP drag button release failed: {response4.get('error')}")
            return False

        return all('return' in r for r in [response1, response2, response3, response4])

    async def send_qmp_keyboard(self, events: List[dict]) -> bool:
        """
        Send keyboard events via QMP input-send-event command.

        Args:
            events: List of QMP keyboard event dictionaries

        Returns:
            True if successful, False otherwise
        """
        command = {
            "execute": "input-send-event",
            "arguments": {"events": events}
        }
        response = await self._send_qmp_command(command)
        return 'return' in response

    async def send_qmp_scroll(self, amount: int) -> bool:
        """
        Send scroll event via QMP input-send-event command.

        Args:
            amount: Scroll amount (positive = up, negative = down)

        Returns:
            True if successful, False otherwise
        """
        command = {
            "execute": "input-send-event",
            "arguments": {
                "events": [
                    {"type": "rel", "data": {"axis": "wheel", "value": amount}}
                ]
            }
        }
        response = await self._send_qmp_command(command)
        return 'return' in response

    def update_screen_resolution(self, width: int, height: int) -> None:
        """
        Update cached screen resolution for coordinate normalization.

        Called automatically when screenshots are captured to track current display size.
        Required because QEMU's USB tablet device expects normalized coordinates (0-32767),
        not raw pixel coordinates.

        Args:
            width: Screen width in pixels
            height: Screen height in pixels
        """
        if self._screen_width != width or self._screen_height != height:
            log.debug(f"CLAUDE: Screen resolution updated: {width}x{height}")
            self._screen_width = width
            self._screen_height = height
            self._resolution_last_updated = time.time()

    def _normalize_coordinates(self, x: int, y: int) -> tuple[int, int]:
        """
        Normalize pixel coordinates to QEMU USB tablet range (0-32767).

        QEMU's USB tablet device uses absolute positioning with a normalized coordinate
        system where 0-32767 maps to the full screen width/height, regardless of actual
        pixel resolution.

        Args:
            x: X coordinate in pixels
            y: Y coordinate in pixels

        Returns:
            Tuple of (normalized_x, normalized_y) in range 0-32767

        Raises:
            RuntimeError: If screen resolution is not yet known
        """
        if self._screen_width is None or self._screen_height is None:
            raise RuntimeError(
                "Screen resolution unknown - cannot normalize coordinates. "
                "Ensure a screenshot is captured before mouse operations. "
                "This updates the cached resolution automatically."
            )

        # Normalize to 0-32767 range (0x7fff = 32767)
        # Formula: normalized = int((pixel / screen_dimension) * 32767)
        normalized_x = int((x / self._screen_width) * 32767)
        normalized_y = int((y / self._screen_height) * 32767)

        # Clamp to valid range (handle edge cases where coordinates might be at/beyond screen edge)
        normalized_x = max(0, min(32767, normalized_x))
        normalized_y = max(0, min(32767, normalized_y))

        log.debug(f"CLAUDE: Normalized coordinates: ({x}, {y}) -> ({normalized_x}, {normalized_y}) "
                  f"for resolution {self._screen_width}x{self._screen_height}")

        return normalized_x, normalized_y

    @staticmethod
    def get_vm_info_by_uuid(uuid: str) -> Optional[Dict[str, Any]]:
        """
        Get VM information by UUID/identifier.
        
        For QEMU, we search through all VM config files to find one with matching UUID.
        
        Args:
            uuid: VM UUID/identifier
            
        Returns:
            Dictionary of VM information if found, None otherwise
        """
        from adare.config import get_vm_credentials
        import glob
        
        # Search for all VM config files
        config_dir = Path.home() / '.adare' / 'qemu' / 'vms'
        if not config_dir.exists():
            return None
            
        config_files = glob.glob(str(config_dir / "*.json"))
        for config_file in config_files:
            try:
                with open(config_file, 'r') as f:
                    data = json.load(f)
                    
                # Check if UUID matches
                if data.get('uuid') == uuid:
                    vm_name = data.get('vm_name')
                    guest_os = data.get('guest_os', 'linux')
                    username, password = get_vm_credentials(guest_os)
                    
                    return {
                        'name': vm_name,
                        'uuid': uuid,
                        'guest_os': guest_os,
                        'username': username,
                        'password': password,
                        'cpus': data.get('cpus', 2),
                        'ram': data.get('ram', 2048),
                        'disk_path': data.get('disk_path'),
                        'config_path': config_file
                    }
            except (json.JSONDecodeError, KeyError, IOError):
                # Skip invalid config files
                continue
                
        return None

    @staticmethod
    def get_vm_name_by_uuid(uuid: str) -> Optional[str]:
        """
        Get VM name by UUID/identifier.
        
        For QEMU, we search through all VM config files to find one with matching UUID.
        
        Args:
            uuid: VM UUID/identifier
            
        Returns:
            VM name if found, None otherwise
        """
        # Search for all VM config files
        config_dir = Path.home() / '.adare' / 'qemu' / 'vms'
        if not config_dir.exists():
            return None
            
        import glob
        config_files = glob.glob(str(config_dir / "*.json"))
        for config_file in config_files:
            try:
                with open(config_file, 'r') as f:
                    data = json.load(f)
                    
                # Check if UUID matches
                if data.get('uuid') == uuid:
                    return data.get('vm_name')
            except (json.JSONDecodeError, KeyError, IOError):
                # Skip invalid config files
                continue
                
        return None

    @staticmethod
    def get_vm_uuid_by_name(vm_name: str) -> Optional[str]:
        """
        Get VM UUID/identifier by name.
        
        For QEMU, the UUID is stored in the VM config file.
        
        Args:
            vm_name: Name of the VM
            
        Returns:
            VM UUID/identifier if found, None otherwise
        """
        # Check if config exists
        config_dir = Path.home() / '.adare' / 'qemu' / 'vms'
        config_path = config_dir / f"{vm_name}.json"
        
        if not config_path.exists():
            return None
            
        try:
            with open(config_path, 'r') as f:
                data = json.load(f)
            return data.get('uuid')
        except (json.JSONDecodeError, KeyError, IOError):
            return None

    @staticmethod
    def verify_vm_exists_by_uuid(uuid: str) -> bool:
        """
        Verify if a VM exists by its UUID/identifier.
        
        For QEMU, we search through all VM config files to find one with matching UUID.
        
        Args:
            uuid: VM UUID/identifier
            
        Returns:
            True if VM exists, False otherwise
        """
        # Search for all VM config files
        config_dir = Path.home() / '.adare' / 'qemu' / 'vms'
        if not config_dir.exists():
            return False
            
        import glob
        config_files = glob.glob(str(config_dir / "*.json"))
        for config_file in config_files:
            try:
                with open(config_file, 'r') as f:
                    data = json.load(f)
                    
                # Check if UUID matches
                if data.get('uuid') == uuid:
                    return True
            except (json.JSONDecodeError, KeyError, IOError):
                # Skip invalid config files
                continue
                
        return False
