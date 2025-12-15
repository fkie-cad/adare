"""
QEMU VM networking operations mixin.

Implements AbstractNetworkingMixin for QEMU with:
- Port forwarding via user-mode networking (hostfwd)
- No shared folder support (uses libguestfs + WebSocket instead)
"""
import logging
from pathlib import Path
from typing import Dict, Optional

from adare.hypervisor.base.mixins.networking import AbstractNetworkingMixin
from adare.hypervisor.exceptions import UnsupportedFeatureException
from adare.hypervisor.qemu.models import PortForwardingRule, SharedFolderConfig

log = logging.getLogger(__name__)


class NetworkingMixin(AbstractNetworkingMixin):
    """Mixin class providing networking operations for QEMU VMs."""

    # ==================== Port Forwarding ====================

    async def list_port_forwarding_rules(
        self,
        ctx_manager=None,
        stop_event=None,
        log_file: Optional[Path] = None,
        silent: bool = False
    ) -> Dict[str, PortForwardingRule]:
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
            log.warning("CLAUDE: VM config not available")
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
            log.debug(f"CLAUDE: Found {len(rules)} port forwarding rules")

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
        log_file: Optional[Path] = None,
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
            log.info(f"CLAUDE: Adding port forwarding rule '{name}': "
                    f"{protocol} {host_ip}:{host_port} -> {guest_ip}:{guest_port}")

        if not hasattr(self, 'config'):
            log.error("CLAUDE: VM config not available")
            return 1

        # Check if rule already exists
        if name in self.config.port_forwarding_rules:
            log.warning(f"CLAUDE: Port forwarding rule '{name}' already exists")
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
            log.info(f"CLAUDE: Successfully added port forwarding rule '{name}'")
            if self.get_state() == "running":
                log.warning("CLAUDE: VM is running. Port forwarding changes require VM restart.")

        return 0

    async def remove_port_forwarding(
        self,
        name: str,
        ctx_manager=None,
        stop_event=None,
        log_file: Optional[Path] = None,
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
            log.info(f"CLAUDE: Removing port forwarding rule '{name}'")

        if not hasattr(self, 'config'):
            log.error("CLAUDE: VM config not available")
            return 1

        if name not in self.config.port_forwarding_rules:
            log.warning(f"CLAUDE: Port forwarding rule '{name}' does not exist")
            return 0  # Consider success if already gone

        # Remove from config
        del self.config.port_forwarding_rules[name]

        # Save config
        self._save_vm_config()

        if not silent:
            log.info(f"CLAUDE: Successfully removed port forwarding rule '{name}'")
            if self.get_state() == "running":
                log.warning("CLAUDE: VM is running. Port forwarding changes require VM restart.")

        return 0

    # ==================== Shared Folders ====================
    # Shared folders are not supported for QEMU - use libguestfs + WebSocket instead

    async def add_shared_folder(
        self,
        name: str,
        host_path: Path,
        readonly: bool = False,
        ctx_manager=None,
        stop_event=None,
        log_file: Optional[Path] = None,
        silent: bool = False
    ) -> int:
        """
        Shared folders are not supported for QEMU.

        QEMU uses libguestfs for before/after VM lifecycle file operations,
        and WebSocket for runtime file operations.

        Raises:
            UnsupportedFeatureException: Always raised for QEMU
        """
        raise UnsupportedFeatureException(
            "Shared folders are not supported for QEMU hypervisor. "
            "Use libguestfs (before/after VM lifecycle) or WebSocket (runtime) for file operations."
        )

    async def mount_shared_folder(
        self,
        name: str,
        mountpoint: Path,
        ctx_manager=None,
        stop_event=None,
        log_file: Optional[Path] = None,
        silent: bool = False
    ) -> bool:
        """
        Shared folders are not supported for QEMU.

        Raises:
            UnsupportedFeatureException: Always raised for QEMU
        """
        raise UnsupportedFeatureException(
            "Shared folders are not supported for QEMU hypervisor. "
            "Use libguestfs (before/after VM lifecycle) or WebSocket (runtime) for file operations."
        )

    async def list_shared_folders(
        self,
        ctx_manager=None,
        stop_event=None,
        log_file: Optional[Path] = None,
        silent: bool = False
    ) -> Dict[str, SharedFolderConfig]:
        """
        List shared folders (always returns empty dict for QEMU).

        Returns:
            Empty dictionary (shared folders not supported)
        """
        return {}

    async def remove_shared_folder(
        self,
        name: str,
        mountpoint: Optional[str] = None,
        ctx_manager=None,
        stop_event=None,
        log_file: Optional[Path] = None,
        silent: bool = False
    ) -> int:
        """
        Remove shared folder (no-op for QEMU).

        Returns:
            0 (success, nothing to do)
        """
        if not silent:
            log.debug(f"CLAUDE: Ignoring remove_shared_folder for '{name}' (not supported on QEMU)")
        return 0

    async def remove_all_shared_folders(
        self,
        ctx_manager=None,
        stop_event=None,
        log_file: Optional[Path] = None,
        silent: bool = False
    ) -> int:
        """
        Remove all shared folders (no-op for QEMU).

        Returns:
            0 (success, nothing to do)
        """
        if not silent:
            log.debug("CLAUDE: Ignoring remove_all_shared_folders (not supported on QEMU)")
        return 0

    def queue_mount_shared_folder(self, name: str, mountpoint: Path):
        """
        Queue a shared folder for mounting (not supported for QEMU).

        This is a no-op for QEMU.
        """
        log.debug(f"CLAUDE: Ignoring queue_mount_shared_folder for '{name}' (not supported on QEMU)")

    async def mount_multiple_shared_folders(
        self,
        folders: dict,
        ctx_manager=None,
        stop_event=None,
        log_file: Optional[Path] = None,
        silent: bool = False
    ) -> int:
        """
        Mount multiple shared folders (not supported for QEMU).

        Returns:
            0 (success, nothing to do)
        """
        if not silent:
            log.debug("CLAUDE: Ignoring mount_multiple_shared_folders (not supported on QEMU)")
        return 0
