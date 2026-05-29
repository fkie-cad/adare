"""OS definitions with ISO download URLs and SHA256 hashes."""

import logging
import os
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path

import yaml

from adare.config.configdirectory import OS_PROFILES_DIR

log = logging.getLogger(__name__)


class SetupLevel(IntEnum):
    """VM setup level controlling what gets installed during creation.

    BARE:  OS + user + basic config (UAC, sleep, autologin)
    BASE:  + guest tools (QGA, virtio, UTM, SPICE) + firewall rule
    FULL:  + Python environment (Miniforge x86_64 / native ARM64)
    AGENT: + pre-installed adarevm from wheels (deferred)
    """
    BARE = 0
    BASE = 1
    FULL = 2
    AGENT = 3


def default_host_cpus() -> int:
    """Return a reasonable CPU count for a VM based on the host's cores.

    Uses half the host's logical cores, clamped to [2, 8].
    """
    total = os.cpu_count() or 4
    return max(2, min(total // 2, 8))


@dataclass(frozen=True)
class OsDefinition:
    """Definition of an OS available for automated VM creation."""
    name: str
    display_name: str
    platform: str           # 'linux' or 'windows'
    distribution: str       # 'ubuntu', 'windows'
    version: str            # '24.04', '22.04', '11', '10'
    iso_url: str            # Direct download URL (empty for Windows - user must supply)
    iso_sha256: str         # Expected SHA256 hash (empty for Windows)
    iso_filename: str       # Cached filename
    default_disk_size: str  # e.g. '60G'
    default_ram_mb: int
    default_cpus: int
    distribution_label: str = ''
    requires_uefi: bool = False
    requires_tpm: bool = False
    kernel_path_in_iso: str = ''    # Path to vmlinuz inside ISO (Linux only)
    initrd_path_in_iso: str = ''    # Path to initrd inside ISO (Linux only)
    extra_packages: list[str] = field(default_factory=list)
    install_mode: str = 'auto'  # 'auto' (unattended) or 'manual' (interactive VNC)
    architecture: str = 'x86_64'  # 'x86_64' or 'aarch64'
    template: str = ''  # Custom template filename (empty = use default lookup)
    # Installer family — selects how the rendered template is laid out on the
    # seed medium. One of: 'subiquity' | 'preseed' | 'kickstart' | 'autoyast'
    # | 'archinstall-cloudinit' | 'manual'. The default keeps Ubuntu working.
    installer: str = 'subiquity'
    # Kernel command line passed via QEMU `-append`. Supports {console}
    # substitution (ttyS0/ttyAMA0). Distros like Anaconda or AutoYaST need
    # their own boot params (e.g. `inst.ks=...`, `autoyast=...`).
    kernel_cmdline: str = 'autoinstall console={console} ---'
    # Volume label of the seed ISO attached as the second drive. Cloud-init
    # NoCloud auto-detects 'cidata'; debian-installer and Anaconda detect
    # 'OEMDRV'; AutoYaST reads from a device path so the label is informational.
    seed_label: str = 'cidata'


# Ubuntu 26.04 LTS (Resolute Raccoon) - Server ISO with autoinstall support
UBUNTU_2604 = OsDefinition(
    name='ubuntu2604',
    display_name='Ubuntu 26.04 LTS (Resolute Raccoon)',
    platform='linux',
    distribution='ubuntu',
    distribution_label='Resolute Raccoon',
    version='26.04',
    iso_url='https://releases.ubuntu.com/26.04/ubuntu-26.04-live-server-amd64.iso',
    iso_sha256='dec49008a71f6098d0bcfc822021f4d042d5f2db279e4d75bdd981304f1ca5d9',
    iso_filename='ubuntu-26.04-live-server-amd64.iso',
    default_disk_size='60G',
    default_ram_mb=8192,
    default_cpus=0,
    kernel_path_in_iso='/casper/vmlinuz',
    initrd_path_in_iso='/casper/initrd',
)

# Ubuntu 26.04 LTS (Resolute Raccoon, ARM64) - User must supply ISO
UBUNTU_2604_ARM64 = OsDefinition(
    name='ubuntu2604arm64',
    display_name='Ubuntu 26.04 LTS (Resolute Raccoon, ARM64)',
    platform='linux',
    distribution='ubuntu',
    distribution_label='Resolute Raccoon',
    version='26.04',
    iso_url='',
    iso_sha256='',
    iso_filename='',
    default_disk_size='60G',
    default_ram_mb=8192,
    default_cpus=0,
    requires_uefi=True,
    kernel_path_in_iso='/casper/vmlinuz',
    initrd_path_in_iso='/casper/initrd',
    architecture='aarch64',
)

# Ubuntu 24.04 LTS (Noble Numbat) - Server ISO with autoinstall support
UBUNTU_2404 = OsDefinition(
    name='ubuntu2404',
    display_name='Ubuntu 24.04 LTS (Noble Numbat)',
    platform='linux',
    distribution='ubuntu',
    distribution_label='Noble Numbat',
    version='24.04',
    iso_url='https://releases.ubuntu.com/24.04.2/ubuntu-24.04.2-live-server-amd64.iso',
    iso_sha256='d6dab0c3a657988501b4bd76f1297c053df710e06e0c3aece60dead24f270b4d',
    iso_filename='ubuntu-24.04.2-live-server-amd64.iso',
    default_disk_size='60G',
    default_ram_mb=8192,
    default_cpus=0,
    kernel_path_in_iso='/casper/vmlinuz',
    initrd_path_in_iso='/casper/initrd',
)

# Ubuntu 24.04 LTS (Noble Numbat, ARM64) - User must supply ISO
UBUNTU_2404_ARM64 = OsDefinition(
    name='ubuntu2404arm64',
    display_name='Ubuntu 24.04 LTS (Noble Numbat, ARM64)',
    platform='linux',
    distribution='ubuntu',
    distribution_label='Noble Numbat',
    version='24.04',
    iso_url='',
    iso_sha256='',
    iso_filename='',
    default_disk_size='60G',
    default_ram_mb=8192,
    default_cpus=0,
    requires_uefi=True,
    kernel_path_in_iso='/casper/vmlinuz',
    initrd_path_in_iso='/casper/initrd',
    architecture='aarch64',
)

# Ubuntu 25.10 (Questing Quokka) - Server ISO with autoinstall support
UBUNTU_2510 = OsDefinition(
    name='ubuntu2510',
    display_name='Ubuntu 25.10 (Questing Quokka)',
    platform='linux',
    distribution='ubuntu',
    distribution_label='Questing Quokka',
    version='25.10',
    iso_url='https://releases.ubuntu.com/25.10/ubuntu-25.10-live-server-amd64.iso',
    iso_sha256='dc54870e5261c0abad19f74b8146659d10e625971792bd42d7ecde820b60a1d0',
    iso_filename='ubuntu-25.10-live-server-amd64.iso',
    default_disk_size='60G',
    default_ram_mb=8192,
    default_cpus=0,
    kernel_path_in_iso='/casper/vmlinuz',
    initrd_path_in_iso='/casper/initrd',
)

# Ubuntu 25.10 (Questing Quokka, ARM64) - User must supply ISO
UBUNTU_2510_ARM64 = OsDefinition(
    name='ubuntu2510arm64',
    display_name='Ubuntu 25.10 (Questing Quokka, ARM64)',
    platform='linux',
    distribution='ubuntu',
    distribution_label='Questing Quokka',
    version='25.10',
    iso_url='',
    iso_sha256='',
    iso_filename='',
    default_disk_size='60G',
    default_ram_mb=8192,
    default_cpus=0,
    requires_uefi=True,
    kernel_path_in_iso='/casper/vmlinuz',
    initrd_path_in_iso='/casper/initrd',
    architecture='aarch64',
)

# Ubuntu 22.04 LTS (Jammy Jellyfish) - Server ISO with autoinstall support
UBUNTU_2204 = OsDefinition(
    name='ubuntu2204',
    display_name='Ubuntu 22.04 LTS (Jammy Jellyfish)',
    platform='linux',
    distribution='ubuntu',
    distribution_label='Jammy Jellyfish',
    version='22.04',
    iso_url='https://releases.ubuntu.com/22.04.5/ubuntu-22.04.5-live-server-amd64.iso',
    iso_sha256='9bc6028870aef3f74f4e16b900008179e78b130e6b0b9a140635571d9c954b60',
    iso_filename='ubuntu-22.04.5-live-server-amd64.iso',
    default_disk_size='60G',
    default_ram_mb=8192,
    default_cpus=0,
    kernel_path_in_iso='/casper/vmlinuz',
    initrd_path_in_iso='/casper/initrd',
)

# Ubuntu 22.04 LTS (Jammy Jellyfish, ARM64) - User must supply ISO
UBUNTU_2204_ARM64 = OsDefinition(
    name='ubuntu2204arm64',
    display_name='Ubuntu 22.04 LTS (Jammy Jellyfish, ARM64)',
    platform='linux',
    distribution='ubuntu',
    distribution_label='Jammy Jellyfish',
    version='22.04',
    iso_url='',
    iso_sha256='',
    iso_filename='',
    default_disk_size='60G',
    default_ram_mb=8192,
    default_cpus=0,
    requires_uefi=True,
    kernel_path_in_iso='/casper/vmlinuz',
    initrd_path_in_iso='/casper/initrd',
    architecture='aarch64',
)

# ─────────────────────────────────────────────────────────────────────────────
# Debian family (preseed via debian-installer)
# ─────────────────────────────────────────────────────────────────────────────
# All Debian/Kali entries use the debian-installer netinst ISO. The seed ISO
# is labeled OEMDRV; d-i auto-loads /preseed.cfg from any OEMDRV-labeled drive
# without needing an explicit preseed/file= path. tasksel inside the preseed
# selects the desktop environment so the resulting VM has a GUI.

_PRESEED_CMDLINE = 'auto=true priority=critical console={console} --- quiet'

DEBIAN_12 = OsDefinition(
    name='debian12',
    display_name='Debian 12 (Bookworm) — GNOME',
    platform='linux',
    distribution='debian',
    distribution_label='Bookworm',
    version='12',
    iso_url='',
    iso_sha256='',
    iso_filename='',
    default_disk_size='60G',
    default_ram_mb=8192,
    default_cpus=0,
    kernel_path_in_iso='/install.amd/vmlinuz',
    initrd_path_in_iso='/install.amd/initrd.gz',
    installer='preseed',
    kernel_cmdline=_PRESEED_CMDLINE,
    seed_label='OEMDRV',
)

DEBIAN_13 = OsDefinition(
    name='debian13',
    display_name='Debian 13 (Trixie) — GNOME',
    platform='linux',
    distribution='debian',
    distribution_label='Trixie',
    version='13',
    iso_url='',
    iso_sha256='',
    iso_filename='',
    default_disk_size='60G',
    default_ram_mb=8192,
    default_cpus=0,
    kernel_path_in_iso='/install.amd/vmlinuz',
    initrd_path_in_iso='/install.amd/initrd.gz',
    installer='preseed',
    kernel_cmdline=_PRESEED_CMDLINE,
    seed_label='OEMDRV',
)

KALI_ROLLING = OsDefinition(
    name='kali',
    display_name='Kali Linux (Rolling) — Xfce',
    platform='linux',
    distribution='kali',
    distribution_label='Rolling',
    version='rolling',
    iso_url='',
    iso_sha256='',
    iso_filename='',
    default_disk_size='80G',
    default_ram_mb=8192,
    default_cpus=0,
    kernel_path_in_iso='/install.amd/vmlinuz',
    initrd_path_in_iso='/install.amd/initrd.gz',
    installer='preseed',
    kernel_cmdline=_PRESEED_CMDLINE,
    seed_label='OEMDRV',
)

# ─────────────────────────────────────────────────────────────────────────────
# Red Hat family (Anaconda / kickstart)
# ─────────────────────────────────────────────────────────────────────────────
# Fedora Workstation/Spins and Rocky/Alma DVDs all boot Anaconda from
# /images/pxeboot/. Anaconda picks up ks.cfg from an OEMDRV-labeled drive
# when given inst.ks=hd:LABEL=OEMDRV:/ks.cfg. inst.text keeps the install
# unattended; the *installed* system still has the chosen DE.

_KICKSTART_CMDLINE = (
    'inst.ks=hd:LABEL=OEMDRV:/ks.cfg inst.text console={console}'
)

FEDORA_41_WORKSTATION = OsDefinition(
    name='fedora41',
    display_name='Fedora 41 Workstation (GNOME)',
    platform='linux',
    distribution='fedora',
    distribution_label='Workstation',
    version='41',
    iso_url='',
    iso_sha256='',
    iso_filename='',
    default_disk_size='60G',
    default_ram_mb=8192,
    default_cpus=0,
    kernel_path_in_iso='/images/pxeboot/vmlinuz',
    initrd_path_in_iso='/images/pxeboot/initrd.img',
    installer='kickstart',
    kernel_cmdline=_KICKSTART_CMDLINE,
    seed_label='OEMDRV',
)

FEDORA_41_KDE = OsDefinition(
    name='fedora41kde',
    display_name='Fedora 41 KDE Plasma',
    platform='linux',
    distribution='fedora',
    distribution_label='KDE Plasma Spin',
    version='41',
    iso_url='',
    iso_sha256='',
    iso_filename='',
    default_disk_size='60G',
    default_ram_mb=8192,
    default_cpus=0,
    kernel_path_in_iso='/images/pxeboot/vmlinuz',
    initrd_path_in_iso='/images/pxeboot/initrd.img',
    installer='kickstart',
    kernel_cmdline=_KICKSTART_CMDLINE,
    seed_label='OEMDRV',
)

FEDORA_42_WORKSTATION = OsDefinition(
    name='fedora42',
    display_name='Fedora 42 Workstation (GNOME)',
    platform='linux',
    distribution='fedora',
    distribution_label='Workstation',
    version='42',
    iso_url='',
    iso_sha256='',
    iso_filename='',
    default_disk_size='60G',
    default_ram_mb=8192,
    default_cpus=0,
    kernel_path_in_iso='/images/pxeboot/vmlinuz',
    initrd_path_in_iso='/images/pxeboot/initrd.img',
    installer='kickstart',
    kernel_cmdline=_KICKSTART_CMDLINE,
    seed_label='OEMDRV',
)

FEDORA_42_KDE = OsDefinition(
    name='fedora42kde',
    display_name='Fedora 42 KDE Plasma',
    platform='linux',
    distribution='fedora',
    distribution_label='KDE Plasma Spin',
    version='42',
    iso_url='',
    iso_sha256='',
    iso_filename='',
    default_disk_size='60G',
    default_ram_mb=8192,
    default_cpus=0,
    kernel_path_in_iso='/images/pxeboot/vmlinuz',
    initrd_path_in_iso='/images/pxeboot/initrd.img',
    installer='kickstart',
    kernel_cmdline=_KICKSTART_CMDLINE,
    seed_label='OEMDRV',
)

FEDORA_43_WORKSTATION = OsDefinition(
    name='fedora43',
    display_name='Fedora 43 Workstation (GNOME)',
    platform='linux',
    distribution='fedora',
    distribution_label='Workstation',
    version='43',
    iso_url='',
    iso_sha256='',
    iso_filename='',
    default_disk_size='60G',
    default_ram_mb=8192,
    default_cpus=0,
    kernel_path_in_iso='/images/pxeboot/vmlinuz',
    initrd_path_in_iso='/images/pxeboot/initrd.img',
    installer='kickstart',
    kernel_cmdline=_KICKSTART_CMDLINE,
    seed_label='OEMDRV',
)

FEDORA_43_KDE = OsDefinition(
    name='fedora43kde',
    display_name='Fedora 43 KDE Plasma',
    platform='linux',
    distribution='fedora',
    distribution_label='KDE Plasma Spin',
    version='43',
    iso_url='',
    iso_sha256='',
    iso_filename='',
    default_disk_size='60G',
    default_ram_mb=8192,
    default_cpus=0,
    kernel_path_in_iso='/images/pxeboot/vmlinuz',
    initrd_path_in_iso='/images/pxeboot/initrd.img',
    installer='kickstart',
    kernel_cmdline=_KICKSTART_CMDLINE,
    seed_label='OEMDRV',
)

# Fedora 44 (released 2026-04-28) — current stable. GNOME 50 / KDE Plasma 6.6.
FEDORA_44_WORKSTATION = OsDefinition(
    name='fedora44',
    display_name='Fedora 44 Workstation (GNOME 50)',
    platform='linux',
    distribution='fedora',
    distribution_label='Workstation',
    version='44',
    iso_url='',
    iso_sha256='',
    iso_filename='',
    default_disk_size='60G',
    default_ram_mb=8192,
    default_cpus=0,
    kernel_path_in_iso='/images/pxeboot/vmlinuz',
    initrd_path_in_iso='/images/pxeboot/initrd.img',
    installer='kickstart',
    kernel_cmdline=_KICKSTART_CMDLINE,
    seed_label='OEMDRV',
)

FEDORA_44_KDE = OsDefinition(
    name='fedora44kde',
    display_name='Fedora 44 KDE Plasma 6.6',
    platform='linux',
    distribution='fedora',
    distribution_label='KDE Plasma Spin',
    version='44',
    iso_url='',
    iso_sha256='',
    iso_filename='',
    default_disk_size='60G',
    default_ram_mb=8192,
    default_cpus=0,
    kernel_path_in_iso='/images/pxeboot/vmlinuz',
    initrd_path_in_iso='/images/pxeboot/initrd.img',
    installer='kickstart',
    kernel_cmdline=_KICKSTART_CMDLINE,
    seed_label='OEMDRV',
)

ROCKY_9 = OsDefinition(
    name='rocky9',
    display_name='Rocky Linux 9 (Workstation, GNOME)',
    platform='linux',
    distribution='rocky',
    distribution_label='Blue Onyx',
    version='9',
    iso_url='',
    iso_sha256='',
    iso_filename='',
    default_disk_size='60G',
    default_ram_mb=8192,
    default_cpus=0,
    kernel_path_in_iso='/images/pxeboot/vmlinuz',
    initrd_path_in_iso='/images/pxeboot/initrd.img',
    installer='kickstart',
    kernel_cmdline=_KICKSTART_CMDLINE,
    seed_label='OEMDRV',
    template='kickstart_rhel_workstation.yaml',
)

ALMA_9 = OsDefinition(
    name='alma9',
    display_name='AlmaLinux 9 (Workstation, GNOME)',
    platform='linux',
    distribution='alma',
    distribution_label='Teal Serval',
    version='9',
    iso_url='',
    iso_sha256='',
    iso_filename='',
    default_disk_size='60G',
    default_ram_mb=8192,
    default_cpus=0,
    kernel_path_in_iso='/images/pxeboot/vmlinuz',
    initrd_path_in_iso='/images/pxeboot/initrd.img',
    installer='kickstart',
    kernel_cmdline=_KICKSTART_CMDLINE,
    seed_label='OEMDRV',
    template='kickstart_rhel_workstation.yaml',
)

# ─────────────────────────────────────────────────────────────────────────────
# SUSE family (AutoYaST)
# ─────────────────────────────────────────────────────────────────────────────
# AutoYaST autoloads autoinst.xml from an OEMDRV-labeled drive when invoked
# with `autoyast=default`. textmode=1 suppresses the graphical installer; the
# resulting system still boots into the configured KDE/GNOME desktop.

_AUTOYAST_CMDLINE = 'autoyast=default console={console} textmode=1'

OPENSUSE_LEAP_156 = OsDefinition(
    name='opensuseleap156',
    display_name='openSUSE Leap 15.6 — KDE Plasma',
    platform='linux',
    distribution='opensuse',
    distribution_label='Leap',
    version='15.6',
    iso_url='',
    iso_sha256='',
    iso_filename='',
    default_disk_size='60G',
    default_ram_mb=8192,
    default_cpus=0,
    kernel_path_in_iso='/boot/x86_64/loader/linux',
    initrd_path_in_iso='/boot/x86_64/loader/initrd',
    installer='autoyast',
    kernel_cmdline=_AUTOYAST_CMDLINE,
    seed_label='OEMDRV',
)

OPENSUSE_TUMBLEWEED = OsDefinition(
    name='opensusetumbleweed',
    display_name='openSUSE Tumbleweed — KDE Plasma',
    platform='linux',
    distribution='opensuse',
    distribution_label='Tumbleweed',
    version='rolling',
    iso_url='',
    iso_sha256='',
    iso_filename='',
    default_disk_size='60G',
    default_ram_mb=8192,
    default_cpus=0,
    kernel_path_in_iso='/boot/x86_64/loader/linux',
    initrd_path_in_iso='/boot/x86_64/loader/initrd',
    installer='autoyast',
    kernel_cmdline=_AUTOYAST_CMDLINE,
    seed_label='OEMDRV',
    template='autoyast_opensuse_leap.yaml',  # same template works for both
)

# ─────────────────────────────────────────────────────────────────────────────
# Manual-mode GUI distros (Phase 6 — Calamares / distinst / nixos installers
# with no documented unattended path)
# ─────────────────────────────────────────────────────────────────────────────
# These boot the live ISO normally; the user clicks through the graphical
# installer. linux_creator skips kernel/seed plumbing for install_mode='manual'
# and writes INSTALL_INSTRUCTIONS.md alongside the qcow2.

LINUX_MINT = OsDefinition(
    name='mint',
    display_name='Linux Mint (Cinnamon) — manual install',
    platform='linux',
    distribution='mint',
    distribution_label='Cinnamon',
    version='22',
    iso_url='',
    iso_sha256='',
    iso_filename='',
    default_disk_size='60G',
    default_ram_mb=8192,
    default_cpus=0,
    install_mode='manual',
    installer='manual',
)

POP_OS = OsDefinition(
    name='popos',
    display_name='Pop!_OS (COSMIC) — manual install',
    platform='linux',
    distribution='popos',
    distribution_label='COSMIC',
    version='24.04',
    iso_url='',
    iso_sha256='',
    iso_filename='',
    default_disk_size='60G',
    default_ram_mb=8192,
    default_cpus=0,
    install_mode='manual',
    installer='manual',
)

NIXOS = OsDefinition(
    name='nixos',
    display_name='NixOS (GNOME live) — manual install',
    platform='linux',
    distribution='nixos',
    distribution_label='GNOME',
    version='25.05',
    iso_url='',
    iso_sha256='',
    iso_filename='',
    default_disk_size='60G',
    default_ram_mb=8192,
    default_cpus=0,
    install_mode='manual',
    installer='manual',
)

ELEMENTARY_OS = OsDefinition(
    name='elementary',
    display_name='elementary OS (Pantheon) — manual install',
    platform='linux',
    distribution='elementary',
    distribution_label='Pantheon',
    version='8',
    iso_url='',
    iso_sha256='',
    iso_filename='',
    default_disk_size='60G',
    default_ram_mb=8192,
    default_cpus=0,
    install_mode='manual',
    installer='manual',
)

# Windows 11 - User must supply ISO
WINDOWS_11 = OsDefinition(
    name='windows11',
    display_name='Windows 11',
    platform='windows',
    distribution='windows',
    distribution_label='Home',
    version='11',
    iso_url='',
    iso_sha256='',
    iso_filename='',
    default_disk_size='80G',
    default_ram_mb=16384,
    default_cpus=0,
    requires_uefi=True,
    requires_tpm=True,
)

# Windows 10 - User must supply ISO
WINDOWS_10 = OsDefinition(
    name='windows10',
    display_name='Windows 10',
    platform='windows',
    distribution='windows',
    distribution_label='Home',
    version='10',
    iso_url='',
    iso_sha256='',
    iso_filename='',
    default_disk_size='80G',
    default_ram_mb=16384,
    default_cpus=0,
    requires_uefi=True,
)

# Virtio-win drivers ISO for Windows guests
VIRTIO_WIN_ISO_URL = 'https://fedorapeople.org/groups/virt/virtio-win/direct-downloads/stable-virtio/virtio-win.iso'
VIRTIO_WIN_ISO_FILENAME = 'virtio-win.iso'

# UTM guest tools ISO for ARM64 Windows guests
# Contains ARM64 virtio drivers, SPICE vdagent, and QEMU guest agent
# See: https://github.com/utmapp/spice-nsis
UTM_GUEST_TOOLS_ISO_URL = 'https://getutm.app/downloads/utm-guest-tools-latest.iso'
UTM_GUEST_TOOLS_ISO_FILENAME = 'utm-guest-tools.iso'

# Built-in OS definitions
_BUILTIN_CATALOG: dict[str, OsDefinition] = {
    'ubuntu2604': UBUNTU_2604,
    'ubuntu2604arm64': UBUNTU_2604_ARM64,
    'ubuntu2510': UBUNTU_2510,
    'ubuntu2510arm64': UBUNTU_2510_ARM64,
    'ubuntu2404': UBUNTU_2404,
    'ubuntu2404arm64': UBUNTU_2404_ARM64,
    'ubuntu2204': UBUNTU_2204,
    'ubuntu2204arm64': UBUNTU_2204_ARM64,
    'debian12': DEBIAN_12,
    'debian13': DEBIAN_13,
    'kali': KALI_ROLLING,
    'fedora41': FEDORA_41_WORKSTATION,
    'fedora41kde': FEDORA_41_KDE,
    'fedora42': FEDORA_42_WORKSTATION,
    'fedora42kde': FEDORA_42_KDE,
    'fedora43': FEDORA_43_WORKSTATION,
    'fedora43kde': FEDORA_43_KDE,
    'fedora44': FEDORA_44_WORKSTATION,
    'fedora44kde': FEDORA_44_KDE,
    'rocky9': ROCKY_9,
    'alma9': ALMA_9,
    'opensuseleap156': OPENSUSE_LEAP_156,
    'opensusetumbleweed': OPENSUSE_TUMBLEWEED,
    'mint': LINUX_MINT,
    'popos': POP_OS,
    'nixos': NIXOS,
    'elementary': ELEMENTARY_OS,
    'windows11': WINDOWS_11,
    'windows10': WINDOWS_10,
}

_REQUIRED_YAML_FIELDS = {'name', 'platform', 'distribution', 'version'}


def _load_yaml_profiles() -> dict[str, OsDefinition]:
    """Load OS profiles from YAML files in the os-profiles directory."""
    profiles: dict[str, OsDefinition] = {}

    search_dirs = [OS_PROFILES_DIR]
    # Dev mode fallback: check source appdata/os-profiles/
    source_profiles = Path(__file__).parent.parent.parent.parent.parent / 'appdata' / 'os-profiles'
    if source_profiles.is_dir() and source_profiles != OS_PROFILES_DIR:
        search_dirs.append(source_profiles)

    for profiles_dir in search_dirs:
        if not profiles_dir.is_dir():
            continue
        for yml_file in sorted(profiles_dir.glob('*.yml')):
            try:
                data = yaml.safe_load(yml_file.read_text())
                if not isinstance(data, dict):
                    log.warning('Skipping %s: not a valid YAML mapping', yml_file)
                    continue

                missing = _REQUIRED_YAML_FIELDS - data.keys()
                if missing:
                    log.warning('Skipping %s: missing required fields: %s', yml_file, missing)
                    continue

                install_mode = data.get('install_mode', 'auto')
                if install_mode not in ('auto', 'manual'):
                    log.warning('Skipping %s: install_mode must be "auto" or "manual", got "%s"', yml_file, install_mode)
                    continue

                architecture = data.get('architecture', 'x86_64')
                if architecture not in ('x86_64', 'aarch64'):
                    log.warning('Skipping %s: architecture must be "x86_64" or "aarch64", got "%s"', yml_file, architecture)
                    continue

                name = data['name']
                if name in profiles:
                    continue  # first directory wins (user dir checked first)

                profiles[name] = OsDefinition(
                    name=name,
                    display_name=data.get('display_name', name),
                    platform=data['platform'],
                    distribution=data['distribution'],
                    distribution_label=data.get('distribution_label', ''),
                    version=str(data['version']),
                    iso_url=data.get('iso_url', ''),
                    iso_sha256=data.get('iso_sha256', ''),
                    iso_filename=data.get('iso_filename', ''),
                    default_disk_size=data.get('default_disk_size', '60G'),
                    default_ram_mb=int(data.get('default_ram_mb', 4096)),
                    default_cpus=int(data.get('default_cpus', 2)),
                    requires_uefi=bool(data.get('requires_uefi', False)),
                    requires_tpm=bool(data.get('requires_tpm', False)),
                    kernel_path_in_iso=data.get('kernel_path_in_iso', ''),
                    initrd_path_in_iso=data.get('initrd_path_in_iso', ''),
                    extra_packages=data.get('extra_packages', []),
                    install_mode=install_mode,
                    architecture=architecture,
                    template=data.get('template', ''),
                    installer=data.get('installer', 'subiquity'),
                    kernel_cmdline=data.get(
                        'kernel_cmdline', 'autoinstall console={console} ---'
                    ),
                    seed_label=data.get('seed_label', 'cidata'),
                )
            except (OSError, yaml.YAMLError, TypeError, ValueError) as e:
                log.warning('Skipping %s: %s', yml_file, e)

    return profiles


def _build_catalog() -> dict[str, OsDefinition]:
    """Build the full OS catalog by merging built-in definitions with YAML profiles.

    YAML profiles override built-in definitions on name collision.
    """
    catalog = dict(_BUILTIN_CATALOG)
    catalog.update(_load_yaml_profiles())
    return catalog


OS_CATALOG: dict[str, OsDefinition] = _build_catalog()


def reload_catalog() -> None:
    """Reload the OS catalog from built-in definitions and YAML profiles."""
    global OS_CATALOG
    OS_CATALOG = _build_catalog()


def get_os_definition(os_name: str) -> OsDefinition:
    """Look up an OS definition by name.

    Args:
        os_name: OS identifier (e.g. 'ubuntu2404', 'windows11')

    Returns:
        OsDefinition for the requested OS

    Raises:
        KeyError: If os_name is not in the catalog
    """
    if os_name not in OS_CATALOG:
        available = ', '.join(sorted(OS_CATALOG.keys()))
        raise KeyError(
            f"Unknown OS '{os_name}'. Available: {available}\n"
            f"Run 'adare manage os-profile list' to see all profiles."
        )
    return OS_CATALOG[os_name]
