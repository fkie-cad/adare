"""Host test mode for standard.file_count: counted from a guest-side listing, never the mirror.

The shared local mirror keeps files pulled by earlier tests, so globbing it would count files
the guest no longer has; directories cannot be pulled at all. The executor asks the guest for
the matching paths and their kind and runs the real testfunction on a fresh skeleton.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from adare.backend.experiment.guest_to_host_test_executor import GuestToHostTestExecutor
from adare.backend.experiment.host_services.guest_file_proxy import GuestFileProxy
from adare.backend.hostside.guestfs import GuestFSError
from adare.backend.hostside.testing import GuestFSFileProxy
from adarelib.constants import StatusEnum
from adarelib.helper.module import import_module_from_pyfile

pytestmark = pytest.mark.unit

COLLECTIONS = Path(__file__).resolve().parents[5] / 'appdata' / 'testfunctions'
standard = import_module_from_pyfile(COLLECTIONS / 'standard' / 'standard.py')
FileCount = standard.file_count._test_class
FileCountParameter = standard.file_count._parameter_class


def _executor(tmp_path, kinds=None, error=None):
    mirror = tmp_path / 'mirror'
    guest_file = MagicMock()
    guest_file._temp_root = mirror
    guest_file._guest_path_to_local = lambda p: mirror / p.lstrip('/')
    guest_file.path_kinds = AsyncMock(return_value=kinds or [], side_effect=error)
    guest_file.pull_file = AsyncMock(side_effect=AssertionError('file_count must not pull'))
    guest_file.resolve_guest_glob = AsyncMock(side_effect=AssertionError('file_count must not glob the mirror'))
    return GuestToHostTestExecutor(guest_file=guest_file, guest_command=MagicMock(), testfunction_collection={})


def _test(dst, **params):
    return FileCount(name='t', parameter=FileCountParameter(dst=dst, **params))


@pytest.mark.asyncio
async def test_stale_mirror_copy_is_not_counted(tmp_path):
    """A file an earlier test pulled, since deleted on the guest, is not counted."""
    stale = tmp_path / 'mirror' / 'home/u/logs/a.log'
    stale.parent.mkdir(parents=True)
    stale.write_text('old')
    executor = _executor(tmp_path, kinds=[])
    instance = _test('/home/u/logs/*.log', expected_count=0)

    result = await executor._execute_file_based_test('t', 'standard.file_count', instance)

    assert result.status == StatusEnum.SUCCESS, result.details
    assert instance.parameter.dst == '/home/u/logs/*.log'  # restored


@pytest.mark.asyncio
@pytest.mark.parametrize(('kind', 'count'), [('file', 2), ('dir', 1), ('any', 4)])
async def test_kinds_from_the_guest(tmp_path, kind, count):
    kinds = [
        ('/home/u/logs/a.log', 'file'),
        ('/home/u/logs/b.log', 'file'),
        ('/home/u/logs/old.log', 'dir'),
        ('/home/u/logs/dangling.log', 'other'),
    ]
    executor = _executor(tmp_path, kinds=kinds)

    result = await executor._execute_file_based_test(
        't', 'standard.file_count', _test('/home/u/logs/*.log', expected_count=count, kind=kind)
    )

    assert result.status == StatusEnum.SUCCESS, result.details
    assert 'adare_count_' not in ' '.join(result.details)  # guest paths, not the skeleton
    if kind == 'file':
        assert '/home/u/logs/a.log, /home/u/logs/b.log' in result.details[0]


@pytest.mark.asyncio
async def test_plain_directory_path(tmp_path):
    executor = _executor(tmp_path, kinds=[('/home/u/logs', 'dir')])

    result = await executor._execute_file_based_test(
        't', 'standard.file_count', _test('/home/u/logs', expected_count=1, kind='dir')
    )

    assert result.status == StatusEnum.SUCCESS, result.details


@pytest.mark.asyncio
async def test_listing_failure_is_error(tmp_path):
    executor = _executor(tmp_path, error=RuntimeError('guest command failed'))

    result = await executor._execute_file_based_test(
        't', 'standard.file_count', _test('/home/u/*.log', expected_count=0)
    )

    assert result.status == StatusEnum.ERROR


def _vm(stdout='', returncode=0):
    vm = MagicMock()
    vm.run_command = AsyncMock(return_value=SimpleNamespace(stdout=stdout, stderr='boom', returncode=returncode))
    return vm


@pytest.mark.asyncio
async def test_qga_proxy_parses_kinds_and_quotes_plain_paths():
    proxy = GuestFileProxy(_vm('F:/a/x.log\nD:/a/d.log\nO:/a/l.log\nnoise\n'), 'linux')
    try:
        assert await proxy.path_kinds('/a/*.log') == [('/a/x.log', 'file'), ('/a/d.log', 'dir'), ('/a/l.log', 'other')]
        await proxy.path_kinds("/a/it's here")
        assert "'/a/it'\"'\"'s here'" in proxy.vm.run_command.await_args.args[0]
    finally:
        proxy.cleanup()


@pytest.mark.asyncio
async def test_qga_proxy_windows_paths_keep_the_drive_colon():
    proxy = GuestFileProxy(_vm('F:C:\\Users\\u\\a.log\r\nD:C:\\Users\\u\\logs\r\n'), 'windows')
    try:
        assert await proxy.path_kinds('C:\\Users\\u\\*') == [
            ('C:\\Users\\u\\a.log', 'file'),
            ('C:\\Users\\u\\logs', 'dir'),
        ]
    finally:
        proxy.cleanup()


@pytest.mark.asyncio
async def test_qga_proxy_failed_command_raises():
    proxy = GuestFileProxy(_vm(returncode=1), 'linux')
    try:
        with pytest.raises(RuntimeError):
            await proxy.path_kinds('/a/*.log')
    finally:
        proxy.cleanup()


@pytest.mark.asyncio
async def test_guestfs_proxy_kinds():
    fs = MagicMock()
    fs.glob.return_value = ['/a/x', '/a/d', '/a/l']
    fs.is_file.side_effect = lambda p: p == '/a/x'
    fs.is_dir.side_effect = lambda p: p == '/a/d'
    proxy = GuestFSFileProxy(fs)
    try:
        assert await proxy.path_kinds('/a/*') == [('/a/x', 'file'), ('/a/d', 'dir'), ('/a/l', 'other')]
        fs.glob.side_effect = GuestFSError('unreadable')
        with pytest.raises(RuntimeError):
            await proxy.path_kinds('/a/*')
    finally:
        proxy.cleanup()
