"""
Hypervisor-agnostic data models.

These models represent common abstractions used across all hypervisor implementations.
"""
from dataclasses import dataclass


@dataclass
class PortForwardingRule:
    """
    Universal port forwarding rule representation.

    Used to forward ports from host to guest VM for network access.
    """
    name: str
    protocol: str  # 'tcp' or 'udp'
    host_ip: str = ""
    host_port: int = 0
    guest_ip: str = ""
    guest_port: int = 0

    def matches(self, other: 'PortForwardingRule') -> bool:
        """
        Check if this rule is functionally identical to another rule.

        Args:
            other: Another PortForwardingRule to compare

        Returns:
            True if rules are identical, False otherwise
        """
        return (self.protocol == other.protocol and
                self.host_ip == other.host_ip and
                self.host_port == other.host_port and
                self.guest_ip == other.guest_ip and
                self.guest_port == other.guest_port)


@dataclass
class SharedFolderConfig:
    """
    Universal shared folder configuration.

    Represents a folder shared between host and guest VM.
    """
    name: str
    host_path: str
    readonly: bool = False

    def matches(self, other: 'SharedFolderConfig') -> bool:
        """
        Check if this shared folder config is identical to another.

        Args:
            other: Another SharedFolderConfig to compare

        Returns:
            True if configurations are identical, False otherwise
        """
        return (self.name == other.name and
                self.host_path == other.host_path and
                self.readonly == other.readonly)


@dataclass
class CommandResult:
    """
    Result of a command execution in a VM.

    Captures return code, output streams, and execution duration.
    """
    returncode: int
    stdout: str
    stderr: str
    duration: int | None = None  # Duration in seconds
