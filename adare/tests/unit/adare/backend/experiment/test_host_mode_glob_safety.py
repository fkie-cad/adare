"""Host test mode: guest glob commands quote their paths, and stale mirror copies are dropped."""

import shutil
import subprocess
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from adare.backend.experiment.guest_to_host_test_executor import GuestToHostTestExecutor
from adare.backend.experiment.host_services.guest_file_proxy import (
    GuestFileProxy,
    powershell_literal,
    shell_glob_word,
)
from adarelib.constants import StatusEnum
from adarelib.event.event import TestResult

pytestmark = pytest.mark.unit

BASH = shutil.which('bash')


@pytest.mark.parametrize(
    ('pattern', 'word'),
    [
        ('/var/log/*.log', '/var/log/*.log'),
        ('/home/my dir/*', "'/home/my dir/'*"),
        ('/a/[ab]?.txt', '/a/[ab]?.txt'),
        ('/a/[!x]', '/a/[!x]'),
        ('/a/b[', "'/a/b['"),  # no closing bracket: literal
        ('/a/$(rm -rf ~)*', "'/a/$(rm -rf ~)'*"),
        ('', "''"),
    ],
)
def test_shell_glob_word(pattern, word):
    assert shell_glob_word(pattern) == word


@pytest.mark.skipif(BASH is None, reason='needs bash')
def test_shell_glob_word_in_bash(tmp_path):
    names = ['a 1.log', 'b.log', 'c.txt', "it's.log", 'x;y.log', 'PWNED-not']
    for name in names[:-1]:
        (tmp_path / name).write_text('x')

    def ls(pattern):
        word = shell_glob_word(f'{tmp_path}/{pattern}')
        out = subprocess.run([BASH, '-c', f'ls -d -- {word} 2>/dev/null || true'], capture_output=True, text=True)
        return sorted(p.rsplit('/', 1)[-1] for p in out.stdout.splitlines())

    assert ls('*.log') == ['a 1.log', 'b.log', "it's.log", 'x;y.log']
    assert ls('[ab]*') == ['a 1.log', 'b.log']
    assert ls("it's*") == ["it's.log"]
    assert ls('x;y.log') == ['x;y.log']
    ls('$(touch PWNED)*')
    assert not (tmp_path.parent / 'PWNED').exists() and not (tmp_path / 'PWNED').exists()


def test_powershell_literal():
    assert powershell_literal("C:\\Users\\O'Brien\\$env:x\\*.log") == "'C:\\Users\\O''Brien\\$env:x\\*.log'"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('guest_os', 'path', 'expected'),
    [
        ('linux', "/home/u/it's; rm x", "-- '/home/u/it'\"'\"'s; rm x'"),
        ('windows', "C:\\Users\\O'Brien\\a.txt", "-LiteralPath 'C:\\Users\\O''Brien\\a.txt'"),
    ],
)
async def test_commands_quote_paths(guest_os, path, expected):
    vm = MagicMock()
    vm.run_command = AsyncMock(return_value=SimpleNamespace(stdout='', stderr='', returncode=0))
    proxy = GuestFileProxy(vm, guest_os)
    try:
        await proxy.get_file_metadata(path)
        assert expected in vm.run_command.await_args.args[0]
        await proxy.resolve_guest_glob(path.replace('a.txt', '*'))
        command = vm.run_command.await_args.args[0]
        assert ("'" in command) and ('"' + path not in command)
    finally:
        proxy.cleanup()


def _executor(tmp_path, guest_matches):
    mirror = tmp_path / 'mirror'
    guest_file = MagicMock()
    guest_file._guest_path_to_local = lambda p: mirror / p.lstrip('/')
    guest_file.resolve_guest_glob = AsyncMock(return_value=guest_matches)

    async def pull(path, force=False):
        local = mirror / path.lstrip('/')
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_text('fresh')
        return local

    guest_file.pull_file = AsyncMock(side_effect=pull)
    executor = GuestToHostTestExecutor(guest_file=guest_file, guest_command=MagicMock(), testfunction_collection={})
    seen = []

    async def run(instance):
        import glob

        seen.append(sorted(glob.glob(instance.parameter.dst)))
        return TestResult.success(['ran'])

    executor._run_test = AsyncMock(side_effect=run)
    return executor, mirror, seen


def _instance(dst):
    instance = MagicMock()
    instance.parameter = SimpleNamespace(dst=dst)
    return instance


@pytest.mark.asyncio
async def test_stale_copy_of_a_deleted_file_is_not_seen(tmp_path):
    executor, mirror, seen = _executor(tmp_path, guest_matches=['/logs/b.log'])
    for name in ('a.log', 'b.log', 'keep.txt'):
        (mirror / 'logs').mkdir(parents=True, exist_ok=True)
        (mirror / 'logs' / name).write_text('old')

    result = await executor._execute_file_based_test('t', 'standard.file_exists', _instance('/logs/*.log'))

    assert result.status == StatusEnum.SUCCESS
    assert seen == [[str(mirror / 'logs' / 'b.log')]]  # a.log (deleted on the guest) is gone
    assert (mirror / 'logs' / 'keep.txt').exists()  # outside the pattern: untouched


@pytest.mark.asyncio
async def test_no_guest_match_removes_all_stale_copies(tmp_path):
    executor, mirror, seen = _executor(tmp_path, guest_matches=[])
    (mirror / 'logs').mkdir(parents=True)
    (mirror / 'logs' / 'a.log').write_text('old')

    await executor._execute_file_based_test('t', 'standard.file_does_not_exist', _instance('/logs/*.log'))

    assert seen == [[]]


@pytest.mark.asyncio
async def test_file_vanished_before_pull_drops_its_old_copy(tmp_path):
    executor, mirror, seen = _executor(tmp_path, guest_matches=['/logs/a.log', '/logs/b.log'])
    (mirror / 'logs').mkdir(parents=True)
    (mirror / 'logs' / 'a.log').write_text('old')
    original_pull = executor.guest_file.pull_file.side_effect

    async def pull(path, force=False):
        if path == '/logs/a.log':
            raise FileNotFoundError(path)
        return await original_pull(path, force)

    executor.guest_file.pull_file = AsyncMock(side_effect=pull)

    await executor._execute_file_based_test('t', 'standard.file_exists', _instance('/logs/*.log'))

    assert seen == [[str(mirror / 'logs' / 'b.log')]]
