"""
libvirt XML domain generation for QEMU VMs.

Generates libvirt XML domain definitions from QEMU VM configurations,
enabling VMs to be managed via virsh and virt-manager while preserving
ADARE's forensic-focused architecture (QMP, Guest Agent, overlays).
"""
import logging
import os
from pathlib import Path
from typing import Optional, Dict, Any, List
import xml.etree.ElementTree as ET
from xml.dom import minidom

from .firmware import find_ovmf_firmware, get_nvram_path_for_vm, create_nvram_for_vm

log = logging.getLogger(__name__)

# libvirt QEMU namespace for custom QEMU commandline arguments
QEMU_NAMESPACE = 'http://libvirt.org/schemas/domain/qemu/1.0'


def _add_q35_pcie_topology(devices: ET.Element, num_virtiofs_devices: int = 0) -> None:
    """Add proper PCIe topology for q35 machines.

    q35 machines require devices to connect through pcie-root-port
    controllers, not directly to the root bus. This mirrors what
    virt-install creates with --machine q35.

    Bus allocation:
    - Bus 1: Network (virtio-net)
    - Bus 2: USB controller
    - Bus 3: Virtio-serial
    - Bus 4: Disk (virtio-block)
    - Bus 5: Memory balloon
    - Buses 6-10: virtio-fs filesystem devices (up to 5)
    - Buses 11+: Reserved for future use

    Args:
        devices: The devices XML element
        num_virtiofs_devices: Number of virtiofs devices to allocate buses for
    """
    # Root controller (bus 0)
    ET.SubElement(devices, 'controller', type='pci', index='0', model='pcie-root')

    # Calculate total buses needed: base (6) + virtiofs devices (up to 5)
    # Minimum 9 buses for backward compatibility, max 14 for 5 virtiofs devices
    total_buses = max(9, 6 + num_virtiofs_devices)

    # Add pcie-root-port controllers (buses 1 to total_buses)
    # Each root port provides a bus for one device
    for i in range(1, total_buses + 1):
        port = ET.SubElement(devices, 'controller', type='pci', index=str(i), model='pcie-root-port')
        ET.SubElement(port, 'model', name='pcie-root-port')
        ET.SubElement(port, 'target', chassis=str(i), port=hex(0x10 + i - 1))

        # Root ports go on bus 0, starting from slot 2
        # Distribute across multiple slots if we have more than 8 ports (max 8 functions per slot)
        idx = i - 1
        slot_idx = 2 + (idx // 8)
        func_idx = idx % 8

        addr_attrs = {
            'type': 'pci',
            'domain': '0x0000',
            'bus': '0x00',
            'slot': hex(slot_idx),
            'function': hex(func_idx)
        }

        # Enable multifunction on function 0 (assumes we might use other functions on this slot)
        if func_idx == 0:
            addr_attrs['multifunction'] = 'on'

        ET.SubElement(port, 'address', **addr_attrs)

    # SATA controller (required for q35 chipset)
    sata = ET.SubElement(devices, 'controller', type='sata', index='0')
    ET.SubElement(sata, 'address', type='pci', domain='0x0000', bus='0x00', slot='0x1f', function='0x2')


def generate_domain_xml(
    vm_config,  # QEMUVMConfig instance
    display_enabled: bool = False,
    vnc_port: Optional[int] = None,
    virtiofs_shares: Optional[List[Dict[str, Any]]] = None
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
        virtiofs_shares: Optional list of virtiofs share configurations for shared directories

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

    # Memory backing for virtio-fs (required for shared memory between host and guest)
    if virtiofs_shares:
        memory_backing = ET.SubElement(domain, 'memoryBacking')
        ET.SubElement(memory_backing, 'source', type='memfd')
        ET.SubElement(memory_backing, 'access', mode='shared')
        log.debug(f"CLAUDE: Added memoryBacking for {len(virtiofs_shares)} virtio-fs shares")

    # IOThreads for disk performance
    # Allocating a dedicated IOThread improves disk I/O latency and throughput
    # We use 1 iothread for the main disk
    ET.SubElement(domain, 'iothreads').text = '1'

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
        # Additional performance optimizations
        ET.SubElement(hyperv, 'vpindex', state='on')
        ET.SubElement(hyperv, 'synic', state='on')
        ET.SubElement(hyperv, 'stimer', state='on')
        ET.SubElement(hyperv, 'reset', state='on')
        ET.SubElement(hyperv, 'frequencies', state='on')
        # tlbflush helps with memory management performance
        ET.SubElement(hyperv, 'tlbflush', state='on')
        # ipi improves inter-processor interrupt performance
        ET.SubElement(hyperv, 'ipi', state='on')
        ET.SubElement(hyperv, 'reenlightenment', state='on')
        ET.SubElement(hyperv, 'vendor_id', state='on', value='GenuineIntel')
        
        log.info(f"CLAUDE: Enabled extensive Hyper-V enlightenments for Windows VM {vm_config.vm_name}")

        # KVM-accelerated IOAPIC for lower interrupt overhead
        ET.SubElement(features, 'ioapic', driver='kvm')

        # Disable VMware backdoor port (conflicts with Hyper-V)
        ET.SubElement(features, 'vmport', state='off')

    # CPU mode (host-passthrough for KVM acceleration)
    cpu = ET.SubElement(domain, 'cpu', mode='host-passthrough', check='none')
    # Use 1 socket with multiple cores to avoid Windows OS license limits and improve scheduling
    ET.SubElement(cpu, 'topology', sockets='1', dies='1', cores=str(vm_config.cpus), threads='1')

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

    # Disable Security Drivers (AppArmor/SELinux) for this VM
    # This is critical for System Mode usage where we access user-home directories
    # (sockets, disks) which are usually blocked by default AppArmor profiles.
    ET.SubElement(domain, 'seclabel', type='none')

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
    # Use iothread for disk I/O to avoid blocking the vCPU
    # aio='native' for direct IO performance, discard='unmap' for SSD trim
    ET.SubElement(disk, 'driver', name='qemu', type=vm_config.drive_format, cache='none', iothread='1', aio='native', discard='unmap')
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
        num_virtiofs = len(virtiofs_shares) if virtiofs_shares else 0
        _add_q35_pcie_topology(devices, num_virtiofs)
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
            
            # SPICE without GL (handled by egl-headless)
            # Enable listening on localhost to allow virt-manager to connect
            # NOTE: Must be defined BEFORE egl-headless for virt-manager to pick it up as the primary console
            graphics = ET.SubElement(devices, 'graphics', type='spice', autoport='yes')
            graphics.set('listen', '127.0.0.1')
            ET.SubElement(graphics, 'listen', type='address', address='127.0.0.1')

            # EGL Headless for OpenGL support without local display context issues
            # This fixes black screen issues on some setups by offloading rendering
            ET.SubElement(devices, 'graphics', type='egl-headless')
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
            # VRAM increased to 256MB (262144 KB) to reduce GUI lag
            model = ET.SubElement(video, 'model', type='virtio', heads='1', primary='yes', vram='262144')
            
            # Only enable 3D acceleration if explicitly requested (currently DISABLED by default)
            # 3D acceleration (virgl) blocks live migration/snapshots in QEMU
            # if vm_config.virtiofs_enabled:
            #    ET.SubElement(model, 'acceleration', accel3d='yes')
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
            
            # Enable listening on localhost to allow virt-manager to connect
            # NOTE: Must be defined BEFORE egl-headless for virt-manager to pick it up as the primary console
            graphics = ET.SubElement(devices, 'graphics', type='spice', autoport='yes')
            graphics.set('listen', '127.0.0.1')
            ET.SubElement(graphics, 'listen', type='address', address='127.0.0.1')

            ET.SubElement(devices, 'graphics', type='egl-headless')
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
            # VRAM increased to 256MB (262144 KB) to reduce GUI lag
            model = ET.SubElement(video, 'model', type='virtio', heads='1', primary='yes', vram='262144')
            
            # Only enable 3D acceleration if explicitly requested (currently DISABLED by default)
            # if vm_config.virtiofs_enabled:
            #    ET.SubElement(model, 'acceleration', accel3d='yes')
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
    # DISABLED: Serial redirection causes permission errors in System Mode
    # if vm_config.serial_console_log_path:
    #    console.set('type', 'file')
    #    ET.SubElement(console, 'source', path=vm_config.serial_console_log_path)
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

    # virtio-fs filesystem devices for shared directories
    if virtiofs_shares:
        _add_virtiofs_filesystems(devices, virtiofs_shares, is_q35)
        log.info(f"CLAUDE: Added {len(virtiofs_shares)} virtio-fs filesystem devices")

    # QEMU commandline arguments (for QMP socket and port forwarding)
    # This preserves ADARE's control mechanisms
    qemu_commandline = ET.SubElement(domain, f'{{{QEMU_NAMESPACE}}}commandline')

    # Add QEMU debug log if configured
    # DISABLED for System Mode: QEMU cannot write to user files, and /tmp fixes failed.
    # if vm_config.qemu_debug_log_path:
    #    _add_qemu_arg(qemu_commandline, '-D')
    #    _add_qemu_arg(qemu_commandline, vm_config.qemu_debug_log_path)
    #    # Add debug categories...
    #    debug_categories = 'guest_errors' if is_windows else 'guest_errors,cpu_reset,unimp'
    #    _add_qemu_arg(qemu_commandline, debug_categories)
    #    if is_windows:
    #        log.info(f"CLAUDE: Using reduced debug logging for Windows VM (guest_errors only)")

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


def _add_virtiofs_filesystems(
    devices: ET.Element,
    virtiofs_shares: List[Dict[str, Any]],
    is_q35: bool
) -> None:
    """
    Add multiple virtio-fs filesystem devices for shared directories.

    Creates a libvirt filesystem element for each share. Each share gets:
    - Unique tag name for guest mounting
    - Unique PCI address (buses 6-10 for q35, slots 7-11 for pc)
    - Separate virtiofsd daemon managed by libvirt

    Args:
        devices: The devices XML element
        virtiofs_shares: List of share configurations, each containing:
            - tag: Unique tag name (e.g., 'run', 'vm', 'experiment')
            - host_path: Absolute path to host directory
            - guest_mount: Mount path in guest (for reference, not used in XML)
            - readonly: Read-only flag (optional)
        is_q35: True if using q35 machine type (affects PCI addressing)

    Note:
        - Requires memoryBacking with shared access mode in domain XML
        - Linux guest mounts with: mount -t virtiofs {tag} {mount_point}
        - Windows guest mounts with: virtiofs.exe -t {tag} -m {mount_point}
    """
    # Base bus/slot for virtiofs devices
    # q35: buses 6, 7, 8, 9, 10...
    # pc: slots 7, 8, 9, 10, 11... on bus 0
    base_bus = 6  # For q35
    base_slot = 7  # For pc

    for idx, share in enumerate(virtiofs_shares):
        filesystem = generate_virtiofs_xml_element(share, is_q35, idx, base_bus, base_slot)
        devices.append(filesystem)


def generate_virtiofs_xml_element(
    share: Dict[str, Any],
    is_q35: bool,
    index: int,
    base_bus: int = 6,
    base_slot: int = 7
) -> ET.Element:
    """
    Generate a single virtiofs filesystem XML element.

    Args:
        share: Share configuration dict
        is_q35: True if using q35 machine type
        index: Index of this share (0-based)
        base_bus: Base bus number for q35 (default 6)
        base_slot: Base slot number for pc (default 7)

    Returns:
        ET.Element: The filesystem XML element
    """
    tag = share['tag']
    host_path = share['host_path']

    filesystem = ET.Element('filesystem', type='mount', accessmode='passthrough')
    ET.SubElement(filesystem, 'driver', type='virtiofs')
    ET.SubElement(filesystem, 'source', dir=host_path)
    # Tag name used when mounting in guest: mount -t virtiofs {tag} {mount_point}
    ET.SubElement(filesystem, 'target', dir=tag)

    # Add idmap for uid/gid mapping (host user -> guest root)
    # This allows the guest to access files owned by the host user
    idmap = ET.SubElement(filesystem, 'idmap')
    host_uid = os.getuid()
    host_gid = os.getgid()
    ET.SubElement(idmap, 'uid', target='0', source=str(host_uid), count='1')
    ET.SubElement(idmap, 'gid', target='0', source=str(host_gid), count='1')

    # PCI addressing - each device gets unique address
    if is_q35:
        # Each device gets its own bus (6, 7, 8, 9, 10...)
        bus = base_bus + index
        ET.SubElement(filesystem, 'address', type='pci', domain='0x0000',
                        bus=f'0x{bus:02x}', slot='0x00', function='0x0')
    else:
        # For pc machine, use slots on bus 0 (7, 8, 9, 10, 11...)
        slot = base_slot + index
        ET.SubElement(filesystem, 'address', type='pci', domain='0x0000',
                        bus='0x00', slot=f'0x{slot:02x}', function='0x0')

    log.debug(f"CLAUDE: Generated virtio-fs XML for '{tag}' -> {host_path}")
    return filesystem
