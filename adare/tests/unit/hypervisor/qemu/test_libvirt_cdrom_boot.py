"""Tests for CDROM device + per-device boot-order in the libvirt XML builder.

Covers Phase 1 of the GUI-automated install feature: booting a live installer
ISO as a libvirt QEMUVM. Uses BIOS boot (explicit ``machine``) to keep the
builder hermetic — the UEFI branch touches the filesystem (OVMF/NVRAM).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from adare.hypervisor.qemu.libvirt_xml import generate_domain_xml
from adare.hypervisor.qemu.models import QEMUVMConfig


def _config(**overrides) -> QEMUVMConfig:
    base = dict(
        vm_name='testvm',
        uuid='11111111-1111-1111-1111-111111111111',
        guest_os='kubuntu2404',
        disk_path='/tmp/testvm.qcow2',
        machine='pc',
        boot_mode='bios',
    )
    base.update(overrides)
    return QEMUVMConfig(**base)


def _disks(xml: str) -> list[ET.Element]:
    root = ET.fromstring(xml)
    return root.findall('./devices/disk')


# ---------------------------------------------------------------------------
# No ISO — behaviour must be unchanged
# ---------------------------------------------------------------------------

def test_no_iso_has_no_cdrom_and_global_boot_hd():
    xml = generate_domain_xml(_config())
    root = ET.fromstring(xml)

    disks = _disks(xml)
    assert [d.get('device') for d in disks] == ['disk']  # only the hard disk

    # Global <os><boot dev='hd'/> preserved when not booting from CDROM.
    boot = root.findall('./os/boot')
    assert len(boot) == 1
    assert boot[0].get('dev') == 'hd'
    # No per-device boot order.
    assert root.find('./devices/disk/boot') is None


# ---------------------------------------------------------------------------
# ISO attached + booting from CDROM
# ---------------------------------------------------------------------------

def test_boot_from_cdrom_adds_cdrom_with_boot_order():
    xml = generate_domain_xml(
        _config(machine='q35', iso_path='/isos/kubuntu.iso', boot_from_cdrom=True)
    )
    root = ET.fromstring(xml)
    disks = _disks(xml)

    devices = {d.get('device') for d in disks}
    assert devices == {'disk', 'cdrom'}

    cdrom = next(d for d in disks if d.get('device') == 'cdrom')
    hd = next(d for d in disks if d.get('device') == 'disk')

    # CDROM: readonly, sourced from the ISO, on the SATA bus (q35), boot order 1.
    assert cdrom.find('source').get('file') == '/isos/kubuntu.iso'
    assert cdrom.find('target').get('bus') == 'sata'
    assert cdrom.find('readonly') is not None
    assert cdrom.find('driver').get('type') == 'raw'
    assert cdrom.find('boot').get('order') == '1'

    # Hard disk: boot order 2.
    assert hd.find('boot').get('order') == '2'

    # Global <os><boot> must be absent (mutually exclusive with per-device order).
    assert root.findall('./os/boot') == []


def test_boot_from_cdrom_uses_ide_on_i440fx():
    xml = generate_domain_xml(
        _config(machine='pc', iso_path='/isos/kubuntu.iso', boot_from_cdrom=True)
    )
    cdrom = next(d for d in _disks(xml) if d.get('device') == 'cdrom')
    assert cdrom.find('target').get('bus') == 'ide'


def test_on_reboot_destroy_when_booting_installer():
    xml = generate_domain_xml(
        _config(iso_path='/isos/kubuntu.iso', boot_from_cdrom=True)
    )
    root = ET.fromstring(xml)
    assert root.find('./on_reboot').text == 'destroy'


# ---------------------------------------------------------------------------
# ISO attached but booting from disk (post-install verification boot)
# ---------------------------------------------------------------------------

def test_iso_attached_but_boot_from_disk():
    xml = generate_domain_xml(
        _config(iso_path='/isos/kubuntu.iso', boot_from_cdrom=False)
    )
    root = ET.fromstring(xml)
    disks = _disks(xml)

    # CDROM still attached (medium present) ...
    assert {d.get('device') for d in disks} == {'disk', 'cdrom'}
    # ... but no per-device boot order, and global boot dev='hd' drives the boot.
    assert root.find('./devices/disk/boot') is None
    cdrom = next(d for d in disks if d.get('device') == 'cdrom')
    assert cdrom.find('boot') is None
    assert root.find('./os/boot').get('dev') == 'hd'
    assert root.find('./on_reboot').text == 'restart'


# ---------------------------------------------------------------------------
# Config round-trips the new fields
# ---------------------------------------------------------------------------

def test_config_serializes_new_fields():
    cfg = _config(iso_path='/isos/kubuntu.iso', boot_from_cdrom=True)
    d = cfg.to_dict()
    assert d['iso_path'] == '/isos/kubuntu.iso'
    assert d['boot_from_cdrom'] is True

    restored = QEMUVMConfig.from_dict(d)
    assert restored.iso_path == '/isos/kubuntu.iso'
    assert restored.boot_from_cdrom is True


def test_config_from_dict_backward_compatible():
    # A config persisted before these fields existed must still load.
    legacy = _config().to_dict()
    del legacy['iso_path']
    del legacy['boot_from_cdrom']
    restored = QEMUVMConfig.from_dict(legacy)
    assert restored.iso_path == ''
    assert restored.boot_from_cdrom is False
