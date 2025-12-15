"""
DEPRECATED: Use adare.hypervisor.virtualbox.models and adare.hypervisor.exceptions instead.

Backward compatibility shim for VirtualBox models and exceptions.
"""
import warnings

warnings.warn(
    "adare.virtualbox.models is deprecated, use adare.hypervisor.virtualbox.models and adare.hypervisor.exceptions instead",
    DeprecationWarning,
    stacklevel=2
)

# Import from new location
from adare.hypervisor.virtualbox.models import PortForwardingRule, SharedFolderConfig, CommandResult
from adare.hypervisor.exceptions import VMImportException, VMAlreadyRunningException, VMNotFoundException

__all__ = [
    'PortForwardingRule',
    'SharedFolderConfig',
    'CommandResult',
    'VMImportException',
    'VMAlreadyRunningException',
    'VMNotFoundException',
]

# Keep original imports
import logging
from dataclasses import dataclass
from typing import Optional

from adare.exceptions import LoggedErrorException

log = logging.getLogger(__name__)


@dataclass
class PortForwardingRule:
    """Represents a VirtualBox NAT port forwarding rule."""
    name: str
    protocol: str  # 'tcp' or 'udp'
    host_ip: str = ""
    host_port: int = 0
    guest_ip: str = ""
    guest_port: int = 0
    
    def matches(self, other: 'PortForwardingRule') -> bool:
        """Check if this rule is identical to another rule."""
        return (self.protocol == other.protocol and
                self.host_ip == other.host_ip and
                self.host_port == other.host_port and
                self.guest_ip == other.guest_ip and
                self.guest_port == other.guest_port)
    
    def to_vbox_format(self) -> str:
        """Convert to VirtualBox command format."""
        return f"{self.name},{self.protocol},{self.host_ip},{self.host_port},{self.guest_ip},{self.guest_port}"
    
    @classmethod
    def from_vbox_format(cls, vbox_string: str) -> 'PortForwardingRule':
        """Create PortForwardingRule from VirtualBox output format."""
        # Parse: "name,protocol,host_ip,host_port,guest_ip,guest_port"
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


@dataclass
class SharedFolderConfig:
    """Represents a VirtualBox shared folder configuration."""
    name: str
    host_path: str
    readonly: bool = False
    
    def matches(self, other: 'SharedFolderConfig') -> bool:
        """Check if this shared folder config is identical to another."""
        return (self.name == other.name and
                self.host_path == other.host_path and
                self.readonly == other.readonly)


@dataclass
class CommandResult:
    """Result of a VirtualBox command execution."""
    returncode: int
    stdout: str
    stderr: str
    duration: int

    def __init__(self, returncode: int, stdout: str, stderr: str, duration: int):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.duration = duration


class VMImportException(LoggedErrorException):
    def __init__(self, message: str):
        super().__init__(log, message)


class VMAlreadyRunningException(LoggedErrorException):
    def __init__(self, message: str):
        super().__init__(log, message)


class VMNotFoundException(LoggedErrorException):
    def __init__(self, message: str):
        super().__init__(log, message)