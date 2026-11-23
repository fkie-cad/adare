"""Host-mode QGA probe tests judge like the in-guest versions (linux / windows / standard collections)."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from adare.backend.experiment.guest_to_host_test_executor import GuestToHostTestExecutor
from adare.backend.experiment.host_services import guest_command_proxy as proxy_module
from adare.backend.experiment.host_services.guest_command_proxy import GuestClock, GuestCommandProxy
from adare.hypervisor.base.models import CommandResult
from adare.hypervisor.qemu.guest_clock import GuestClockError
from adarelib.constants import StatusEnum

pytestmark = pytest.mark.unit

# ============================================================================
# GuestCommandProxy: what the guest commands are and how their answers are read
# ============================================================================


def _proxy(guest_os='linux', *replies):
    """A proxy over a VM whose ``run_command`` answers with ``replies`` in turn; records the commands."""
    vm = SimpleNamespace(commands=[])
    answers = list(replies)

    async def run_command(command, **kwargs):
        vm.commands.append(command)
        return answers.pop(0)

    vm.run_command = run_command
    return GuestCommandProxy(vm, guest_os), vm


def _ok(stdout='', returncode=0, stderr=''):
    return CommandResult(returncode=returncode, stdout=stdout, stderr=stderr)


class TestProcessListing:
    @pytest.mark.asyncio
    async def test_matches_the_command_line_like_agent_mode_and_skips_its_own_shell(self):
        proxy, vm = _proxy('linux', _ok('SELF:100\n100\n200\n201\n'))
        assert await proxy.list_processes('someapp') == ['200', '201']
        # pgrep -f (regex on the full command line), not -x (exact process name)
        assert 'pgrep -f -- someapp' in vm.commands[0] and '-x' not in vm.commands[0]

    @pytest.mark.asyncio
    async def test_pattern_is_shell_quoted(self):
        proxy, vm = _proxy('linux', _ok('SELF:1\n', returncode=1))
        await proxy.list_processes("^/usr/bin/some app; rm -rf /'")
        assert "pgrep -f -- '^/usr/bin/some app; rm -rf /'" in vm.commands[0]

    @pytest.mark.asyncio
    async def test_no_match_is_an_empty_list(self):
        proxy, _ = _proxy('linux', _ok('SELF:7\n', returncode=1))
        assert await proxy.list_processes('nothing') == []

    @pytest.mark.asyncio
    async def test_pgrep_failure_is_not_a_missing_process(self):
        proxy, _ = _proxy('linux', _ok('SELF:7\n', returncode=2, stderr='pgrep: invalid regex'))
        with pytest.raises(RuntimeError, match='pgrep failed'):
            await proxy.list_processes('(')


class TestUserInfo:
    @pytest.mark.asyncio
    async def test_reads_uid_and_home_from_the_user_database(self):
        proxy, vm = _proxy('linux', _ok('alice:x:1001:1001:Alice:/home/alice:/bin/bash\n'))
        assert await proxy.get_user_info('alice') == {'uid': 1001, 'home': '/home/alice'}
        assert vm.commands[0].startswith('getent passwd')

    @pytest.mark.asyncio
    async def test_unknown_user_is_none(self):
        proxy, _ = _proxy('linux', _ok('', returncode=2))
        assert await proxy.get_user_info('ghost') is None
        assert await _proxy('linux', _ok('', returncode=2))[0].user_exists('ghost') is False

    @pytest.mark.asyncio
    async def test_a_failing_lookup_is_an_error_not_absence(self):
        proxy, _ = _proxy('linux', _ok('', returncode=127, stderr='getent: not found'))
        with pytest.raises(RuntimeError):
            await proxy.get_user_info('alice')


class TestStatFailures:
    @pytest.mark.asyncio
    @pytest.mark.parametrize('method', ['get_file_permissions', 'get_file_timestamps'])
    async def test_missing_file_raises_file_not_found(self, method):
        proxy, _ = _proxy('linux', _ok('', returncode=1, stderr="stat: cannot statx '/x': No such file or directory"))
        with pytest.raises(FileNotFoundError):
            await getattr(proxy, method)('/x')

    @pytest.mark.asyncio
    @pytest.mark.parametrize('method', ['get_file_permissions', 'get_file_timestamps'])
    async def test_permission_denied_is_not_absence(self, method):
        proxy, _ = _proxy('linux', _ok('', returncode=1, stderr="stat: cannot statx '/x': Permission denied"))
        with pytest.raises(RuntimeError):
            await getattr(proxy, method)('/x')


class TestRegistryValueGet:
    @staticmethod
    def _answer(kind, json_value):
        return _ok(f'TYPE:{kind}\nVALUE:{json_value}\n')

    @pytest.mark.asyncio
    async def test_dword_is_an_unsigned_int_named_reg_dword(self):
        proxy, _ = _proxy('windows', self._answer('DWord', '-1'))
        assert await proxy.registry_value_get('HKCU/Software/x', 'n') == (True, 0xFFFFFFFF, 'REG_DWORD')

    @pytest.mark.asyncio
    async def test_qword_string_binary_multistring_types(self):
        for kind, data, expected, name in (
            ('QWord', '5000000000', 5000000000, 'REG_QWORD'),
            ('String', '"1"', '1', 'REG_SZ'),
            ('ExpandString', '"%PATH%"', '%PATH%', 'REG_EXPAND_SZ'),
            ('Binary', '[1,2,255]', b'\x01\x02\xff', 'REG_BINARY'),
            ('MultiString', '["a","b"]', ['a', 'b'], 'REG_MULTI_SZ'),
        ):
            proxy, _ = _proxy('windows', self._answer(kind, data))
            assert await proxy.registry_value_get('HKCU/Software/x', 'n') == (True, expected, name)

    @pytest.mark.asyncio
    async def test_expand_string_is_read_unexpanded(self):
        proxy, vm = _proxy('windows', self._answer('ExpandString', '"%PATH%"'))
        await proxy.registry_value_get('HKCU/Software/x', 'n')
        assert 'DoNotExpandEnvironmentNames' in vm.commands[0]

    @pytest.mark.asyncio
    async def test_missing_value(self):
        proxy, _ = _proxy('windows', _ok('NOTFOUND\n'))
        assert await proxy.registry_value_get('HKCU/Software/x', 'n') == (False, None, None)


class TestGuestClock:
    @pytest.mark.asyncio
    async def test_reads_the_guest_time_and_zone(self):
        proxy, _ = _proxy('linux')
        with (
            patch.object(proxy_module, 'read_guest_time', AsyncMock(return_value=1000.0)),
            patch.object(proxy_module, 'read_guest_utc_offset', AsyncMock(return_value='-05:30')),
        ):
            assert await proxy.get_guest_clock() == GuestClock(1000.0, -(5 * 3600 + 30 * 60))

    @pytest.mark.asyncio
    async def test_unanswered_clock_is_none(self):
        proxy, _ = _proxy('linux')
        with patch.object(proxy_module, 'read_guest_time', AsyncMock(side_effect=GuestClockError('no agent'))):
            assert await proxy.get_guest_clock() is None


# ============================================================================
# Executor: the verdicts
# ============================================================================


class FakeCommand:
    """A command proxy with scripted answers (an Exception value is raised)."""

    def __init__(self, **answers):
        self.answers = answers

    def __getattr__(self, name):
        if name.startswith('_') or name not in self.answers:
            raise AttributeError(name)

        async def answer(*args, **kwargs):
            value = self.answers[name]
            if isinstance(value, Exception):
                raise value
            return value

        return answer


def _executor(command=None, guest_file=None):
    return GuestToHostTestExecutor(
        guest_file=guest_file or SimpleNamespace(), guest_command=command, testfunction_collection={}
    )


def _test(**parameter):
    return SimpleNamespace(parameter=SimpleNamespace(**parameter))


class TestProcessRunning:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ('pids', 'minimum', 'status'),
        [
            (['5'], 1, StatusEnum.SUCCESS),
            (['5'], 2, StatusEnum.FAILED),  # min_instances is honoured
            (['5', '6', '7'], 2, StatusEnum.SUCCESS),
            ([], 1, StatusEnum.FAILED),
            ([], 0, StatusEnum.FAILED),  # no process always fails, as in agent mode
        ],
    )
    async def test_min_instances(self, pids, minimum, status):
        executor = _executor(FakeCommand(list_processes=pids))
        result = await executor._test_process_running(_test(process_name='someapp', min_instances=minimum))
        assert result.status == status

    @pytest.mark.asyncio
    async def test_default_is_one_instance(self):
        executor = _executor(FakeCommand(list_processes=['5']))
        assert (await executor._test_process_running(_test(process_name='x'))).status == StatusEnum.SUCCESS

    @pytest.mark.asyncio
    async def test_guest_failure_is_an_error(self):
        executor = _executor(FakeCommand(list_processes=RuntimeError('boom')))
        result = await executor._test_process_running(_test(process_name='x'))
        assert result.status == StatusEnum.ERROR


class TestUserExists:
    @staticmethod
    async def _run(info, **parameter):
        executor = _executor(FakeCommand(get_user_info=info))
        return await executor._test_user_exists(_test(username='alice', **parameter))

    @pytest.mark.asyncio
    async def test_name_only(self):
        assert (await self._run({'uid': 1001, 'home': '/home/alice'})).status == StatusEnum.SUCCESS
        assert (await self._run(None)).status == StatusEnum.FAILED

    @pytest.mark.asyncio
    async def test_uid_is_checked(self):
        info = {'uid': 1001, 'home': '/home/alice'}
        assert (await self._run(info, uid=1001)).status == StatusEnum.SUCCESS
        assert (await self._run(info, uid=1002)).status == StatusEnum.FAILED

    @pytest.mark.asyncio
    async def test_home_dir_is_checked_exactly(self):
        info = {'uid': 1001, 'home': '/home/alice'}
        assert (await self._run(info, home_dir='/home/alice')).status == StatusEnum.SUCCESS
        assert (await self._run(info, home_dir='/home/alice/')).status == StatusEnum.FAILED
        assert (await self._run(info, home_dir='/home/bob')).status == StatusEnum.FAILED

    @pytest.mark.asyncio
    async def test_lookup_failure_is_an_error(self):
        executor = _executor(FakeCommand(get_user_info=RuntimeError('getent failed')))
        assert (await executor._test_user_exists(_test(username='alice'))).status == StatusEnum.ERROR


class TestRegistryValueMatches:
    @staticmethod
    async def _run(value, reg_type, **parameter):
        executor = _executor(FakeCommand(registry_value_get=(True, value, reg_type)))
        base = {'key_path': 'HKCU/Software/x', 'value_name': 'n', 'expected_value': None}
        return await executor._test_registry_value_matches(_test(**{**base, **parameter}))

    @pytest.mark.asyncio
    async def test_dword_compares_as_int_like_agent_mode(self):
        assert (await self._run(1, 'REG_DWORD', expected_value=1)).status == StatusEnum.SUCCESS
        # winreg gives an int and Python's 1 == '1' is False: so does host mode
        assert (await self._run(1, 'REG_DWORD', expected_value='1')).status == StatusEnum.FAILED

    @pytest.mark.asyncio
    async def test_string_compares_as_text(self):
        assert (await self._run('1', 'REG_SZ', expected_value='1')).status == StatusEnum.SUCCESS
        assert (await self._run('1', 'REG_SZ', expected_value=1)).status == StatusEnum.FAILED

    @pytest.mark.asyncio
    async def test_binary_compares_as_bytes_and_multi_sz_never_matches(self):
        assert (await self._run(b'\x01', 'REG_BINARY', expected_value=b'\x01')).status == StatusEnum.SUCCESS
        assert (await self._run(['a'], 'REG_MULTI_SZ', expected_value='a')).status == StatusEnum.FAILED

    @pytest.mark.asyncio
    @pytest.mark.parametrize('value_type', ['REG_DWORD', 'reg_dword', 'REG_DWORD_LITTLE_ENDIAN'])
    async def test_canonical_and_legacy_dword_names_are_accepted(self, value_type):
        result = await self._run(1, 'REG_DWORD', expected_value=1, value_type=value_type)
        assert result.status == StatusEnum.SUCCESS

    @pytest.mark.asyncio
    async def test_qword_names(self):
        for value_type in ('REG_QWORD', 'UNKNOWN_TYPE_11'):
            result = await self._run(2**40, 'REG_QWORD', expected_value=2**40, value_type=value_type)
            assert result.status == StatusEnum.SUCCESS

    @pytest.mark.asyncio
    async def test_type_mismatch_reports_canonical_names(self):
        result = await self._run(1, 'REG_DWORD', expected_value=1, value_type='REG_SZ')
        assert result.status == StatusEnum.FAILED
        assert result.details == ['registry value type mismatch. Expected: REG_SZ, Got: REG_DWORD']

    @pytest.mark.asyncio
    async def test_value_detail_names_the_canonical_type(self):
        result = await self._run(1, 'REG_DWORD', expected_value=1)
        assert result.details == ['registry value matches: 1 (REG_DWORD)']

    @pytest.mark.asyncio
    async def test_missing_value_fails(self):
        executor = _executor(FakeCommand(registry_value_get=(False, None, None)))
        result = await executor._test_registry_value_matches(_test(key_path='HKCU/x', value_name='n', expected_value=1))
        assert result.status == StatusEnum.FAILED


class _Files:
    """A file proxy that resolves globs from a table."""

    def __init__(self, globs=None, error=None):
        self.globs = globs or {}
        self.error = error

    async def resolve_guest_glob(self, pattern):
        if self.error:
            raise self.error
        return self.globs.get(pattern, [])


class TestFilePermissions:
    @staticmethod
    async def _run(command, dst='/home/u/f', files=None, **parameter):
        executor = _executor(command, files)
        return await executor._test_file_permissions(
            't', _test(dst=dst, **{'expected_permissions': '644', **parameter})
        )

    @pytest.mark.asyncio
    async def test_missing_file_is_an_error_not_a_failure(self):
        result = await self._run(FakeCommand(get_file_permissions=FileNotFoundError('gone')))
        assert result.status == StatusEnum.ERROR

    @pytest.mark.asyncio
    async def test_unreadable_file_is_an_error(self):
        result = await self._run(FakeCommand(get_file_permissions=RuntimeError('denied')))
        assert result.status == StatusEnum.ERROR

    @pytest.mark.asyncio
    async def test_mismatch_is_a_failure_and_match_a_success(self):
        command = FakeCommand(get_file_permissions={'permissions': '600', 'owner': 'u', 'group': 'g'})
        assert (await self._run(command)).status == StatusEnum.FAILED
        assert (await self._run(command, expected_permissions='600', check_owner='u')).status == StatusEnum.SUCCESS
        assert (await self._run(command, expected_permissions='rw-------', check_group='x')).status == StatusEnum.FAILED

    @pytest.mark.asyncio
    async def test_invalid_expected_permissions_is_an_error(self):
        command = FakeCommand(get_file_permissions={'permissions': '600'})
        assert (await self._run(command, expected_permissions='')).status == StatusEnum.ERROR
        assert (await self._run(command, expected_permissions='8')).status == StatusEnum.ERROR

    @pytest.mark.asyncio
    async def test_glob_resolves_to_the_one_match(self):
        seen = []

        class Command:
            async def get_file_permissions(self, path):
                seen.append(path)
                return {'permissions': '644'}

        files = _Files({'/home/u/*.txt': ['/home/u/a.txt']})
        result = await self._run(Command(), dst='/home/u/*.txt', files=files)
        assert result.status == StatusEnum.SUCCESS and seen == ['/home/u/a.txt']

    @pytest.mark.asyncio
    async def test_glob_must_match_exactly_one(self):
        command = FakeCommand(get_file_permissions={'permissions': '644'})
        for matches in ([], ['/a/1', '/a/2']):
            result = await self._run(command, dst='/a/*', files=_Files({'/a/*': matches}))
            assert result.status == StatusEnum.ERROR

    @pytest.mark.asyncio
    async def test_glob_listing_failure_is_an_error(self):
        command = FakeCommand(get_file_permissions={'permissions': '644'})
        result = await self._run(command, dst='/a/*', files=_Files(error=RuntimeError('QGA timeout')))
        assert result.status == StatusEnum.ERROR

    @pytest.mark.asyncio
    async def test_archive_member_is_refused_not_read_as_a_missing_path(self):
        command = FakeCommand(get_file_permissions=FileNotFoundError('would be wrong'))
        result = await self._run(command, dst='/home/u/b.tar.gz!/etc/x')
        assert result.status == StatusEnum.ERROR and 'archive' in result.details[0]


class TestFileTimestamps:
    GUEST_NOW = 1_800_000_000.0

    @staticmethod
    async def _run(command, dst='/home/u/f', files=None, **parameter):
        executor = _executor(command, files)
        return await executor._test_file_timestamps('t', _test(dst=dst, **parameter))

    @classmethod
    def _command(cls, mtime, clock):
        return FakeCommand(get_file_timestamps={'mtime': mtime, 'atime': mtime, 'ctime': mtime}, get_guest_clock=clock)

    @pytest.mark.asyncio
    async def test_missing_file_is_an_error_not_a_failure(self):
        result = await self._run(FakeCommand(get_file_timestamps=FileNotFoundError('gone')), comparison_type='before')
        assert result.status == StatusEnum.ERROR

    @pytest.mark.asyncio
    async def test_within_last_uses_the_guest_clock_not_the_host_clock(self):
        # the file is 60 s old on the guest, whose clock is years away from the host's
        command = self._command(self.GUEST_NOW - 60, GuestClock(self.GUEST_NOW, 0))
        ok = await self._run(command, comparison_type='within_last', within_duration='5m')
        late = await self._run(command, comparison_type='within_last', within_duration='30s')
        assert ok.status == StatusEnum.SUCCESS
        assert late.status == StatusEnum.FAILED

    @pytest.mark.asyncio
    async def test_naive_dates_are_read_in_the_guest_time_zone(self):
        moment = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone(timedelta(hours=9)))
        command = self._command(moment.timestamp(), GuestClock(self.GUEST_NOW, 9 * 3600))
        result = await self._run(command, comparison_type='equals', expected_time='2026-01-15 12:00:00')
        assert result.status == StatusEnum.SUCCESS
        # the same wall-clock text in another zone is another moment
        other = self._command(moment.timestamp(), GuestClock(self.GUEST_NOW, 0))
        result = await self._run(other, comparison_type='equals', expected_time='2026-01-15 12:00:00')
        assert result.status == StatusEnum.FAILED

    @pytest.mark.asyncio
    async def test_epoch_values_need_no_clock(self):
        command = self._command(100.0, None)
        command.get_guest_clock = AsyncMock(return_value=None)
        result = await self._run(command, comparison_type='between', start_time=50, end_time=150)
        assert result.status == StatusEnum.SUCCESS
        command.get_guest_clock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unavailable_guest_clock_falls_back_and_says_so(self):
        command = self._command(100.0, None)
        result = await self._run(command, comparison_type='within_last', within_duration='1h')
        assert result.status == StatusEnum.FAILED
        assert any('guest clock unavailable' in d for d in result.details)

    @pytest.mark.asyncio
    async def test_glob_resolves_to_the_one_match(self):
        seen = []

        class Command:
            async def get_file_timestamps(self, path):
                seen.append(path)
                return {'mtime': 100.0}

        files = _Files({'/home/u/*.odt': ['/home/u/r.odt']})
        result = await self._run(Command(), dst='/home/u/*.odt', files=files, comparison_type='after', expected_time=50)
        assert result.status == StatusEnum.SUCCESS and seen == ['/home/u/r.odt']

    @pytest.mark.asyncio
    async def test_glob_with_two_matches_is_an_error(self):
        command = FakeCommand(get_file_timestamps={'mtime': 100.0})
        files = _Files({'/a/*': ['/a/1', '/a/2']})
        result = await self._run(command, dst='/a/*', files=files, comparison_type='after', expected_time=50)
        assert result.status == StatusEnum.ERROR

    @pytest.mark.asyncio
    async def test_archive_member_is_refused(self):
        command = FakeCommand(get_file_timestamps={'mtime': 100.0})
        result = await self._run(command, dst='/a/b.zip!/x', comparison_type='after', expected_time=50)
        assert result.status == StatusEnum.ERROR

    @pytest.mark.asyncio
    async def test_unparseable_time_is_an_error(self):
        command = FakeCommand(get_file_timestamps={'mtime': 100.0})
        result = await self._run(command, comparison_type='after', expected_time='not a time')
        assert result.status == StatusEnum.ERROR

    @pytest.mark.asyncio
    async def test_missing_timestamp_type_is_an_error(self):
        command = FakeCommand(get_file_timestamps={'mtime': 100.0})
        result = await self._run(command, timestamp_type='bogus', comparison_type='after', expected_time=50)
        assert result.status == StatusEnum.ERROR


class TestGuestOsGuard:
    """linux.* on a Windows guest (and windows.* elsewhere) is an ERROR, as the agent reports it."""

    @staticmethod
    def _command(is_windows, **answers):
        command = FakeCommand(**answers)
        command.is_windows = is_windows
        return command

    @pytest.mark.asyncio
    @pytest.mark.parametrize('function', ['linux.process_running', 'linux.user_exists', 'linux.system_service_status'])
    async def test_linux_probe_on_windows_is_an_error(self, function):
        executor = _executor(self._command(True, list_processes=['5'], get_user_info={}))
        result = await executor._execute_qga_probe_test('t', function, _test(process_name='x', username='u'))
        assert result.status == StatusEnum.ERROR
        assert 'only runs on Linux' in result.details[0]

    @pytest.mark.asyncio
    async def test_windows_probe_on_linux_is_an_error(self):
        executor = _executor(self._command(False))
        result = await executor._execute_qga_probe_test('t', 'windows.registry_key_exists', _test(key_path='HKCU\\X'))
        assert result.status == StatusEnum.ERROR

    @pytest.mark.asyncio
    async def test_linux_probe_on_linux_runs(self):
        executor = _executor(self._command(False, list_processes=['5']))
        result = await executor._execute_qga_probe_test('t', 'linux.process_running', _test(process_name='x'))
        assert result.status == StatusEnum.SUCCESS

    @pytest.mark.asyncio
    async def test_standard_probe_runs_on_windows(self):
        executor = _executor(self._command(True, get_file_permissions=FileNotFoundError('gone')))
        result = await executor._execute_qga_probe_test(
            't', 'standard.file_permissions', _test(dst='C:\\x.txt', expected_permissions='644')
        )
        assert 'only runs' not in ' '.join(result.details)
