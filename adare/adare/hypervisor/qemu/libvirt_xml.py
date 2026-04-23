"""
libvirt XML domain generation for QEMU VMs.

Generates libvirt XML domain definitions from QEMU VM configurations,
enabling VMs to be managed via virsh and virt-manager while preserving
ADARE's forensic-focused architecture (QMP, Guest Agent, overlays).

The heavy lifting is done by DomainXMLBuilder in libvirt_xml_builder.py.
This module provides the backward-compatible public API.
"""
import logging
import os
import xml.etree.ElementTree as ET
from typing import Any

from .libvirt_xml_builder import DomainXMLBuilder

log = logging.getLogger(__name__)


def generate_domain_xml(
    vm_config,  # QEMUVMConfig instance
    display_enabled: bool = False,
    vnc_port: int | None = None,
    virtiofs_shares: list[dict[str, Any]] | None = None
) -> str:
    """
    Generate libvirt XML domain definition from QEMU VM config.

    Backward-compatible wrapper around DomainXMLBuilder.

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
    builder = DomainXMLBuilder(vm_config, display_enabled, vnc_port, virtiofs_shares)
    return builder.build()


def generate_virtiofs_xml_element(
    share: dict[str, Any],
    is_q35: bool,
    index: int,
    base_bus: int = 6,
    base_slot: int = 7,
    is_virt: bool = False
) -> ET.Element:
    """
    Generate a single virtiofs filesystem XML element.

    This function is used by snapshot restore logic to add virtiofs devices
    to existing domain XML. Kept here for backward compatibility.

    Args:
        share: Share configuration dict
        is_q35: True if using q35 machine type
        index: Index of this share (0-based)
        base_bus: Base bus number for q35 (default 6)
        base_slot: Base slot number for pc (default 7)
        is_virt: True if using virt machine type (libvirt auto-assigns addresses)

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
    # For virt machine, libvirt auto-assigns addresses
    if is_virt:
        pass  # libvirt auto-assigns addresses on virt machine
    elif is_q35:
        # Each device gets its own bus (6, 7, 8, 9, 10...)
        bus = base_bus + index
        ET.SubElement(filesystem, 'address', type='pci', domain='0x0000',
                        bus=f'0x{bus:02x}', slot='0x00', function='0x0')
    else:
        # For pc machine, use slots on bus 0 (7, 8, 9, 10, 11...)
        slot = base_slot + index
        ET.SubElement(filesystem, 'address', type='pci', domain='0x0000',
                        bus='0x00', slot=f'0x{slot:02x}', function='0x0')

    log.debug(f"Generated virtio-fs XML for '{tag}' -> {host_path}")
    return filesystem
