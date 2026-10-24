"""Which Python environment the agent is installed into on a Windows guest."""

import asyncio
import threading
from types import SimpleNamespace

import pytest

from adare.backend.experiment.agent_command_builders import detect_environment

pytestmark = pytest.mark.unit


class _FakeVM:
    """Answers run_command from a list of (substring, returncode, stdout) rules."""

    vm_name = 'win'
    username = 'adare'
    architecture = 'x86_64'

    def __init__(self, rules):
        self.rules = rules
        self.commands = []

    async def run_command(self, command, stop_event=None, timeout=None):
        self.commands.append(command)
        for needle, returncode, stdout in self.rules:
            if needle in command:
                return SimpleNamespace(returncode=returncode, stdout=stdout, stderr='')
        raise AssertionError(f'unexpected command: {command}')


def _detect(vm):
    return asyncio.run(detect_environment(vm, 'windows', threading.Event()))


def test_the_env_check_branches_on_the_match_not_on_dollar_question():
    # `Select-String ... | Out-Null; if ($?)` reported "env_exists" for a Miniforge
    # whose pyadare env was never created, and the agent install then failed.
    vm = _FakeVM([('Test-Path', 0, ''), ('env list', 0, 'env_exists')])

    _detect(vm)

    env_check = next(command for command in vm.commands if 'env list' in command)
    assert '$?' not in env_check
    assert env_check.startswith('if (& ')


def test_a_missing_env_is_created_before_it_is_used():
    vm = _FakeVM([('Test-Path', 0, ''), ('env list', 0, 'env_not_found'), ('create -n pyadare', 0, '')])

    info = _detect(vm)

    assert info.use_conda
    assert any('create -n pyadare python=3.10' in command for command in vm.commands)


def test_falls_back_to_system_python_when_the_env_cannot_be_created():
    vm = _FakeVM([('Test-Path', 0, ''), ('env list', 0, 'env_not_found'), ('create -n pyadare', 1, '')])

    info = _detect(vm)

    assert not info.use_conda
