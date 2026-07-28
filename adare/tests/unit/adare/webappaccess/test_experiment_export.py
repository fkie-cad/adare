"""Tests for the publish preflight, gate 1 (T11).

`_preflight_environment` is the AUTHORITATIVE publish check — it is the only place
the full recipe contract is enforced before a Gitea branch/PR exists, because the
server cannot resolve an OS profile to a platform. It previously had zero test
coverage (this directory had no `__init__.py`), including on the baked branch.
"""

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

from adare.exceptions import DataStructuringError
from adare.webappaccess.experiment_export import (
    EnvironmentSubmissionError,
    _preflight_environment,
)

WIN_ISO_URL = 'https://files.example.org/isos/Win11_25H2_English_Arm64_v2.iso'
UBUNTU_ISO_URL = 'https://releases.ubuntu.com/24.04/ubuntu-24.04-live-server-amd64.iso'
SHA = 'a' * 64

_WINDOWS_OS = {
    'os': 'Windows 11 (ARM64)', 'platform': 'windows', 'distribution': 'Home',
    'version': '11', 'language': 'English', 'architecture': 'aarch64',
}
_LINUX_OS = {
    'os': 'Ubuntu 24.04', 'platform': 'linux', 'distribution': 'ubuntu',
    'version': '24.04', 'language': 'English', 'architecture': 'x86_64',
}


# --- Helpers ---

def _write(tmp_path: Path, env: dict, name: str = 'env.yml') -> Path:
    path = tmp_path / name
    path.write_text(yaml.dump(env))
    return path


def _recipe_env(os_block: dict | None = None, **recipe) -> dict:
    return {
        'vm_type': 'recipe', 'hypervisor': 'qemu',
        'recipe': {'profile': 'windows11arm64', 'iso': WIN_ISO_URL,
                   'iso_sha256': SHA, **recipe},
        'os': _WINDOWS_OS if os_block is None else os_block,
    }


def _baked_env(**overrides) -> dict:
    env = {
        'vm': 'https://files.example.org/disks/ubuntu.qcow2',
        'vm_type': 'url', 'vm_sha256': SHA, 'hypervisor': 'qemu', 'os': _LINUX_OS,
    }
    env.update(overrides)
    return env


# --- Recipe, URL form ---

def test_url_form_with_lowercase_sha_passes(tmp_path):
    _preflight_environment(_write(tmp_path, _recipe_env()))


def test_local_iso_path_is_rejected(tmp_path):
    """A publisher's filesystem path is meaningless to a consumer."""
    env = _recipe_env(iso='/Users/miq/Documents/ISO/Win11.iso')
    with pytest.raises(EnvironmentSubmissionError, match='http'):
        _preflight_environment(_write(tmp_path, env))


def test_local_iso_path_error_suggests_recipe_byo_for_windows(tmp_path):
    env = _recipe_env(iso='/Users/miq/Documents/ISO/Win11.iso')
    with pytest.raises(EnvironmentSubmissionError, match='recipe-byo'):
        _preflight_environment(_write(tmp_path, env))


@pytest.mark.parametrize('bad_sha,reason', [
    ('', 'missing'),
    ('a' * 63, 'too short'),
    ('a' * 65, 'too long'),
    ('z' * 64, 'non-hex'),
    ('A' * 64, 'uppercase: verify_iso_hash compares case-sensitively'),
])
def test_bad_iso_sha256_is_rejected(tmp_path, bad_sha, reason):
    env = _recipe_env(iso_sha256=bad_sha)
    with pytest.raises(EnvironmentSubmissionError, match='iso_sha256'):
        _preflight_environment(_write(tmp_path, env))


# --- Recipe, BYO form ---

def test_byo_with_a_windows_profile_passes(tmp_path):
    env = _recipe_env(iso=None, iso_name='Win11_25H2_English_Arm64_v2.iso')
    del env['recipe']['iso']
    _preflight_environment(_write(tmp_path, env))


def test_byo_with_iso_notes_passes(tmp_path):
    env = _recipe_env(iso_name='Win11_25H2_English_Arm64_v2.iso',
                      iso_notes='Download from microsoft.com')
    del env['recipe']['iso']
    _preflight_environment(_write(tmp_path, env))


def test_byo_with_a_linux_profile_is_rejected_naming_the_real_url(tmp_path):
    """The error tells the publisher the exact URL to host, not just "no"."""
    env = {
        'vm_type': 'recipe', 'hypervisor': 'qemu',
        'recipe': {'profile': 'ubuntu2404', 'iso_sha256': SHA,
                   'iso_name': 'ubuntu-24.04-live-server-amd64.iso'},
        'os': _LINUX_OS,
    }
    with pytest.raises(EnvironmentSubmissionError) as excinfo:
        _preflight_environment(_write(tmp_path, env))
    message = str(excinfo.value)
    assert 'Windows profiles only' in message
    assert 'releases.ubuntu.com' in message


def test_byo_with_a_urlless_linux_profile_uses_the_fallback_wording(tmp_path):
    """ubuntu2404arm64 has an empty catalog iso_url — the user supplies the ISO."""
    env = {
        'vm_type': 'recipe', 'hypervisor': 'qemu',
        'recipe': {'profile': 'ubuntu2404arm64', 'iso_sha256': SHA,
                   'iso_name': 'ubuntu-24.04-live-server-arm64.iso'},
        'os': {**_LINUX_OS, 'architecture': 'aarch64'},
    }
    with pytest.raises(EnvironmentSubmissionError) as excinfo:
        _preflight_environment(_write(tmp_path, env))
    message = str(excinfo.value)
    assert 'Windows profiles only' in message
    assert 'declares no download URL' in message


@pytest.mark.parametrize('bad_name', [
    '../../etc/passwd', '/absolute/Win11.iso', 'sub/dir/w.iso', 'C:\\ISO\\Win11.iso',
    'https://example.com/Win11.iso', 'Win11.img', '', 'x' * 250 + '.iso',
])
def test_bad_iso_name_is_rejected(tmp_path, bad_name):
    env = _recipe_env(iso_name=bad_name)
    del env['recipe']['iso']
    with pytest.raises(EnvironmentSubmissionError):
        _preflight_environment(_write(tmp_path, env))


def test_over_long_iso_notes_is_rejected(tmp_path):
    """iso_notes is rendered in web UIs; bound it as the server column does."""
    env = _recipe_env(iso_name='Win11.iso', iso_notes='x' * 1001)
    del env['recipe']['iso']
    with pytest.raises(EnvironmentSubmissionError, match='iso_notes'):
        _preflight_environment(_write(tmp_path, env))


# --- exactly-one-of ---

def test_both_iso_and_iso_name_is_rejected(tmp_path):
    env = _recipe_env(iso_name='Win11.iso')
    with pytest.raises(EnvironmentSubmissionError, match='both'):
        _preflight_environment(_write(tmp_path, env))


def test_neither_iso_nor_iso_name_is_rejected(tmp_path):
    """Must be loud: cattrs silently ignores unknown keys, so `iso_nmae:` parses."""
    env = _recipe_env()
    del env['recipe']['iso']
    with pytest.raises(EnvironmentSubmissionError, match='no ISO source'):
        _preflight_environment(_write(tmp_path, env))


def test_misspelled_iso_key_is_reported_as_no_iso_source(tmp_path):
    env = _recipe_env()
    env['recipe']['iso_nmae'] = 'Win11.iso'
    del env['recipe']['iso']
    with pytest.raises(EnvironmentSubmissionError, match='misspelled'):
        _preflight_environment(_write(tmp_path, env))


# --- profile / platform agreement ---

def test_unknown_profile_is_rejected(tmp_path):
    env = _recipe_env()
    env['recipe']['profile'] = 'windows12quantum'
    with pytest.raises(EnvironmentSubmissionError, match='not a known OS profile'):
        _preflight_environment(_write(tmp_path, env))


def test_windows_platform_over_a_linux_profile_is_rejected(tmp_path):
    env = {
        'vm_type': 'recipe', 'hypervisor': 'qemu',
        'recipe': {'profile': 'ubuntu2404', 'iso': UBUNTU_ISO_URL, 'iso_sha256': SHA},
        'os': _WINDOWS_OS,
    }
    with pytest.raises(EnvironmentSubmissionError, match='does not build'):
        _preflight_environment(_write(tmp_path, env))


def test_linux_platform_over_a_windows_profile_is_rejected(tmp_path):
    """Both directions: the mismatch is a lie either way round."""
    env = _recipe_env(os_block=_LINUX_OS)
    with pytest.raises(EnvironmentSubmissionError, match='does not build'):
        _preflight_environment(_write(tmp_path, env))


def test_linux_recipe_with_a_published_url_passes(tmp_path):
    env = {
        'vm_type': 'recipe', 'hypervisor': 'qemu',
        'recipe': {'profile': 'ubuntu2404', 'iso': UBUNTU_ISO_URL, 'iso_sha256': SHA},
        'os': _LINUX_OS,
    }
    _preflight_environment(_write(tmp_path, env))


# --- baked branch: regression cover for previously untested code ---

def test_baked_url_with_sha_passes(tmp_path):
    _preflight_environment(_write(tmp_path, _baked_env()))


def test_baked_local_path_is_rejected(tmp_path):
    env = _baked_env(vm='/Users/miq/.adare/state/vms/ubuntu.qcow2', vm_type='path')
    with pytest.raises(EnvironmentSubmissionError, match='http'):
        _preflight_environment(_write(tmp_path, env))


def test_baked_missing_vm_sha256_is_rejected(tmp_path):
    env = _baked_env()
    del env['vm_sha256']
    with pytest.raises(EnvironmentSubmissionError, match='vm_sha256'):
        _preflight_environment(_write(tmp_path, env))


def test_baked_uppercase_vm_sha256_is_accepted(tmp_path):
    """Asymmetric with iso_sha256 ON PURPOSE.

    The baked download check lowercases the declared value before comparing, so an
    uppercase vm_sha256 verifies fine. The ISO check does not, hence its stricter
    rule. Tightening this one would reject previously-valid environments without
    fixing anything.
    """
    _preflight_environment(_write(tmp_path, _baked_env(vm_sha256='A' * 64)))


def test_baked_url_without_a_disk_extension_needs_vm_format(tmp_path):
    env = _baked_env(vm='https://cloud.example.org/s/TOKEN/download')
    with pytest.raises(EnvironmentSubmissionError, match='vm_format'):
        _preflight_environment(_write(tmp_path, env))


def test_baked_url_without_an_extension_passes_with_vm_format(tmp_path):
    env = _baked_env(vm='https://cloud.example.org/s/TOKEN/download', vm_format='qcow2')
    _preflight_environment(_write(tmp_path, env))


def test_baked_invalid_vm_format_is_rejected(tmp_path):
    """An out-of-allow-list vm_format fails; cattrs rejects it before the gate."""
    env = _baked_env(vm_format='iso')
    with pytest.raises((EnvironmentSubmissionError, DataStructuringError)):
        _preflight_environment(_write(tmp_path, env))


def test_vagrantbox_is_left_to_the_server(tmp_path):
    """owner/box is verified against Vagrant Cloud; nothing local to leak."""
    env = {'vagrantbox': 'ubuntu/jammy64', 'hypervisor': 'virtualbox', 'os': _LINUX_OS}
    _preflight_environment(_write(tmp_path, env))
