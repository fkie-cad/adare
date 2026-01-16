"""
Unit tests for adare/hypervisor/qemu/libvirt_xml.py

Tests the generate_domain_xml() function for correct XML generation
across various QEMUVMConfig configurations.
"""
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Dict, Any, Optional
from unittest.mock import patch

import pytest

from adare.hypervisor.qemu.libvirt_xml import (
    generate_domain_xml,
    QEMU_NAMESPACE,
    _add_qemu_arg,
    _prettify_xml,
)
from adare.hypervisor.qemu.models import QEMUVMConfig


# --- Test Fixtures ---

@pytest.fixture
def minimal_vm_config():
    """Create a minimal QEMUVMConfig for testing."""
    return QEMUVMConfig(
        vm_name="test-vm",
        uuid="12345678-1234-1234-1234-123456789abc",
        guest_os="linux",
        disk_path="/tmp/test-disk.qcow2",
        qmp_socket_path="/tmp/test-vm-qmp.sock",
        guest_agent_socket_path="/tmp/test-vm-ga.sock",
    )


@pytest.fixture
def full_vm_config():
    """Create a fully-configured QEMUVMConfig for testing."""
    return QEMUVMConfig(
        vm_name="full-test-vm",
        uuid="abcdef12-3456-7890-abcd-ef1234567890",
        guest_os="windows",
        disk_path="/var/lib/adare/disks/windows.qcow2",
        cpus=4,
        ram=8192,
        machine="q35",
        accel="kvm",
        drive_format="qcow2",
        network="user",
        port_forwarding_rules={
            "ssh": {
                "protocol": "tcp",
                "host_port": 2222,
                "guest_port": 22,
                "host_ip": "",
                "guest_ip": "",
            },
            "rdp": {
                "protocol": "tcp",
                "host_port": 3389,
                "guest_port": 3389,
                "host_ip": "127.0.0.1",
                "guest_ip": "10.0.2.15",
            },
        },
        qmp_socket_path="/var/run/adare/full-test-vm-qmp.sock",
        guest_agent_socket_path="/var/run/adare/full-test-vm-ga.sock",
        pid_file_path="/var/run/adare/full-test-vm.pid",
        display_enabled=True,
        vnc_port=5900,
        serial_console_log_path="/var/log/adare/full-test-vm-serial.log",
        qemu_debug_log_path="/var/log/adare/full-test-vm-debug.log",
    )


@pytest.fixture
def config_with_multiple_port_forwards():
    """Create a QEMUVMConfig with multiple port forwarding rules."""
    return QEMUVMConfig(
        vm_name="multi-port-vm",
        uuid="11111111-2222-3333-4444-555555555555",
        guest_os="linux",
        disk_path="/tmp/multi-port-disk.qcow2",
        qmp_socket_path="/tmp/multi-port-qmp.sock",
        guest_agent_socket_path="/tmp/multi-port-ga.sock",
        port_forwarding_rules={
            "ssh": {"protocol": "tcp", "host_port": 2222, "guest_port": 22},
            "http": {"protocol": "tcp", "host_port": 8080, "guest_port": 80},
            "https": {"protocol": "tcp", "host_port": 8443, "guest_port": 443},
            "dns": {"protocol": "udp", "host_port": 5353, "guest_port": 53},
        },
    )


def parse_xml_string(xml_str: str) -> ET.Element:
    """Parse XML string and return the root element."""
    return ET.fromstring(xml_str)


def find_with_namespace(root: ET.Element, path: str) -> ET.Element:
    """Find element using namespace-aware path."""
    namespaces = {"qemu": QEMU_NAMESPACE}
    return root.find(path, namespaces)


def findall_with_namespace(root: ET.Element, path: str) -> list:
    """Find all elements using namespace-aware path."""
    namespaces = {"qemu": QEMU_NAMESPACE}
    return root.findall(path, namespaces)


# --- Test Basic XML Structure ---

class TestBasicXMLStructure:
    """Tests for basic XML structure and validity."""

    def test_returns_valid_xml_string(self, minimal_vm_config):
        """Test that generate_domain_xml returns a valid XML string."""
        xml_str = generate_domain_xml(minimal_vm_config)

        assert isinstance(xml_str, str)
        assert len(xml_str) > 0
        # Should parse without error
        root = parse_xml_string(xml_str)
        assert root is not None

    def test_root_element_is_domain(self, minimal_vm_config):
        """Test that root element is 'domain' with type='kvm'."""
        xml_str = generate_domain_xml(minimal_vm_config)
        root = parse_xml_string(xml_str)

        assert root.tag == "domain"
        assert root.get("type") == "kvm"

    def test_contains_qemu_namespace(self, minimal_vm_config):
        """Test that XML contains QEMU namespace declaration."""
        xml_str = generate_domain_xml(minimal_vm_config)
        root = parse_xml_string(xml_str)

        # The namespace should be declared in the root element
        assert f"xmlns:qemu" in xml_str or f'xmlns:qemu="{QEMU_NAMESPACE}"' in xml_str


class TestRequiredDomainElements:
    """Tests for required domain elements."""

    def test_contains_name_element(self, minimal_vm_config):
        """Test that XML contains name element with correct value."""
        xml_str = generate_domain_xml(minimal_vm_config)
        root = parse_xml_string(xml_str)

        name_elem = root.find("name")
        assert name_elem is not None
        assert name_elem.text == "test-vm"

    def test_contains_uuid_element(self, minimal_vm_config):
        """Test that XML contains uuid element with correct value."""
        xml_str = generate_domain_xml(minimal_vm_config)
        root = parse_xml_string(xml_str)

        uuid_elem = root.find("uuid")
        assert uuid_elem is not None
        assert uuid_elem.text == "12345678-1234-1234-1234-123456789abc"

    def test_contains_memory_element(self, minimal_vm_config):
        """Test that XML contains memory element."""
        xml_str = generate_domain_xml(minimal_vm_config)
        root = parse_xml_string(xml_str)

        memory_elem = root.find("memory")
        assert memory_elem is not None
        assert memory_elem.get("unit") == "MiB"
        assert memory_elem.text == str(minimal_vm_config.ram)

    def test_contains_current_memory_element(self, minimal_vm_config):
        """Test that XML contains currentMemory element."""
        xml_str = generate_domain_xml(minimal_vm_config)
        root = parse_xml_string(xml_str)

        current_mem = root.find("currentMemory")
        assert current_mem is not None
        assert current_mem.get("unit") == "MiB"
        assert current_mem.text == str(minimal_vm_config.ram)

    def test_contains_vcpu_element(self, minimal_vm_config):
        """Test that XML contains vcpu element."""
        xml_str = generate_domain_xml(minimal_vm_config)
        root = parse_xml_string(xml_str)

        vcpu_elem = root.find("vcpu")
        assert vcpu_elem is not None
        assert vcpu_elem.get("placement") == "static"
        assert vcpu_elem.text == str(minimal_vm_config.cpus)

    def test_contains_os_element(self, minimal_vm_config):
        """Test that XML contains os element with proper configuration."""
        xml_str = generate_domain_xml(minimal_vm_config)
        root = parse_xml_string(xml_str)

        os_elem = root.find("os")
        assert os_elem is not None

        os_type = os_elem.find("type")
        assert os_type is not None
        assert os_type.text == "hvm"
        assert os_type.get("arch") == "x86_64"
        assert os_type.get("machine") == minimal_vm_config.machine

        boot = os_elem.find("boot")
        assert boot is not None
        assert boot.get("dev") == "hd"

    def test_contains_features_element(self, minimal_vm_config):
        """Test that XML contains features element with ACPI and APIC."""
        xml_str = generate_domain_xml(minimal_vm_config)
        root = parse_xml_string(xml_str)

        features = root.find("features")
        assert features is not None
        assert features.find("acpi") is not None
        assert features.find("apic") is not None

    def test_contains_devices_element(self, minimal_vm_config):
        """Test that XML contains devices element."""
        xml_str = generate_domain_xml(minimal_vm_config)
        root = parse_xml_string(xml_str)

        devices = root.find("devices")
        assert devices is not None


class TestQMPSocketConfiguration:
    """Tests for QMP socket configuration."""

    def test_qmp_socket_in_qemu_commandline(self, minimal_vm_config):
        """Test that QMP socket path is included in qemu:commandline."""
        xml_str = generate_domain_xml(minimal_vm_config)
        root = parse_xml_string(xml_str)

        # Find qemu:commandline element
        qemu_cmdline = find_with_namespace(root, "qemu:commandline")
        assert qemu_cmdline is not None

        # Find all qemu:arg elements
        args = findall_with_namespace(qemu_cmdline, "qemu:arg")
        arg_values = [arg.get("value") for arg in args]

        # Check for -qmp argument
        assert "-qmp" in arg_values

        # Check for the socket path
        qmp_index = arg_values.index("-qmp")
        expected_socket = f"unix:{minimal_vm_config.qmp_socket_path},server=on,wait=off"
        assert arg_values[qmp_index + 1] == expected_socket


class TestGuestAgentConfiguration:
    """Tests for guest agent channel configuration."""

    def test_guest_agent_channel_exists(self, minimal_vm_config):
        """Test that guest agent channel is configured."""
        xml_str = generate_domain_xml(minimal_vm_config)
        root = parse_xml_string(xml_str)

        devices = root.find("devices")
        channel = devices.find("channel[@type='unix']")
        assert channel is not None

    def test_guest_agent_socket_path(self, minimal_vm_config):
        """Test that guest agent socket path is correct."""
        xml_str = generate_domain_xml(minimal_vm_config)
        root = parse_xml_string(xml_str)

        devices = root.find("devices")
        channel = devices.find("channel[@type='unix']")
        source = channel.find("source")

        assert source is not None
        assert source.get("mode") == "bind"
        assert source.get("path") == minimal_vm_config.guest_agent_socket_path

    def test_guest_agent_target_configuration(self, minimal_vm_config):
        """Test that guest agent target is properly configured."""
        xml_str = generate_domain_xml(minimal_vm_config)
        root = parse_xml_string(xml_str)

        devices = root.find("devices")
        channel = devices.find("channel[@type='unix']")
        target = channel.find("target")

        assert target is not None
        assert target.get("type") == "virtio"
        assert target.get("name") == "org.qemu.guest_agent.0"


class TestPortForwardingRules:
    """Tests for port forwarding rule serialization."""

    def test_no_port_forwarding_uses_libvirt_interface(self, minimal_vm_config):
        """Test that VMs without port forwarding use libvirt-managed interface."""
        xml_str = generate_domain_xml(minimal_vm_config)
        root = parse_xml_string(xml_str)

        devices = root.find("devices")
        interface = devices.find("interface[@type='user']")

        assert interface is not None
        model = interface.find("model")
        assert model is not None
        assert model.get("type") == "virtio"

    def test_port_forwarding_uses_qemu_commandline(self, full_vm_config):
        """Test that port forwarding is configured via qemu:commandline."""
        xml_str = generate_domain_xml(full_vm_config)
        root = parse_xml_string(xml_str)

        qemu_cmdline = find_with_namespace(root, "qemu:commandline")
        args = findall_with_namespace(qemu_cmdline, "qemu:arg")
        arg_values = [arg.get("value") for arg in args]

        # Should have -netdev argument
        assert "-netdev" in arg_values

    def test_port_forwarding_netdev_format(self, full_vm_config):
        """Test that netdev argument contains correct hostfwd format."""
        xml_str = generate_domain_xml(full_vm_config)
        root = parse_xml_string(xml_str)

        qemu_cmdline = find_with_namespace(root, "qemu:commandline")
        args = findall_with_namespace(qemu_cmdline, "qemu:arg")
        arg_values = [arg.get("value") for arg in args]

        netdev_index = arg_values.index("-netdev")
        netdev_value = arg_values[netdev_index + 1]

        assert netdev_value.startswith("user,id=net0")
        # Check SSH rule (no host_ip)
        assert "hostfwd=tcp::2222-:22" in netdev_value
        # Check RDP rule (with host_ip and guest_ip)
        assert "hostfwd=tcp:127.0.0.1:3389-10.0.2.15:3389" in netdev_value

    def test_port_forwarding_includes_device(self, full_vm_config):
        """Test that port forwarding includes -device virtio-net-pci."""
        xml_str = generate_domain_xml(full_vm_config)
        root = parse_xml_string(xml_str)

        qemu_cmdline = find_with_namespace(root, "qemu:commandline")
        args = findall_with_namespace(qemu_cmdline, "qemu:arg")
        arg_values = [arg.get("value") for arg in args]

        assert "-device" in arg_values
        device_index = arg_values.index("-device")
        assert arg_values[device_index + 1] == "virtio-net-pci,netdev=net0"

    def test_port_forwarding_no_libvirt_interface(self, full_vm_config):
        """Test that VMs with port forwarding don't use libvirt interface."""
        xml_str = generate_domain_xml(full_vm_config)
        root = parse_xml_string(xml_str)

        devices = root.find("devices")
        interface = devices.find("interface[@type='user']")

        # Should not have libvirt-managed interface when port forwarding exists
        assert interface is None

    def test_multiple_port_forwarding_rules(self, config_with_multiple_port_forwards):
        """Test that multiple port forwarding rules are all included."""
        xml_str = generate_domain_xml(config_with_multiple_port_forwards)
        root = parse_xml_string(xml_str)

        qemu_cmdline = find_with_namespace(root, "qemu:commandline")
        args = findall_with_namespace(qemu_cmdline, "qemu:arg")
        arg_values = [arg.get("value") for arg in args]

        netdev_index = arg_values.index("-netdev")
        netdev_value = arg_values[netdev_index + 1]

        # All rules should be present
        assert "hostfwd=tcp::2222-:22" in netdev_value
        assert "hostfwd=tcp::8080-:80" in netdev_value
        assert "hostfwd=tcp::8443-:443" in netdev_value
        assert "hostfwd=udp::5353-:53" in netdev_value


class TestDisplayConfiguration:
    """Tests for display configuration variations."""

    def test_display_disabled_still_has_vnc(self, minimal_vm_config):
        """Test that display_enabled=False still configures VNC for on-demand access."""
        xml_str = generate_domain_xml(minimal_vm_config, display_enabled=False)
        root = parse_xml_string(xml_str)

        devices = root.find("devices")
        graphics = devices.find("graphics[@type='vnc']")

        assert graphics is not None
        assert graphics.get("autoport") == "yes"
        assert graphics.get("listen") == "127.0.0.1"

    def test_display_enabled_has_vnc(self, minimal_vm_config):
        """Test that display_enabled=True configures VNC."""
        xml_str = generate_domain_xml(minimal_vm_config, display_enabled=True)
        root = parse_xml_string(xml_str)

        devices = root.find("devices")
        graphics = devices.find("graphics[@type='vnc']")

        assert graphics is not None

    def test_explicit_vnc_port(self, minimal_vm_config):
        """Test that explicit VNC port is used when provided."""
        xml_str = generate_domain_xml(minimal_vm_config, display_enabled=True, vnc_port=5901)
        root = parse_xml_string(xml_str)

        devices = root.find("devices")
        graphics = devices.find("graphics[@type='vnc']")

        assert graphics.get("port") == "5901"
        assert graphics.get("autoport") == "no"

    def test_autoport_when_no_vnc_port(self, minimal_vm_config):
        """Test that autoport is used when no VNC port specified."""
        xml_str = generate_domain_xml(minimal_vm_config, display_enabled=True)
        root = parse_xml_string(xml_str)

        devices = root.find("devices")
        graphics = devices.find("graphics[@type='vnc']")

        assert graphics.get("port") == "-1"
        assert graphics.get("autoport") == "yes"

    def test_video_device_always_present(self, minimal_vm_config):
        """Test that video device is present regardless of display_enabled."""
        for display_enabled in [True, False]:
            xml_str = generate_domain_xml(minimal_vm_config, display_enabled=display_enabled)
            root = parse_xml_string(xml_str)

            devices = root.find("devices")
            video = devices.find("video")

            assert video is not None
            model = video.find("model")
            assert model is not None
            assert model.get("type") == "qxl"


class TestSerialConsoleConfiguration:
    """Tests for serial console logging configuration."""

    def test_console_without_log_path(self, minimal_vm_config):
        """Test console configuration when no log path is set."""
        xml_str = generate_domain_xml(minimal_vm_config)
        root = parse_xml_string(xml_str)

        devices = root.find("devices")
        console = devices.find("console")

        assert console is not None
        # When no log path, type should remain 'pty' (default)
        # The function sets type to 'file' only when log path is set
        target = console.find("target")
        assert target is not None
        assert target.get("type") == "serial"
        assert target.get("port") == "0"

    def test_console_with_log_path(self, full_vm_config):
        """Test console configuration when log path is set."""
        xml_str = generate_domain_xml(full_vm_config)
        root = parse_xml_string(xml_str)

        devices = root.find("devices")
        console = devices.find("console")

        assert console is not None
        assert console.get("type") == "file"

        source = console.find("source")
        assert source is not None
        assert source.get("path") == full_vm_config.serial_console_log_path


class TestNetworkConfiguration:
    """Tests for network configuration."""

    def test_user_mode_networking_without_port_forwarding(self, minimal_vm_config):
        """Test user-mode networking when no port forwarding is configured."""
        xml_str = generate_domain_xml(minimal_vm_config)
        root = parse_xml_string(xml_str)

        devices = root.find("devices")
        interface = devices.find("interface[@type='user']")

        assert interface is not None
        model = interface.find("model")
        assert model.get("type") == "virtio"


class TestVariousMemorySizes:
    """Tests for various memory configurations."""

    @pytest.mark.parametrize("ram_mb", [512, 1024, 2048, 4096, 8192, 16384, 32768])
    def test_memory_sizes(self, ram_mb):
        """Test various memory sizes are correctly set."""
        config = QEMUVMConfig(
            vm_name="mem-test-vm",
            uuid="00000000-0000-0000-0000-000000000000",
            guest_os="linux",
            disk_path="/tmp/disk.qcow2",
            ram=ram_mb,
            qmp_socket_path="/tmp/qmp.sock",
            guest_agent_socket_path="/tmp/ga.sock",
        )

        xml_str = generate_domain_xml(config)
        root = parse_xml_string(xml_str)

        memory = root.find("memory")
        current_memory = root.find("currentMemory")

        assert memory.text == str(ram_mb)
        assert current_memory.text == str(ram_mb)


class TestVariouscpuCounts:
    """Tests for various vCPU configurations."""

    @pytest.mark.parametrize("vcpu_count", [1, 2, 4, 8, 16])
    def test_vcpu_counts(self, vcpu_count):
        """Test various vCPU counts are correctly set."""
        config = QEMUVMConfig(
            vm_name="cpu-test-vm",
            uuid="00000000-0000-0000-0000-000000000000",
            guest_os="linux",
            disk_path="/tmp/disk.qcow2",
            cpus=vcpu_count,
            qmp_socket_path="/tmp/qmp.sock",
            guest_agent_socket_path="/tmp/ga.sock",
        )

        xml_str = generate_domain_xml(config)
        root = parse_xml_string(xml_str)

        vcpu = root.find("vcpu")
        assert vcpu.text == str(vcpu_count)


class TestEmptyPortForwardingList:
    """Tests for edge case of empty port forwarding."""

    def test_empty_port_forwarding_dict(self):
        """Test with explicitly empty port forwarding rules."""
        config = QEMUVMConfig(
            vm_name="empty-pf-vm",
            uuid="00000000-0000-0000-0000-000000000000",
            guest_os="linux",
            disk_path="/tmp/disk.qcow2",
            port_forwarding_rules={},
            qmp_socket_path="/tmp/qmp.sock",
            guest_agent_socket_path="/tmp/ga.sock",
        )

        xml_str = generate_domain_xml(config)
        root = parse_xml_string(xml_str)

        # Should use libvirt-managed interface
        devices = root.find("devices")
        interface = devices.find("interface[@type='user']")
        assert interface is not None

    def test_none_port_forwarding(self):
        """Test with None port forwarding rules (uses __post_init__ default)."""
        config = QEMUVMConfig(
            vm_name="none-pf-vm",
            uuid="00000000-0000-0000-0000-000000000000",
            guest_os="linux",
            disk_path="/tmp/disk.qcow2",
            port_forwarding_rules=None,
            qmp_socket_path="/tmp/qmp.sock",
            guest_agent_socket_path="/tmp/ga.sock",
        )

        xml_str = generate_domain_xml(config)
        root = parse_xml_string(xml_str)

        # Should use libvirt-managed interface
        devices = root.find("devices")
        interface = devices.find("interface[@type='user']")
        assert interface is not None


class TestDiskConfiguration:
    """Tests for disk configuration."""

    def test_disk_element_present(self, minimal_vm_config):
        """Test that disk element is properly configured."""
        xml_str = generate_domain_xml(minimal_vm_config)
        root = parse_xml_string(xml_str)

        devices = root.find("devices")
        disk = devices.find("disk[@type='file'][@device='disk']")

        assert disk is not None

    def test_disk_source_path(self, minimal_vm_config):
        """Test that disk source path is correct."""
        xml_str = generate_domain_xml(minimal_vm_config)
        root = parse_xml_string(xml_str)

        devices = root.find("devices")
        disk = devices.find("disk[@type='file']")
        source = disk.find("source")

        assert source.get("file") == minimal_vm_config.disk_path

    def test_disk_driver_format(self, minimal_vm_config):
        """Test that disk driver format matches config."""
        xml_str = generate_domain_xml(minimal_vm_config)
        root = parse_xml_string(xml_str)

        devices = root.find("devices")
        disk = devices.find("disk[@type='file']")
        driver = disk.find("driver")

        assert driver.get("type") == minimal_vm_config.drive_format

    def test_disk_target_virtio(self, minimal_vm_config):
        """Test that disk uses virtio bus."""
        xml_str = generate_domain_xml(minimal_vm_config)
        root = parse_xml_string(xml_str)

        devices = root.find("devices")
        disk = devices.find("disk[@type='file']")
        target = disk.find("target")

        assert target.get("bus") == "virtio"
        assert target.get("dev") == "vda"

    def test_disk_iothread_configuration(self, minimal_vm_config):
        """Test that disk is configured with a dedicated IOThread."""
        xml_str = generate_domain_xml(minimal_vm_config)
        root = parse_xml_string(xml_str)

        devices = root.find("devices")
        disk = devices.find("disk[@type='file']")
        driver = disk.find("driver")

        assert driver.get("iothread") == "1"


class TestIOThreadsConfiguration:
    """Tests for global IOThreads configuration."""

    def test_iothreads_element_present(self, minimal_vm_config):
        """Test that iothreads element is present and set to 1."""
        xml_str = generate_domain_xml(minimal_vm_config)
        root = parse_xml_string(xml_str)

        iothreads = root.find("iothreads")
        assert iothreads is not None
        assert iothreads.text == "1"


class TestHyperVConfiguration:
    """Tests for Hyper-V enlightenments."""

    def test_hyperv_features_present_for_windows(self, full_vm_config):
        """Test that extensive Hyper-V features are present for Windows VMs."""
        # Ensure the config is for Windows
        assert full_vm_config.guest_os == "windows"
        
        xml_str = generate_domain_xml(full_vm_config)
        root = parse_xml_string(xml_str)

        features = root.find("features")
        hyperv = features.find("hyperv")
        assert hyperv is not None

        # Check standard features
        assert hyperv.find("relaxed").get("state") == "on"
        assert hyperv.find("vapic").get("state") == "on"
        assert hyperv.find("spinlocks").get("state") == "on"
        assert hyperv.find("spinlocks").get("retries") == "8191"

        # Check new performance optimizations
        assert hyperv.find("vpindex").get("state") == "on"
        assert hyperv.find("synic").get("state") == "on"
        assert hyperv.find("stimer").get("state") == "on"
        assert hyperv.find("reset").get("state") == "on"
        assert hyperv.find("frequencies").get("state") == "on"
        assert hyperv.find("tlbflush").get("state") == "on"
        assert hyperv.find("ipi").get("state") == "on"

    def test_no_hyperv_for_linux(self, minimal_vm_config):
        """Test that Hyper-V features are NOT present for Linux VMs."""
        assert minimal_vm_config.guest_os == "linux"

        xml_str = generate_domain_xml(minimal_vm_config)
        root = parse_xml_string(xml_str)

        features = root.find("features")
        hyperv = features.find("hyperv")
        assert hyperv is None



class TestQEMUDebugLog:
    """Tests for QEMU debug log configuration."""

    def test_no_debug_log_when_not_configured(self, minimal_vm_config):
        """Test that -D argument is not present when debug log not configured."""
        xml_str = generate_domain_xml(minimal_vm_config)
        root = parse_xml_string(xml_str)

        qemu_cmdline = find_with_namespace(root, "qemu:commandline")
        args = findall_with_namespace(qemu_cmdline, "qemu:arg")
        arg_values = [arg.get("value") for arg in args]

        assert "-D" not in arg_values

    def test_debug_log_when_configured(self, full_vm_config):
        """Test that -D argument is present when debug log is configured."""
        xml_str = generate_domain_xml(full_vm_config)
        root = parse_xml_string(xml_str)

        qemu_cmdline = find_with_namespace(root, "qemu:commandline")
        args = findall_with_namespace(qemu_cmdline, "qemu:arg")
        arg_values = [arg.get("value") for arg in args]

        assert "-D" in arg_values
        d_index = arg_values.index("-D")
        assert arg_values[d_index + 1] == full_vm_config.qemu_debug_log_path

        # Also check for -d argument with debug categories
        assert "-d" in arg_values
        d_lower_index = arg_values.index("-d")
        assert arg_values[d_lower_index + 1] == "guest_errors"


class TestPowerManagement:
    """Tests for power management configuration."""

    def test_on_poweroff_destroy(self, minimal_vm_config):
        """Test that on_poweroff is set to destroy."""
        xml_str = generate_domain_xml(minimal_vm_config)
        root = parse_xml_string(xml_str)

        on_poweroff = root.find("on_poweroff")
        assert on_poweroff is not None
        assert on_poweroff.text == "destroy"

    def test_on_reboot_restart(self, minimal_vm_config):
        """Test that on_reboot is set to restart."""
        xml_str = generate_domain_xml(minimal_vm_config)
        root = parse_xml_string(xml_str)

        on_reboot = root.find("on_reboot")
        assert on_reboot is not None
        assert on_reboot.text == "restart"

    def test_on_crash_destroy(self, minimal_vm_config):
        """Test that on_crash is set to destroy."""
        xml_str = generate_domain_xml(minimal_vm_config)
        root = parse_xml_string(xml_str)

        on_crash = root.find("on_crash")
        assert on_crash is not None
        assert on_crash.text == "destroy"


class TestCPUConfiguration:
    """Tests for CPU configuration."""

    def test_cpu_mode_host_passthrough(self, minimal_vm_config):
        """Test that CPU mode is host-passthrough for KVM acceleration."""
        xml_str = generate_domain_xml(minimal_vm_config)
        root = parse_xml_string(xml_str)

        cpu = root.find("cpu")
        assert cpu is not None
        assert cpu.get("mode") == "host-passthrough"
        assert cpu.get("check") == "none"


class TestClockConfiguration:
    """Tests for clock configuration."""

    def test_clock_offset_utc(self, minimal_vm_config):
        """Test that clock offset is UTC."""
        xml_str = generate_domain_xml(minimal_vm_config)
        root = parse_xml_string(xml_str)

        clock = root.find("clock")
        assert clock is not None
        assert clock.get("offset") == "utc"

    def test_clock_timers(self, minimal_vm_config):
        """Test that clock timers are properly configured."""
        xml_str = generate_domain_xml(minimal_vm_config)
        root = parse_xml_string(xml_str)

        clock = root.find("clock")

        rtc_timer = clock.find("timer[@name='rtc']")
        assert rtc_timer is not None
        assert rtc_timer.get("tickpolicy") == "catchup"

        pit_timer = clock.find("timer[@name='pit']")
        assert pit_timer is not None
        assert pit_timer.get("tickpolicy") == "delay"

        hpet_timer = clock.find("timer[@name='hpet']")
        assert hpet_timer is not None
        assert hpet_timer.get("present") == "no"


class TestInputDevices:
    """Tests for input device configuration."""

    def test_tablet_input(self, minimal_vm_config):
        """Test that USB tablet input is configured."""
        xml_str = generate_domain_xml(minimal_vm_config)
        root = parse_xml_string(xml_str)

        devices = root.find("devices")
        tablet = devices.find("input[@type='tablet'][@bus='usb']")
        assert tablet is not None

    def test_mouse_input(self, minimal_vm_config):
        """Test that PS/2 mouse input is configured."""
        xml_str = generate_domain_xml(minimal_vm_config)
        root = parse_xml_string(xml_str)

        devices = root.find("devices")
        mouse = devices.find("input[@type='mouse'][@bus='ps2']")
        assert mouse is not None

    def test_keyboard_input(self, minimal_vm_config):
        """Test that PS/2 keyboard input is configured."""
        xml_str = generate_domain_xml(minimal_vm_config)
        root = parse_xml_string(xml_str)

        devices = root.find("devices")
        keyboard = devices.find("input[@type='keyboard'][@bus='ps2']")
        assert keyboard is not None


class TestMemoryBalloon:
    """Tests for memory balloon configuration."""

    def test_memballoon_present(self, minimal_vm_config):
        """Test that memory balloon device is configured."""
        xml_str = generate_domain_xml(minimal_vm_config)
        root = parse_xml_string(xml_str)

        devices = root.find("devices")
        memballoon = devices.find("memballoon")

        assert memballoon is not None
        assert memballoon.get("model") == "virtio"


class TestControllers:
    """Tests for controller configuration."""

    def test_virtio_serial_controller(self, minimal_vm_config):
        """Test that virtio-serial controller is configured."""
        xml_str = generate_domain_xml(minimal_vm_config)
        root = parse_xml_string(xml_str)

        devices = root.find("devices")
        virtio_serial = devices.find("controller[@type='virtio-serial']")

        assert virtio_serial is not None
        assert virtio_serial.get("index") == "0"

    def test_pci_root_controller(self, minimal_vm_config):
        """Test that PCI root controller is configured."""
        xml_str = generate_domain_xml(minimal_vm_config)
        root = parse_xml_string(xml_str)

        devices = root.find("devices")
        pci_root = devices.find("controller[@type='pci'][@model='pci-root']")

        assert pci_root is not None

    def test_usb_controller(self, minimal_vm_config):
        """Test that USB controller is configured."""
        xml_str = generate_domain_xml(minimal_vm_config)
        root = parse_xml_string(xml_str)

        devices = root.find("devices")
        usb = devices.find("controller[@type='usb']")

        assert usb is not None
        assert usb.get("model") == "qemu-xhci"


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_add_qemu_arg(self):
        """Test _add_qemu_arg function."""
        parent = ET.Element(f"{{{QEMU_NAMESPACE}}}commandline")
        _add_qemu_arg(parent, "test-value")

        children = list(parent)
        assert len(children) == 1
        assert children[0].get("value") == "test-value"

    def test_prettify_xml(self):
        """Test _prettify_xml function."""
        elem = ET.Element("root")
        ET.SubElement(elem, "child").text = "content"

        result = _prettify_xml(elem)

        assert isinstance(result, str)
        assert "<?xml" in result
        assert "<root>" in result
        assert "<child>content</child>" in result
        assert "\n" in result  # Should be formatted with newlines


class TestMachineTypes:
    """Tests for different machine type configurations."""

    @pytest.mark.parametrize("machine", ["pc", "q35", "pc-i440fx-focal"])
    def test_machine_types(self, machine):
        """Test various machine types are correctly set."""
        config = QEMUVMConfig(
            vm_name="machine-test-vm",
            uuid="00000000-0000-0000-0000-000000000000",
            guest_os="linux",
            disk_path="/tmp/disk.qcow2",
            machine=machine,
            qmp_socket_path="/tmp/qmp.sock",
            guest_agent_socket_path="/tmp/ga.sock",
        )

        xml_str = generate_domain_xml(config)
        root = parse_xml_string(xml_str)

        os_elem = root.find("os")
        os_type = os_elem.find("type")
        assert os_type.get("machine") == machine

class TestWindowsVideoConfiguration:
    """Tests for Windows video configuration."""

    def test_windows_vm_uses_virtio_and_accel3d(self, full_vm_config):
        """Test that Windows VMs use virtio model with 3D acceleration and GL enabled."""
        # full_vm_config is Windows and display_enabled=True
        xml_str = generate_domain_xml(full_vm_config)
        root = parse_xml_string(xml_str)

        devices = root.find("devices")
        
        # Check properties of video model
        video = devices.find("video")
        model = video.find("model")

        assert model.get("type") == "virtio"
        assert model.get("heads") == "1"
        assert model.get("primary") == "yes"
        
        # Check for acceleration
        accel = model.find("acceleration")
        assert accel is not None
        assert accel.get("accel3d") == "yes"
        
        # Check resolution
        resolution = model.find("resolution")
        assert resolution is not None
        assert resolution.get("x") == "1920"
        assert resolution.get("y") == "1080"
        
        # Check absence of qxl fields
        assert model.get("ram") is None
        # valid for virtio now
        assert model.get("vram") == "65536"
        assert model.get("vgamem") is None
        
        # Check graphics configuration for GL
        graphics = devices.find("graphics[@type='spice']")
        assert graphics is not None
        assert graphics.get("listen") == "127.0.0.1"
        # gl removed from spice as it conflicts with egl-headless
        gl = graphics.find("gl")
        assert gl is None

    def test_windows_vm_headless_uses_virtio_and_accel3d(self, full_vm_config):
        """Test that Windows VMs use virtio/3D/GL even in headless mode."""
        xml_str = generate_domain_xml(full_vm_config, display_enabled=False)
        root = parse_xml_string(xml_str)

        devices = root.find("devices")
        video = devices.find("video")
        model = video.find("model")

        assert model.get("type") == "virtio"
        
        accel = model.find("acceleration")
        assert accel is not None
        assert accel.get("accel3d") == "yes"
        
        # Check graphics configuration for GL
        graphics = devices.find("graphics[@type='spice']")
        assert graphics is not None
        assert graphics.get("listen") == "127.0.0.1"
        # gl removed from spice as it conflicts with egl-headless
        gl = graphics.find("gl")
        assert gl is None

    def test_linux_vm_uses_qxl(self, minimal_vm_config):
         """Test that Linux VMs still use QXL."""
         # minimal_vm_config is Linux
         xml_str = generate_domain_xml(minimal_vm_config)
         root = parse_xml_string(xml_str)
         
         devices = root.find("devices")
         video = devices.find("video")
         model = video.find("model")
         
         assert model.get("type") == "qxl"
         assert model.find("acceleration") is None
         
         # Check presence of qxl fields
         assert model.get("ram") is not None
         assert model.get("vram") is not None
