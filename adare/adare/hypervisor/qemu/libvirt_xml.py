"""
libvirt XML domain generation for QEMU VMs.

Generates libvirt XML domain definitions from QEMU VM configurations,
enabling VMs to be managed via virsh and virt-manager while preserving
ADARE's forensic-focused architecture (QMP, Guest Agent, overlays).

The heavy lifting is done by DomainXMLBuilder in libvirt_xml_builder.py.
This module provides the backward-compatible public API.
"""

import logging
import xml.etree.ElementTree as ET
from typing import Any

from .libvirt_xml_builder import DomainXMLBuilder, _generate_virtiofs_xml_element

log = logging.getLogger(__name__)


def generate_domain_xml(
    vm_config,  # QEMUVMConfig instance
    display_enabled: bool = False,
    vnc_port: int | None = None,
    virtiofs_shares: list[dict[str, Any]] | None = None,
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
    share: dict[str, Any], is_q35: bool, index: int, base_bus: int = 6, base_slot: int = 7, is_virt: bool = False
) -> ET.Element:
    """
    Generate a single virtiofs filesystem XML element.

    This function is used by snapshot restore logic to add virtiofs devices
    to existing domain XML. Kept here for backward compatibility; the element
    is built by the same code as for new domains.

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
    return _generate_virtiofs_xml_element(share, is_q35, index, base_bus, base_slot, is_virt)
