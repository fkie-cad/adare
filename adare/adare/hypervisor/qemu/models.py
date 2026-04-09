"""
QEMU-specific data models.

Extends base hypervisor models with QEMU-specific format conversion.
"""
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List

from adare.hypervisor.base.models import (
    PortForwardingRule as BasePortForwardingRule,
    SharedFolderConfig as BaseSharedFolderConfig,
    CommandResult as BaseCommandResult
)

log = logging.getLogger(__name__)


@dataclass
class PortForwardingRule(BasePortForwardingRule):
    """
    QEMU port forwarding rule with QEMU-specific format conversion.
    """

    def to_qemu_hostfwd(self) -> str:
        """
        Convert to QEMU hostfwd format for user networking.

        Returns:
            String in QEMU format: "tcp::host_port-guest_ip:guest_port" or "udp::host_port-guest_ip:guest_port"

        Example:
            "tcp::2222-:22" forwards host port 2222 to guest port 22
        """
        guest_ip_str = f"{self.guest_ip}:" if self.guest_ip else ":"
        host_ip_str = f"{self.host_ip}:" if self.host_ip else ":"
        return f"{self.protocol}:{host_ip_str}{self.host_port}-{guest_ip_str}{self.guest_port}"

    @classmethod
    def from_qemu_hostfwd(cls, hostfwd_string: str, name: str = "") -> 'PortForwardingRule':
        """
        Create PortForwardingRule from QEMU hostfwd format.

        Args:
            hostfwd_string: String in format "tcp::host_port-guest_ip:guest_port"
            name: Optional name for the rule

        Returns:
            PortForwardingRule instance

        Raises:
            ValueError: If format is invalid
        """
        try:
            # Parse format: protocol:host_ip:host_port-guest_ip:guest_port
            protocol, rest = hostfwd_string.split(':', 1)
            host_part, guest_part = rest.split('-', 1)

            # Parse host part (may be ":port" or "ip:port")
            host_parts = host_part.split(':')
            if len(host_parts) == 1:
                host_ip = ""
                host_port = int(host_parts[0])
            elif len(host_parts) == 2:
                host_ip = host_parts[0]
                host_port = int(host_parts[1])
            else:
                raise ValueError(f"Invalid host part: {host_part}")

            # Parse guest part (may be ":port" or "ip:port")
            guest_parts = guest_part.split(':')
            if len(guest_parts) == 1:
                guest_ip = ""
                guest_port = int(guest_parts[0])
            elif len(guest_parts) == 2:
                guest_ip = guest_parts[0]
                guest_port = int(guest_parts[1])
            else:
                raise ValueError(f"Invalid guest part: {guest_part}")

            return cls(
                name=name or f"{protocol}_{guest_port}",
                protocol=protocol,
                host_ip=host_ip,
                host_port=host_port,
                guest_ip=guest_ip,
                guest_port=guest_port
            )
        except (ValueError, IndexError) as e:
            raise ValueError(f"Invalid QEMU hostfwd format '{hostfwd_string}': {e}")


# SharedFolderConfig and CommandResult can use base implementations directly
# Re-export them for backward compatibility
SharedFolderConfig = BaseSharedFolderConfig
CommandResult = BaseCommandResult


@dataclass
class QEMUVMConfig:
    """
    QEMU VM configuration stored in JSON format.

    This configuration is saved to a JSON file for each VM to persist its settings.
    """
    vm_name: str
    uuid: str
    guest_os: str
    disk_path: str
    architecture: str = 'x86_64'  # 'x86_64' or 'aarch64'
    cpus: int = 2
    ram: int = 2048  # MB
    machine: str = 'pc'
    accel: str = 'kvm'
    drive_format: str = 'qcow2'
    boot_mode: str = 'bios'  # 'bios' or 'uefi'
    network: str = 'user'
    port_forwarding_rules: Dict[str, Dict[str, Any]] = None  # Serialized port forwarding rules
    qmp_socket_path: str = ""  # Path to QMP monitor socket
    guest_agent_socket_path: str = ""  # Path to guest agent socket
    pid_file_path: str = ""  # Path to PID file for running VM
    is_external: bool = False  # True if disk is external (--no-copy mode)

    # Display configuration (for libvirt integration)
    display_enabled: bool = False  # False = headless (virt-manager can still connect via VNC)
    vnc_port: Optional[int] = None  # None = autoport, or specify explicit port
    libvirt_domain_name: Optional[str] = None  # Track libvirt domain name

    # VM logging configuration (for experiment runs)
    serial_console_log_path: Optional[str] = None  # Path to serial console log
    qemu_debug_log_path: Optional[str] = None      # Path to QEMU debug log

    # virtio-fs shared directory configuration
    # When enabled, uses virtio-fs instead of libguestfs for file transfer
    virtiofs_enabled: bool = True  # Default to virtio-fs mode
    virtiofs_shares: List[Dict[str, Any]] = field(default_factory=list)  # List of share configs

    # SMB share path — ephemeral temp dir for QEMU SLIRP SMB sharing (macOS)
    smb_share_path: Optional[str] = None

    def __post_init__(self):
        """Initialize empty collections if None."""
        if self.port_forwarding_rules is None:
            self.port_forwarding_rules = {}
        # Defensive: ensure virtiofs_shares is never None even if set externally
        if self.virtiofs_shares is None:
            self.virtiofs_shares = []

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary for JSON serialization."""
        return {
            'vm_name': self.vm_name,
            'uuid': self.uuid,
            'guest_os': self.guest_os,
            'disk_path': self.disk_path,
            'architecture': self.architecture,
            'cpus': self.cpus,
            'ram': self.ram,
            'machine': self.machine,
            'accel': self.accel,
            'drive_format': self.drive_format,
            'boot_mode': self.boot_mode,
            'network': self.network,
            'port_forwarding_rules': self.port_forwarding_rules,
            'qmp_socket_path': self.qmp_socket_path,
            'guest_agent_socket_path': self.guest_agent_socket_path,
            'pid_file_path': self.pid_file_path,
            'is_external': self.is_external,
            'display_enabled': self.display_enabled,
            'vnc_port': self.vnc_port,
            'libvirt_domain_name': self.libvirt_domain_name,
            'serial_console_log_path': self.serial_console_log_path,
            'qemu_debug_log_path': self.qemu_debug_log_path,
            'virtiofs_enabled': self.virtiofs_enabled,
            'virtiofs_shares': self.virtiofs_shares,
            'smb_share_path': self.smb_share_path,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'QEMUVMConfig':
        """Create config from dictionary (JSON deserialization).

        Provides backward compatibility for VMs created before libvirt integration
        and for migration from single virtiofs_shared_dir to multiple shares.
        """
        # Provide defaults for new fields if missing (backward compatibility)
        data.setdefault('display_enabled', False)
        data.setdefault('vnc_port', None)
        data.setdefault('libvirt_domain_name', None)
        data.setdefault('serial_console_log_path', None)
        data.setdefault('qemu_debug_log_path', None)
        data.setdefault('boot_mode', 'bios')
        data.setdefault('architecture', 'x86_64')

        # virtio-fs defaults and backward compatibility
        data.setdefault('virtiofs_enabled', True)

        # Migrate old single-directory format to new multi-share format
        if 'virtiofs_shared_dir' in data:
            old_path = data.pop('virtiofs_shared_dir')
            if old_path and 'virtiofs_shares' not in data:
                # Convert old single-share to new list format
                data['virtiofs_shares'] = [{
                    'tag': 'adare',
                    'host_path': old_path,
                    'guest_mount': '/adare',
                    'readonly': False
                }]
                log.debug(f"Migrated old virtiofs_shared_dir to virtiofs_shares list")

        data.setdefault('virtiofs_shares', [])
        data.setdefault('smb_share_path', None)
        return cls(**data)
