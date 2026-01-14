"""
libvirt XML domain generation for QEMU VMs.

Generates libvirt XML domain definitions from QEMU VM configurations,
enabling VMs to be managed via virsh and virt-manager while preserving
ADARE's forensic-focused architecture (QMP, Guest Agent, overlays).
"""
import logging
from pathlib import Path
from typing import Optional, Dict, Any
import xml.etree.ElementTree as ET
from xml.dom import minidom

from .firmware import find_ovmf_firmware, get_nvram_path_for_vm, create_nvram_for_vm

log = logging.getLogger(__name__)

# libvirt QEMU namespace for custom QEMU commandline arguments
QEMU_NAMESPACE = 'http://libvirt.org/schemas/domain/qemu/1.0'


def _add_q35_pcie_topology(devices: ET.Element) -> None:
    """Add proper PCIe topology for q35 machines.

    q35 machines require devices to connect through pcie-root-port
    controllers, not directly to the root bus. This mirrors what
    virt-install creates with --machine q35.
    """
    # Root controller (bus 0)
    ET.SubElement(devices, 'controller', type='pci', index='0', model='pcie-root')

    # Add pcie-root-port controllers (buses 1-8)
    # Each root port provides a bus for one device
    for i in range(1, 9):
        port = ET.SubElement(devices, 'controller', type='pci', index=str(i), model='pcie-root-port')
        ET.SubElement(port, 'model', name='pcie-root-port')
        ET.SubElement(port, 'target', chassis=str(i), port=hex(0x10 + i - 1))
        # Root ports go on bus 0, slot 2, with multifunction for first one
        func = '0x0' if i == 1 else hex(i - 1)
        addr_attrs = {'type': 'pci', 'domain': '0x0000', 'bus': '0x00', 'slot': '0x02', 'function': func}
        if i == 1:
            addr_attrs['multifunction'] = 'on'
        ET.SubElement(port, 'address', **addr_attrs)

    # SATA controller (required for q35 chipset)
    sata = ET.SubElement(devices, 'controller', type='sata', index='0')
    ET.SubElement(sata, 'address', type='pci', domain='0x0000', bus='0x00', slot='0x1f', function='0x2')


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

    # Determine machine type early - affects device addresses
    is_windows = 'windows' in vm_config.guest_os.lower()
    effective_machine = 'q35' if (vm_config.boot_mode == 'uefi' and vm_config.machine == 'pc') else vm_config.machine
    is_q35 = effective_machine == 'q35'

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

    # OS configuration (BIOS or UEFI)
    os = ET.SubElement(domain, 'os')

    if vm_config.boot_mode == 'uefi':
        # UEFI boot configuration with OVMF firmware
        log.info(f"CLAUDE: Using UEFI boot for VM {vm_config.vm_name} (guest_os={vm_config.guest_os})")
        # NOTE: Do NOT set firmware='efi' - it conflicts with explicit loader/nvram elements
        # When firmware='efi' is set, libvirt auto-manages firmware paths, but we use
        # explicit <loader> and <nvram> elements for per-VM NVRAM control

        # Use q35 machine type for better UEFI support
        machine_type = 'q35' if vm_config.machine == 'pc' else vm_config.machine
        os_type = ET.SubElement(os, 'type', arch='x86_64', machine=machine_type)
        os_type.text = 'hvm'

        # Add OVMF firmware loader
        ovmf_code, ovmf_vars = find_ovmf_firmware()
        ET.SubElement(os, 'loader', readonly='yes', type='pflash').text = ovmf_code

        # NVRAM for UEFI variables (per-VM copy of OVMF_VARS.fd)
        # Extract VM config directory from disk path
        vm_config_dir = Path(vm_config.disk_path).parent
        nvram_path = create_nvram_for_vm(vm_config.vm_name, vm_config_dir)
        nvram_elem = ET.SubElement(os, 'nvram')
        nvram_elem.text = nvram_path
        nvram_elem.set('template', ovmf_vars)

        ET.SubElement(os, 'boot', dev='hd')
    else:
        # Legacy BIOS boot
        log.info(f"CLAUDE: Using BIOS boot for VM {vm_config.vm_name} (guest_os={vm_config.guest_os})")
        os_type = ET.SubElement(os, 'type', arch='x86_64', machine=vm_config.machine)
        os_type.text = 'hvm'
        ET.SubElement(os, 'boot', dev='hd')

    # Features (ACPI for proper shutdown)
    features = ET.SubElement(domain, 'features')
    ET.SubElement(features, 'acpi')
    ET.SubElement(features, 'apic')

    # Enable SMM for Windows VMs (required for UEFI firmware with Windows 10/11)
    # Windows UEFI firmware crashes without SMM enabled (Invalid Opcode exception)
    if is_windows:
        ET.SubElement(features, 'smm', state='on')
        log.info(f"CLAUDE: Enabled SMM for Windows VM {vm_config.vm_name}")

        # Hyper-V enlightenments for Windows VMs (improves performance and stability)
        # These paravirtual features tell Windows it's running under Hyper-V,
        # enabling optimized timers, ACPI, and reduced CPU usage
        hyperv = ET.SubElement(features, 'hyperv')
        ET.SubElement(hyperv, 'relaxed', state='on')
        ET.SubElement(hyperv, 'vapic', state='on')
        ET.SubElement(hyperv, 'spinlocks', state='on', retries='8191')
        log.info(f"CLAUDE: Enabled Hyper-V enlightenments for Windows VM {vm_config.vm_name}")

        # Disable VMware backdoor port (conflicts with Hyper-V)
        ET.SubElement(features, 'vmport', state='off')

    # CPU mode (host-passthrough for KVM acceleration)
    cpu = ET.SubElement(domain, 'cpu', mode='host-passthrough', check='none')

    # Clock configuration
    clock = ET.SubElement(domain, 'clock', offset='utc')
    ET.SubElement(clock, 'timer', name='rtc', tickpolicy='catchup')
    ET.SubElement(clock, 'timer', name='pit', tickpolicy='delay')
    ET.SubElement(clock, 'timer', name='hpet', present='no')
    if is_windows:
        # Hyper-V clock for better time synchronization in Windows guests
        ET.SubElement(clock, 'timer', name='hypervclock', present='yes')

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
    # For q35, disk goes on bus 4 (via pcie-root-port), for pc it stays on bus 0
    if is_q35:
        ET.SubElement(disk, 'address', type='pci', domain='0x0000', bus='0x04', slot='0x00', function='0x0')
    else:
        ET.SubElement(disk, 'address', type='pci', domain='0x0000', bus='0x00', slot='0x04', function='0x0')

    # Network interface
    # Windows VMs use bridge networking (network=default) for better reliability
    # Linux VMs use user-mode networking for simplicity
    # When port forwarding exists, network is fully configured via qemu:commandline
    # to avoid conflicts. Otherwise, use libvirt-managed interface for simplicity.
    if not vm_config.port_forwarding_rules:
        if is_windows:
            # Bridge networking for Windows VMs - better DHCP and network stack compatibility
            log.info(f"CLAUDE: Using bridge networking for Windows VM {vm_config.vm_name}")
            interface = ET.SubElement(devices, 'interface', type='network')
            ET.SubElement(interface, 'source', network='default')
            ET.SubElement(interface, 'model', type='virtio')
        else:
            # User-mode networking for Linux VMs
            interface = ET.SubElement(devices, 'interface', type='user')
            ET.SubElement(interface, 'model', type='virtio')
        # For q35, network goes on bus 1 (via pcie-root-port), for pc it stays on bus 0
        if is_q35:
            ET.SubElement(interface, 'address', type='pci', domain='0x0000', bus='0x01', slot='0x00', function='0x0')
        else:
            ET.SubElement(interface, 'address', type='pci', domain='0x0000', bus='0x00', slot='0x03', function='0x0')

    # Guest Agent channel (virtio-serial)
    channel = ET.SubElement(devices, 'channel', type='unix')
    channel_source = ET.SubElement(channel, 'source', mode='bind')
    channel_source.set('path', vm_config.guest_agent_socket_path)
    channel_target = ET.SubElement(channel, 'target', type='virtio', name='org.qemu.guest_agent.0')
    ET.SubElement(channel, 'address', type='virtio-serial', controller='0', bus='0', port='1')

    # SPICE vdagent channel for Windows VMs (improves graphics, clipboard, resolution)
    if 'windows' in vm_config.guest_os.lower():
        spice_channel = ET.SubElement(devices, 'channel', type='spicevmc')
        ET.SubElement(spice_channel, 'target', type='virtio', name='com.redhat.spice.0')
        ET.SubElement(spice_channel, 'address', type='virtio-serial', controller='0', bus='0', port='2')

    # Virtio-serial controller (required for Guest Agent and SPICE channels)
    controller_virtio = ET.SubElement(devices, 'controller', type='virtio-serial', index='0')
    # For q35, virtio-serial goes on bus 3 (via pcie-root-port), for pc it stays on bus 0
    if is_q35:
        ET.SubElement(controller_virtio, 'address', type='pci', domain='0x0000', bus='0x03', slot='0x00', function='0x0')
    else:
        ET.SubElement(controller_virtio, 'address', type='pci', domain='0x0000', bus='0x00', slot='0x05', function='0x0')

    # PCI controllers
    # For q35 machine (used with UEFI), use proper PCIe topology with root ports
    # For pc machine (BIOS), use simple pci-root
    if is_q35:
        _add_q35_pcie_topology(devices)
    else:
        ET.SubElement(devices, 'controller', type='pci', index='0', model='pci-root')

    # USB controller - on bus 2 for q35 (via pcie-root-port), bus 0 for pc
    usb = ET.SubElement(devices, 'controller', type='usb', index='0', model='qemu-xhci')
    if is_q35:
        ET.SubElement(usb, 'address', type='pci', domain='0x0000', bus='0x02', slot='0x00', function='0x0')

    # Graphics/Display configuration
    # Use SPICE for Windows VMs (better performance and faster initialization)
    # Use VNC for Linux VMs (backward compatibility)
    # Windows uses SPICE even in headless mode for better virt-manager compatibility
    if display_enabled:
        # Display visible by default (virt-manager will show console immediately)
        if is_windows:
            # SPICE for Windows VMs - eliminates graphics timeout
            log.info(f"CLAUDE: Using SPICE graphics for Windows VM {vm_config.vm_name}")
            
            # EGL Headless for OpenGL support without local display context issues
            # This fixes black screen issues on some setups by offloading rendering
            ET.SubElement(devices, 'graphics', type='egl-headless')
            
            # SPICE without GL (handled by egl-headless)
            graphics = ET.SubElement(devices, 'graphics', type='spice', autoport='no')
            graphics.set('listen', 'none')
            # Note: <gl enable='yes'/> removed from SPICE as it conflicts with egl-headless in some versions
            # or causes black screens. egl-headless handles the GL context.
        else:
            # VNC for Linux VMs
            if vnc_port:
                graphics = ET.SubElement(devices, 'graphics', type='vnc', port=str(vnc_port), autoport='no')
            else:
                graphics = ET.SubElement(devices, 'graphics', type='vnc', port='-1', autoport='yes')
            graphics.set('listen', '127.0.0.1')  # Localhost only for security
            ET.SubElement(graphics, 'listen', type='address', address='127.0.0.1')

        # Add video device for display
        video = ET.SubElement(devices, 'video')
        if is_windows:
            # Use virtio-gpu with 3D acceleration for Windows
            model = ET.SubElement(video, 'model', type='virtio', heads='1', primary='yes')
            ET.SubElement(model, 'acceleration', accel3d='yes')
        else:
            # Use QXL for Linux (better compatibility with standard drivers)
            model = ET.SubElement(video, 'model', type='qxl', ram='65536', vram='65536', vgamem='16384', heads='1', primary='yes')
        
        ET.SubElement(model, 'resolution', x='1920', y='1080')
        # For q35, video goes on slot 0x01 (slot 0x02 is used by pcie-root-ports)
        if is_q35:
            ET.SubElement(video, 'address', type='pci', domain='0x0000', bus='0x00', slot='0x01', function='0x0')
        else:
            ET.SubElement(video, 'address', type='pci', domain='0x0000', bus='0x00', slot='0x02', function='0x0')
    else:
        # Headless mode: graphics available but not shown by default
        # virt-manager can connect on-demand via "Open" button
        if is_windows:
            # Use SPICE for Windows even in headless mode - much better graphics initialization
            log.info(f"CLAUDE: Using SPICE graphics for Windows VM {vm_config.vm_name} (headless mode)")
            ET.SubElement(devices, 'graphics', type='egl-headless')
            graphics = ET.SubElement(devices, 'graphics', type='spice', autoport='no')
            graphics.set('listen', 'none')
            # gl removed here as well
        else:
            # VNC for Linux headless mode
            if vnc_port:
                graphics = ET.SubElement(devices, 'graphics', type='vnc', port=str(vnc_port), autoport='no')
            else:
                graphics = ET.SubElement(devices, 'graphics', type='vnc', port='-1', autoport='yes')
            graphics.set('listen', '127.0.0.1')
            ET.SubElement(graphics, 'listen', type='address', address='127.0.0.1')

        # Video device
        video = ET.SubElement(devices, 'video')
        if is_windows:
            # Use virtio-gpu with 3D acceleration for Windows
            model = ET.SubElement(video, 'model', type='virtio', heads='1', primary='yes')
            ET.SubElement(model, 'acceleration', accel3d='yes')
        else:
            # Use QXL for Linux
            model = ET.SubElement(video, 'model', type='qxl', ram='65536', vram='65536', vgamem='16384', heads='1', primary='yes')

        ET.SubElement(model, 'resolution', x='1920', y='1080')
        # For q35, video goes on slot 0x01 (slot 0x02 is used by pcie-root-ports)
        if is_q35:
            ET.SubElement(video, 'address', type='pci', domain='0x0000', bus='0x00', slot='0x01', function='0x0')
        else:
            ET.SubElement(video, 'address', type='pci', domain='0x0000', bus='0x00', slot='0x02', function='0x0')

    # Add TPM 2.0 for Windows VMs (required by Windows 11)
    # Windows 11 checks for TPM during boot and refuses to start without it
    # Uses software TPM emulator (swtpm) - no hardware TPM needed
    if is_windows:
        tpm = ET.SubElement(devices, 'tpm', model='tpm-crb')
        ET.SubElement(tpm, 'backend', type='emulator', version='2.0')
        log.info(f"CLAUDE: Added TPM 2.0 emulator for Windows VM {vm_config.vm_name}")

    # Console (serial console) - redirect to file if configured
    # NOTE: Empty serial_console.log is EXPECTED for most guest configurations
    # because modern Linux/Windows use graphical boot and don't output to serial.
    # To enable serial output in guest OS:
    #   Linux: Add 'console=ttyS0,115200 console=tty0' to GRUB_CMDLINE_LINUX
    #   Windows: Configure Emergency Management Services (EMS)
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
    # For q35, memballoon goes on bus 5 (via pcie-root-port), for pc it stays on bus 0
    if is_q35:
        ET.SubElement(memballoon, 'address', type='pci', domain='0x0000', bus='0x05', slot='0x00', function='0x0')
    else:
        ET.SubElement(memballoon, 'address', type='pci', domain='0x0000', bus='0x00', slot='0x06', function='0x0')

    # QEMU commandline arguments (for QMP socket and port forwarding)
    # This preserves ADARE's control mechanisms
    qemu_commandline = ET.SubElement(domain, f'{{{QEMU_NAMESPACE}}}commandline')

    # Add QEMU debug log if configured
    if vm_config.qemu_debug_log_path:
        _add_qemu_arg(qemu_commandline, '-D')
        _add_qemu_arg(qemu_commandline, vm_config.qemu_debug_log_path)
        # Add debug categories to enable actual logging output
        # Without -d, QEMU produces no debug output despite -D being set
        # For Windows, reduce debug categories to avoid interfering with UEFI firmware
        # The 'unimp' and 'cpu_reset' flags can trap UEFI operations and cause crashes
        debug_categories = 'guest_errors' if is_windows else 'guest_errors,cpu_reset,unimp'
        _add_qemu_arg(qemu_commandline, '-d')
        _add_qemu_arg(qemu_commandline, debug_categories)
        if is_windows:
            log.info(f"CLAUDE: Using reduced debug logging for Windows VM (guest_errors only)")

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
