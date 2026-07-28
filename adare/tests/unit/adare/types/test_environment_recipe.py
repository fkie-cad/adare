"""Tests for parsing the six environment shapes and the ISO-source truth table (T13).

`parse_environment_file` uses the *global* `cattrs.structure`, so the new
`ProvisionCommand` / `ProvisionStep` classes must structure natively as two flat
concrete classes — no union hooks, no self-recursion. These tests pin that, plus
the fact that cattrs silently DROPS unknown keys, which is the reason the gates
must reject "no ISO source" loudly rather than treating it as absence.
"""

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

from adare.exceptions import DataStructuringError
from adare.services.recipe_contract import classify_iso_source
from adare.types.environment import Recipe, parse_environment_file

SHA = 'a' * 64
_LINUX_OS = {'os': 'Ubuntu 24.04', 'platform': 'linux', 'distribution': 'ubuntu'}
_WINDOWS_OS = {'os': 'Windows 11 (ARM64)', 'platform': 'windows', 'distribution': 'Home',
               'version': '11', 'language': 'English', 'architecture': 'aarch64'}


def _parse(tmp_path: Path, env: dict, name: str = 'env.yml'):
    path = tmp_path / name
    path.write_text(yaml.dump(env))
    return parse_environment_file(path)


# --- the six environment shapes ---

def test_baked_local_path_round_trips(tmp_path):
    metadata = _parse(tmp_path, {
        'vm': '/Users/miq/.adare/state/vms/ubuntu.qcow2', 'vm_type': 'path',
        'hypervisor': 'qemu', 'os': _LINUX_OS,
    })
    assert metadata.vm_type == 'path'
    assert metadata.is_vm_environment and not metadata.is_recipe_environment


def test_baked_url_round_trips(tmp_path):
    metadata = _parse(tmp_path, {
        'vm': 'https://files.example.org/ubuntu.qcow2', 'vm_type': 'url',
        'vm_sha256': SHA, 'vm_format': 'qcow2', 'hypervisor': 'qemu', 'os': _LINUX_OS,
    })
    assert metadata.vm_sha256 == SHA
    assert metadata.vm_format == 'qcow2'


def test_vagrantbox_round_trips(tmp_path):
    metadata = _parse(tmp_path, {'vagrantbox': 'ubuntu/jammy64', 'os': _LINUX_OS})
    assert metadata.is_vagrant_environment


def test_recipe_url_form_round_trips(tmp_path):
    metadata = _parse(tmp_path, {
        'vm_type': 'recipe', 'hypervisor': 'qemu', 'os': _LINUX_OS,
        'recipe': {'profile': 'ubuntu2404',
                   'iso': 'https://releases.ubuntu.com/24.04/x.iso',
                   'iso_sha256': SHA, 'params': {'setup_level': 1}},
    })
    assert metadata.recipe.iso.startswith('https://')
    assert metadata.recipe.iso_name == ''
    assert metadata.recipe.params.setup_level == 1
    assert metadata.recipe.provision == []


def test_recipe_byo_form_round_trips(tmp_path):
    metadata = _parse(tmp_path, {
        'vm_type': 'recipe', 'hypervisor': 'qemu', 'os': _WINDOWS_OS,
        'recipe': {'profile': 'windows11arm64', 'iso_sha256': SHA,
                   'iso_name': 'Win11.iso', 'iso_notes': 'From Microsoft'},
    })
    assert metadata.recipe.iso == ''
    assert metadata.recipe.iso_name == 'Win11.iso'
    assert metadata.recipe.iso_notes == 'From Microsoft'


def test_recipe_with_provision_round_trips(tmp_path):
    metadata = _parse(tmp_path, {
        'vm_type': 'recipe', 'hypervisor': 'qemu', 'os': _WINDOWS_OS,
        'recipe': {
            'profile': 'windows11arm64', 'iso_sha256': SHA, 'iso_name': 'Win11.iso',
            'provision': [
                {'name': 'harden', 'shell': 'cmd', 'command': 'bcdedit /x'},
                {'name': 'autopsy', 'description': 'Autopsy {{ item }}',
                 'for_each': ['4.4.0', '4.4.1'],
                 'steps': [
                     {'name': 'dl-{{ item }}', 'command': 'curl {{ item }}',
                      'timeout_minutes': 20},
                     {'name': 'inst-{{ item }}', 'command': 'msiexec {{ item }}',
                      'allow_exit_codes': [0, 3010], 'verify': 'test {{ item }}',
                      'log_files': ['C:\\Windows\\Temp\\{{ item }}.log'],
                      'reboot': False},
                 ]},
            ],
        },
    })
    provision = metadata.recipe.provision
    assert len(provision) == 2
    assert provision[0].shell == 'cmd' and provision[0].command == 'bcdedit /x'
    assert provision[0].steps == [] and provision[0].for_each == []
    group = provision[1]
    assert group.for_each == ['4.4.0', '4.4.1']
    assert len(group.steps) == 2
    assert group.steps[1].allow_exit_codes == [0, 3010]
    assert group.steps[1].log_files == ['C:\\Windows\\Temp\\{{ item }}.log']
    assert group.steps[1].timeout_minutes == 30  # default


def test_provision_defaults_are_applied(tmp_path):
    metadata = _parse(tmp_path, {
        'vm_type': 'recipe', 'hypervisor': 'qemu', 'os': _WINDOWS_OS,
        'recipe': {'profile': 'windows11arm64', 'iso_sha256': SHA,
                   'iso_name': 'Win11.iso',
                   'provision': [{'name': 'x', 'command': 'do-x'}]},
    })
    command = metadata.recipe.provision[0]
    assert command.shell == 'auto'
    assert command.allow_exit_codes == [0]
    assert command.verify is None
    assert command.log_files == []
    assert command.timeout_minutes == 30
    assert command.reboot is False


def test_postsetupinstallations_still_parse_alongside_provision(tmp_path):
    """The two lists are independent and must not interfere."""
    metadata = _parse(tmp_path, {
        'vm_type': 'recipe', 'hypervisor': 'qemu', 'os': _WINDOWS_OS,
        'postsetupinstallations': [{'name': 'per-run', 'command': 'each-time'}],
        'recipe': {'profile': 'windows11arm64', 'iso_sha256': SHA,
                   'iso_name': 'Win11.iso',
                   'provision': [{'name': 'build-time', 'command': 'once'}]},
    })
    assert [i.name for i in metadata.postsetupinstallations] == ['per-run']
    assert [c.name for c in metadata.recipe.provision] == ['build-time']


# --- schema errors surface through the existing DataStructuringError route ---

def test_a_provision_entry_with_both_command_and_steps_fails_parsing(tmp_path):
    with pytest.raises(DataStructuringError):
        _parse(tmp_path, {
            'vm_type': 'recipe', 'hypervisor': 'qemu', 'os': _WINDOWS_OS,
            'recipe': {'profile': 'windows11arm64', 'iso_sha256': SHA,
                       'iso_name': 'Win11.iso',
                       'provision': [{'name': 'x', 'command': 'a',
                                      'steps': [{'name': 'y', 'command': 'b'}]}]},
        })


def test_a_provision_entry_with_neither_command_nor_steps_fails_parsing(tmp_path):
    with pytest.raises(DataStructuringError):
        _parse(tmp_path, {
            'vm_type': 'recipe', 'hypervisor': 'qemu', 'os': _WINDOWS_OS,
            'recipe': {'profile': 'windows11arm64', 'iso_sha256': SHA,
                       'iso_name': 'Win11.iso', 'provision': [{'name': 'x'}]},
        })


def test_an_invalid_shell_value_fails_parsing(tmp_path):
    with pytest.raises(DataStructuringError):
        _parse(tmp_path, {
            'vm_type': 'recipe', 'hypervisor': 'qemu', 'os': _WINDOWS_OS,
            'recipe': {'profile': 'windows11arm64', 'iso_sha256': SHA,
                       'iso_name': 'Win11.iso',
                       'provision': [{'name': 'x', 'command': 'a', 'shell': 'zsh'}]},
        })


def test_vm_type_recipe_without_a_recipe_block_fails_parsing(tmp_path):
    with pytest.raises(DataStructuringError):
        _parse(tmp_path, {'vm_type': 'recipe', 'hypervisor': 'qemu', 'os': _LINUX_OS})


# --- unknown keys are silently dropped: WHY the gates must reject "neither" ---

def test_cattrs_silently_ignores_an_unknown_recipe_key(tmp_path):
    """A misspelled `iso_nmae:` parses cleanly with NO ISO source at all.

    This is exactly why `classify_iso_source` reports 'none' and every gate
    rejects it loudly: absence here is indistinguishable from a typo, and an
    environment with no ISO source must never be treated as merely incomplete.
    """
    metadata = _parse(tmp_path, {
        'vm_type': 'recipe', 'hypervisor': 'qemu', 'os': _WINDOWS_OS,
        'recipe': {'profile': 'windows11arm64', 'iso_sha256': SHA,
                   'iso_nmae': 'Win11.iso'},
    })
    assert metadata.recipe.iso == ''
    assert metadata.recipe.iso_name == ''
    assert classify_iso_source(metadata.recipe) == 'none'


def test_a_nested_group_inside_steps_is_dropped_and_then_rejected(tmp_path):
    """`steps` inside `steps` is not a supported shape.

    cattrs drops the inner key, leaving a leaf command with an empty `command`,
    which `ProvisionCommand` then rejects — a legible failure rather than silently
    skipping the nested work.
    """
    with pytest.raises(DataStructuringError):
        _parse(tmp_path, {
            'vm_type': 'recipe', 'hypervisor': 'qemu', 'os': _WINDOWS_OS,
            'recipe': {'profile': 'windows11arm64', 'iso_sha256': SHA,
                       'iso_name': 'Win11.iso',
                       'provision': [{'name': 'outer', 'steps': [
                           {'name': 'inner-group',
                            'steps': [{'name': 'deep', 'command': 'a'}]},
                       ]}]},
        })


# --- classify_iso_source truth table ---

@pytest.mark.parametrize('iso,iso_name,expected', [
    ('https://x/y.iso', '', 'url'),
    ('http://x/y.iso', '', 'url'),
    ('/local/y.iso', '', 'path'),
    ('relative/y.iso', '', 'path'),
    ('', 'y.iso', 'byo'),
    ('https://x/y.iso', 'y.iso', 'both'),
    ('/local/y.iso', 'y.iso', 'both'),
    ('', '', 'none'),
    ('   ', '   ', 'none'),
])
def test_classify_iso_source_truth_table(iso, iso_name, expected):
    recipe = Recipe(profile='p', iso_sha256=SHA, iso=iso, iso_name=iso_name)
    assert classify_iso_source(recipe) == expected


def test_the_shipped_win11arm64_fresh_file_parses_byte_exactly():
    """Guards against a schema change breaking the file that ships in the repo."""
    shipped = Path(__file__).parents[5] / 'win11arm64-fresh.yml'
    if not shipped.is_file():  # pragma: no cover - layout guard
        pytest.skip(f'shipped recipe not found at {shipped}')
    metadata = parse_environment_file(shipped)
    assert metadata.recipe.profile == 'windows11arm64'
    assert metadata.recipe.provision == []
    assert classify_iso_source(metadata.recipe) == 'path'


def test_the_shipped_autopsy_recipes_parse_and_expand():
    """The two Phase-3 artifacts must stay parseable as the schema evolves."""
    from adare.backend.vm.provision import expand_provision

    root = Path(__file__).parents[5]
    provisioning = (root / 'paper' / 'experiments'
                    / '4_autopsy_tool_regression_testing' / 'provisioning')
    if not provisioning.is_dir():  # pragma: no cover - layout guard
        pytest.skip(f'paper case study not found at {provisioning}')

    # 2 boot-hardening steps + versions x 3 (download / install / cleanup).
    expected_counts = {'win11-autopsy-solr4': 2 + 16 * 3, 'win11-autopsy-solr8': 2 + 8 * 3}
    for name, count in expected_counts.items():
        metadata = parse_environment_file(provisioning / f'{name}.yml')
        commands = expand_provision(metadata.recipe.provision, 'windows')
        assert len(commands) == count, name
        assert classify_iso_source(metadata.recipe) == 'byo'
        assert commands[0].shell == 'cmd'  # boot-hardening needs cmd, not PowerShell
        # Every install step asserts its own outcome.
        installs = [c for c in commands if c.name.endswith('-install')]
        assert installs and all(c.verify for c in installs)
        assert all(3010 in c.allow_exit_codes for c in installs)
