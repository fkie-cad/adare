"""
VirtualBox-specific data models.

Extends base hypervisor models with VirtualBox-specific format conversion.
"""
import logging
from dataclasses import dataclass

from adare.hypervisor.base.models import (
    PortForwardingRule as BasePortForwardingRule,
    SharedFolderConfig as BaseSharedFolderConfig,
    CommandResult as BaseCommandResult
)

log = logging.getLogger(__name__)


@dataclass
class PortForwardingRule(BasePortForwardingRule):
    """
    VirtualBox port forwarding rule with VirtualBox-specific format conversion.
    """

    def to_vbox_format(self) -> str:
        """
        Convert to VirtualBox command format.

        Returns:
            String in VirtualBox format: "name,protocol,host_ip,host_port,guest_ip,guest_port"
        """
        return f"{self.name},{self.protocol},{self.host_ip},{self.host_port},{self.guest_ip},{self.guest_port}"

    @classmethod
    def from_vbox_format(cls, vbox_string: str) -> 'PortForwardingRule':
        """
        Create PortForwardingRule from VirtualBox output format.

        Args:
            vbox_string: String in format "name,protocol,host_ip,host_port,guest_ip,guest_port"

        Returns:
            PortForwardingRule instance

        Raises:
            ValueError: If format is invalid
        """
        parts = vbox_string.split(',')
        if len(parts) != 6:
            raise ValueError(f"Invalid VirtualBox port forwarding format: {vbox_string}")

        name, protocol, host_ip, host_port_str, guest_ip, guest_port_str = parts
        return cls(
            name=name,
            protocol=protocol,
            host_ip=host_ip,
            host_port=int(host_port_str) if host_port_str.isdigit() else 0,
            guest_ip=guest_ip,
            guest_port=int(guest_port_str) if guest_port_str.isdigit() else 0
        )


# SharedFolderConfig and CommandResult can use base implementations directly
# Re-export them for backward compatibility
SharedFolderConfig = BaseSharedFolderConfig
CommandResult = BaseCommandResult
