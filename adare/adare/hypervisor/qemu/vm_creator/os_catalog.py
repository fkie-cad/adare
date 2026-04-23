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

# Ubuntu 25.10 - Desktop ARM64 ISO with autoinstall support
UBUNTU_2510 = OsDefinition(
    name='ubuntu2510',
    display_name='Ubuntu 25.10',
    platform='linux',
    distribution='ubuntu',
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
    'ubuntu2510': UBUNTU_2510,
    'ubuntu2404': UBUNTU_2404,
    'ubuntu2204': UBUNTU_2204,
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
