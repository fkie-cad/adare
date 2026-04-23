"""Tests for libvirt XML builder pattern (PCIBusAllocator + DomainXMLBuilder)."""

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.unit

from adare.hypervisor.qemu.libvirt_xml import generate_domain_xml
from adare.hypervisor.qemu.libvirt_xml_builder import (
    DomainXMLBuilder,
    PCIBusAllocator,
)

# --- Test fixtures ---

@dataclass
class MockVMConfig:
    """Minimal mock of QEMUVMConfig with fields accessed by DomainXMLBuilder."""

    vm_name: str = 'test-vm'
    uuid: str = '12345678-1234-1234-1234-123456789abc'
    guest_os: str = 'ubuntu2204'
    disk_path: str = '/tmp/test-disk.qcow2'
    architecture: str = 'x86_64'
    cpus: int = 2
    ram: int = 2048
    machine: str = 'pc'
    accel: str = 'kvm'
    drive_format: str = 'qcow2'
    boot_mode: str = 'bios'
    network: str = 'user'
    port_forwarding_rules: dict[str, dict[str, Any]] = field(default_factory=dict)
    qmp_socket_path: str = '/tmp/test-qmp.sock'
    guest_agent_socket_path: str = '/tmp/test-ga.sock'
    pid_file_path: str = '/tmp/test.pid'
    is_external: bool = False
    display_enabled: bool = False
    vnc_port: int | None = None
    libvirt_domain_name: str | None = None
    serial_console_log_path: str | None = None
    qemu_debug_log_path: str | None = None
    virtiofs_enabled: bool = True
    virtiofs_shares: list[dict[str, Any]] | None = field(default_factory=list)


def make_linux_pc_config(**overrides) -> MockVMConfig:
    """Create a Linux VM config with pc machine type."""
    return MockVMConfig(**overrides)


def make_linux_q35_config(**overrides) -> MockVMConfig:
    """Create a Linux VM config with q35 machine type."""
    defaults = {'machine': 'q35', 'boot_mode': 'uefi'}
    defaults.update(overrides)
    return MockVMConfig(**defaults)


def make_windows_config(**overrides) -> MockVMConfig:
    """Create a Windows VM config."""
    defaults = {'guest_os': 'windows10', 'machine': 'q35', 'boot_mode': 'uefi'}
    defaults.update(overrides)
    return MockVMConfig(**defaults)


# --- PCIBusAllocator tests ---

class TestPCIBusAllocatorQ35:
    """Tests for PCIBusAllocator with Q35 machine type."""

    def test_disk_returns_bus_4(self):
        pci = PCIBusAllocator(is_q35=True)
        addr = pci.address_for('disk')
        assert addr['bus'] == '0x04'
        assert addr['slot'] == '0x00'

    def test_network_returns_bus_1(self):
        pci = PCIBusAllocator(is_q35=True)
        addr = pci.address_for('network')
        assert addr['bus'] == '0x01'
        assert addr['slot'] == '0x00'

    def test_usb_returns_bus_2(self):
        pci = PCIBusAllocator(is_q35=True)
        addr = pci.address_for('usb')
        assert addr['bus'] == '0x02'
        assert addr['slot'] == '0x00'

    def test_virtio_serial_returns_bus_3(self):
        pci = PCIBusAllocator(is_q35=True)
        addr = pci.address_for('virtio_serial')
        assert addr['bus'] == '0x03'
        assert addr['slot'] == '0x00'

    def test_memballoon_returns_bus_5(self):
        pci = PCIBusAllocator(is_q35=True)
        addr = pci.address_for('memballoon')
        assert addr['bus'] == '0x05'
        assert addr['slot'] == '0x00'

    def test_virtiofs_index_0_returns_bus_6(self):
        pci = PCIBusAllocator(is_q35=True)
        addr = pci.address_for('virtiofs', index=0)
        assert addr['bus'] == '0x06'
        assert addr['slot'] == '0x00'

    def test_virtiofs_index_1_returns_bus_7(self):
        pci = PCIBusAllocator(is_q35=True)
        addr = pci.address_for('virtiofs', index=1)
        assert addr['bus'] == '0x07'
        assert addr['slot'] == '0x00'

    def test_virtiofs_indices_return_different_buses(self):
        pci = PCIBusAllocator(is_q35=True)
        addr0 = pci.address_for('virtiofs', index=0)
        addr1 = pci.address_for('virtiofs', index=1)
        assert addr0['bus'] != addr1['bus']

    def test_all_named_devices_have_unique_addresses(self):
        pci = PCIBusAllocator(is_q35=True)
        devices = ['network', 'usb', 'virtio_serial', 'disk', 'memballoon']
        addresses = set()
        for device in devices:
            addr = pci.address_for(device)
            key = (addr['bus'], addr['slot'])
            assert key not in addresses, f"Duplicate address for {device}: {key}"
            addresses.add(key)

    def test_address_has_required_pci_fields(self):
        pci = PCIBusAllocator(is_q35=True)
        addr = pci.address_for('disk')
        assert addr['type'] == 'pci'
        assert addr['domain'] == '0x0000'
        assert addr['function'] == '0x0'

    def test_unknown_device_raises_key_error(self):
        pci = PCIBusAllocator(is_q35=True)
        with pytest.raises(KeyError, match="Unknown device type 'nonexistent'"):
            pci.address_for('nonexistent')


class TestPCIBusAllocatorPC:
    """Tests for PCIBusAllocator with PC/i440FX machine type."""

    def test_disk_returns_slot_4(self):
        pci = PCIBusAllocator(is_q35=False)
        addr = pci.address_for('disk')
        assert addr['bus'] == '0x00'
        assert addr['slot'] == '0x04'

    def test_network_returns_slot_3(self):
        pci = PCIBusAllocator(is_q35=False)
        addr = pci.address_for('network')
        assert addr['bus'] == '0x00'
        assert addr['slot'] == '0x03'

    def test_virtio_serial_returns_slot_5(self):
        pci = PCIBusAllocator(is_q35=False)
        addr = pci.address_for('virtio_serial')
        assert addr['bus'] == '0x00'
        assert addr['slot'] == '0x05'

    def test_memballoon_returns_slot_6(self):
        pci = PCIBusAllocator(is_q35=False)
        addr = pci.address_for('memballoon')
        assert addr['bus'] == '0x00'
        assert addr['slot'] == '0x06'

    def test_virtiofs_index_0_returns_slot_7(self):
        pci = PCIBusAllocator(is_q35=False)
        addr = pci.address_for('virtiofs', index=0)
        assert addr['bus'] == '0x00'
        assert addr['slot'] == '0x07'

    def test_virtiofs_index_1_returns_slot_8(self):
        pci = PCIBusAllocator(is_q35=False)
        addr = pci.address_for('virtiofs', index=1)
        assert addr['bus'] == '0x00'
        assert addr['slot'] == '0x08'

    def test_all_named_devices_have_unique_slots(self):
        pci = PCIBusAllocator(is_q35=False)
        devices = ['network', 'disk', 'virtio_serial', 'memballoon']
        slots = set()
        for device in devices:
            addr = pci.address_for(device)
            key = (addr['bus'], addr['slot'])
            assert key not in slots, f"Duplicate address for {device}: {key}"
            slots.add(key)

    def test_pc_does_not_have_usb_assignment(self):
        """PC machine type does not have explicit USB PCI address (no root port needed)."""
        pci = PCIBusAllocator(is_q35=False)
        with pytest.raises(KeyError):
            pci.address_for('usb')


# --- DomainXMLBuilder tests ---

class TestDomainXMLBuilderBasic:
    """Tests for DomainXMLBuilder producing valid XML."""

    @patch('adare.hypervisor.qemu.libvirt_xml_builder.shutil.which', return_value='/usr/bin/qemu-system-x86_64')
    @patch('adare.hypervisor.qemu.libvirt_xml_builder.platform.system', return_value='Linux')
    def test_build_produces_parseable_xml(self, mock_platform, mock_which):
        """build() produces XML that can be parsed by ElementTree."""
        config = make_linux_pc_config()
        builder = DomainXMLBuilder(config)
        xml_str = builder.build()

        # Should parse without error
        root = ET.fromstring(xml_str)
        assert root.tag == 'domain'

    @patch('adare.hypervisor.qemu.libvirt_xml_builder.shutil.which', return_value='/usr/bin/qemu-system-x86_64')
    @patch('adare.hypervisor.qemu.libvirt_xml_builder.platform.system', return_value='Linux')
    def test_build_contains_required_elements(self, mock_platform, mock_which):
        """build() XML contains domain, memory, vcpu, os, devices."""
        config = make_linux_pc_config()
        builder = DomainXMLBuilder(config)
        xml_str = builder.build()
        root = ET.fromstring(xml_str)

        assert root.find('name') is not None
        assert root.find('name').text == 'test-vm'
        assert root.find('uuid') is not None
        assert root.find('memory') is not None
        assert root.find('vcpu') is not None
        assert root.find('os') is not None
        assert root.find('devices') is not None

    @patch('adare.hypervisor.qemu.libvirt_xml_builder.shutil.which', return_value='/usr/bin/qemu-system-x86_64')
    @patch('adare.hypervisor.qemu.libvirt_xml_builder.platform.system', return_value='Linux')
    def test_build_contains_memory_values(self, mock_platform, mock_which):
        """build() sets correct memory values from config."""
        config = make_linux_pc_config(ram=4096)
        builder = DomainXMLBuilder(config)
        xml_str = builder.build()
        root = ET.fromstring(xml_str)

        assert root.find('memory').text == '4096'
        assert root.find('memory').get('unit') == 'MiB'
        assert root.find('currentMemory').text == '4096'

    @patch('adare.hypervisor.qemu.libvirt_xml_builder.shutil.which', return_value='/usr/bin/qemu-system-x86_64')
    @patch('adare.hypervisor.qemu.libvirt_xml_builder.platform.system', return_value='Linux')
    def test_build_contains_vcpu(self, mock_platform, mock_which):
        """build() sets correct vCPU count."""
        config = make_linux_pc_config(cpus=4)
        builder = DomainXMLBuilder(config)
        xml_str = builder.build()
        root = ET.fromstring(xml_str)

        assert root.find('vcpu').text == '4'

    @patch('adare.hypervisor.qemu.libvirt_xml_builder.shutil.which', return_value='/usr/bin/qemu-system-x86_64')
    @patch('adare.hypervisor.qemu.libvirt_xml_builder.platform.system', return_value='Linux')
    def test_build_domain_type_kvm_on_linux(self, mock_platform, mock_which):
        """build() uses kvm domain type on Linux."""
        config = make_linux_pc_config()
        builder = DomainXMLBuilder(config)
        xml_str = builder.build()
        root = ET.fromstring(xml_str)

        assert root.get('type') == 'kvm'

    @patch('adare.hypervisor.qemu.libvirt_xml_builder.shutil.which', return_value='/opt/homebrew/bin/qemu-system-x86_64')
    @patch('adare.hypervisor.qemu.libvirt_xml_builder.platform.system', return_value='Darwin')
    def test_build_domain_type_hvf_on_darwin(self, mock_platform, mock_which):
        """build() uses hvf domain type on macOS."""
        config = make_linux_pc_config()
        builder = DomainXMLBuilder(config)
        xml_str = builder.build()
        root = ET.fromstring(xml_str)

        assert root.get('type') == 'hvf'


class TestDomainXMLBuilderBIOS:
    """Tests for BIOS boot configuration."""

    @patch('adare.hypervisor.qemu.libvirt_xml_builder.shutil.which', return_value='/usr/bin/qemu-system-x86_64')
    @patch('adare.hypervisor.qemu.libvirt_xml_builder.platform.system', return_value='Linux')
    def test_bios_boot_has_hvm_type(self, mock_platform, mock_which):
        """BIOS boot sets os/type to hvm."""
        config = make_linux_pc_config()
        builder = DomainXMLBuilder(config)
        xml_str = builder.build()
        root = ET.fromstring(xml_str)

        os_type = root.find('os/type')
        assert os_type is not None
        assert os_type.text == 'hvm'
        assert os_type.get('arch') == 'x86_64'
        assert os_type.get('machine') == 'pc'

    @patch('adare.hypervisor.qemu.libvirt_xml_builder.shutil.which', return_value='/usr/bin/qemu-system-x86_64')
    @patch('adare.hypervisor.qemu.libvirt_xml_builder.platform.system', return_value='Linux')
    def test_bios_boot_has_no_loader(self, mock_platform, mock_which):
        """BIOS boot does not include OVMF loader."""
        config = make_linux_pc_config()
        builder = DomainXMLBuilder(config)
        xml_str = builder.build()
        root = ET.fromstring(xml_str)

        assert root.find('os/loader') is None


class TestDomainXMLBuilderUEFI:
    """Tests for UEFI boot configuration."""

    @patch('adare.hypervisor.qemu.libvirt_xml_builder.create_nvram_for_vm', return_value='/tmp/nvram.fd')
    @patch('adare.hypervisor.qemu.libvirt_xml_builder.find_ovmf_firmware', return_value=('/usr/share/OVMF/OVMF_CODE.fd', '/usr/share/OVMF/OVMF_VARS.fd'))
    @patch('adare.hypervisor.qemu.libvirt_xml_builder.shutil.which', return_value='/usr/bin/qemu-system-x86_64')
    @patch('adare.hypervisor.qemu.libvirt_xml_builder.platform.system', return_value='Linux')
    def test_uefi_boot_has_loader_and_nvram(self, mock_platform, mock_which, mock_firmware, mock_nvram):
        """UEFI boot includes OVMF loader and NVRAM elements."""
        config = make_linux_q35_config()
        builder = DomainXMLBuilder(config)
        xml_str = builder.build()
        root = ET.fromstring(xml_str)

        assert root.find('os/loader') is not None
        assert root.find('os/loader').get('type') == 'pflash'
        assert root.find('os/nvram') is not None

    @patch('adare.hypervisor.qemu.libvirt_xml_builder.create_nvram_for_vm', return_value='/tmp/nvram.fd')
    @patch('adare.hypervisor.qemu.libvirt_xml_builder.find_ovmf_firmware', return_value=('/usr/share/OVMF/OVMF_CODE.fd', '/usr/share/OVMF/OVMF_VARS.fd'))
    @patch('adare.hypervisor.qemu.libvirt_xml_builder.shutil.which', return_value='/usr/bin/qemu-system-x86_64')
    @patch('adare.hypervisor.qemu.libvirt_xml_builder.platform.system', return_value='Linux')
    def test_uefi_pc_promotes_to_q35(self, mock_platform, mock_which, mock_firmware, mock_nvram):
        """UEFI boot with pc machine promotes to q35."""
        config = make_linux_pc_config(boot_mode='uefi')
        builder = DomainXMLBuilder(config)
        xml_str = builder.build()
        root = ET.fromstring(xml_str)

        os_type = root.find('os/type')
        assert os_type.get('machine') == 'q35'


class TestDomainXMLBuilderDevices:
    """Tests for device configuration."""

    @patch('adare.hypervisor.qemu.libvirt_xml_builder.shutil.which', return_value='/usr/bin/qemu-system-x86_64')
    @patch('adare.hypervisor.qemu.libvirt_xml_builder.platform.system', return_value='Linux')
    def test_pc_disk_uses_correct_pci_address(self, mock_platform, mock_which):
        """PC machine disk uses bus 0, slot 4."""
        config = make_linux_pc_config()
        builder = DomainXMLBuilder(config)
        xml_str = builder.build()
        root = ET.fromstring(xml_str)

        disk = root.find('.//disk[@device="disk"]')
        addr = disk.find('address')
        assert addr is not None
        assert addr.get('bus') == '0x00'
        assert addr.get('slot') == '0x04'

    @patch('adare.hypervisor.qemu.libvirt_xml_builder.create_nvram_for_vm', return_value='/tmp/nvram.fd')
    @patch('adare.hypervisor.qemu.libvirt_xml_builder.find_ovmf_firmware', return_value=('/usr/share/OVMF/OVMF_CODE.fd', '/usr/share/OVMF/OVMF_VARS.fd'))
    @patch('adare.hypervisor.qemu.libvirt_xml_builder.shutil.which', return_value='/usr/bin/qemu-system-x86_64')
    @patch('adare.hypervisor.qemu.libvirt_xml_builder.platform.system', return_value='Linux')
    def test_q35_disk_uses_correct_pci_address(self, mock_platform, mock_which, mock_firmware, mock_nvram):
        """Q35 machine disk uses bus 4, slot 0."""
        config = make_linux_q35_config()
        builder = DomainXMLBuilder(config)
        xml_str = builder.build()
        root = ET.fromstring(xml_str)

        disk = root.find('.//disk[@device="disk"]')
        addr = disk.find('address')
        assert addr is not None
        assert addr.get('bus') == '0x04'
        assert addr.get('slot') == '0x00'

    @patch('adare.hypervisor.qemu.libvirt_xml_builder.shutil.which', return_value='/usr/bin/qemu-system-x86_64')
    @patch('adare.hypervisor.qemu.libvirt_xml_builder.platform.system', return_value='Linux')
    def test_pc_network_uses_user_mode(self, mock_platform, mock_which):
        """Linux PC VM uses user-mode networking."""
        config = make_linux_pc_config()
        builder = DomainXMLBuilder(config)
        xml_str = builder.build()
        root = ET.fromstring(xml_str)

        interface = root.find('.//interface')
        assert interface is not None
        assert interface.get('type') == 'user'

    @patch('adare.hypervisor.qemu.libvirt_xml_builder.shutil.which', return_value='/usr/bin/qemu-system-x86_64')
    @patch('adare.hypervisor.qemu.libvirt_xml_builder.platform.system', return_value='Linux')
    def test_no_network_interface_with_port_forwarding(self, mock_platform, mock_which):
        """Port forwarding rules suppress libvirt network interface (configured via qemu:commandline)."""
        config = make_linux_pc_config(
            port_forwarding_rules={
                'ssh': {'protocol': 'tcp', 'host_port': 2222, 'guest_port': 22}
            }
        )
        builder = DomainXMLBuilder(config)
        xml_str = builder.build()
        root = ET.fromstring(xml_str)

        interface = root.find('.//interface')
        assert interface is None

    @patch('adare.hypervisor.qemu.libvirt_xml_builder.shutil.which', return_value='/usr/bin/qemu-system-x86_64')
    @patch('adare.hypervisor.qemu.libvirt_xml_builder.platform.system', return_value='Linux')
    def test_guest_agent_channel_present(self, mock_platform, mock_which):
        """Guest agent channel is always present."""
        config = make_linux_pc_config()
        builder = DomainXMLBuilder(config)
        xml_str = builder.build()
        root = ET.fromstring(xml_str)

        channels = root.findall('.//channel')
        ga_channels = [c for c in channels if c.find('target') is not None
                       and c.find('target').get('name') == 'org.qemu.guest_agent.0']
        assert len(ga_channels) == 1

    @patch('adare.hypervisor.qemu.libvirt_xml_builder.shutil.which', return_value='/usr/bin/qemu-system-x86_64')
    @patch('adare.hypervisor.qemu.libvirt_xml_builder.platform.system', return_value='Linux')
    def test_memballoon_present(self, mock_platform, mock_which):
        """Memballoon device is present."""
        config = make_linux_pc_config()
        builder = DomainXMLBuilder(config)
        xml_str = builder.build()
        root = ET.fromstring(xml_str)

        memballoon = root.find('.//memballoon')
        assert memballoon is not None
        assert memballoon.get('model') == 'virtio'

    @patch('adare.hypervisor.qemu.libvirt_xml_builder.shutil.which', return_value='/usr/bin/qemu-system-x86_64')
    @patch('adare.hypervisor.qemu.libvirt_xml_builder.platform.system', return_value='Linux')
    def test_pc_has_pci_root_controller(self, mock_platform, mock_which):
        """PC machine has a pci-root controller."""
        config = make_linux_pc_config()
        builder = DomainXMLBuilder(config)
        xml_str = builder.build()
        root = ET.fromstring(xml_str)

        pci_controllers = root.findall('.//controller[@type="pci"]')
        models = [c.get('model') for c in pci_controllers]
        assert 'pci-root' in models


class TestDomainXMLBuilderWindows:
    """Tests for Windows-specific configuration."""

    @patch('adare.hypervisor.qemu.libvirt_xml_builder.create_nvram_for_vm', return_value='/tmp/nvram.fd')
    @patch('adare.hypervisor.qemu.libvirt_xml_builder.find_ovmf_firmware', return_value=('/usr/share/OVMF/OVMF_CODE.fd', '/usr/share/OVMF/OVMF_VARS.fd'))
    @patch('adare.hypervisor.qemu.libvirt_xml_builder.shutil.which', return_value='/usr/bin/qemu-system-x86_64')
    @patch('adare.hypervisor.qemu.libvirt_xml_builder.platform.system', return_value='Linux')
    def test_windows_has_smm_enabled(self, mock_platform, mock_which, mock_firmware, mock_nvram):
        """Windows VM has SMM feature enabled."""
        config = make_windows_config()
        builder = DomainXMLBuilder(config)
        xml_str = builder.build()
        root = ET.fromstring(xml_str)

        smm = root.find('.//features/smm')
        assert smm is not None
        assert smm.get('state') == 'on'

    @patch('adare.hypervisor.qemu.libvirt_xml_builder.create_nvram_for_vm', return_value='/tmp/nvram.fd')
    @patch('adare.hypervisor.qemu.libvirt_xml_builder.find_ovmf_firmware', return_value=('/usr/share/OVMF/OVMF_CODE.fd', '/usr/share/OVMF/OVMF_VARS.fd'))
    @patch('adare.hypervisor.qemu.libvirt_xml_builder.shutil.which', return_value='/usr/bin/qemu-system-x86_64')
    @patch('adare.hypervisor.qemu.libvirt_xml_builder.platform.system', return_value='Linux')
    def test_windows_has_hyperv_enlightenments_on_linux(self, mock_platform, mock_which, mock_firmware, mock_nvram):
        """Windows VM on Linux has Hyper-V enlightenments."""
        config = make_windows_config()
        builder = DomainXMLBuilder(config)
        xml_str = builder.build()
        root = ET.fromstring(xml_str)

        hyperv = root.find('.//features/hyperv')
        assert hyperv is not None
        assert hyperv.find('relaxed') is not None
        assert hyperv.find('vapic') is not None

    @patch('adare.hypervisor.qemu.libvirt_xml_builder.create_nvram_for_vm', return_value='/tmp/nvram.fd')
    @patch('adare.hypervisor.qemu.libvirt_xml_builder.find_ovmf_firmware', return_value=('/usr/share/OVMF/OVMF_CODE.fd', '/usr/share/OVMF/OVMF_VARS.fd'))
    @patch('adare.hypervisor.qemu.libvirt_xml_builder.shutil.which', return_value='/opt/homebrew/bin/qemu-system-x86_64')
    @patch('adare.hypervisor.qemu.libvirt_xml_builder.platform.system', return_value='Darwin')
    def test_windows_no_hyperv_on_darwin(self, mock_platform, mock_which, mock_firmware, mock_nvram):
        """Windows VM on macOS has no Hyper-V enlightenments."""
        config = make_windows_config()
        builder = DomainXMLBuilder(config)
        xml_str = builder.build()
        root = ET.fromstring(xml_str)

        hyperv = root.find('.//features/hyperv')
        assert hyperv is None

    @patch('adare.hypervisor.qemu.libvirt_xml_builder.create_nvram_for_vm', return_value='/tmp/nvram.fd')
    @patch('adare.hypervisor.qemu.libvirt_xml_builder.find_ovmf_firmware', return_value=('/usr/share/OVMF/OVMF_CODE.fd', '/usr/share/OVMF/OVMF_VARS.fd'))
    @patch('adare.hypervisor.qemu.libvirt_xml_builder.shutil.which', return_value='/usr/bin/qemu-system-x86_64')
    @patch('adare.hypervisor.qemu.libvirt_xml_builder.platform.system', return_value='Linux')
    def test_windows_has_spice_channel(self, mock_platform, mock_which, mock_firmware, mock_nvram):
        """Windows VM on Linux has SPICE vdagent channel."""
        config = make_windows_config()
        builder = DomainXMLBuilder(config)
        xml_str = builder.build()
        root = ET.fromstring(xml_str)

        channels = root.findall('.//channel')
        spice_channels = [c for c in channels if c.find('target') is not None
                         and c.find('target').get('name') == 'com.redhat.spice.0']
        assert len(spice_channels) == 1

    @patch('adare.hypervisor.qemu.libvirt_xml_builder.create_nvram_for_vm', return_value='/tmp/nvram.fd')
    @patch('adare.hypervisor.qemu.libvirt_xml_builder.find_ovmf_firmware', return_value=('/usr/share/OVMF/OVMF_CODE.fd', '/usr/share/OVMF/OVMF_VARS.fd'))
    @patch('adare.hypervisor.qemu.libvirt_xml_builder.shutil.which', return_value='/usr/bin/qemu-system-x86_64')
    @patch('adare.hypervisor.qemu.libvirt_xml_builder.platform.system', return_value='Linux')
    def test_windows_uses_bridge_networking(self, mock_platform, mock_which, mock_firmware, mock_nvram):
        """Windows VM on Linux uses bridge networking."""
        config = make_windows_config()
        builder = DomainXMLBuilder(config)
        xml_str = builder.build()
        root = ET.fromstring(xml_str)

        interface = root.find('.//interface')
        assert interface is not None
        assert interface.get('type') == 'network'
        source = interface.find('source')
        assert source.get('network') == 'default'


class TestDomainXMLBuilderQemuCommandline:
    """Tests for QEMU commandline arguments."""

    @patch('adare.hypervisor.qemu.libvirt_xml_builder.shutil.which', return_value='/usr/bin/qemu-system-x86_64')
    @patch('adare.hypervisor.qemu.libvirt_xml_builder.platform.system', return_value='Linux')
    def test_qmp_socket_in_commandline(self, mock_platform, mock_which):
        """QMP socket argument is present in qemu:commandline."""
        config = make_linux_pc_config()
        builder = DomainXMLBuilder(config)
        xml_str = builder.build()
        root = ET.fromstring(xml_str)

        ns = {'qemu': 'http://libvirt.org/schemas/domain/qemu/1.0'}
        args = root.findall('.//qemu:commandline/qemu:arg', ns)
        arg_values = [a.get('value') for a in args]

        assert '-qmp' in arg_values
        qmp_idx = arg_values.index('-qmp')
        assert arg_values[qmp_idx + 1] == 'unix:/tmp/test-qmp.sock,server=on,wait=off'

    @patch('adare.hypervisor.qemu.libvirt_xml_builder.shutil.which', return_value='/opt/homebrew/bin/qemu-system-x86_64')
    @patch('adare.hypervisor.qemu.libvirt_xml_builder.platform.system', return_value='Darwin')
    def test_hvf_domain_type_on_darwin(self, mock_platform, mock_which):
        """HVF acceleration is set via domain type='hvf' on macOS (not -accel arg)."""
        config = make_linux_pc_config()
        builder = DomainXMLBuilder(config)
        xml_str = builder.build()
        root = ET.fromstring(xml_str)

        assert root.get('type') == 'hvf'

    @patch('adare.hypervisor.qemu.libvirt_xml_builder.shutil.which', return_value='/usr/bin/qemu-system-x86_64')
    @patch('adare.hypervisor.qemu.libvirt_xml_builder.platform.system', return_value='Linux')
    def test_port_forwarding_in_commandline(self, mock_platform, mock_which):
        """Port forwarding rules are added to qemu:commandline."""
        config = make_linux_pc_config(
            port_forwarding_rules={
                'ssh': {'protocol': 'tcp', 'host_port': 2222, 'guest_port': 22}
            }
        )
        builder = DomainXMLBuilder(config)
        xml_str = builder.build()
        root = ET.fromstring(xml_str)

        ns = {'qemu': 'http://libvirt.org/schemas/domain/qemu/1.0'}
        args = root.findall('.//qemu:commandline/qemu:arg', ns)
        arg_values = [a.get('value') for a in args]

        assert '-netdev' in arg_values
        netdev_idx = arg_values.index('-netdev')
        assert arg_values[netdev_idx + 1] == 'user,id=net0,hostfwd=tcp::2222-:22'

        assert '-device' in arg_values
        device_idx = arg_values.index('-device')
        assert arg_values[device_idx + 1] == 'virtio-net-pci,netdev=net0'


class TestDomainXMLBuilderVirtioFS:
    """Tests for virtio-fs filesystem devices."""

    @patch('adare.hypervisor.qemu.libvirt_xml_builder.shutil.which', return_value='/usr/bin/qemu-system-x86_64')
    @patch('adare.hypervisor.qemu.libvirt_xml_builder.platform.system', return_value='Linux')
    def test_virtiofs_adds_memory_backing(self, mock_platform, mock_which):
        """Virtio-fs shares add memoryBacking element."""
        shares = [{'tag': 'run', 'host_path': '/tmp/run'}]
        config = make_linux_pc_config()
        builder = DomainXMLBuilder(config, virtiofs_shares=shares)
        xml_str = builder.build()
        root = ET.fromstring(xml_str)

        mb = root.find('memoryBacking')
        assert mb is not None
        assert mb.find('source').get('type') == 'memfd'
        assert mb.find('access').get('mode') == 'shared'

    @patch('adare.hypervisor.qemu.libvirt_xml_builder.shutil.which', return_value='/usr/bin/qemu-system-x86_64')
    @patch('adare.hypervisor.qemu.libvirt_xml_builder.platform.system', return_value='Linux')
    def test_virtiofs_filesystems_added(self, mock_platform, mock_which):
        """Virtio-fs shares create filesystem elements."""
        shares = [
            {'tag': 'run', 'host_path': '/tmp/run'},
            {'tag': 'vm', 'host_path': '/tmp/vm'},
        ]
        config = make_linux_pc_config()
        builder = DomainXMLBuilder(config, virtiofs_shares=shares)
        xml_str = builder.build()
        root = ET.fromstring(xml_str)

        filesystems = root.findall('.//filesystem')
        assert len(filesystems) == 2

        tags = [fs.find('target').get('dir') for fs in filesystems]
        assert 'run' in tags
        assert 'vm' in tags


class TestDomainXMLBuilderClock:
    """Tests for clock configuration."""

    @patch('adare.hypervisor.qemu.libvirt_xml_builder.shutil.which', return_value='/usr/bin/qemu-system-x86_64')
    @patch('adare.hypervisor.qemu.libvirt_xml_builder.platform.system', return_value='Linux')
    def test_x86_has_rtc_pit_timers(self, mock_platform, mock_which):
        """x86_64 VM has RTC and PIT timers."""
        config = make_linux_pc_config()
        builder = DomainXMLBuilder(config)
        xml_str = builder.build()
        root = ET.fromstring(xml_str)

        clock = root.find('clock')
        assert clock is not None
        timer_names = [t.get('name') for t in clock.findall('timer')]
        assert 'rtc' in timer_names
        assert 'pit' in timer_names
        assert 'hpet' in timer_names

    @patch('adare.hypervisor.qemu.libvirt_xml_builder.create_nvram_for_vm', return_value='/tmp/nvram.fd')
    @patch('adare.hypervisor.qemu.libvirt_xml_builder.find_ovmf_firmware', return_value=('/usr/share/OVMF/OVMF_CODE.fd', '/usr/share/OVMF/OVMF_VARS.fd'))
    @patch('adare.hypervisor.qemu.libvirt_xml_builder.shutil.which', return_value='/usr/bin/qemu-system-x86_64')
    @patch('adare.hypervisor.qemu.libvirt_xml_builder.platform.system', return_value='Linux')
    def test_windows_has_hypervclock(self, mock_platform, mock_which, mock_firmware, mock_nvram):
        """Windows VM on Linux has hypervclock timer."""
        config = make_windows_config()
        builder = DomainXMLBuilder(config)
        xml_str = builder.build()
        root = ET.fromstring(xml_str)

        clock = root.find('clock')
        timer_names = [t.get('name') for t in clock.findall('timer')]
        assert 'hypervclock' in timer_names


class TestDomainXMLBuilderGraphics:
    """Tests for graphics/display configuration."""

    @patch('adare.hypervisor.qemu.libvirt_xml_builder.shutil.which', return_value='/usr/bin/qemu-system-x86_64')
    @patch('adare.hypervisor.qemu.libvirt_xml_builder.platform.system', return_value='Linux')
    def test_headless_linux_uses_vnc(self, mock_platform, mock_which):
        """Headless Linux VM uses VNC graphics."""
        config = make_linux_pc_config()
        builder = DomainXMLBuilder(config, display_enabled=False)
        xml_str = builder.build()
        root = ET.fromstring(xml_str)

        graphics = root.findall('.//graphics')
        vnc_graphics = [g for g in graphics if g.get('type') == 'vnc']
        assert len(vnc_graphics) >= 1

    @patch('adare.hypervisor.qemu.libvirt_xml_builder.shutil.which', return_value='/usr/bin/qemu-system-x86_64')
    @patch('adare.hypervisor.qemu.libvirt_xml_builder.platform.system', return_value='Linux')
    def test_explicit_vnc_port(self, mock_platform, mock_which):
        """Explicit VNC port is set correctly."""
        config = make_linux_pc_config()
        builder = DomainXMLBuilder(config, display_enabled=True, vnc_port=5901)
        xml_str = builder.build()
        root = ET.fromstring(xml_str)

        graphics = root.find('.//graphics[@type="vnc"]')
        assert graphics is not None
        assert graphics.get('port') == '5901'
        assert graphics.get('autoport') == 'no'

    @patch('adare.hypervisor.qemu.libvirt_xml_builder.shutil.which', return_value='/usr/bin/qemu-system-x86_64')
    @patch('adare.hypervisor.qemu.libvirt_xml_builder.platform.system', return_value='Linux')
    def test_video_device_has_resolution(self, mock_platform, mock_which):
        """Video device has 1920x1080 resolution."""
        config = make_linux_pc_config()
        builder = DomainXMLBuilder(config)
        xml_str = builder.build()
        root = ET.fromstring(xml_str)

        resolution = root.find('.//video/model/resolution')
        assert resolution is not None
        assert resolution.get('x') == '1920'
        assert resolution.get('y') == '1080'


class TestBackwardCompatibility:
    """Tests that the wrapper generate_domain_xml() still works."""

    @patch('adare.hypervisor.qemu.libvirt_xml_builder.shutil.which', return_value='/usr/bin/qemu-system-x86_64')
    @patch('adare.hypervisor.qemu.libvirt_xml_builder.platform.system', return_value='Linux')
    def test_generate_domain_xml_returns_valid_xml(self, mock_platform, mock_which):
        """generate_domain_xml() backward-compat wrapper produces valid XML."""
        config = make_linux_pc_config()
        xml_str = generate_domain_xml(config)

        root = ET.fromstring(xml_str)
        assert root.tag == 'domain'
        assert root.find('name').text == 'test-vm'
        assert root.find('devices') is not None

    @patch('adare.hypervisor.qemu.libvirt_xml_builder.shutil.which', return_value='/usr/bin/qemu-system-x86_64')
    @patch('adare.hypervisor.qemu.libvirt_xml_builder.platform.system', return_value='Linux')
    def test_generate_domain_xml_accepts_all_parameters(self, mock_platform, mock_which):
        """generate_domain_xml() accepts display_enabled, vnc_port, virtiofs_shares."""
        config = make_linux_pc_config()
        shares = [{'tag': 'test', 'host_path': '/tmp/test'}]
        xml_str = generate_domain_xml(
            config,
            display_enabled=True,
            vnc_port=5902,
            virtiofs_shares=shares,
        )

        root = ET.fromstring(xml_str)
        assert root.tag == 'domain'

    @patch('adare.hypervisor.qemu.libvirt_xml_builder.shutil.which', return_value='/usr/bin/qemu-system-x86_64')
    @patch('adare.hypervisor.qemu.libvirt_xml_builder.platform.system', return_value='Linux')
    def test_generate_domain_xml_same_as_builder(self, mock_platform, mock_which):
        """generate_domain_xml() output matches DomainXMLBuilder.build()."""
        config = make_linux_pc_config()

        wrapper_xml = generate_domain_xml(config)
        builder = DomainXMLBuilder(config)
        builder_xml = builder.build()

        assert wrapper_xml == builder_xml
