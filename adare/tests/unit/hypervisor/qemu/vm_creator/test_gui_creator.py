"""Tests for the gui-auto install mode: profile whitelist + creator wiring."""

from __future__ import annotations

from pathlib import Path

import pytest

from adare.hypervisor.qemu.vm_creator import os_catalog
from adare.hypervisor.qemu.vm_creator.gui_creator import (
    GUIVMCreationError,
    GUIVMCreator,
    _template_stems,
)
from adare.hypervisor.qemu.vm_creator.os_catalog import OsDefinition

pytestmark = pytest.mark.unit


def _write_profile(dir_: Path, name: str, install_mode: str) -> Path:
    p = dir_ / f'{name}.yml'
    p.write_text(
        f'name: {name}\n'
        'display_name: "Test"\n'
        'platform: linux\n'
        'distribution: ubuntu\n'
        'version: "24.04"\n'
        f'install_mode: {install_mode}\n'
        'installer: gui\n'
    )
    return p


def test_gui_auto_profile_is_accepted(tmp_path, monkeypatch):
    _write_profile(tmp_path, 'kubuntutest', 'gui-auto')
    monkeypatch.setattr(os_catalog, 'OS_PROFILES_DIR', tmp_path)
    profiles = os_catalog._load_yaml_profiles()
    assert 'kubuntutest' in profiles
    assert profiles['kubuntutest'].install_mode == 'gui-auto'


def test_bogus_install_mode_is_skipped(tmp_path, monkeypatch):
    _write_profile(tmp_path, 'bogus', 'sorcery')
    monkeypatch.setattr(os_catalog, 'OS_PROFILES_DIR', tmp_path)
    profiles = os_catalog._load_yaml_profiles()
    assert 'bogus' not in profiles


@pytest.fixture
def kubuntu_def() -> OsDefinition:
    os_catalog.reload_catalog()
    return os_catalog.get_os_definition('kubuntu2404')


def test_template_stems_derives_kubuntu(kubuntu_def):
    assert _template_stems(kubuntu_def, None) == ['kubuntu', 'ubuntu']
    # An explicit override wins.
    assert _template_stems(kubuntu_def, 'custom')[0] == 'custom'


def test_bundled_kubuntu_template_loads(kubuntu_def):
    creator = GUIVMCreator(os_def=kubuntu_def, iso_path=Path('/tmp/x.iso'), vm_name='k')
    spec = creator._load_goal_spec()
    assert spec['goal']
    assert spec['acceptance']['visual']
    # No cached playbook yet → creator would record; write path is under user dir.
    path, cached = creator._resolve_playbook()
    assert cached is False
    assert path.name == 'gui_kubuntu.play.yaml'


def test_missing_iso_raises(kubuntu_def):
    creator = GUIVMCreator(os_def=kubuntu_def, iso_path=None, vm_name='k')
    with pytest.raises(GUIVMCreationError):
        creator._ensure_iso()
