"""
Configuration Mixin - VM configuration lifecycle (load, save, defaults).
"""
import contextlib
import json
import logging
import subprocess
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from adare.config import DEFAULT_RESOLUTION_WH
from adare.hypervisor.exceptions import HypervisorException
from adare.hypervisor.qemu.models import QEMUVMConfig
from adare.hypervisor.qemu.utilities.disk_utils import get_boot_mode_for_os, resolve_boot_mode

if TYPE_CHECKING:
    from adare.hypervisor.qemu.vm import QEMUVM

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Managed QEMU storage locations (single source of truth)
# ---------------------------------------------------------------------------

def get_qemu_disk_dir() -> Path:
    """Directory holding managed disks (base/overlay/nvram): ~/.adare/qemu/disks."""
    disk_dir = Path.home() / '.adare' / 'qemu' / 'disks'
    disk_dir.mkdir(parents=True, exist_ok=True)
    return disk_dir


def get_qemu_runtime_dir() -> Path:
    """Directory holding runtime sockets/pids (QMP/QGA/pid): ~/.adare/qemu/run."""
    runtime_dir = Path.home() / '.adare' / 'qemu' / 'run'
    runtime_dir.mkdir(parents=True, exist_ok=True)
    return runtime_dir


def get_qemu_vm_config_dir() -> Path:
    """Directory holding per-VM config JSON: ~/.adare/qemu/vms."""
    config_dir = Path.home() / '.adare' / 'qemu' / 'vms'
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def is_socket_listening(socket_path: str, timeout: float = 0.2) -> bool:
    """Return True if a Unix socket currently accepts a new connection.

    A successful non-blocking connect proves something is serving the socket,
    so it is definitely live. The converse is NOT reliable: QMP/QGA are
    single-client channels, so a *live* socket that already has its one client
    connected refuses further connects (``ECONNREFUSED``). Treat this only as a
    positive "definitely alive" signal — never infer "stale" from a failure
    alone (cross-check with the owning domain via ``get_active_domain_names``).
    """
    import socket as _socket

    sock = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
    try:
        sock.settimeout(timeout)
        sock.connect(socket_path)
        return True
    except OSError:
        return False
    finally:
        sock.close()


def get_active_domain_names() -> set[str] | None:
    """Return the set of running libvirt domain names, or None if unknowable.

    The QMP/QGA socket basename stem equals the VM/domain name, so a running
    domain authoritatively marks its sockets as live. Returns None (rather than
    an empty set) when libvirt is unavailable or the query fails, so callers can
    refuse to reap anything rather than risk deleting a live socket.
    """
    try:
        import libvirt
    except ImportError:
        return None

    try:
        from adare.config import HYPERVISOR_CONFIGS
        libvirt_uri = HYPERVISOR_CONFIGS.get('qemu', {}).get('libvirt_uri', 'qemu:///session')
    except ImportError:
        libvirt_uri = 'qemu:///session'

    conn = None
    try:
        conn = libvirt.open(libvirt_uri)
        if conn is None:
            return None
        # VIR_CONNECT_LIST_DOMAINS_ACTIVE = running/paused domains only.
        active = conn.listAllDomains(libvirt.VIR_CONNECT_LIST_DOMAINS_ACTIVE)
        return {domain.name() for domain in active}
    except libvirt.libvirtError as e:
        log.warning(f"Could not query active libvirt domains: {e}")
        return None
    finally:
        if conn is not None:
            with contextlib.suppress(libvirt.libvirtError):
                conn.close()


def find_stale_sockets(runtime_dir: Path | None = None, keep: set[str] | None = None) -> list[Path]:
    """Return QMP/QGA sockets in *runtime_dir* that no running QEMU owns.

    A socket is considered LIVE (and never returned) if its owning domain is
    active, or if it still accepts a connection. It is only reported stale when
    BOTH checks say it is dead — this is what protects a live-but-occupied QGA
    socket from being reaped. Sockets whose absolute path or basename is in
    *keep* are always skipped.

    Returns an empty list (reaping nothing) if the active-domain set cannot be
    determined, so we never delete a socket we could not verify as dead.
    """
    if runtime_dir is None:
        runtime_dir = get_qemu_runtime_dir()
    keep = keep or set()

    active = get_active_domain_names()
    if active is None:
        log.warning("Cannot determine active libvirt domains — skipping stale-socket sweep for safety")
        return []

    stale: list[Path] = []
    for pattern in ('*.qmp', '*.qga'):
        for sock_path in runtime_dir.glob(pattern):
            if str(sock_path) in keep or sock_path.name in keep:
                continue
            # Only ever operate on genuine sockets.
            try:
                if not sock_path.is_socket():
                    continue
            except OSError:
                continue
            # sock_path.stem strips the .qmp/.qga suffix → the domain/VM name.
            if sock_path.stem in active:
                continue  # owning domain running → live
            if is_socket_listening(str(sock_path)):
                continue  # someone is still serving it → live
            stale.append(sock_path)
    return stale


def sweep_stale_sockets(runtime_dir: Path | None = None, keep: set[str] | None = None) -> list[str]:
    """Reap crash-orphaned QMP/QGA sockets (those no running QEMU owns).

    Uses :func:`find_stale_sockets` for the safe liveness determination, then
    unlinks each. Returns the list of unlinked socket paths (errors swallowed).
    """
    removed: list[str] = []
    for sock_path in find_stale_sockets(runtime_dir, keep):
        try:
            sock_path.unlink()
            removed.append(str(sock_path))
            log.debug(f"Swept stale socket: {sock_path}")
        except OSError as e:
            log.warning(f"Could not remove stale socket {sock_path}: {e}")
    return removed


class ConfigurationMixin:
    """
    Mixin for VM configuration operations.

    Provides methods for loading, saving, and managing VM configuration files.
    Configuration includes disk paths, boot mode, resources, and runtime settings.
    """

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
            log.debug(f"OVA file detected, will need extraction: {file_path}")
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

            log.debug(f"Detected disk format: {disk_format} for {file_path}")
            return disk_format

        except json.JSONDecodeError as e:
            raise HypervisorException(
                f"Failed to parse qemu-img info output: {e}"
            ) from e
        except FileNotFoundError:
            raise HypervisorException(
                "qemu-img executable not found. Please install QEMU tools."
            ) from None
        except OSError as e:
            raise HypervisorException(
                f"Error detecting disk format: {e}"
            ) from e

    def _detect_disk_format(self: 'QEMUVM', file_path: Path) -> str:
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

    def _get_vm_config_path(self: 'QEMUVM') -> Path:
        """Get path to VM configuration JSON file."""
        # Store VM configs in ~/.adare/qemu/vms/
        return get_qemu_vm_config_dir() / f"{self.vm_name}.json"

    def _load_or_create_vm_config(self: 'QEMUVM') -> QEMUVMConfig:
        """Load VM config from JSON or create new one."""
        config_path = self._get_vm_config_path()

        if config_path.exists():
            log.debug(f"Loading VM config from {config_path}")
            with open(config_path) as f:
                data = json.load(f)
            config = QEMUVMConfig.from_dict(data)

            # CRITICAL FIX: Override disk_path if external path provided
            # This prevents using stale disk_path from saved config
            if self._external_disk_path:
                config.disk_path = self._external_disk_path
                log.debug(f"Overriding config disk_path with external: {self._external_disk_path}")

            # Validate and sync guest_os, architecture, and boot_mode from current environment
            # This fixes stale configs that may have incorrect values
            current_arch = getattr(self, 'architecture', 'x86_64')
            expected_boot_mode = resolve_boot_mode(self.guest_os, self._hypervisor_config, current_arch)
            config_updated = False

            if config.guest_os != self.guest_os:
                log.info(f"Updating guest_os in VM config: {config.guest_os} → {self.guest_os}")
                config.guest_os = self.guest_os
                config_updated = True

            if config.architecture != current_arch:
                log.info(f"Updating architecture in VM config: {config.architecture} → {current_arch}")
                config.architecture = current_arch
                config_updated = True

            if config.boot_mode != expected_boot_mode:
                log.info(f"Updating boot_mode in VM config: {config.boot_mode} → {expected_boot_mode}")
                config.boot_mode = expected_boot_mode
                config_updated = True

            # Apply live-installer boot settings passed to the constructor
            # (e.g. a GUI-automated install re-attaching its ISO).
            requested_iso = getattr(self, '_iso_path', '')
            requested_cdrom = getattr(self, '_boot_from_cdrom', False)
            if requested_iso and config.iso_path != requested_iso:
                config.iso_path = requested_iso
                config_updated = True
            if config.boot_from_cdrom != requested_cdrom:
                config.boot_from_cdrom = requested_cdrom
                config_updated = True

            # Sync Windows resource defaults
            # Windows VMs need more resources (4 vCPU, 8GB RAM) for proper operation
            if 'windows' in self.guest_os.lower():
                # Upgrade to Windows defaults if currently at standard defaults
                if config.cpus == 2:
                    log.info("Upgrading Windows VM to 4 vCPUs (was: 2)")
                    config.cpus = 4
                    config_updated = True

                if config.ram == 2048:
                    log.info("Upgrading Windows VM to 8192 MB RAM (was: 2048)")
                    config.ram = 8192
                    config_updated = True

            if config_updated:
                log.info(f"Saving updated VM config to {config_path}")
                self._save_vm_config_obj(config)

            return config
        log.debug(f"Creating new VM config for '{self.vm_name}'")
        # Create new config
        vm_uuid = str(uuid.uuid4())

        # Determine disk path: use external path if provided, otherwise use managed storage
        if self._external_disk_path:
            disk_path = self._external_disk_path
            log.debug(f"Using external disk path for --no-copy mode: {disk_path}")
        else:
            disk_dir = get_qemu_disk_dir()
            disk_path = str(disk_dir / f"{self.vm_name}.qcow2")
            log.debug(f"Using managed disk path: {disk_path}")

        # Socket paths
        runtime_dir = get_qemu_runtime_dir()
        qmp_socket = str(runtime_dir / f"{self.vm_name}.qmp")
        qga_socket = str(runtime_dir / f"{self.vm_name}.qga")
        pid_file = str(runtime_dir / f"{self.vm_name}.pid")

        # Validate socket path lengths (Unix sockets have ~108 character limit)
        for name, path in [("QMP", qmp_socket), ("Guest Agent", qga_socket)]:
            if len(path) > 107:
                raise ValueError(f"{name} socket path too long ({len(path)} > 107 chars): {path}")

        # Determine boot mode: environment YAML override, else architecture-aware auto-detection
        current_arch = getattr(self, 'architecture', 'x86_64')
        boot_mode = resolve_boot_mode(self.guest_os, self._hypervisor_config, current_arch)

        # Windows VMs need more resources for proper operation
        # Use higher defaults if the current values are the standard defaults
        if 'windows' in self.guest_os.lower():
            # If using default values (2 vCPU, 2048 MB), upgrade to Windows defaults
            config_cpus = self.cpus if self.cpus != 2 else 4
            config_ram = self.ram if self.ram != 2048 else 8192  # 8GB for Windows 11
            if config_cpus != self.cpus or config_ram != self.ram:
                log.info(f"Using Windows VM defaults: {config_cpus} vCPU, {config_ram} MB RAM")
        else:
            config_cpus = self.cpus
            config_ram = self.ram

        # Guest display resolution: default from config, allow an optional per-VM
        # override (tuple or "WxH" string) via the same getattr pattern as iso_path.
        resolution_x, resolution_y = DEFAULT_RESOLUTION_WH
        override = getattr(self, '_resolution', None)
        if override:
            if isinstance(override, str):
                resolution_x, resolution_y = (int(v) for v in override.split('x'))
            else:
                resolution_x, resolution_y = int(override[0]), int(override[1])

        config = QEMUVMConfig(
            vm_name=self.vm_name,
            uuid=vm_uuid,
            guest_os=self.guest_os,
            architecture=current_arch,
            disk_path=disk_path,
            cpus=config_cpus,
            ram=config_ram,
            machine=self.machine,
            accel=self.accel,
            drive_format=self.drive_format,
            boot_mode=boot_mode,
            network='user',
            qmp_socket_path=qmp_socket,
            guest_agent_socket_path=qga_socket,
            pid_file_path=pid_file,
            iso_path=getattr(self, '_iso_path', ''),
            boot_from_cdrom=getattr(self, '_boot_from_cdrom', False),
            resolution_x=resolution_x,
            resolution_y=resolution_y,
        )

        self._save_vm_config_obj(config)
        return config

    def _save_vm_config(self: 'QEMUVM'):
        """Save current VM config to JSON file."""
        self._save_vm_config_obj(self.config)

    def _save_vm_config_obj(self: 'QEMUVM', config: QEMUVMConfig):
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
                log.debug(f"Config save: replacing overlay path with external: {original_path}")
            else:
                # Managed VM: use the base disk path (without -base suffix for config)
                # The original config disk_path format is: /path/to/VM-name.qcow2
                # Strip overlay suffix and -base to get back to original format
                stripped = self._strip_overlay_suffixes(Path(disk_path).stem)
                stripped = stripped.replace('-base', '')
                original_path = str(Path(disk_path).parent / f"{stripped}{Path(disk_path).suffix}")
                log.debug(f"Config save: replacing overlay path with original: {original_path}")

            config_dict['disk_path'] = original_path

        log.debug(f"Saving VM config to {config_path}")
        with open(config_path, 'w') as f:
            json.dump(config_dict, f, indent=2)
