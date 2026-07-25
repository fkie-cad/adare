"""
Builder pattern for libvirt domain XML generation.

Decomposes the monolithic generate_domain_xml() into focused methods,
each responsible for a logical section of the domain XML. PCIBusAllocator
provides a single source of truth for PCI bus/slot assignments.
"""
import logging
import os
import platform
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from xml.dom import minidom

from .accel import cpu_mode_and_model, native_accel
from .firmware import create_nvram_for_vm, find_ovmf_firmware

log = logging.getLogger(__name__)

# libvirt QEMU namespace for custom QEMU commandline arguments
QEMU_NAMESPACE = 'http://libvirt.org/schemas/domain/qemu/1.0'


class PCIBusAllocator:
    """Single source of truth for PCI bus/slot assignments.

    Q35 machine type uses PCIe with multiple buses (one device per bus via
    pcie-root-ports). PC/i440FX uses a single PCI bus with different slots.
    Virt machine type (aarch64) uses auto-assignment by libvirt.
    """

    # Q35 machine type (PCIe-based, multiple buses)
    _Q35_ASSIGNMENTS: dict[str, tuple[int, int]] = {
        'network': (1, 0),       # bus 1, slot 0
        'usb': (2, 0),           # bus 2, slot 0
        'virtio_serial': (3, 0), # bus 3, slot 0
        'disk': (4, 0),          # bus 4, slot 0
        'memballoon': (5, 0),    # bus 5, slot 0
    }
    _Q35_VIRTIOFS_BASE_BUS = 6  # buses 6+ for virtiofs shares

    # PC/i440FX machine type (PCI-based, single bus)
    _PC_ASSIGNMENTS: dict[str, tuple[int, int]] = {
        'network': (0, 3),       # bus 0, slot 3
        'disk': (0, 4),          # bus 0, slot 4
        'virtio_serial': (0, 5), # bus 0, slot 5
        'memballoon': (0, 6),    # bus 0, slot 6
        'usb': (0, 7),           # bus 0, slot 7 (qemu-xhci)
    }
    _PC_VIRTIOFS_BASE_SLOT = 8  # slots 8+ for virtiofs shares

    def __init__(self, is_q35: bool):
        self.is_q35 = is_q35

    def address_for(self, device: str, index: int = 0) -> dict[str, str]:
        """Return PCI address attributes dict for ET.SubElement.

        Args:
            device: Device type name (e.g. 'disk', 'network', 'virtiofs')
            index: Index for multi-instance devices like virtiofs shares

        Returns:
            Dict with PCI address attributes suitable for passing to
            ET.SubElement as keyword arguments.

        Raises:
            KeyError: If device is not a recognized type
        """
        if device == 'virtiofs':
            if self.is_q35:
                bus = self._Q35_VIRTIOFS_BASE_BUS + index
                return self._make_address(bus, 0)
            slot = self._PC_VIRTIOFS_BASE_SLOT + index
            return self._make_address(0, slot)

        assignments = self._Q35_ASSIGNMENTS if self.is_q35 else self._PC_ASSIGNMENTS

        if device not in assignments:
            raise KeyError(f"Unknown device type '{device}' for {'q35' if self.is_q35 else 'pc'} machine")

        bus, slot = assignments[device]
        return self._make_address(bus, slot)

    @staticmethod
    def _make_address(bus: int, slot: int) -> dict[str, str]:
        """Create PCI address attribute dict."""
        return {
            'type': 'pci',
            'domain': '0x0000',
            'bus': f'0x{bus:02x}',
            'slot': f'0x{slot:02x}',
            'function': '0x0',
        }


class DomainXMLBuilder:
    """Builder for libvirt domain XML configuration.

    Decomposes the monolithic generate_domain_xml() into focused methods,
    each responsible for a logical section of the domain XML. Produces
    identical output to the original function.
    """

    def __init__(
        self,
        vm_config,  # QEMUVMConfig instance
        display_enabled: bool = False,
        vnc_port: int | None = None,
        virtiofs_shares: list[dict[str, Any]] | None = None,
    ):
        self._config = vm_config
        self._display_enabled = display_enabled
        self._vnc_port = vnc_port
        self._virtiofs_shares = virtiofs_shares or []

        # Derived flags used across methods
        self._is_windows = 'windows' in vm_config.guest_os.lower()
        self._is_aarch64 = getattr(vm_config, 'architecture', 'x86_64') == 'aarch64'
        self._is_virt = vm_config.machine == 'virt' or self._is_aarch64
        self._is_darwin = platform.system().lower() == 'darwin'

        # Accelerator: trust an explicitly-resolved config.accel (hvf/kvm/tcg);
        # fall back to the host's native accelerator for configs that predate
        # this field or were never routed through the resolve_accel chokepoint.
        self._accel = getattr(vm_config, 'accel', None) or native_accel()

        # Determine effective machine type
        if self._is_virt:
            self._effective_machine = 'virt'
        elif vm_config.boot_mode == 'uefi' and vm_config.machine == 'pc':
            self._effective_machine = 'q35'
        else:
            self._effective_machine = vm_config.machine
        self._is_q35 = self._effective_machine == 'q35'

        self._guest_arch = 'aarch64' if self._is_aarch64 else 'x86_64'

        # Live-installer CDROM boot (GUI-automated / manual installs). Read
        # defensively so configs persisted before these fields existed still load.
        self._iso_path = getattr(vm_config, 'iso_path', '') or ''
        self._boot_from_cdrom = bool(getattr(vm_config, 'boot_from_cdrom', False))

        self._pci = PCIBusAllocator(self._is_q35)

        self._domain: ET.Element | None = None
        self._devices: ET.Element | None = None

    def build(self) -> str:
        """Build and return the complete domain XML string."""
        log.debug(f"Generating libvirt XML for VM: {self._config.vm_name}")

        # libvirt's 'qemu' domain type is the correct idiom for "no fixed
        # accelerator" (TCG); hvf/kvm otherwise name the accelerator directly.
        domain_type = 'qemu' if self._accel == 'tcg' else self._accel
        self._domain = ET.Element('domain', type=domain_type)
        self._domain.set('xmlns:qemu', QEMU_NAMESPACE)

        self._add_identity()
        self._add_memory()
        self._add_iothreads()
        self._add_cpu()
        self._add_os_boot()
        self._add_features()
        self._add_cpu_model()
        self._add_clock()
        self._add_power_management()
        self._add_security()
        self._add_devices()
        self._add_qemu_commandline()

        xml_str = self._prettify()
        log.debug(f"Generated libvirt XML ({len(xml_str)} bytes)")
        return xml_str

    def _add_identity(self) -> None:
        """Add VM name and UUID."""
        ET.SubElement(self._domain, 'name').text = self._config.vm_name
        ET.SubElement(self._domain, 'uuid').text = self._config.uuid

    def _add_memory(self) -> None:
        """Add memory configuration and optional memory backing for virtiofs."""
        memory = ET.SubElement(self._domain, 'memory', unit='MiB')
        memory.text = str(self._config.ram)
        current_memory = ET.SubElement(self._domain, 'currentMemory', unit='MiB')
        current_memory.text = str(self._config.ram)

        # Memory backing for virtio-fs (required for shared memory between host and guest)
        if self._virtiofs_shares:
            memory_backing = ET.SubElement(self._domain, 'memoryBacking')
            ET.SubElement(memory_backing, 'source', type='memfd')
            ET.SubElement(memory_backing, 'access', mode='shared')
            log.debug(f"Added memoryBacking for {len(self._virtiofs_shares)} virtio-fs shares")

    def _add_iothreads(self) -> None:
        """Add IOThread for disk performance."""
        ET.SubElement(self._domain, 'iothreads').text = '1'

    def _add_cpu(self) -> None:
        """Add vCPU count."""
        vcpu = ET.SubElement(self._domain, 'vcpu', placement='static')
        vcpu.text = str(self._config.cpus)

    def _add_os_boot(self) -> None:
        """Add OS boot configuration (BIOS or UEFI)."""
        os_elem = ET.SubElement(self._domain, 'os')

        if self._config.boot_mode == 'uefi' or self._is_aarch64:
            log.info(
                f"Using UEFI boot for VM {self._config.vm_name} "
                f"(guest_os={self._config.guest_os}, arch={self._guest_arch})"
            )

            os_type = ET.SubElement(os_elem, 'type', arch=self._guest_arch, machine=self._effective_machine)
            os_type.text = 'hvm'

            # Add OVMF firmware loader (architecture-aware)
            ovmf_code, ovmf_vars = find_ovmf_firmware(self._guest_arch)
            ET.SubElement(os_elem, 'loader', readonly='yes', type='pflash').text = ovmf_code

            # NVRAM for UEFI variables (per-VM copy of OVMF_VARS.fd)
            vm_config_dir = Path(self._config.disk_path).parent
            nvram_path = create_nvram_for_vm(self._config.vm_name, vm_config_dir, self._guest_arch)
            nvram_elem = ET.SubElement(os_elem, 'nvram')
            nvram_elem.text = nvram_path

            # Per-device <boot order> (set in _add_disk/_add_cdrom) is mutually
            # exclusive with a global <boot dev>. Only emit the global element
            # when we are NOT booting from CDROM.
            if not self._boot_from_cdrom:
                ET.SubElement(os_elem, 'boot', dev='hd')
        else:
            log.info(f"Using BIOS boot for VM {self._config.vm_name} (guest_os={self._config.guest_os})")
            os_type = ET.SubElement(os_elem, 'type', arch='x86_64', machine=self._config.machine)
            os_type.text = 'hvm'
            if not self._boot_from_cdrom:
                ET.SubElement(os_elem, 'boot', dev='hd')

    def _add_features(self) -> None:
        """Add CPU features: ACPI, APIC, SMM, Hyper-V enlightenments."""
        features = ET.SubElement(self._domain, 'features')
        ET.SubElement(features, 'acpi')
        if not self._is_aarch64:
            ET.SubElement(features, 'apic')

        if self._is_windows:
            if not self._is_aarch64:
                ET.SubElement(features, 'smm', state='on')
                log.info(f"Enabled SMM for Windows VM {self._config.vm_name}")

            # Hyper-V enlightenments (KVM-only — not available under HVF or TCG)
            if self._accel == 'kvm':
                hyperv = ET.SubElement(features, 'hyperv')
                ET.SubElement(hyperv, 'relaxed', state='on')
                ET.SubElement(hyperv, 'vapic', state='on')
                ET.SubElement(hyperv, 'spinlocks', state='on', retries='8191')
                ET.SubElement(hyperv, 'vpindex', state='on')
                ET.SubElement(hyperv, 'synic', state='on')
                ET.SubElement(hyperv, 'stimer', state='on')
                ET.SubElement(hyperv, 'reset', state='on')
                ET.SubElement(hyperv, 'frequencies', state='on')
                ET.SubElement(hyperv, 'tlbflush', state='on')
                ET.SubElement(hyperv, 'ipi', state='on')
                ET.SubElement(hyperv, 'reenlightenment', state='on')
                ET.SubElement(hyperv, 'vendor_id', state='on', value='GenuineIntel')
                log.info(f"Enabled Hyper-V enlightenments for Windows VM {self._config.vm_name}")

            # KVM-accelerated IOAPIC (KVM-only)
            if self._accel == 'kvm':
                ET.SubElement(features, 'ioapic', driver='kvm')

            # Disable VMware backdoor port (x86-only, conflicts with Hyper-V)
            if not self._is_aarch64:
                ET.SubElement(features, 'vmport', state='off')

    def _add_cpu_model(self) -> None:
        """Add CPU model and topology.

        Under hardware acceleration, host-passthrough exposes the real host
        CPU. Under TCG there is no host CPU to pass through (especially
        cross-arch emulation), so a generic model is used instead.
        """
        cpu_mode, cpu_model = cpu_mode_and_model(self._accel, self._guest_arch)
        if cpu_mode == 'host-passthrough':
            cpu = ET.SubElement(self._domain, 'cpu', mode='host-passthrough', check='none')
        else:
            cpu = ET.SubElement(self._domain, 'cpu', mode='custom', match='exact')
            ET.SubElement(cpu, 'model', fallback='allow').text = cpu_model
        ET.SubElement(cpu, 'topology', sockets='1', dies='1', cores=str(self._config.cpus), threads='1')

    def _add_clock(self) -> None:
        """Add clock configuration with platform-specific timers."""
        clock = ET.SubElement(self._domain, 'clock', offset='utc')
        if not self._is_aarch64:
            ET.SubElement(clock, 'timer', name='rtc', tickpolicy='catchup')
            ET.SubElement(clock, 'timer', name='pit', tickpolicy='delay')
            ET.SubElement(clock, 'timer', name='hpet', present='no')
        if self._is_windows and not self._is_darwin:
            ET.SubElement(clock, 'timer', name='hypervclock', present='yes')

    def _add_power_management(self) -> None:
        """Add power management actions."""
        ET.SubElement(self._domain, 'on_poweroff').text = 'destroy'
        # GUI installers reboot when finished. Booting from CDROM with
        # on_reboot=restart would re-enter the installer, so power off instead;
        # the creator then boots the installed disk (boot_from_cdrom=False).
        on_reboot = 'destroy' if self._boot_from_cdrom else 'restart'
        ET.SubElement(self._domain, 'on_reboot').text = on_reboot
        ET.SubElement(self._domain, 'on_crash').text = 'destroy'

    def _add_security(self) -> None:
        """Disable security drivers (AppArmor/SELinux) for user-home access."""
        ET.SubElement(self._domain, 'seclabel', type='none')

    def _add_devices(self) -> None:
        """Add all device configurations."""
        self._devices = ET.SubElement(self._domain, 'devices')

        self._add_emulator()
        self._add_disk()
        self._add_cdrom()
        self._add_network()
        self._add_guest_agent_channel()
        self._add_spice_channel()
        self._add_virtio_serial_controller()
        self._add_pci_controllers()
        self._add_usb_controller()
        self._add_graphics()
        self._add_tpm()
        self._add_console()
        self._add_input_devices()
        self._add_memballoon()
        self._add_virtiofs_filesystems()

    def _add_emulator(self) -> None:
        """Add QEMU emulator path (architecture-aware).

        Search order on macOS: PATH, MacPorts (/opt/local/bin), Homebrew.
        """
        qemu_exe = f'qemu-system-{self._guest_arch}'
        qemu_full_path = shutil.which(qemu_exe)
        if not qemu_full_path:
            if self._is_darwin:
                for candidate in [
                    f'/opt/local/bin/{qemu_exe}',       # MacPorts
                    f'/opt/homebrew/bin/{qemu_exe}',     # Homebrew (Apple Silicon)
                    f'/usr/local/bin/{qemu_exe}',        # Homebrew (Intel)
                ]:
                    if os.path.isfile(candidate):
                        qemu_full_path = candidate
                        break
            if not qemu_full_path:
                qemu_full_path = shutil.which(qemu_exe) or f'/usr/bin/{qemu_exe}'
        log.info(f"Using QEMU emulator: {qemu_full_path}")
        ET.SubElement(self._devices, 'emulator').text = qemu_full_path

    def _add_disk(self) -> None:
        """Add disk configuration with iothread.

        ARM64 disks are added via qemu:commandline (see _add_qemu_commandline):
        Windows uses NVMe (native driver, matches installation), Linux uses
        virtio-blk (migratable, so savevm/loadvm checkpoints work).
        x86_64 uses virtio-blk (viostor loaded by Windows).
        """
        if self._is_aarch64:
            return  # NVMe disk added via qemu:commandline in _add_qemu_commandline()

        disk = ET.SubElement(self._devices, 'disk', type='file', device='disk')
        aio_mode = 'threads' if self._is_darwin else 'native'
        ET.SubElement(
            disk, 'driver', name='qemu', type=self._config.drive_format,
            cache='none', iothread='1', aio=aio_mode, discard='unmap',
        )
        ET.SubElement(disk, 'source', file=self._config.disk_path)
        ET.SubElement(disk, 'target', dev='vda', bus='virtio')

        # When booting an installer from CDROM, the hard disk is the second boot
        # device (per-device order; the CDROM gets order 1 in _add_cdrom).
        if self._boot_from_cdrom:
            ET.SubElement(disk, 'boot', order='2')

        if self._is_virt:
            pass  # libvirt auto-assigns addresses on virt machine
        elif self._is_q35:
            ET.SubElement(disk, 'address', **self._pci.address_for('disk'))
        else:
            ET.SubElement(disk, 'address', **self._pci.address_for('disk'))

    def _add_cdrom(self) -> None:
        """Attach an installer ISO as a read-only CDROM device.

        Emitted only when the config carries an ``iso_path``. On q35 the CDROM
        rides the built-in SATA controller (added by _add_q35_pcie_topology);
        on plain i440FX ``pc`` it falls back to the IDE bus. aarch64 has no
        <disk>-based path (NVMe/virtio via commandline) so the ISO is attached
        in _add_qemu_commandline() instead — skip here.
        """
        if not self._iso_path or self._is_aarch64:
            return

        cdrom = ET.SubElement(self._devices, 'disk', type='file', device='cdrom')
        ET.SubElement(cdrom, 'driver', name='qemu', type='raw')
        ET.SubElement(cdrom, 'source', file=self._iso_path)
        bus = 'sata' if self._is_q35 else 'ide'
        ET.SubElement(cdrom, 'target', dev='sda', bus=bus)
        ET.SubElement(cdrom, 'readonly')

        # Boot the installer first; the disk (order 2) is the post-install target.
        if self._boot_from_cdrom:
            ET.SubElement(cdrom, 'boot', order='1')

    def _add_network(self) -> None:
        """Add network interface (unless port forwarding or SMB is via qemu:commandline)."""
        smb_path = getattr(self._config, 'smb_share_path', None)
        if self._config.port_forwarding_rules or smb_path:
            return  # Network configured via qemu:commandline instead

        if self._is_windows and not self._is_darwin:
            log.info(f"Using bridge networking for Windows VM {self._config.vm_name}")
            interface = ET.SubElement(self._devices, 'interface', type='network')
            ET.SubElement(interface, 'source', network='default')
            ET.SubElement(interface, 'model', type='virtio')
        else:
            interface = ET.SubElement(self._devices, 'interface', type='user')
            ET.SubElement(interface, 'model', type='virtio')

        if self._is_virt:
            pass  # libvirt auto-assigns addresses on virt machine
        elif self._is_q35:
            ET.SubElement(interface, 'address', **self._pci.address_for('network'))
        else:
            ET.SubElement(interface, 'address', **self._pci.address_for('network'))

    def _add_guest_agent_channel(self) -> None:
        """Add QEMU Guest Agent virtio-serial channel."""
        channel = ET.SubElement(self._devices, 'channel', type='unix')
        channel_source = ET.SubElement(channel, 'source', mode='bind')
        channel_source.set('path', self._config.guest_agent_socket_path)
        ET.SubElement(channel, 'target', type='virtio', name='org.qemu.guest_agent.0')
        if not self._is_virt:
            ET.SubElement(channel, 'address', type='virtio-serial', controller='0', bus='0', port='1')

    def _add_spice_channel(self) -> None:
        """Add SPICE vdagent channel (clipboard, resolution negotiation)."""
        if not self._is_windows and not self._is_darwin:
            return
        spice_channel = ET.SubElement(self._devices, 'channel', type='spicevmc')
        ET.SubElement(spice_channel, 'target', type='virtio', name='com.redhat.spice.0')
        if not self._is_virt:
            ET.SubElement(spice_channel, 'address', type='virtio-serial', controller='0', bus='0', port='2')

    def _add_virtio_serial_controller(self) -> None:
        """Add virtio-serial controller (required for Guest Agent and SPICE channels)."""
        controller = ET.SubElement(self._devices, 'controller', type='virtio-serial', index='0')
        if self._is_virt:
            pass
        elif self._is_q35:
            ET.SubElement(controller, 'address', **self._pci.address_for('virtio_serial'))
        else:
            ET.SubElement(controller, 'address', **self._pci.address_for('virtio_serial'))

    def _add_pci_controllers(self) -> None:
        """Add PCI controller topology (varies by machine type)."""
        if self._is_virt:
            ET.SubElement(self._devices, 'controller', type='pci', index='0', model='pcie-root')
        elif self._is_q35:
            num_virtiofs = len(self._virtiofs_shares) if self._virtiofs_shares else 0
            _add_q35_pcie_topology(self._devices, num_virtiofs)
        else:
            ET.SubElement(self._devices, 'controller', type='pci', index='0', model='pci-root')

    def _add_usb_controller(self) -> None:
        """Add USB controller."""
        usb = ET.SubElement(self._devices, 'controller', type='usb', index='0', model='qemu-xhci')
        if not self._is_virt:
            ET.SubElement(usb, 'address', **self._pci.address_for('usb'))

    def _add_graphics(self) -> None:
        """Add graphics/display and video device configuration."""
        if self._display_enabled:
            self._add_graphics_enabled()
        else:
            self._add_graphics_headless()

    def _add_spice_graphics(self) -> None:
        """Add SPICE graphics (dirty-region updates, lower latency than VNC)."""
        graphics = ET.SubElement(self._devices, 'graphics', type='spice', autoport='yes')
        graphics.set('listen', '127.0.0.1')
        ET.SubElement(graphics, 'listen', type='address', address='127.0.0.1')
        # Force a codec the ADARE-owned SPICE client fully decodes. The server emits
        # LZ_RGB (image_type 101); if the client advertises SPICE_DISPLAY_CAP_LZ4 the
        # server upgrades to LZ4 (109) — both have real decoders. This keeps QUIC/GLZ
        # (unimplemented) off the wire. Localhost listen makes LZ4's larger frames free.
        ET.SubElement(graphics, 'image', compression='lz')
        # Disable MJPEG video streaming so no STREAM_* messages are emitted — the client
        # has no stream parser and does not need one.
        ET.SubElement(graphics, 'streaming', mode='off')

    def _add_vnc_graphics(self) -> None:
        """Add VNC graphics as fallback (e.g. Linux hosts without SPICE client)."""
        attrs = {'type': 'vnc', 'autoport': 'yes', 'passwd': 'adare'}
        if self._vnc_port:
            attrs['port'] = str(self._vnc_port)
            attrs['autoport'] = 'no'
        else:
            attrs['port'] = '-1'
        graphics = ET.SubElement(self._devices, 'graphics', **attrs)
        graphics.set('listen', '127.0.0.1')
        ET.SubElement(graphics, 'listen', type='address', address='127.0.0.1')

    def _add_graphics_enabled(self) -> None:
        """Add display-enabled graphics configuration."""
        if self._is_darwin:
            self._add_spice_graphics()
        elif self._is_windows:
            self._add_spice_graphics()
            ET.SubElement(self._devices, 'graphics', type='egl-headless')
        else:
            self._add_vnc_graphics()

        self._add_video_device()

    def _add_graphics_headless(self) -> None:
        """Add headless graphics configuration."""
        if self._is_darwin:
            self._add_spice_graphics()
        elif self._is_windows:
            self._add_spice_graphics()
            ET.SubElement(self._devices, 'graphics', type='egl-headless')
        else:
            self._add_vnc_graphics()

        self._add_video_device()

    def _add_video_device(self) -> None:
        """Add video device with resolution configuration."""
        video = ET.SubElement(self._devices, 'video')
        if self._is_aarch64:
            # type='none' tells libvirt not to create any video device.
            # The actual GPU (virtio-gpu-pci for Linux, virtio-gpu-device/MMIO for
            # Windows) and boot framebuffer (ramfb) are added via qemu:commandline
            # in _add_qemu_commandline(). This prevents libvirt's video device from
            # intercepting SPICE display channels — the virtio-gpu auto-outputs to
            # SPICE instead.
            model = ET.SubElement(video, 'model', type='none')
        elif self._is_windows and not self._is_darwin:
            model = ET.SubElement(video, 'model', type='virtio', heads='1', primary='yes', vram='262144')
        else:
            model = ET.SubElement(video, 'model', type='qxl', ram='65536', vram='65536', vgamem='16384', heads='1', primary='yes')

        if not self._is_aarch64:  # type='none' doesn't support resolution hints
            rx = getattr(self._config, 'resolution_x', 1920)
            ry = getattr(self._config, 'resolution_y', 1080)
            ET.SubElement(model, 'resolution', x=str(rx), y=str(ry))
        if self._is_virt:
            pass
        elif self._is_q35:
            ET.SubElement(video, 'address', type='pci', domain='0x0000', bus='0x00', slot='0x01', function='0x0')
        else:
            ET.SubElement(video, 'address', type='pci', domain='0x0000', bus='0x00', slot='0x02', function='0x0')

    def _add_tpm(self) -> None:
        """Add TPM 2.0 for Windows VMs (required by Windows 11)."""
        if not self._is_windows:
            return
        if shutil.which('swtpm'):
            # tpm-crb is an x86-only interface; aarch64 QEMU only provides the
            # TIS device (tpm-tis-device). Advertising tpm-crb on aarch64 makes
            # libvirt reject the domain ("does not support TPM model tpm-crb").
            tpm_model = 'tpm-tis' if self._is_aarch64 else 'tpm-crb'
            tpm = ET.SubElement(self._devices, 'tpm', model=tpm_model)
            ET.SubElement(tpm, 'backend', type='emulator', version='2.0')
            log.info(f"Added TPM 2.0 emulator ({tpm_model}) for Windows VM {self._config.vm_name}")
        elif self._is_darwin:
            log.warning(
                "swtpm not available — Windows 11 may not boot without TPM. "
                "Windows 10 works without TPM. Consider VirtualBox for Win11."
            )

    def _add_console(self) -> None:
        """Add serial console device."""
        console = ET.SubElement(self._devices, 'console', type='pty')
        console_target_type = 'virtio' if self._is_virt else 'serial'
        ET.SubElement(console, 'target', type=console_target_type, port='0')

    def _add_input_devices(self) -> None:
        """Add input devices (tablet, mouse, keyboard).

        On macOS/HVF, the secondary mouse is omitted to prevent BTN event
        routing conflicts — the USB tablet handles both positioning and clicks.
        """
        # IMPORTANT: Tablet MUST be added first. QEMU routes input events to the first
        # matching handler in its global list. If a secondary mouse (virtio/ps2) registers
        # before the tablet, BTN (click) events go to the mouse while ABS (position) events
        # go to the tablet — causing clicks to land on the wrong device. On macOS/HVF the
        # secondary mouse is omitted entirely to avoid this conflict.
        ET.SubElement(self._devices, 'input', type='tablet', bus='usb')
        if self._is_aarch64:
            if not self._is_darwin:
                ET.SubElement(self._devices, 'input', type='mouse', bus='virtio')
            # Virtio keyboard added via qemu:commandline in _add_qemu_commandline()
            # so it registers before this USB keyboard in QEMU's handler list,
            # making input-send-event key events route to virtio (works on HVF).
            ET.SubElement(self._devices, 'input', type='keyboard', bus='usb')
        else:
            if not self._is_darwin:
                ET.SubElement(self._devices, 'input', type='mouse', bus='ps2')
            ET.SubElement(self._devices, 'input', type='keyboard', bus='ps2')

    def _add_memballoon(self) -> None:
        """Add virtio memory balloon device."""
        memballoon = ET.SubElement(self._devices, 'memballoon', model='virtio')
        if self._is_virt:
            pass
        elif self._is_q35:
            ET.SubElement(memballoon, 'address', **self._pci.address_for('memballoon'))
        else:
            ET.SubElement(memballoon, 'address', **self._pci.address_for('memballoon'))

    def _add_virtiofs_filesystems(self) -> None:
        """Add virtio-fs filesystem devices for shared directories."""
        if not self._virtiofs_shares:
            return

        for idx, share in enumerate(self._virtiofs_shares):
            filesystem = _generate_virtiofs_xml_element(
                share, self._is_q35, idx,
                PCIBusAllocator._Q35_VIRTIOFS_BASE_BUS,
                PCIBusAllocator._PC_VIRTIOFS_BASE_SLOT,
                self._is_virt,
            )
            self._devices.append(filesystem)

        log.info(f"Added {len(self._virtiofs_shares)} virtio-fs filesystem devices")

    def _add_qemu_commandline(self) -> None:
        """Add QEMU commandline arguments (QMP, HVF, port forwarding, NVMe)."""
        qemu_commandline = ET.SubElement(self._domain, f'{{{QEMU_NAMESPACE}}}commandline')

        # QMP monitor socket
        _add_qemu_arg(qemu_commandline, '-qmp')
        _add_qemu_arg(qemu_commandline, f'unix:{self._config.qmp_socket_path},server=on,wait=off')

        # QEMU debug logging (lifecycle.py sets qemu_debug_log_path but only
        # vm.py direct-QEMU uses it — add -D/-d so libvirt launches get logs too)
        if self._config.qemu_debug_log_path:
            log_path = f"/tmp/adare_qemu_debug_{self._config.vm_name}.log"
            _add_qemu_arg(qemu_commandline, '-D')
            _add_qemu_arg(qemu_commandline, log_path)
            _add_qemu_arg(qemu_commandline, '-d')
            _add_qemu_arg(qemu_commandline, 'guest_errors,cpu_reset,unimp')

        # ARM64 guest disk — attached via raw QEMU args because the controller
        # lives on pcie.0 at a pinned high slot (kept clear of libvirt's
        # auto-assigned pcie-root-ports). Controller choice depends on the guest:
        #
        #   * Windows aarch64 -> nvme. Windows ships a native NVMe driver and the
        #     guest was installed on nvme; virtio-blk would need viostor.
        #   * Linux aarch64   -> virtio-blk-pci. nvme is a NON-MIGRATABLE QEMU
        #     device, which makes savevm/loadvm (dev-mode checkpoint/restore on
        #     qemu:///session, where libvirt external snapshots are unavailable)
        #     abort with "State blocked by non-migratable device". virtio-blk-pci
        #     is fully migratable, so the VM RAM+device state can be captured into
        #     an internal qcow2 snapshot. Linux's generic initramfs carries
        #     virtio_blk and mounts by UUID, so the /dev/nvme0n1 -> /dev/vda
        #     controller change does not affect boot.
        if self._is_aarch64:
            _add_qemu_arg(qemu_commandline, '-drive')
            disk_cache = 'writethrough' if self._is_darwin else 'none'
            _add_qemu_arg(
                qemu_commandline,
                f'file={self._config.disk_path},format={self._config.drive_format},'
                f'if=none,id=hd0,cache={disk_cache},discard=unmap',
            )
            _add_qemu_arg(qemu_commandline, '-device')
            # When installing from an ISO the CDROM boots first (bootindex 0) and
            # the target disk is bootindex 1; otherwise the disk boots first.
            disk_bootindex = 1 if (self._iso_path and self._boot_from_cdrom) else 0
            disk_model = 'nvme' if self._is_windows else 'virtio-blk-pci'
            _add_qemu_arg(
                qemu_commandline,
                f'{disk_model},drive=hd0,serial=disk0,bootindex={disk_bootindex},'
                f'bus=pcie.0,addr=0x1e',
            )

        # aarch64 installer CDROM (libvirt <disk device='cdrom'> is skipped for
        # aarch64 in _add_cdrom, so attach the ISO via raw QEMU args here).
        if self._is_aarch64 and self._iso_path:
            _add_qemu_arg(qemu_commandline, '-drive')
            _add_qemu_arg(
                qemu_commandline,
                f'file={self._iso_path},format=raw,if=none,id=cd0,media=cdrom,readonly=on',
            )
            _add_qemu_arg(qemu_commandline, '-device')
            cd_bootindex = 0 if self._boot_from_cdrom else 2
            _add_qemu_arg(qemu_commandline, f'usb-storage,drive=cd0,bootindex={cd_bootindex}')

        # aarch64 display device — transport differs per guest OS (see branches).
        if self._is_aarch64:
            rx = getattr(self._config, 'resolution_x', 1920)
            ry = getattr(self._config, 'resolution_y', 1080)
            if self._is_windows and not self._iso_path:
                # Windows aarch64, running a baked env (no installer ISO): PCI
                # virtio-gpu with NO ramfb, mirroring the Linux branch below. This is
                # the default runtime path. edk2 VirtioGpuDxe provides the boot GOP,
                # and viogpudo (VioGpuDod, shipped by UTM Guest Tools) binds to PCI
                # virtio-gpu (DEV_1050) — a real display driver instead of the
                # Microsoft Basic Display Driver. The MMIO virtio-gpu-device (install
                # branch) otherwise lands on an ACPI\LNRO0005 virtio-mmio slot Windows
                # has no bus driver for, so the display falls back to the Basic Display
                # Driver over ramfb at 800x600.
                #
                # NOTE: viogpudo does NOT honour the advertised EDID/xres/yres at boot
                # (live-tested: it comes up at its 1024x768 default). The configured
                # resolution is applied at runtime by a guest-side ChangeDisplaySettings
                # call in the console session — see agent_lifecycle._build_windows_set_
                # resolution_command. edid=on is kept as it is harmless and advertises
                # the intended mode.
                _add_qemu_arg(qemu_commandline, '-device')
                _add_qemu_arg(
                    qemu_commandline,
                    f'virtio-gpu-pci,edid=on,xres={rx},yres={ry},bus=pcie.0,addr=0x1d',
                )
            elif self._is_windows:
                # Windows aarch64, installing (installer ISO attached): ramfb boot
                # framebuffer + the MMIO virtio-gpu-device. PCI virtio-gpu risks the
                # documented WinPE/boot BSOD on the ramfb->GPU handoff (see vm_creator/
                # qmp_utils.py, windows_creator.py), and the resolution is irrelevant
                # during install anyway. edid=on + xres/yres advertise the target mode.
                _add_qemu_arg(qemu_commandline, '-device')
                _add_qemu_arg(qemu_commandline, 'ramfb')
                _add_qemu_arg(qemu_commandline, '-device')
                _add_qemu_arg(qemu_commandline, f'virtio-gpu-device,edid=on,xres={rx},yres={ry}')
            else:
                # Linux aarch64: virtio-gpu-PCI ONLY, no ramfb. The Linux virtio_gpu
                # driver probes it and honors the EDID/xres/yres, giving a single
                # display at the configured resolution (edk2/AAVMF drives it as the
                # boot GOP). ramfb must NOT be added here: it creates a competing
                # 800x600 simple-framebuffer/simpledrm card (card0) that GNOME latches
                # onto instead of the virtio-gpu card — the exact reason the guest was
                # stuck at 800x600. Pin an explicit high slot on pcie.0 (like the
                # NVMe/net devices at 0x1e/0x1f) so it doesn't collide with libvirt's
                # auto-assigned pcie-root-ports on the low slots.
                _add_qemu_arg(qemu_commandline, '-device')
                _add_qemu_arg(
                    qemu_commandline,
                    f'virtio-gpu-pci,edid=on,xres={rx},yres={ry},bus=pcie.0,addr=0x1d',
                )

        # Keyboards: qemu:commandline args are placed on the QEMU command line
        # BEFORE libvirt's own -device args. virtio-keyboard-device here therefore
        # registers its input handler before the usb-kbd added via <input> in
        # _add_input_devices(), making input-send-event key events route to virtio
        # (which works reliably on HVF). usb-kbd stays as a libvirt <input> element
        # because it needs the USB bus from the xHCI controller (also a libvirt device).
        if self._is_aarch64:
            _add_qemu_arg(qemu_commandline, '-device')
            _add_qemu_arg(qemu_commandline, 'virtio-keyboard-device')

        # aarch64 + HVF: keep device MMIO/ECAM/GIC regions below 4 GB so edk2
        # firmware can enumerate devices. Fine-grained properties avoid the
        # ~3 GB RAM cap imposed by blanket highmem=off.
        if self._is_aarch64 and self._is_darwin:
            for prop in ('highmem-mmio', 'highmem-ecam', 'highmem-redists'):
                _add_qemu_arg(qemu_commandline, '-global')
                _add_qemu_arg(qemu_commandline, f'virt-machine.{prop}=off')

        # Network commandline (port forwarding and/or SMB share)
        smb_path = getattr(self._config, 'smb_share_path', None)
        if self._config.port_forwarding_rules or smb_path:
            self._add_network_commandline(qemu_commandline)

    def _add_network_commandline(self, qemu_commandline: ET.Element) -> None:
        """Add network backend with port forwarding and/or SMB via QEMU commandline."""
        netdev_args = 'user,id=net0'

        # SMB share (QEMU SLIRP built-in smbd)
        smb_path = getattr(self._config, 'smb_share_path', None)
        if smb_path:
            netdev_args += f',smb={smb_path}'

        # Port forwarding (can coexist with SMB on same netdev)
        for _name, rule in self._config.port_forwarding_rules.items():
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

        _add_qemu_arg(qemu_commandline, '-netdev')
        _add_qemu_arg(qemu_commandline, netdev_args)

        _add_qemu_arg(qemu_commandline, '-device')
        if self._is_virt:
            _add_qemu_arg(qemu_commandline, 'virtio-net-pci,netdev=net0,bus=pcie.0,addr=0x1f')
        elif self._is_q35:
            # network root-port = PCIBusAllocator network slot (bus 1, slot 0)
            _add_qemu_arg(qemu_commandline, 'virtio-net-pci,netdev=net0,bus=pci.1,addr=0x0')
        else:
            # PC/i440FX: PCIBusAllocator reserves bus 0 slot 3 for network
            _add_qemu_arg(qemu_commandline, 'virtio-net-pci,netdev=net0,addr=0x3')

    def _prettify(self) -> str:
        """Convert the domain XML tree to a pretty-printed string."""
        return _prettify_xml(self._domain)


# --- Module-level helper functions (kept for backward compatibility) ---

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
    for i in range(1, total_buses + 1):
        port = ET.SubElement(devices, 'controller', type='pci', index=str(i), model='pcie-root-port')
        ET.SubElement(port, 'model', name='pcie-root-port')
        ET.SubElement(port, 'target', chassis=str(i), port=hex(0x10 + i - 1))

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

        if func_idx == 0:
            addr_attrs['multifunction'] = 'on'

        ET.SubElement(port, 'address', **addr_attrs)

    # SATA controller (required for q35 chipset)
    sata = ET.SubElement(devices, 'controller', type='sata', index='0')
    ET.SubElement(sata, 'address', type='pci', domain='0x0000', bus='0x00', slot='0x1f', function='0x2')


def _add_qemu_arg(qemu_commandline_element: ET.Element, value: str) -> None:
    """Add a QEMU commandline argument to the qemu:commandline section."""
    arg = ET.SubElement(qemu_commandline_element, f'{{{QEMU_NAMESPACE}}}arg')
    arg.set('value', value)


def _prettify_xml(elem: ET.Element) -> str:
    """Convert XML element to pretty-printed string."""
    rough_string = ET.tostring(elem, encoding='unicode')
    reparsed = minidom.parseString(rough_string)
    return reparsed.toprettyxml(indent='  ')


def _generate_virtiofs_xml_element(
    share: dict[str, Any],
    is_q35: bool,
    index: int,
    base_bus: int = 6,
    base_slot: int = 7,
    is_virt: bool = False,
) -> ET.Element:
    """Generate a single virtiofs filesystem XML element.

    Args:
        share: Share configuration dict
        is_q35: True if using q35 machine type
        index: Index of this share (0-based)
        base_bus: Base bus number for q35 (default 6)
        base_slot: Base slot number for pc (default 7)
        is_virt: True if using virt machine type

    Returns:
        ET.Element: The filesystem XML element
    """
    tag = share['tag']
    host_path = share['host_path']

    filesystem = ET.Element('filesystem', type='mount', accessmode='passthrough')
    ET.SubElement(filesystem, 'driver', type='virtiofs')
    ET.SubElement(filesystem, 'source', dir=host_path)
    ET.SubElement(filesystem, 'target', dir=tag)

    # Add idmap for uid/gid mapping (host user -> guest root)
    idmap = ET.SubElement(filesystem, 'idmap')
    host_uid = os.getuid()
    host_gid = os.getgid()
    ET.SubElement(idmap, 'uid', target='0', source=str(host_uid), count='1')
    ET.SubElement(idmap, 'gid', target='0', source=str(host_gid), count='1')

    # PCI addressing
    if is_virt:
        pass  # libvirt auto-assigns addresses on virt machine
    elif is_q35:
        bus = base_bus + index
        ET.SubElement(
            filesystem, 'address', type='pci', domain='0x0000',
            bus=f'0x{bus:02x}', slot='0x00', function='0x0',
        )
    else:
        slot = base_slot + index
        ET.SubElement(
            filesystem, 'address', type='pci', domain='0x0000',
            bus='0x00', slot=f'0x{slot:02x}', function='0x0',
        )

    log.debug(f"Generated virtio-fs XML for '{tag}' -> {host_path}")
    return filesystem
