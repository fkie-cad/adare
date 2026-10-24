"""The YAML profiles in appdata/os-profiles define their OSes; built-ins cover only the rest."""

from pathlib import Path

import pytest
import yaml

from adare.hypervisor.qemu.vm_creator import os_catalog

pytestmark = pytest.mark.unit

PROFILES_DIR = Path(os_catalog.__file__).resolve().parents[4] / 'appdata' / 'os-profiles'


def _profiles() -> dict[str, dict]:
    profiles = {}
    for path in PROFILES_DIR.glob('*.yml'):
        data = yaml.safe_load(path.read_text())
        profiles[data['name']] = data
    return profiles


def test_profiles_are_found():
    assert 'ubuntu2404' in _profiles()


def test_no_built_in_shadowed_by_a_profile():
    """A profile replaces the built-in of the same name whole: the copy would only drift."""
    assert sorted(set(os_catalog._BUILTIN_CATALOG) & set(_profiles())) == []


def _desktop_lts(name: str, profile: dict) -> bool:
    if profile['distribution'] not in ('ubuntu', 'kubuntu') or name.endswith('arm64'):
        return False
    year, month = profile['version'].split('.')
    return month == '04' and int(year) % 2 == 0


@pytest.mark.parametrize('name', sorted(name for name, p in _profiles().items() if _desktop_lts(name, p)))
def test_ubuntu_lts_installs_the_desktop_edition(name):
    """x86_64 Ubuntu/Kubuntu LTS images are genuine desktop installs, not server + desktop packages."""
    profile = _profiles()[name]

    assert profile['install_mode'] == 'playbook'
    assert '-desktop-' in profile['iso_filename']
    assert profile['install_steps']
