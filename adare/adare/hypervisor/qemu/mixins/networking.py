"""
QEMU VM networking operations mixin.

Implements AbstractNetworkingMixin for QEMU with:
- Port forwarding via user-mode networking (hostfwd)
- Shared folders via virtio-fs (default) or libguestfs fallback

File transfer modes:
1. virtio-fs (default): Uses multiple virtio-fs shared directories, configured in libvirt XML
   - Fast, real-time file sharing between host and guest
   - Multiple shares: run, vm, experiment, project_shared, shared
   - Managed by lifecycle.py via _setup_virtiofs_shared_directories()

2. libguestfs (fallback, when QEMU_LIBGUESTFS=true):
   - Files copied to disk before boot, retrieved after shutdown
   - Managed by lifecycle.py via _setup_file_transfer_via_libguestfs()

Note: The actual file transfer setup is handled by lifecycle.py.
The shared folder methods here are mostly no-ops since virtio-fs
configuration is done through the libvirt XML, not VirtualBox-style
shared folders.
"""
import logging
import os
from pathlib import Path

from adare.hypervisor.base.mixins.networking import AbstractNetworkingMixin
from adare.hypervisor.exceptions import UnsupportedFeatureException
from adare.hypervisor.qemu.models import PortForwardingRule, SharedFolderConfig

log = logging.getLogger(__name__)


def _use_shared_folder_mode() -> bool:
    """Check if shared folder mode (virtio-fs) should be used (default) or libguestfs fallback."""
    libguestfs_env = os.environ.get('QEMU_LIBGUESTFS', '').lower()
    return libguestfs_env not in ('true', '1', 'yes')


class NetworkingMixin(AbstractNetworkingMixin):
    """Mixin class providing networking operations for QEMU VMs."""

    # ==================== Port Forwarding ====================

    async def list_port_forwarding_rules(
        self,
        ctx_manager=None,
        stop_event=None,
        log_file: Path | None = None,
        silent: bool = False
    ) -> dict[str, PortForwardingRule]:
        """
        List all port forwarding rules for the VM.

        Port forwarding rules are stored in the VM config.

        Args:
            ctx_manager: Optional context manager for status updates
            stop_event: Optional threading event to signal cancellation
            log_file: Optional path to log file
            silent: If True, suppress log output

        Returns:
            Dict mapping rule names to PortForwardingRule objects
        """
        if not hasattr(self, 'config'):
            log.warning("VM config not available")
            return {}

        rules = {}
        for name, rule_data in self.config.port_forwarding_rules.items():
            rules[name] = PortForwardingRule(
                name=rule_data['name'],
                protocol=rule_data['protocol'],
                host_ip=rule_data.get('host_ip', ''),
                host_port=rule_data.get('host_port', 0),
                guest_ip=rule_data.get('guest_ip', ''),
                guest_port=rule_data.get('guest_port', 0)
            )

        if not silent:
            log.debug(f"Found {len(rules)} port forwarding rules")

        return rules

    async def add_port_forwarding(
        self,
        name: str,
        protocol: str,
        host_port: int,
        guest_port: int,
        host_ip: str = "",
        guest_ip: str = "",
        ctx_manager=None,
        stop_event=None,
        log_file: Path | None = None,
        silent: bool = False
    ) -> int:
        """
        Add a port forwarding rule to the VM configuration.

        Rule will be applied on next VM start. If VM is running, must be restarted.

        Args:
            name: Name for the port forwarding rule
            protocol: Protocol ('tcp' or 'udp')
            host_port: Port on the host machine
            guest_port: Port in the guest VM
            host_ip: Host IP address (empty string for all interfaces)
            guest_ip: Guest IP address (empty string for default)
            ctx_manager: Optional context manager for status updates
            stop_event: Optional threading event to signal cancellation
            log_file: Optional path to log file
            silent: If True, suppress log output

        Returns:
            Return code (0 for success, non-zero for failure)
        """
        if not silent:
            log.info(f"Adding port forwarding rule '{name}': "
                    f"{protocol} {host_ip}:{host_port} -> {guest_ip}:{guest_port}")

        if not hasattr(self, 'config'):
            log.error("VM config not available")
            return 1

        # Check if rule already exists
        if name in self.config.port_forwarding_rules:
            log.warning(f"Port forwarding rule '{name}' already exists")
            return 1

        # Create rule
        rule = PortForwardingRule(
            name=name,
            protocol=protocol,
            host_ip=host_ip,
            host_port=host_port,
            guest_ip=guest_ip,
            guest_port=guest_port
        )

        # Add to config
        self.config.port_forwarding_rules[name] = {
            'name': rule.name,
            'protocol': rule.protocol,
            'host_ip': rule.host_ip,
            'host_port': rule.host_port,
            'guest_ip': rule.guest_ip,
            'guest_port': rule.guest_port
        }

        # Save config
        self._save_vm_config()

        if not silent:
            log.info(f"Successfully added port forwarding rule '{name}'")
            if self.get_state() == "running":
                log.warning("VM is running. Port forwarding changes require VM restart.")

        return 0

    async def remove_port_forwarding(
        self,
        name: str,
        ctx_manager=None,
        stop_event=None,
        log_file: Path | None = None,
        silent: bool = False
    ) -> int:
        """
        Remove a port forwarding rule from the VM configuration.

        Args:
            name: Name of the port forwarding rule to remove
            ctx_manager: Optional context manager for status updates
            stop_event: Optional threading event to signal cancellation
            log_file: Optional path to log file
            silent: If True, suppress log output

        Returns:
            Return code (0 for success, non-zero for failure)
        """
        if not silent:
            log.info(f"Removing port forwarding rule '{name}'")

        if not hasattr(self, 'config'):
            log.error("VM config not available")
            return 1

        if name not in self.config.port_forwarding_rules:
            if not silent:
                log.warning(f"Port forwarding rule '{name}' does not exist")
            return 0  # Consider success if already gone

        # Remove from config
        del self.config.port_forwarding_rules[name]

        # Save config
        self._save_vm_config()

        if not silent:
            log.info(f"Successfully removed port forwarding rule '{name}'")
            if self.get_state() == "running":
                log.warning("VM is running. Port forwarding changes require VM restart.")

        return 0

    # ==================== Shared Folders ====================
    # QEMU uses virtio-fs (default) or libguestfs (fallback) for file sharing
    # The actual setup is handled by lifecycle.py - these methods are compatibility stubs

    async def add_shared_folder(
        self,
        name: str,
        host_path: Path,
        readonly: bool = False,
        guest_mount: str | None = None,
        ctx_manager=None,
        stop_event=None,
        log_file: Path | None = None,
        silent: bool = False
    ) -> int:
        """
        Add a virtio-fs shared folder configuration.

        For QEMU with virtio-fs mode, this adds a shared folder to the list
        which will be used when generating the libvirt domain XML.

        Note: In practice, virtio-fs setup is handled by lifecycle.py's
        _setup_virtiofs_shared_directories() method. This method is provided
        for API compatibility and manual configuration.

        Args:
            name: Tag name for the shared folder (e.g., 'run', 'vm')
            host_path: Path on host to share
            readonly: Whether to mount read-only
            guest_mount: Mount path in guest (e.g., '/adare/run')
            ctx_manager: Optional context manager for status updates
            stop_event: Optional threading event to signal cancellation
            log_file: Optional path to log file
            silent: If True, suppress log output

        Returns:
            0 for success

        Raises:
            UnsupportedFeatureException: If libguestfs mode is active (no virtio-fs)
        """
        if not _use_shared_folder_mode():
            raise UnsupportedFeatureException(
                "Shared folders require virtio-fs mode. "
                "Unset QEMU_LIBGUESTFS environment variable to enable virtio-fs."
            )

        if not silent:
            log.info(f"Configuring virtio-fs shared folder: {name} -> {host_path}")

        # Store configuration in VM config
        if hasattr(self, 'config'):
            self.config.virtiofs_enabled = True
            if self.config.virtiofs_shares is None:
                self.config.virtiofs_shares = []

            # Check if share with this tag already exists
            existing_idx = None
            for idx, share in enumerate(self.config.virtiofs_shares):
                if share['tag'] == name:
                    existing_idx = idx
                    break

            new_share = {
                'tag': name,
                'host_path': str(host_path),
                'guest_mount': guest_mount or f'/adare/{name}',
                'readonly': readonly
            }

            if existing_idx is not None:
                self.config.virtiofs_shares[existing_idx] = new_share
            else:
                self.config.virtiofs_shares.append(new_share)

            self._save_vm_config()

        return 0

    async def mount_shared_folder(
        self,
        name: str,
        mountpoint: Path,
        ctx_manager=None,
        stop_event=None,
        log_file: Path | None = None,
        silent: bool = False
    ) -> bool:
        """
        Mount shared folder in guest (handled by lifecycle.py for QEMU).

        For QEMU, virtio-fs mounting is handled by lifecycle.py's
        _mount_virtiofs_linux() or _verify_windows_virtiofs_mount() methods.

        This method is a no-op since mounting is done during VM initialization.

        Returns:
            True (mounting is handled elsewhere)
        """
        if not silent:
            log.debug(f"mount_shared_folder called for '{name}' - handled by lifecycle.py")
        return True

    async def list_shared_folders(
        self,
        ctx_manager=None,
        stop_event=None,
        log_file: Path | None = None,
        silent: bool = False
    ) -> dict[str, SharedFolderConfig]:
        """
        List shared folders configured for the VM.

        Returns all virtio-fs shares if configured.

        Returns:
            Dict mapping tag names to SharedFolderConfig objects
        """
        if hasattr(self, 'config') and self.config.virtiofs_enabled and self.config.virtiofs_shares:
            shares = {}
            for share in self.config.virtiofs_shares:
                shares[share['tag']] = SharedFolderConfig(
                    name=share['tag'],
                    host_path=Path(share['host_path']),
                    readonly=share.get('readonly', False)
                )
            return shares
        return {}

    async def remove_shared_folder(
        self,
        name: str,
        mountpoint: str | None = None,
        ctx_manager=None,
        stop_event=None,
        log_file: Path | None = None,
        silent: bool = False
    ) -> int:
        """
        Remove a specific shared folder configuration by tag name.

        For QEMU, this removes the share with the given tag from the list.

        Returns:
            0 (success)
        """
        if hasattr(self, 'config') and self.config.virtiofs_shares:
            original_len = len(self.config.virtiofs_shares)
            self.config.virtiofs_shares = [
                s for s in self.config.virtiofs_shares if s['tag'] != name
            ]
            if len(self.config.virtiofs_shares) < original_len:
                self._save_vm_config()
                if not silent:
                    log.debug(f"Removed virtio-fs share '{name}'")
            # Disable virtiofs if no shares left
            if not self.config.virtiofs_shares:
                self.config.virtiofs_enabled = False
                self._save_vm_config()
        return 0

    async def remove_all_shared_folders(
        self,
        ctx_manager=None,
        stop_event=None,
        log_file: Path | None = None,
        silent: bool = False
    ) -> int:
        """
        Remove all shared folder configurations (clears all virtio-fs shares).

        For QEMU, this clears all virtio-fs share configurations from the VM config.

        Returns:
            0 (success)
        """
        if hasattr(self, 'config') and self.config.virtiofs_enabled:
            self.config.virtiofs_enabled = False
            self.config.virtiofs_shares = []
            self._save_vm_config()
            if not silent:
                log.debug("Cleared all virtio-fs share configurations")
        return 0

    def queue_mount_shared_folder(self, name: str, mountpoint: Path):
        """
        Queue a shared folder for mounting (no-op for QEMU).

        For QEMU, virtio-fs mounting is handled by lifecycle.py during
        VM initialization. This method exists for API compatibility.
        """
        log.debug(f"queue_mount_shared_folder for '{name}' - handled by lifecycle.py")

    async def mount_multiple_shared_folders(
        self,
        folders: dict,
        ctx_manager=None,
        stop_event=None,
        log_file: Path | None = None,
        silent: bool = False
    ) -> int:
        """
        Mount multiple shared folders (handled by lifecycle.py for QEMU).

        For QEMU, virtio-fs uses multiple shared directories, each with its own
        filesystem device in libvirt XML. The mounting is handled by lifecycle.py
        during VM initialization (_mount_virtiofs_linux or _mount_virtiofs_windows).

        Returns:
            0 (success, mounting handled elsewhere)
        """
        if not silent:
            log.debug("mount_multiple_shared_folders - handled by lifecycle.py")
        return 0
