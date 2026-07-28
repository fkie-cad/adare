"""Tests for build-time provisioning expansion (T4, T5).

`adare.backend.vm.provision` imports no QEMU code, so the whole provisioning
contract — for_each expansion, template strictness, shell resolution, uniqueness —
is testable here without a hypervisor, a disk, or a guest.
"""

import pytest

pytestmark = pytest.mark.unit

from adare.backend.vm.provision import (
    ProvisionSchemaError,
    expand_provision,
    provision_identity,
    resolve_shell,
)
from adare.types.environment import ProvisionCommand, ProvisionStep

# --- Helpers ---

AUTOPSY_VERSIONS = [
    '4.4.0', '4.4.1', '4.5.0', '4.6.0', '4.7.0', '4.8.0', '4.9.0', '4.9.1',
    '4.10.0', '4.11.0', '4.12.0', '4.13.0', '4.14.0', '4.15.0', '4.16.0', '4.17.0',
]


def _autopsy_group(versions=None) -> ProvisionStep:
    """The real Autopsy solr4 group shape: download / install / cleanup per version."""
    return ProvisionStep(
        name='autopsy',
        description='Autopsy {{ item }} (Solr 4.10.3)',
        for_each=list(AUTOPSY_VERSIONS if versions is None else versions),
        steps=[
            ProvisionCommand(
                name='autopsy-{{ item }}-download',
                command='curl.exe -L -f -o "C:\\Windows\\Temp\\autopsy-{{ item }}.msi" '
                        'https://example.invalid/autopsy-{{ item }}-64bit.msi',
                timeout_minutes=20,
            ),
            ProvisionCommand(
                name='autopsy-{{ item }}-install',
                command='msiexec /i "C:\\Windows\\Temp\\autopsy-{{ item }}.msi"',
                allow_exit_codes=[0, 3010],
                verify='if (-not (Test-Path "C:\\Program Files\\Autopsy-{{ item }}")) { exit 1 }',
                log_files=['C:\\Windows\\Temp\\autopsy-{{ item }}-msi.log'],
                timeout_minutes=45,
            ),
            ProvisionCommand(
                name='autopsy-{{ item }}-cleanup',
                command='Remove-Item -Force "C:\\Windows\\Temp\\autopsy-{{ item }}.msi"',
            ),
        ],
    )


# --- T4: expansion ---

def test_for_each_expands_to_versions_times_steps():
    """16 versions x 3 steps -> 48 commands."""
    expanded = expand_provision([_autopsy_group()], 'windows')
    assert len(expanded) == 48


def test_expansion_is_group_major_so_each_item_stays_contiguous():
    """All of item 1's steps run before item 2's.

    The download/install/cleanup triple must stay adjacent per item, or the temp
    MSI of every version would accumulate before the first cleanup.
    """
    expanded = expand_provision([_autopsy_group(['4.4.0', '4.4.1'])], 'windows')
    assert [c.name for c in expanded] == [
        'autopsy-4.4.0-download', 'autopsy-4.4.0-install', 'autopsy-4.4.0-cleanup',
        'autopsy-4.4.1-download', 'autopsy-4.4.1-install', 'autopsy-4.4.1-cleanup',
    ]


def test_item_is_substituted_in_every_templated_field():
    expanded = expand_provision([_autopsy_group(['4.12.0'])], 'windows')
    install = expanded[1]
    assert install.name == 'autopsy-4.12.0-install'
    assert 'autopsy-4.12.0.msi' in install.command
    assert install.verify == 'if (-not (Test-Path "C:\\Program Files\\Autopsy-4.12.0")) { exit 1 }'
    assert install.log_files == ['C:\\Windows\\Temp\\autopsy-4.12.0-msi.log']
    assert install.description == 'Autopsy 4.12.0 (Solr 4.10.3)'


def test_non_templated_fields_pass_through_unchanged():
    install = expand_provision([_autopsy_group(['4.12.0'])], 'windows')[1]
    assert install.allow_exit_codes == [0, 3010]
    assert install.timeout_minutes == 45
    assert install.reboot is False


def test_single_command_shorthand_yields_one_command():
    """A step with `command` and no `steps` is one command, not a group."""
    step = ProvisionStep(name='boot-hardening', shell='cmd',
                         command='bcdedit /set {default} recoveryenabled No')
    expanded = expand_provision([step], 'windows')
    assert len(expanded) == 1
    assert expanded[0].name == 'boot-hardening'
    assert expanded[0].shell == 'cmd'


def test_literal_braces_survive_when_there_is_no_for_each():
    """`{default}` in a bcdedit command must not be touched by the templater."""
    step = ProvisionStep(name='hardening', shell='cmd',
                         command='bcdedit /set {default} bootstatuspolicy ignoreallfailures')
    expanded = expand_provision([step], 'windows')
    assert expanded[0].command == (
        'bcdedit /set {default} bootstatuspolicy ignoreallfailures'
    )


def test_declared_order_of_top_level_steps_is_preserved():
    steps = [
        ProvisionStep(name='first', command='echo 1'),
        _autopsy_group(['4.4.0']),
        ProvisionStep(name='last', command='echo 2'),
    ]
    names = [c.name for c in expand_provision(steps, 'windows')]
    assert names[0] == 'first'
    assert names[-1] == 'last'


# --- T5: rejections ---

def test_unknown_jinja_variable_is_a_hard_error():
    """StrictUndefined: `{{ version }}` must raise, not render empty.

    With Jinja's default Undefined this would silently produce
    '.../autopsy--64bit.msi' and a plausible-but-wrong disk.
    """
    step = ProvisionStep(
        name='g', for_each=['1.0'],
        steps=[ProvisionCommand(name='s-{{ item }}', command='get autopsy-{{ version }}.msi')],
    )
    with pytest.raises(ProvisionSchemaError, match="'version' is undefined"):
        expand_provision([step], 'windows')


def test_error_message_names_the_step_and_the_field():
    step = ProvisionStep(
        name='g', for_each=['1.0'],
        steps=[ProvisionCommand(name='dl-{{ item }}', command='ok',
                                verify='Test-Path {{ nope }}')],
    )
    with pytest.raises(ProvisionSchemaError) as excinfo:
        expand_provision([step], 'windows')
    assert 'dl-1.0' in str(excinfo.value)
    assert "'verify'" in str(excinfo.value)


def test_duplicate_expanded_name_is_rejected():
    """Forgetting `{{ item }}` in a for_each step's name yields 16 identical names."""
    step = ProvisionStep(
        name='g', for_each=['1.0', '2.0'],
        steps=[ProvisionCommand(name='install', command='msiexec {{ item }}')],
    )
    with pytest.raises(ProvisionSchemaError, match='duplicate provision step name'):
        expand_provision([step], 'windows')


def test_duplicate_names_across_separate_top_level_steps_are_rejected():
    steps = [
        ProvisionStep(name='same', command='echo 1'),
        ProvisionStep(name='same', command='echo 2'),
    ]
    with pytest.raises(ProvisionSchemaError, match='duplicate provision step name'):
        expand_provision(steps, 'windows')


def test_empty_command_is_rejected():
    with pytest.raises(ValueError, match='non-empty'):
        ProvisionCommand(name='x', command='   ')


def test_step_with_both_command_and_steps_is_rejected():
    with pytest.raises(ValueError, match='both'):
        ProvisionStep(name='x', command='echo 1',
                      steps=[ProvisionCommand(name='y', command='echo 2')])


def test_step_with_neither_command_nor_steps_is_rejected():
    with pytest.raises(ValueError, match='must set either'):
        ProvisionStep(name='x')


def test_for_each_without_steps_is_rejected():
    """for_each replays a group; on a single command it is almost certainly a typo."""
    with pytest.raises(ValueError, match='for_each'):
        ProvisionStep(name='x', command='echo {{ item }}', for_each=['1', '2'])


def test_non_positive_timeout_is_rejected():
    with pytest.raises(ValueError, match='timeout_minutes'):
        ProvisionCommand(name='x', command='echo 1', timeout_minutes=0)


# --- shell resolution ---

@pytest.mark.parametrize('platform,expected', [('windows', 'powershell'), ('linux', 'bash')])
def test_auto_shell_resolves_per_platform(platform, expected):
    assert resolve_shell('auto', platform) == expected


@pytest.mark.parametrize('shell,platform', [
    ('powershell', 'windows'), ('cmd', 'windows'), ('bash', 'linux'),
])
def test_explicit_available_shell_passes_through(shell, platform):
    assert resolve_shell(shell, platform) == shell


@pytest.mark.parametrize('shell,platform', [
    ('cmd', 'linux'), ('powershell', 'linux'), ('bash', 'windows'),
])
def test_shell_unavailable_on_platform_is_rejected(shell, platform):
    """A silent substitution would run the author's text through the wrong parser."""
    with pytest.raises(ProvisionSchemaError, match='not available'):
        resolve_shell(shell, platform)


def test_unsupported_platform_is_rejected():
    with pytest.raises(ProvisionSchemaError, match='not supported'):
        resolve_shell('auto', 'plan9')


def test_expanded_shell_is_never_auto():
    """Downstream code must never have to re-resolve 'auto'."""
    expanded = expand_provision([_autopsy_group(['4.4.0'])], 'windows')
    assert all(c.shell != 'auto' for c in expanded)


# --- identity projection ---

def test_identity_excludes_description_and_log_files():
    """Neither can affect the disk, so a typo in prose must not force a rebuild."""
    identity = provision_identity(expand_provision([_autopsy_group(['4.4.0'])], 'windows'))
    for entry in identity:
        assert 'description' not in entry
        assert 'log_files' not in entry


def test_identity_includes_the_fields_that_change_the_disk():
    identity = provision_identity(expand_provision([_autopsy_group(['4.4.0'])], 'windows'))
    install = identity[1]
    assert install['command'].startswith('msiexec')
    assert install['allow_exit_codes'] == [0, 3010]
    assert install['verify'] is not None
    assert install['shell'] == 'powershell'
    assert install['timeout_minutes'] == 45


def test_identity_is_order_sensitive():
    a = provision_identity(expand_provision([_autopsy_group(['4.4.0', '4.4.1'])], 'windows'))
    b = provision_identity(expand_provision([_autopsy_group(['4.4.1', '4.4.0'])], 'windows'))
    assert a != b
