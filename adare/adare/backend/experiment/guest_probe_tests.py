"""Host-mode evaluation of the QGA probe tests (``HostModeCategory.QGA_PROBE``).

A probe test cannot run on the host against a pulled copy (the answer is state of the
running guest: a process list, the user database, the registry, file metadata a pull
would overwrite). The executor asks the guest (or, for the hostside backend, the disk image)
through a command proxy and judges the answer here, with the semantics of the in-guest
versions in ``appdata/testfunctions`` (linux, windows, standard): same matching rule, same
FAILED (examined, does not match) versus ERROR (could not be examined) split.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Any

from adarelib.event.event import TestResult
from adarelib.testset.archive import has_archive_separator
from adarelib.testset.basictest import BasicTest
from adarelib.testset.content import parse_duration
from adarelib.testset.fileinfo import parse_permissions

log = logging.getLogger(__name__)

# Names the in-guest registry test also accepts for ``value_type``, and the canonical name each means.
_REGISTRY_TYPE_ALIASES = {
    'REG_DWORD_LITTLE_ENDIAN': 'REG_DWORD',
    'REG_QWORD_LITTLE_ENDIAN': 'REG_QWORD',
    'UNKNOWN_TYPE_11': 'REG_QWORD',
}

_TIMESTAMP_KEYS = {'modified': 'mtime', 'accessed': 'atime', 'created': 'ctime'}
_COMMON_TIME_FORMATS = (
    '%Y-%m-%d %H:%M:%S',
    '%Y-%m-%dT%H:%M:%S',
    '%Y-%m-%dT%H:%M:%SZ',
    '%Y-%m-%d',
    '%m/%d/%Y %H:%M:%S',
    '%m/%d/%Y',
)


def parse_time(value, time_format: str | None = None, tz: tzinfo | None = None) -> float:
    """Epoch seconds of ``value`` as the in-guest ``file_timestamps`` reads it.

    Numbers pass through; strings are tried with ``time_format`` first, then as a number, then
    the common formats. A string without a zone is wall-clock time of ``tz`` (the guest's zone;
    ``None``: this machine's).

    Raises:
        ValueError: ``value`` is not a time
    """
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value)

    def epoch(moment: datetime) -> float:
        if tz is not None and moment.tzinfo is None:
            moment = moment.replace(tzinfo=tz)
        return moment.timestamp()

    if time_format:
        try:
            return epoch(datetime.strptime(text, time_format))
        except ValueError:
            pass
    try:
        return float(text)
    except ValueError:
        pass
    for fmt in _COMMON_TIME_FORMATS:
        try:
            return epoch(datetime.strptime(text, fmt))
        except ValueError:
            continue
    raise ValueError(f'Cannot parse timestamp: {value}')


def _show(epoch: float, tz: tzinfo | None) -> datetime:
    return datetime.fromtimestamp(epoch, tz)


class QgaProbeTests:
    """The ``_test_*`` probe evaluations of :class:`GuestToHostTestExecutor` (a mixin).

    Expects ``self.guest_command`` (the command proxy) and ``self.guest_file`` (the file proxy).
    """

    guest_command: Any
    guest_file: Any

    @staticmethod
    def _pull_error(test_name: str, guest_path: str, error: Exception) -> TestResult:
        """ERROR result for a path that could not be read (the executor's implementation)."""
        raise NotImplementedError

    @staticmethod
    def _resolved(test_instance: BasicTest, text):
        """``text`` with ``{{ }}`` placeholders resolved."""
        if (
            isinstance(text, str)
            and hasattr(test_instance, 'has_placeholders')
            and test_instance.has_placeholders(text)
        ):
            return test_instance.resolve_variables(text)
        return text

    async def _test_process_running(self, test_instance: BasicTest) -> TestResult:
        """Count the processes matching ``process_name`` (``pgrep -f``: a regex on the full command line)."""
        process_name = self._resolved(test_instance, test_instance.parameter.process_name)
        min_instances = getattr(test_instance.parameter, 'min_instances', 1)
        try:
            pids = await self.guest_command.list_processes(process_name)
        except RuntimeError as e:
            return TestResult.execution_error(e, f'Failed to check process {process_name}')

        if not pids:
            return TestResult.failed([f'process {process_name} is not running'])
        if len(pids) >= min_instances:
            return TestResult.success(
                [f'process {process_name} running with {len(pids)} instances (PIDs: {", ".join(pids)})']
            )
        return TestResult.failed(
            [f'process {process_name} has {len(pids)} instances, expected at least {min_instances}']
        )

    async def _test_service_status(self, test_instance: BasicTest) -> TestResult:
        """Check service status via QGA."""
        service_name = self._resolved(test_instance, test_instance.parameter.service_name)
        expected_status = self._resolved(test_instance, test_instance.parameter.expected_status)

        actual_status = await self.guest_command.get_service_status(service_name)

        if actual_status == expected_status:
            return TestResult.success([f'service {service_name} is {actual_status}'])
        return TestResult.failed(
            [f'service {service_name} status mismatch. Expected: {expected_status}, Got: {actual_status}']
        )

    async def _test_user_exists(self, test_instance: BasicTest) -> TestResult:
        """The account exists and its ``uid`` / ``home_dir`` (when given) match."""
        username = self._resolved(test_instance, test_instance.parameter.username)
        expected_uid = getattr(test_instance.parameter, 'uid', None)
        expected_home = self._resolved(test_instance, getattr(test_instance.parameter, 'home_dir', None))

        try:
            info = await self.guest_command.get_user_info(username)
        except RuntimeError as e:
            return TestResult.execution_error(e, f'Failed to look up user {username}')
        if info is None:
            return TestResult.failed([f'user {username} does not exist'])

        for label, expected, key in (('UID', expected_uid, 'uid'), ('home directory', expected_home, 'home')):
            if expected is None:
                continue
            if key not in info:
                return TestResult.error([f'user {username}: the {label} cannot be read on this guest'])
            if info[key] != expected:
                return TestResult.failed([f'user {username} {label} mismatch. Expected: {expected}, Got: {info[key]}'])
        if 'uid' in info:
            return TestResult.success([f'user {username} exists (UID: {info["uid"]}, Home: {info["home"]})'])
        return TestResult.success([f'user {username} exists'])

    async def _test_registry_key_exists(self, test_instance: BasicTest) -> TestResult:
        """Check if a Windows registry key exists via QGA PowerShell."""
        key_path = self._resolved(test_instance, test_instance.parameter.key_path)

        exists = await self.guest_command.registry_key_exists(key_path)

        if exists:
            return TestResult.success([f'registry key exists: {key_path}'])
        return TestResult.failed([f'registry key does not exist: {key_path}'])

    async def _test_registry_value_matches(self, test_instance: BasicTest) -> TestResult:
        """The registry value equals ``expected_value``, typed as the in-guest test (``winreg``) types it.

        DWORD/QWORD data is an ``int``, String/ExpandString a ``str`` (not expanded), Binary
        ``bytes``; the types are reported as ``REG_SZ`` ... ``REG_DWORD``, ``REG_QWORD``.
        """
        parameter = test_instance.parameter
        key_path = self._resolved(test_instance, parameter.key_path)
        value_name = self._resolved(test_instance, parameter.value_name)
        expected_value = parameter.expected_value
        value_type = getattr(parameter, 'value_type', None)
        if isinstance(expected_value, str) and self._resolved(test_instance, expected_value) != expected_value:
            # a placeholder resolved at run time: all-digit results become int, as in the in-guest test
            expected_value = self._resolved(test_instance, expected_value)
            if isinstance(expected_value, str) and expected_value.isdigit():
                expected_value = int(expected_value)

        try:
            found, actual_value, actual_type = await self.guest_command.registry_value_get(key_path, value_name)
        except RuntimeError as e:
            return TestResult.execution_error(e, f'Failed to read registry value {key_path}\\{value_name}')
        if not found:
            return TestResult.failed([f'registry key or value does not exist: {key_path}\\{value_name}'])

        if value_type:
            expected_type = value_type.upper()
            expected_type = _REGISTRY_TYPE_ALIASES.get(expected_type, expected_type)
            if expected_type != actual_type:
                return TestResult.failed(
                    [f'registry value type mismatch. Expected: {expected_type}, Got: {actual_type}']
                )

        if actual_value == expected_value:
            return TestResult.success([f'registry value matches: {actual_value} ({actual_type})'])
        return TestResult.failed(
            [f'registry value mismatch. Expected: {expected_value}, Got: {actual_value} ({actual_type})']
        )

    async def _resolve_probe_path(self, test_name: str, dst: str) -> tuple[str, TestResult | None]:
        """The one guest path ``dst`` names, or a result that ends the test.

        Like the in-guest tests, a glob must match exactly one path. A path inside an archive
        has no file metadata of its own (the member's metadata is the archive's), so it is refused.
        """
        if has_archive_separator(dst):
            return dst, TestResult.error(
                [f'{dst}: a member of an archive has no file metadata of its own; name the archive file itself']
            )
        if not any(c in dst for c in ('*', '?', '[', ']')):
            return dst, None
        try:
            matches = await self.guest_file.resolve_guest_glob(dst)
        except RuntimeError as e:
            return dst, self._pull_error(test_name, dst, e)
        if len(matches) != 1:
            why = (
                'no files match the given path (glob) expression'
                if not matches
                else f'{len(matches)} files found that match given path (glob) expression'
            )
            return dst, TestResult.error(
                [f"file {dst} can't be used, because no unambiguous file could be identified (because {why})"]
            )
        return matches[0], None

    async def _test_file_permissions(self, test_name: str, test_instance: BasicTest) -> TestResult:
        """Mode bits (and owner / group) of the path, as the in-guest ``standard.file_permissions``."""
        parameter = test_instance.parameter
        dst, early = await self._resolve_probe_path(test_name, self._resolved(test_instance, parameter.dst))
        if early is not None:
            return early

        try:
            perm_info = await self.guest_command.get_file_permissions(dst)
        except FileNotFoundError:
            return TestResult.error([f'file {dst} does not exist'])
        except RuntimeError as e:
            return TestResult.execution_error(e, f'Cannot access file {dst}')
        try:
            expected_perms = parse_permissions(parameter.expected_permissions)
        except ValueError as e:
            return TestResult.execution_error(e, 'Permission parsing error')

        results = []
        success = True
        try:
            actual_perms = int(perm_info['permissions'], 8) & 0o777
        except (KeyError, ValueError):
            return TestResult.failed([f'could not determine permissions for {dst}'])
        if actual_perms == expected_perms:
            results.append(f'permissions match: {oct(actual_perms)[-3:]}')
        else:
            results.append(f'permission mismatch. Expected: {oct(expected_perms)[-3:]}, Got: {oct(actual_perms)[-3:]}')
            success = False

        for label, expected, key in (
            ('owner', getattr(parameter, 'check_owner', None), 'owner'),
            ('group', getattr(parameter, 'check_group', None), 'group'),
        ):
            if not expected:
                continue
            actual = perm_info.get(key)
            if actual == expected:
                results.append(f'{label} matches: {actual}')
            else:
                results.append(f'{label} mismatch. Expected: {expected}, Got: {actual}')
                success = False

        return TestResult.success(results) if success else TestResult.failed(results)

    async def _guest_clock_for(self, parameter, comparison_type: str) -> tuple[float, tzinfo | None, list[str]]:
        """``(now, guest zone, notes)`` for the time comparisons of a ``file_timestamps`` test.

        Only asked when the test needs it (``within_last``, or a date string to read in the guest's
        zone); otherwise this machine's clock stands in and nothing is noted. From the guest's own clock (QGA; the hostside backend answers with the host clock and
        the image's zone). When the guest does not answer, this machine's clock and zone, and
        a note says so.
        """
        wanted = ('expected_time', 'start_time', 'end_time')
        if comparison_type != 'within_last' and not any(isinstance(getattr(parameter, n, None), str) for n in wanted):
            return time.time(), None, []
        clock = None
        get_clock = getattr(self.guest_command, 'get_guest_clock', None)
        if get_clock is not None:
            clock = await get_clock()
        if clock is None:
            return time.time(), None, ['guest clock unavailable: used the host clock and time zone']
        tz = None
        if clock.utc_offset_seconds is not None:
            tz = timezone(timedelta(seconds=clock.utc_offset_seconds))
        return clock.now, tz, []

    async def _test_file_timestamps(self, test_name: str, test_instance: BasicTest) -> TestResult:
        """Chosen timestamp of the path vs ``comparison_type``, as the in-guest ``standard.file_timestamps``."""
        parameter = test_instance.parameter
        timestamp_type = getattr(parameter, 'timestamp_type', 'modified')
        comparison_type = getattr(parameter, 'comparison_type', 'equals')
        time_format = getattr(parameter, 'time_format', None)
        dst, early = await self._resolve_probe_path(test_name, self._resolved(test_instance, parameter.dst))
        if early is not None:
            return early

        try:
            timestamps = await self.guest_command.get_file_timestamps(dst)
        except FileNotFoundError:
            return TestResult.error([f'file {dst} does not exist'])
        except RuntimeError as e:
            return TestResult.execution_error(e, f'Cannot access file {dst}')
        stat_key = _TIMESTAMP_KEYS.get(timestamp_type)
        if not stat_key or stat_key not in timestamps:
            return TestResult.error([f'timestamp type {timestamp_type} not available for {dst}'])
        actual = timestamps[stat_key]

        now, tz, notes = await self._guest_clock_for(parameter, comparison_type)
        try:
            result = self._compare_time(parameter, timestamp_type, comparison_type, actual, time_format, now, tz)
        except ValueError as e:
            return TestResult.execution_error(e, 'Timestamp parsing/comparison error')
        result.details = [*result.details, *notes]
        return result

    @staticmethod
    def _compare_time(parameter, kind: str, comparison_type: str, actual: float, time_format, now: float, tz):
        """The verdict of one ``comparison_type`` (raises ``ValueError`` for an unparseable time)."""

        def read(name):
            return parse_time(getattr(parameter, name, None), time_format, tz)

        if comparison_type == 'equals':
            expected = read('expected_time')
            tolerance = getattr(parameter, 'tolerance_seconds', 0) or 0
            if abs(actual - expected) <= tolerance:
                return TestResult.success([f'{kind} timestamp matches (±{tolerance}s): {_show(actual, tz)}'])
            return TestResult.failed(
                [f'{kind} timestamp mismatch. Expected: {_show(expected, tz)}, Got: {_show(actual, tz)}']
            )
        if comparison_type == 'before':
            expected = read('expected_time')
            if actual < expected:
                return TestResult.success([f'{kind} timestamp is before {_show(expected, tz)}'])
            return TestResult.failed([f'{kind} timestamp is not before {_show(expected, tz)}'])
        if comparison_type == 'after':
            expected = read('expected_time')
            if actual > expected:
                return TestResult.success([f'{kind} timestamp is after {_show(expected, tz)}'])
            return TestResult.failed([f'{kind} timestamp is not after {_show(expected, tz)}'])
        if comparison_type == 'between':
            start, end = read('start_time'), read('end_time')
            bounds = f'{_show(start, tz)} and {_show(end, tz)}'
            if start <= actual <= end:
                return TestResult.success([f'{kind} timestamp is between {bounds}'])
            return TestResult.failed([f'{kind} timestamp is not between {bounds}'])
        if comparison_type == 'within_last':
            within = getattr(parameter, 'within_duration', None)
            if actual >= now - parse_duration(within):
                return TestResult.success([f'{kind} timestamp is within last {within}'])
            return TestResult.failed([f'{kind} timestamp is not within last {within}'])
        return TestResult.error([f'Unsupported comparison type: {comparison_type}'])
