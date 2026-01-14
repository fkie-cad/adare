"""
Comprehensive unit tests for adare.hypervisor.qemu.models module.

Tests cover:
- PortForwardingRule QEMU-specific format conversion
- QEMUVMConfig dataclass serialization/deserialization
"""
import pytest
from adare.hypervisor.qemu.models import PortForwardingRule, QEMUVMConfig


# =============================================================================
# PortForwardingRule Tests
# =============================================================================

class TestPortForwardingRuleToQemuHostfwd:
    """Tests for PortForwardingRule.to_qemu_hostfwd() method."""

    @pytest.mark.parametrize("rule_kwargs,expected", [
        # Basic TCP forwarding: host:2222 -> guest:22
        pytest.param(
            dict(name="ssh", protocol="tcp", host_ip="", host_port=2222, guest_ip="", guest_port=22),
            "tcp::2222-:22",
            id="tcp_basic_ssh"
        ),
        # UDP forwarding
        pytest.param(
            dict(name="dns", protocol="udp", host_ip="", host_port=5353, guest_ip="", guest_port=53),
            "udp::5353-:53",
            id="udp_basic"
        ),
        # With explicit host IP
        pytest.param(
            dict(name="ssh_bound", protocol="tcp", host_ip="127.0.0.1", host_port=2222, guest_ip="", guest_port=22),
            "tcp:127.0.0.1:2222-:22",
            id="tcp_with_host_ip"
        ),
        # With explicit guest IP
        pytest.param(
            dict(name="web", protocol="tcp", host_ip="", host_port=8080, guest_ip="10.0.2.15", guest_port=80),
            "tcp::8080-10.0.2.15:80",
            id="tcp_with_guest_ip"
        ),
        # With both host and guest IP
        pytest.param(
            dict(name="full", protocol="tcp", host_ip="192.168.1.1", host_port=3000, guest_ip="10.0.2.15", guest_port=3000),
            "tcp:192.168.1.1:3000-10.0.2.15:3000",
            id="tcp_with_both_ips"
        ),
        # WebSocket port
        pytest.param(
            dict(name="ws", protocol="tcp", host_ip="", host_port=8765, guest_ip="", guest_port=8765),
            "tcp::8765-:8765",
            id="tcp_websocket"
        ),
        # High port numbers
        pytest.param(
            dict(name="high_port", protocol="tcp", host_ip="", host_port=65535, guest_ip="", guest_port=65534),
            "tcp::65535-:65534",
            id="tcp_high_ports"
        ),
    ])
    def test_to_qemu_hostfwd_formats(self, rule_kwargs, expected):
        """Test conversion to QEMU hostfwd format."""
        rule = PortForwardingRule(**rule_kwargs)
        assert rule.to_qemu_hostfwd() == expected


class TestPortForwardingRuleFromQemuHostfwd:
    """Tests for PortForwardingRule.from_qemu_hostfwd() class method."""

    @pytest.mark.parametrize("hostfwd_string,expected_attrs", [
        # Basic TCP with empty IPs
        pytest.param(
            "tcp::2222-:22",
            dict(protocol="tcp", host_ip="", host_port=2222, guest_ip="", guest_port=22),
            id="tcp_basic"
        ),
        # UDP protocol
        pytest.param(
            "udp::5353-:53",
            dict(protocol="udp", host_ip="", host_port=5353, guest_ip="", guest_port=53),
            id="udp_basic"
        ),
        # With host IP
        pytest.param(
            "tcp:127.0.0.1:2222-:22",
            dict(protocol="tcp", host_ip="127.0.0.1", host_port=2222, guest_ip="", guest_port=22),
            id="tcp_with_host_ip"
        ),
        # With guest IP
        pytest.param(
            "tcp::8080-10.0.2.15:80",
            dict(protocol="tcp", host_ip="", host_port=8080, guest_ip="10.0.2.15", guest_port=80),
            id="tcp_with_guest_ip"
        ),
        # With both IPs
        pytest.param(
            "tcp:192.168.1.1:3000-10.0.2.15:3000",
            dict(protocol="tcp", host_ip="192.168.1.1", host_port=3000, guest_ip="10.0.2.15", guest_port=3000),
            id="tcp_with_both_ips"
        ),
    ])
    def test_from_qemu_hostfwd_parsing(self, hostfwd_string, expected_attrs):
        """Test parsing QEMU hostfwd format strings."""
        rule = PortForwardingRule.from_qemu_hostfwd(hostfwd_string)

        for attr, expected_value in expected_attrs.items():
            assert getattr(rule, attr) == expected_value

    def test_from_qemu_hostfwd_with_name(self):
        """Test that custom name is used when provided."""
        rule = PortForwardingRule.from_qemu_hostfwd("tcp::2222-:22", name="my_custom_name")
        assert rule.name == "my_custom_name"

    def test_from_qemu_hostfwd_default_name(self):
        """Test that default name is generated as protocol_guest_port."""
        rule = PortForwardingRule.from_qemu_hostfwd("tcp::2222-:22")
        assert rule.name == "tcp_22"

        rule_udp = PortForwardingRule.from_qemu_hostfwd("udp::5353-:53")
        assert rule_udp.name == "udp_53"

    @pytest.mark.parametrize("invalid_string", [
        pytest.param("", id="empty_string"),
        pytest.param("tcp", id="protocol_only"),
        pytest.param("tcp:2222", id="missing_guest"),
        pytest.param("tcp::abc-:22", id="non_numeric_host_port"),
        pytest.param("tcp::2222-:abc", id="non_numeric_guest_port"),
        pytest.param("invalid_format", id="no_colons"),
    ])
    def test_from_qemu_hostfwd_invalid_format(self, invalid_string):
        """Test that invalid formats raise ValueError."""
        with pytest.raises(ValueError, match="Invalid QEMU hostfwd format"):
            PortForwardingRule.from_qemu_hostfwd(invalid_string)


class TestPortForwardingRuleRoundtrip:
    """Tests for roundtrip conversion: to_qemu_hostfwd -> from_qemu_hostfwd."""

    @pytest.mark.parametrize("rule_kwargs", [
        pytest.param(
            dict(name="ssh", protocol="tcp", host_ip="", host_port=2222, guest_ip="", guest_port=22),
            id="basic_tcp"
        ),
        pytest.param(
            dict(name="udp_test", protocol="udp", host_ip="", host_port=5353, guest_ip="", guest_port=53),
            id="basic_udp"
        ),
        pytest.param(
            dict(name="bound", protocol="tcp", host_ip="127.0.0.1", host_port=8080, guest_ip="", guest_port=80),
            id="with_host_ip"
        ),
        pytest.param(
            dict(name="guest", protocol="tcp", host_ip="", host_port=3000, guest_ip="10.0.2.15", guest_port=3000),
            id="with_guest_ip"
        ),
        pytest.param(
            dict(name="full", protocol="tcp", host_ip="192.168.1.1", host_port=9000, guest_ip="10.0.2.15", guest_port=9000),
            id="with_both_ips"
        ),
    ])
    def test_roundtrip_preserves_values(self, rule_kwargs):
        """Test that to_qemu_hostfwd() -> from_qemu_hostfwd() preserves all values except name."""
        original = PortForwardingRule(**rule_kwargs)
        hostfwd_string = original.to_qemu_hostfwd()
        restored = PortForwardingRule.from_qemu_hostfwd(hostfwd_string, name=original.name)

        assert restored.name == original.name
        assert restored.protocol == original.protocol
        assert restored.host_ip == original.host_ip
        assert restored.host_port == original.host_port
        assert restored.guest_ip == original.guest_ip
        assert restored.guest_port == original.guest_port


# =============================================================================
# QEMUVMConfig Tests
# =============================================================================

class TestQEMUVMConfigCreation:
    """Tests for QEMUVMConfig dataclass creation."""

    def test_creation_with_required_fields_only(self):
        """Test creating config with only required fields."""
        config = QEMUVMConfig(
            vm_name="test_vm",
            uuid="12345678-1234-1234-1234-123456789abc",
            guest_os="linux",
            disk_path="/path/to/disk.qcow2"
        )

        assert config.vm_name == "test_vm"
        assert config.uuid == "12345678-1234-1234-1234-123456789abc"
        assert config.guest_os == "linux"
        assert config.disk_path == "/path/to/disk.qcow2"

    def test_default_values(self):
        """Test that default values are correctly set."""
        config = QEMUVMConfig(
            vm_name="test_vm",
            uuid="12345678-1234-1234-1234-123456789abc",
            guest_os="linux",
            disk_path="/path/to/disk.qcow2"
        )

        assert config.cpus == 2
        assert config.ram == 2048
        assert config.machine == "pc"
        assert config.accel == "kvm"
        assert config.drive_format == "qcow2"
        assert config.network == "user"
        assert config.port_forwarding_rules == {}
        assert config.qmp_socket_path == ""
        assert config.guest_agent_socket_path == ""
        assert config.pid_file_path == ""
        assert config.is_external is False
        assert config.display_enabled is False
        assert config.vnc_port is None
        assert config.libvirt_domain_name is None
        assert config.serial_console_log_path is None
        assert config.qemu_debug_log_path is None

    def test_creation_with_all_fields(self):
        """Test creating config with all fields specified."""
        port_rules = {"ssh": {"protocol": "tcp", "host_port": 2222, "guest_port": 22}}
        config = QEMUVMConfig(
            vm_name="full_config_vm",
            uuid="abcdef12-3456-7890-abcd-ef1234567890",
            guest_os="windows",
            disk_path="/var/lib/vms/test.qcow2",
            cpus=4,
            ram=8192,
            machine="q35",
            accel="hvf",
            drive_format="raw",
            network="bridge",
            port_forwarding_rules=port_rules,
            qmp_socket_path="/tmp/qmp.sock",
            guest_agent_socket_path="/tmp/guest.sock",
            pid_file_path="/tmp/vm.pid",
            is_external=True,
            display_enabled=True,
            vnc_port=5901,
            libvirt_domain_name="my_libvirt_vm",
            serial_console_log_path="/var/log/serial.log",
            qemu_debug_log_path="/var/log/qemu.log"
        )

        assert config.vm_name == "full_config_vm"
        assert config.uuid == "abcdef12-3456-7890-abcd-ef1234567890"
        assert config.guest_os == "windows"
        assert config.disk_path == "/var/lib/vms/test.qcow2"
        assert config.cpus == 4
        assert config.ram == 8192
        assert config.machine == "q35"
        assert config.accel == "hvf"
        assert config.drive_format == "raw"
        assert config.network == "bridge"
        assert config.port_forwarding_rules == port_rules
        assert config.qmp_socket_path == "/tmp/qmp.sock"
        assert config.guest_agent_socket_path == "/tmp/guest.sock"
        assert config.pid_file_path == "/tmp/vm.pid"
        assert config.is_external is True
        assert config.display_enabled is True
        assert config.vnc_port == 5901
        assert config.libvirt_domain_name == "my_libvirt_vm"
        assert config.serial_console_log_path == "/var/log/serial.log"
        assert config.qemu_debug_log_path == "/var/log/qemu.log"

    def test_port_forwarding_rules_none_becomes_empty_dict(self):
        """Test that None for port_forwarding_rules becomes empty dict via __post_init__."""
        config = QEMUVMConfig(
            vm_name="test",
            uuid="uuid",
            guest_os="linux",
            disk_path="/disk.qcow2",
            port_forwarding_rules=None
        )
        assert config.port_forwarding_rules == {}


class TestQEMUVMConfigToDict:
    """Tests for QEMUVMConfig.to_dict() method."""

    def test_to_dict_contains_all_fields(self):
        """Test that to_dict() includes all 18 configuration fields."""
        config = QEMUVMConfig(
            vm_name="test_vm",
            uuid="test-uuid",
            guest_os="linux",
            disk_path="/path/to/disk.qcow2"
        )

        data = config.to_dict()

        # Verify all expected keys are present
        expected_keys = {
            "vm_name", "uuid", "guest_os", "disk_path",
            "cpus", "ram", "machine", "accel", "drive_format", "boot_mode", "network",
            "port_forwarding_rules", "qmp_socket_path", "guest_agent_socket_path",
            "pid_file_path", "is_external", "display_enabled", "vnc_port",
            "libvirt_domain_name", "serial_console_log_path", "qemu_debug_log_path"
        }
        assert set(data.keys()) == expected_keys

    def test_to_dict_values_match_config(self):
        """Test that to_dict() values match the config attributes."""
        port_rules = {"ws": {"protocol": "tcp", "host_port": 8765, "guest_port": 8765}}
        config = QEMUVMConfig(
            vm_name="my_vm",
            uuid="my-uuid-1234",
            guest_os="ubuntu",
            disk_path="/home/user/vms/test.qcow2",
            cpus=8,
            ram=16384,
            port_forwarding_rules=port_rules,
            display_enabled=True,
            vnc_port=5900
        )

        data = config.to_dict()

        assert data["vm_name"] == "my_vm"
        assert data["uuid"] == "my-uuid-1234"
        assert data["guest_os"] == "ubuntu"
        assert data["disk_path"] == "/home/user/vms/test.qcow2"
        assert data["cpus"] == 8
        assert data["ram"] == 16384
        assert data["port_forwarding_rules"] == port_rules
        assert data["display_enabled"] is True
        assert data["vnc_port"] == 5900


class TestQEMUVMConfigFromDict:
    """Tests for QEMUVMConfig.from_dict() class method."""

    def test_from_dict_creates_valid_config(self):
        """Test that from_dict() creates a valid config from a dictionary."""
        data = {
            "vm_name": "restored_vm",
            "uuid": "restored-uuid",
            "guest_os": "fedora",
            "disk_path": "/var/vms/fedora.qcow2",
            "cpus": 4,
            "ram": 4096,
            "machine": "q35",
            "accel": "kvm",
            "drive_format": "qcow2",
            "network": "user",
            "port_forwarding_rules": {},
            "qmp_socket_path": "/tmp/qmp.sock",
            "guest_agent_socket_path": "",
            "pid_file_path": "",
            "is_external": False,
            "display_enabled": False,
            "vnc_port": None,
            "libvirt_domain_name": None,
            "serial_console_log_path": None,
            "qemu_debug_log_path": None
        }

        config = QEMUVMConfig.from_dict(data)

        assert config.vm_name == "restored_vm"
        assert config.uuid == "restored-uuid"
        assert config.guest_os == "fedora"
        assert config.disk_path == "/var/vms/fedora.qcow2"
        assert config.cpus == 4
        assert config.ram == 4096
        assert config.machine == "q35"
        assert config.qmp_socket_path == "/tmp/qmp.sock"

    @pytest.mark.parametrize("missing_field,default_value", [
        pytest.param("display_enabled", False, id="display_enabled_default"),
        pytest.param("vnc_port", None, id="vnc_port_default"),
        pytest.param("libvirt_domain_name", None, id="libvirt_domain_name_default"),
        pytest.param("serial_console_log_path", None, id="serial_console_log_path_default"),
        pytest.param("qemu_debug_log_path", None, id="qemu_debug_log_path_default"),
    ])
    def test_from_dict_backward_compatibility(self, missing_field, default_value):
        """Test that from_dict() provides defaults for missing new fields (backward compatibility)."""
        # Create a dict without the field being tested
        data = {
            "vm_name": "old_vm",
            "uuid": "old-uuid",
            "guest_os": "linux",
            "disk_path": "/disk.qcow2",
            "cpus": 2,
            "ram": 2048,
            "machine": "pc",
            "accel": "kvm",
            "drive_format": "qcow2",
            "network": "user",
            "port_forwarding_rules": {},
            "qmp_socket_path": "",
            "guest_agent_socket_path": "",
            "pid_file_path": "",
            "is_external": False,
            "display_enabled": False,
            "vnc_port": None,
            "libvirt_domain_name": None,
            "serial_console_log_path": None,
            "qemu_debug_log_path": None
        }
        # Remove the field we're testing
        del data[missing_field]

        config = QEMUVMConfig.from_dict(data)

        assert getattr(config, missing_field) == default_value

    def test_from_dict_with_port_forwarding_rules(self):
        """Test from_dict() with populated port forwarding rules."""
        data = {
            "vm_name": "vm_with_ports",
            "uuid": "port-uuid",
            "guest_os": "linux",
            "disk_path": "/disk.qcow2",
            "cpus": 2,
            "ram": 2048,
            "machine": "pc",
            "accel": "kvm",
            "drive_format": "qcow2",
            "network": "user",
            "port_forwarding_rules": {
                "ssh": {"protocol": "tcp", "host_port": 2222, "guest_port": 22},
                "web": {"protocol": "tcp", "host_port": 8080, "guest_port": 80}
            },
            "qmp_socket_path": "",
            "guest_agent_socket_path": "",
            "pid_file_path": "",
            "is_external": False,
            "display_enabled": False,
            "vnc_port": None,
            "libvirt_domain_name": None,
            "serial_console_log_path": None,
            "qemu_debug_log_path": None
        }

        config = QEMUVMConfig.from_dict(data)

        assert len(config.port_forwarding_rules) == 2
        assert "ssh" in config.port_forwarding_rules
        assert config.port_forwarding_rules["ssh"]["guest_port"] == 22


class TestQEMUVMConfigRoundtrip:
    """Tests for roundtrip serialization: to_dict() -> from_dict()."""

    @pytest.mark.parametrize("config_kwargs", [
        pytest.param(
            dict(
                vm_name="minimal_vm",
                uuid="min-uuid",
                guest_os="linux",
                disk_path="/disk.qcow2"
            ),
            id="minimal_config"
        ),
        pytest.param(
            dict(
                vm_name="full_vm",
                uuid="full-uuid-1234-5678-abcd",
                guest_os="windows",
                disk_path="/var/lib/vms/win.qcow2",
                cpus=16,
                ram=32768,
                machine="q35",
                accel="hvf",
                drive_format="raw",
                network="bridge",
                port_forwarding_rules={"rdp": {"protocol": "tcp", "host_port": 3389, "guest_port": 3389}},
                qmp_socket_path="/run/qmp.sock",
                guest_agent_socket_path="/run/guest.sock",
                pid_file_path="/run/vm.pid",
                is_external=True,
                display_enabled=True,
                vnc_port=5905,
                libvirt_domain_name="windows_domain",
                serial_console_log_path="/var/log/serial.log",
                qemu_debug_log_path="/var/log/debug.log"
            ),
            id="full_config"
        ),
        pytest.param(
            dict(
                vm_name="typical_vm",
                uuid="typical-uuid",
                guest_os="ubuntu-22.04",
                disk_path="/home/user/vms/ubuntu.qcow2",
                cpus=4,
                ram=8192,
                port_forwarding_rules={
                    "ssh": {"protocol": "tcp", "host_port": 2222, "guest_port": 22},
                    "ws": {"protocol": "tcp", "host_port": 8765, "guest_port": 8765}
                },
                display_enabled=True
            ),
            id="typical_config"
        ),
    ])
    def test_roundtrip_preserves_all_values(self, config_kwargs):
        """Test that to_dict() -> from_dict() roundtrip preserves all values."""
        original = QEMUVMConfig(**config_kwargs)
        serialized = original.to_dict()
        restored = QEMUVMConfig.from_dict(serialized)

        # Compare all 18+ fields
        assert restored.vm_name == original.vm_name
        assert restored.uuid == original.uuid
        assert restored.guest_os == original.guest_os
        assert restored.disk_path == original.disk_path
        assert restored.cpus == original.cpus
        assert restored.ram == original.ram
        assert restored.machine == original.machine
        assert restored.accel == original.accel
        assert restored.drive_format == original.drive_format
        assert restored.network == original.network
        assert restored.port_forwarding_rules == original.port_forwarding_rules
        assert restored.qmp_socket_path == original.qmp_socket_path
        assert restored.guest_agent_socket_path == original.guest_agent_socket_path
        assert restored.pid_file_path == original.pid_file_path
        assert restored.is_external == original.is_external
        assert restored.display_enabled == original.display_enabled
        assert restored.vnc_port == original.vnc_port
        assert restored.libvirt_domain_name == original.libvirt_domain_name
        assert restored.serial_console_log_path == original.serial_console_log_path
        assert restored.qemu_debug_log_path == original.qemu_debug_log_path

    def test_roundtrip_with_dataclass_equality(self):
        """Test roundtrip creates an equivalent object (dataclass equality)."""
        original = QEMUVMConfig(
            vm_name="equality_test",
            uuid="eq-uuid",
            guest_os="linux",
            disk_path="/disk.qcow2",
            cpus=4,
            ram=4096
        )

        serialized = original.to_dict()
        restored = QEMUVMConfig.from_dict(serialized)

        # Dataclass generates __eq__ automatically
        assert restored == original


class TestQEMUVMConfigFieldCount:
    """Tests to verify all configuration fields are handled."""

    def test_to_dict_field_count(self):
        """Verify to_dict() returns exactly 20 fields."""
        config = QEMUVMConfig(
            vm_name="test",
            uuid="uuid",
            guest_os="linux",
            disk_path="/disk.qcow2"
        )
        data = config.to_dict()
        # 4 required + 17 optional = 21 total fields
        assert len(data) == 21

    def test_all_dataclass_fields_in_to_dict(self):
        """Verify all dataclass fields are included in to_dict()."""
        config = QEMUVMConfig(
            vm_name="test",
            uuid="uuid",
            guest_os="linux",
            disk_path="/disk.qcow2"
        )
        data = config.to_dict()

        # Get all dataclass field names
        from dataclasses import fields
        dataclass_field_names = {f.name for f in fields(config)}

        # All dataclass fields should be in the dict
        assert set(data.keys()) == dataclass_field_names
