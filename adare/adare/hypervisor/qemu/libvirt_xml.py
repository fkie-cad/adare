"""
libvirt XML domain generation for QEMU VMs.

Generates libvirt XML domain definitions from QEMU VM configurations,
enabling VMs to be managed via virsh and virt-manager while preserving
ADARE's forensic-focused architecture (QMP, Guest Agent, overlays).
"""
import logging
from typing import Optional, Dict, Any
import xml.etree.ElementTree as ET
from xml.dom import minidom

log = logging.getLogger(__name__)

# libvirt QEMU namespace for custom QEMU commandline arguments
QEMU_NAMESPACE = 'http://libvirt.org/schemas/domain/qemu/1.0'


def generate_domain_xml(
    vm_config,  # QEMUVMConfig instance
    display_enabled: bool = False,
    vnc_port: Optional[int] = None
) -> str:
    """
    Generate libvirt XML domain definition from QEMU VM config.

    This function creates a complete libvirt XML domain that:
    - Makes VMs visible in virsh and virt-manager
    - Configures VNC display (off by default, accessible via virt-manager)
    - Preserves QMP socket functionality via qemu:commandline
    - Preserves Guest Agent socket via virtio-serial channel
    - Supports port forwarding via qemu:commandline
    - Uses overlay disks for forensic integrity

    Args:
        vm_config: QEMUVMConfig instance with VM settings
        display_enabled: If True, shows display by default (False = headless)
        vnc_port: Optional explicit VNC port (None = autoport)

    Returns:
        str: Formatted libvirt XML domain definition

    Example:
        xml = generate_domain_xml(vm_config, display_enabled=False)
        conn = libvirt.open('qemu:///session')
        domain = conn.defineXML(xml)
        domain.create()
    """
    log.debug(f"CLAUDE: Generating libvirt XML for VM: {vm_config.vm_name}")

    # Create root domain element with qemu namespace
    domain = ET.Element('domain', type='kvm')
    domain.set(f'xmlns:qemu', QEMU_NAMESPACE)

    # Basic VM identification
    ET.SubElement(domain, 'name').text = vm_config.vm_name
    ET.SubElement(domain, 'uuid').text = vm_config.uuid

    # Memory configuration (in MiB)
    memory = ET.SubElement(domain, 'memory', unit='MiB')
    memory.text = str(vm_config.ram)
    current_memory = ET.SubElement(domain, 'currentMemory', unit='MiB')
    current_memory.text = str(vm_config.ram)

    # CPU configuration
    vcpu = ET.SubElement(domain, 'vcpu', placement='static')
    vcpu.text = str(vm_config.cpus)

    # OS configuration
    os = ET.SubElement(domain, 'os')
    os_type = ET.SubElement(os, 'type', arch='x86_64', machine=vm_config.machine)
    os_type.text = 'hvm'
    ET.SubElement(os, 'boot', dev='hd')

    # Features (ACPI for proper shutdown)
    features = ET.SubElement(domain, 'features')
    ET.SubElement(features, 'acpi')
    ET.SubElement(features, 'apic')

    # CPU mode (host-passthrough for KVM acceleration)
    cpu = ET.SubElement(domain, 'cpu', mode='host-passthrough', check='none')

    # Clock configuration
    clock = ET.SubElement(domain, 'clock', offset='utc')
    ET.SubElement(clock, 'timer', name='rtc', tickpolicy='catchup')
    ET.SubElement(clock, 'timer', name='pit', tickpolicy='delay')
    ET.SubElement(clock, 'timer', name='hpet', present='no')

    # Power management (on_poweroff, on_reboot, on_crash)
    ET.SubElement(domain, 'on_poweroff').text = 'destroy'
    ET.SubElement(domain, 'on_reboot').text = 'restart'
    ET.SubElement(domain, 'on_crash').text = 'destroy'

    # Devices section
    devices = ET.SubElement(domain, 'devices')

    # Emulator path (qemu-system-x86_64)
    from adare.config import HYPERVISOR_CONFIGS
    qemu_config = HYPERVISOR_CONFIGS.get('qemu', {})
    qemu_exe = qemu_config.get('qemu_system_exe', 'qemu-system-x86_64')

    # Try to find full path
    import shutil
    qemu_full_path = shutil.which(qemu_exe) or f'/usr/bin/{qemu_exe}'
    ET.SubElement(devices, 'emulator').text = qemu_full_path

    # Disk configuration (virtio driver, overlay disk)
    disk = ET.SubElement(devices, 'disk', type='file', device='disk')
    ET.SubElement(disk, 'driver', name='qemu', type=vm_config.drive_format, cache='none')
    ET.SubElement(disk, 'source', file=vm_config.disk_path)
    ET.SubElement(disk, 'target', dev='vda', bus='virtio')
    ET.SubElement(disk, 'address', type='pci', domain='0x0000', bus='0x00', slot='0x04', function='0x0')

    # Network interface (user-mode networking)
    # When port forwarding exists, network is fully configured via qemu:commandline
    # to avoid conflicts. Otherwise, use libvirt-managed interface for simplicity.
    if not vm_config.port_forwarding_rules:
        interface = ET.SubElement(devices, 'interface', type='user')
        ET.SubElement(interface, 'model', type='virtio')
        ET.SubElement(interface, 'address', type='pci', domain='0x0000', bus='0x00', slot='0x03', function='0x0')

    # Guest Agent channel (virtio-serial)
    channel = ET.SubElement(devices, 'channel', type='unix')
    channel_source = ET.SubElement(channel, 'source', mode='bind')
    channel_source.set('path', vm_config.guest_agent_socket_path)
    channel_target = ET.SubElement(channel, 'target', type='virtio', name='org.qemu.guest_agent.0')
    ET.SubElement(channel, 'address', type='virtio-serial', controller='0', bus='0', port='1')

    # Virtio-serial controller (required for Guest Agent)
    controller_virtio = ET.SubElement(devices, 'controller', type='virtio-serial', index='0')
    ET.SubElement(controller_virtio, 'address', type='pci', domain='0x0000', bus='0x00', slot='0x05', function='0x0')

    # PCI controllers
    ET.SubElement(devices, 'controller', type='pci', index='0', model='pci-root')
    ET.SubElement(devices, 'controller', type='usb', index='0', model='qemu-xhci')

    # Graphics/Display configuration
    if display_enabled:
        # Display visible by default (virt-manager will show console immediately)
        if vnc_port:
            graphics = ET.SubElement(devices, 'graphics', type='vnc', port=str(vnc_port), autoport='no')
        else:
            graphics = ET.SubElement(devices, 'graphics', type='vnc', port='-1', autoport='yes')
        graphics.set('listen', '127.0.0.1')  # Localhost only for security
        ET.SubElement(graphics, 'listen', type='address', address='127.0.0.1')

        # Add video device for display
        video = ET.SubElement(devices, 'video')
        ET.SubElement(video, 'model', type='qxl', ram='65536', vram='65536', vgamem='16384', heads='1', primary='yes')
        ET.SubElement(video, 'address', type='pci', domain='0x0000', bus='0x00', slot='0x02', function='0x0')
    else:
        # Headless mode: VNC still available but not shown by default
        # virt-manager can connect on-demand via "Open" button
        if vnc_port:
            graphics = ET.SubElement(devices, 'graphics', type='vnc', port=str(vnc_port), autoport='no')
        else:
            graphics = ET.SubElement(devices, 'graphics', type='vnc', port='-1', autoport='yes')
        graphics.set('listen', '127.0.0.1')
        ET.SubElement(graphics, 'listen', type='address', address='127.0.0.1')

        # Minimal video device (QXL for efficient VNC)
        video = ET.SubElement(devices, 'video')
        ET.SubElement(video, 'model', type='qxl', ram='65536', vram='65536', vgamem='16384', heads='1', primary='yes')
        ET.SubElement(video, 'address', type='pci', domain='0x0000', bus='0x00', slot='0x02', function='0x0')

    # Console (serial console) - redirect to file if configured
    console = ET.SubElement(devices, 'console', type='pty')
    if vm_config.serial_console_log_path:
        console.set('type', 'file')
        ET.SubElement(console, 'source', path=vm_config.serial_console_log_path)
    ET.SubElement(console, 'target', type='serial', port='0')

    # Input devices
    ET.SubElement(devices, 'input', type='tablet', bus='usb')
    ET.SubElement(devices, 'input', type='mouse', bus='ps2')
    ET.SubElement(devices, 'input', type='keyboard', bus='ps2')

    # Memory balloon
    memballoon = ET.SubElement(devices, 'memballoon', model='virtio')
    ET.SubElement(memballoon, 'address', type='pci', domain='0x0000', bus='0x00', slot='0x06', function='0x0')

    # QEMU commandline arguments (for QMP socket and port forwarding)
    # This preserves ADARE's control mechanisms
    qemu_commandline = ET.SubElement(domain, f'{{{QEMU_NAMESPACE}}}commandline')

    # Add QEMU debug log if configured
    if vm_config.qemu_debug_log_path:
        _add_qemu_arg(qemu_commandline, '-D')
        _add_qemu_arg(qemu_commandline, vm_config.qemu_debug_log_path)

    # Add QMP monitor socket
    _add_qemu_arg(qemu_commandline, '-qmp')
    _add_qemu_arg(qemu_commandline, f'unix:{vm_config.qmp_socket_path},server=on,wait=off')

    # Add port forwarding rules
    if vm_config.port_forwarding_rules:
        # Build netdev with port forwarding
        netdev_args = 'user,id=net0'
        for name, rule in vm_config.port_forwarding_rules.items():
            protocol = rule['protocol']
            host_port = rule['host_port']
            guest_port = rule['guest_port']
            host_ip = rule.get('host_ip', '')
            guest_ip = rule.get('guest_ip', '')

            if host_ip:
                hostfwd = f"{protocol}:{host_ip}:{host_port}-{guest_ip}:{guest_port}"
            else:
                hostfwd = f"{protocol}::{host_port}-:{guest_port}"

            netdev_args += f",hostfwd={hostfwd}"

        # Add network backend with port forwarding
        _add_qemu_arg(qemu_commandline, '-netdev')
        _add_qemu_arg(qemu_commandline, netdev_args)

        # Add network device connected to the netdev
        # This is critical - without it, the netdev exists but no device uses it
        _add_qemu_arg(qemu_commandline, '-device')
        _add_qemu_arg(qemu_commandline, 'virtio-net-pci,netdev=net0')

    # Convert to formatted XML string
    xml_str = _prettify_xml(domain)
    log.debug(f"CLAUDE: Generated libvirt XML ({len(xml_str)} bytes)")

    return xml_str


def _add_qemu_arg(qemu_commandline_element: ET.Element, value: str) -> None:
    """
    Add a QEMU commandline argument to the qemu:commandline section.

    Args:
        qemu_commandline_element: The qemu:commandline XML element
        value: The argument value
    """
    arg = ET.SubElement(qemu_commandline_element, f'{{{QEMU_NAMESPACE}}}arg')
    arg.set('value', value)


def _prettify_xml(elem: ET.Element) -> str:
    """
    Convert XML element to pretty-printed string.

    Args:
        elem: XML element to format

    Returns:
        str: Formatted XML string
    """
    rough_string = ET.tostring(elem, encoding='unicode')
    reparsed = minidom.parseString(rough_string)
    return reparsed.toprettyxml(indent='  ')
