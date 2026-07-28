"""Tests for `_build_exec_args` — the guest-exec spawn contract.

The `cmd` case pins a non-obvious decision. Handing the guest agent
`['cmd.exe', '/c', <script>]` is the natural form, but its spawn (glib on Windows)
reproducibly rejects certain scripts with "Failed to execute helper program
(Permission denied)" *before* cmd parses them — measured on a real Win11-ARM64
guest, `bcdedit /set {default} bootstatuspolicy ignoreallfailures && bcdedit /set
{default} recoveryenabled No` fails 2/2 while each half alone, `bcdedit /enum &&
bcdedit /enum`, and a 1000-character `echo` all succeed.

So `cmd` is routed through PowerShell, which spawns cmd itself. Every Windows
exec then presents the agent with the same command-line shape, which is what makes
it immune to that class of failure. These tests exist so nobody "simplifies" it
back.
"""

import base64

import pytest

pytestmark = pytest.mark.unit

from adare.hypervisor.qemu.vm_creator.qga_utils import QgaError, _build_exec_args

FAILING_CMD = ('bcdedit /set {default} bootstatuspolicy ignoreallfailures && '
               'bcdedit /set {default} recoveryenabled No')


def _decode_ps(args: list[str]) -> str:
    """Decode a `-EncodedCommand` payload back to its PowerShell source."""
    assert args[0] == 'powershell.exe'
    assert args[1] == '-EncodedCommand'
    return base64.b64decode(args[2]).decode('utf-16le')


# --- powershell ---

def test_powershell_uses_encoded_command():
    args = _build_exec_args('Write-Output hi', None, True, 'powershell')
    assert args[0] == 'powershell.exe'
    assert _decode_ps(args) == 'Write-Output hi'


def test_powershell_folds_in_cwd():
    args = _build_exec_args('Write-Output hi', 'C:\\Temp', True, 'powershell')
    assert _decode_ps(args) == 'cd C:\\Temp; Write-Output hi'


# --- cmd, via PowerShell ---

def test_cmd_is_spawned_as_powershell_not_cmd():
    """The agent must never be asked to spawn cmd.exe directly."""
    args = _build_exec_args(FAILING_CMD, None, True, 'cmd')
    assert args[0] == 'powershell.exe'
    assert args[1] == '-EncodedCommand'


def test_cmd_and_powershell_present_the_same_command_line_shape():
    """Uniform shape is the property that removes the whole failure class."""
    as_cmd = _build_exec_args('echo hi', None, True, 'cmd')
    as_ps = _build_exec_args('Write-Output hi', None, True, 'powershell')
    assert as_cmd[:2] == as_ps[:2]
    assert len(as_cmd) == len(as_ps) == 3


def test_cmd_script_is_carried_base64_so_it_is_never_quoted():
    """No layer escapes the script, so no script text can break the wrapper."""
    args = _build_exec_args(FAILING_CMD, None, True, 'cmd')
    wrapper = _decode_ps(args)
    # The raw script must NOT appear literally in the PowerShell source.
    assert FAILING_CMD not in wrapper
    payload = base64.b64encode(FAILING_CMD.encode('utf-8')).decode('ascii')
    assert payload in wrapper


def test_cmd_wrapper_invokes_cmd_and_propagates_its_exit_code():
    wrapper = _decode_ps(_build_exec_args('exit 3010', None, True, 'cmd'))
    assert '& cmd.exe /c $s' in wrapper
    assert 'exit $LASTEXITCODE' in wrapper


@pytest.mark.parametrize('script', [
    FAILING_CMD,
    'echo "he said ""hi"" & then left"',
    'echo 100%% done',
    'echo a^&b',
    "echo it's fine",
    'echo ' + 'a' * 1000,
    'bcdedit /enum {default} /v | findstr /r /i /c:"recoveryenabled  *No"',
])
def test_any_cmd_script_round_trips_through_the_wrapper(script):
    """Decoding the wrapper's payload must yield the script byte for byte.

    Each of these was executed successfully on a real guest through this path.
    """
    wrapper = _decode_ps(_build_exec_args(script, None, True, 'cmd'))
    payload = wrapper.split("FromBase64String('")[1].split("')")[0]
    assert base64.b64decode(payload).decode('utf-8') == script


def test_cmd_folds_in_cwd_with_cd_slash_d():
    """`cd /d` is required to change drive as well as directory."""
    wrapper = _decode_ps(_build_exec_args('echo hi', 'D:\\work', True, 'cmd'))
    payload = wrapper.split("FromBase64String('")[1].split("')")[0]
    assert base64.b64decode(payload).decode('utf-8') == 'cd /d D:\\work && echo hi'


# --- bash / defaults ---

def test_bash_uses_bin_bash_dash_c():
    args = _build_exec_args('jq --version', None, False, 'bash')
    assert args == ['/bin/bash', '-c', 'jq --version']


def test_bash_folds_in_cwd():
    args = _build_exec_args('ls', '/tmp', False, 'bash')
    assert args == ['/bin/bash', '-c', 'cd /tmp && ls']


def test_windows_flag_defaults_to_powershell_when_no_shell_given():
    """Back-compat: existing callers pass only `windows=`."""
    args = _build_exec_args('Write-Output hi', None, True)
    assert args[0] == 'powershell.exe'


def test_non_windows_defaults_to_bash_when_no_shell_given():
    args = _build_exec_args('echo hi', None, False)
    assert args[0] == '/bin/bash'


def test_an_unsupported_shell_is_rejected():
    with pytest.raises(QgaError, match='Unsupported guest shell'):
        _build_exec_args('echo hi', None, True, 'zsh')
