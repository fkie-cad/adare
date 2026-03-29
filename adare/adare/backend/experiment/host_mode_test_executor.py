"""
Host-Mode Test Executor for ADARE.

Executes tests on the host by pulling files from the guest VM via QGA
and running testfunctions locally. This eliminates the need for the
in-guest adarevm agent for test execution.

Strategy:
- File-based tests: Pull target files via QGA, rewrite dst param, run test() locally
- QGA probe tests: Run probe commands via QGA guest-exec, create TestResult on host
- Visual tests: Delegate to existing HostTestExecutor (already host-side)
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from adarelib.testset.basictest import BasicTest, HostModeCategory
from adarelib.event.event import TestResult
from adare.backend.experiment.host_services.guest_file_proxy import GuestFileProxy
from adare.backend.experiment.host_services.guest_command_proxy import GuestCommandProxy

log = logging.getLogger(__name__)


class HostModeTestExecutor:
    """
    Executes tests on the host machine using QGA for guest file/command access.

    This executor replaces the in-guest adarevm agent for test execution,
    pulling files to the host and running testfunctions locally.
    """

    def __init__(
        self,
        guest_file: GuestFileProxy,
        guest_command: GuestCommandProxy,
        testfunction_collection: dict,
    ):
        """
        Initialize host-mode test executor.

        Args:
            guest_file: GuestFileProxy for file operations
            guest_command: GuestCommandProxy for command execution
            testfunction_collection: Pre-loaded testfunction collection from import_basictest_subclasses()
        """
        self.guest_file = guest_file
        self.guest_command = guest_command
        self.testfunction_collection = testfunction_collection

    @staticmethod
    def validate_playbook_tests(
        playbook_tests: list,
        testfunction_collection: dict,
    ) -> tuple[bool, list[str]]:
        """Check all playbook tests for host-mode compatibility.

        Called before execution starts. Returns (ok, issues).
        - ok=True: all tests can run in host mode
        - ok=False: some tests cannot run, issues lists them

        Args:
            playbook_tests: List of Test objects (with .name, .function attributes)
            testfunction_collection: Loaded testfunction collection dict

        Classification uses HostModeCategory ClassVar on each test class:
        - FILE_BASED / FILE_CONTENT: pull file + rewrite dst + run test() locally
        - QGA_PROBE: run via QGA guest-exec, parse result on host
        - HOST_NATIVE: already host-side (e.g., visual tests)
        - AGENT_ONLY: not supported in host mode
        """
        issues = []

        for test_def in playbook_tests:
            func_name_full = getattr(test_def, 'function', '')
            # Extract short name (without collection prefix)
            if '.' in func_name_full:
                collection, func_name = func_name_full.split('.', 1)
            else:
                func_name = func_name_full
                collection = ''

            # Look up test class in testfunction_collection
            test_cls = None
            for coll_tests in testfunction_collection.values():
                if isinstance(coll_tests, dict):
                    test_cls = coll_tests.get(func_name)
                    if test_cls:
                        break

            if test_cls:
                category = getattr(test_cls, 'host_mode_category', HostModeCategory.AGENT_ONLY)
                if category == HostModeCategory.AGENT_ONLY:
                    test_name = getattr(test_def, 'name', '<unnamed>')
                    issues.append(
                        f"Test '{test_name}' uses function '{func_name_full}' which is not supported "
                        f"in host test mode (category: agent_only). Use --test-mode agent instead."
                    )
            else:
                # Unknown test class — report as unsupported
                test_name = getattr(test_def, 'name', '<unnamed>')
                issues.append(
                    f"Test '{test_name}' uses function '{func_name_full}' which is not supported "
                    f"in host test mode (unknown test type). Use --test-mode agent instead."
                )

        return (len(issues) == 0, issues)

    def _get_test_category(self, test_function: str, test_instance: BasicTest) -> HostModeCategory:
        """Determine the test category from the test instance's ClassVar.

        Args:
            test_function: Testfunction name (e.g. 'standard.file_exists', 'linux.process_running')
            test_instance: Structured test instance (BasicTest subclass)

        Returns:
            HostModeCategory enum value from the test class
        """
        return getattr(type(test_instance), 'host_mode_category', HostModeCategory.AGENT_ONLY)

    async def execute_test(
        self,
        test_name: str,
        test_function: str,
        test_instance: BasicTest,
    ) -> TestResult:
        """Execute a test in host mode.

        Args:
            test_name: Name of the test from playbook
            test_function: Testfunction identifier (e.g. 'standard.file_exists')
            test_instance: Structured test instance (BasicTest subclass)

        Returns:
            TestResult from test execution
        """
        category = self._get_test_category(test_function, test_instance)
        log.info(f"HostModeTestExecutor: executing '{test_name}' (function={test_function}, category={category.value})")

        try:
            if category == HostModeCategory.QGA_PROBE:
                return await self._execute_qga_probe_test(test_name, test_function, test_instance)
            elif category in (HostModeCategory.FILE_BASED, HostModeCategory.FILE_CONTENT):
                return await self._execute_file_based_test(test_name, test_function, test_instance)
            elif category == HostModeCategory.HOST_NATIVE:
                # Host-native tests (e.g., visual) already run on host
                # This shouldn't normally reach here (visual tests have execute_on_host=True)
                return TestResult.error([f"Host-native test '{test_name}' should use existing host test executor"])
            elif category == HostModeCategory.AGENT_ONLY:
                return TestResult.error([f"Test '{test_function}' requires in-guest agent (category: agent_only)"])
            else:
                # Fallback: try file-based approach if parameter has dst
                if hasattr(test_instance, 'parameter') and hasattr(test_instance.parameter, 'dst'):
                    return await self._execute_file_based_test(test_name, test_function, test_instance)
                else:
                    return TestResult.error([f"Unknown test category for '{test_function}' in host mode"])
        except Exception as e:
            log.error(f"HostModeTestExecutor: test '{test_name}' failed: {e}", exc_info=True)
            return TestResult.execution_error(e, f"Host-mode test execution failed for '{test_name}'")

    async def _execute_file_based_test(
        self,
        test_name: str,
        test_function: str,
        test_instance: BasicTest,
    ) -> TestResult:
        """Execute a file-based test by pulling files and rewriting dst.

        Strategy:
        1. Read the original guest path from parameter.dst
        2. Handle glob patterns by resolving on guest first
        3. Pull the file(s) from guest to local temp dir
        4. Rewrite parameter.dst to local path
        5. Run test() locally
        """
        if not hasattr(test_instance, 'parameter') or not hasattr(test_instance.parameter, 'dst'):
            return TestResult.error([f"Test '{test_name}' has no parameter.dst — cannot run in host mode"])

        original_dst = test_instance.parameter.dst
        log.debug(f"HostModeTestExecutor: original dst='{original_dst}'")

        # Check for glob patterns
        has_glob = any(c in original_dst for c in ['*', '?', '[', ']'])

        if has_glob:
            # Resolve glob on guest side, then pull matching files
            matching_paths = await self.guest_file.resolve_guest_glob(original_dst)
            if not matching_paths:
                # No matches — let the test handle it (will get empty glob results)
                local_dst = str(self.guest_file._guest_path_to_local(original_dst))
                object.__setattr__(test_instance.parameter, 'dst', local_dst)
                result = await self._run_test(test_instance)
                object.__setattr__(test_instance.parameter, 'dst', original_dst)
                return result

            # Pull each matching file
            for guest_path in matching_paths:
                try:
                    await self.guest_file.pull_file(guest_path)
                except RuntimeError as e:
                    log.warning(f"HostModeTestExecutor: failed to pull {guest_path}: {e}")

            # Rewrite dst to local glob pattern
            local_dst = str(self.guest_file._guest_path_to_local(original_dst))
        else:
            # Simple path — pull directly
            try:
                local_path = await self.guest_file.pull_file(original_dst)
                local_dst = str(local_path)
            except (RuntimeError, FileNotFoundError) as e:
                # For existence tests, this is expected if file doesn't exist
                func_name = test_function.split('.')[-1] if '.' in test_function else test_function
                if func_name in ('file_does_not_exist', 'dir_does_not_exist'):
                    # File not found on guest = test should pass (file doesn't exist)
                    return TestResult.success([f'{original_dst} does not exist on guest'])
                elif func_name in ('file_exists', 'dir_exists'):
                    return TestResult.failed([f'{original_dst} does not exist on guest: {e}'])
                else:
                    log.warning(f"HostModeTestExecutor: could not pull {original_dst}: {e}")
                    local_dst = str(self.guest_file._guest_path_to_local(original_dst))

        # Rewrite dst and run test
        object.__setattr__(test_instance.parameter, 'dst', local_dst)
        try:
            result = await self._run_test(test_instance)
        finally:
            # Restore original dst for correct reporting
            object.__setattr__(test_instance.parameter, 'dst', original_dst)

        return result

    async def _execute_qga_probe_test(
        self,
        test_name: str,
        test_function: str,
        test_instance: BasicTest,
    ) -> TestResult:
        """Execute a non-portable test via QGA guest-exec.

        Instead of running OS-specific code locally (which would give wrong
        results for the guest), we execute probe commands on the guest via
        QGA and interpret the results on the host.
        """
        func_name = test_function.split('.')[-1] if '.' in test_function else test_function

        if func_name == 'process_running':
            return await self._test_process_running(test_instance)
        elif func_name == 'system_service_status':
            return await self._test_service_status(test_instance)
        elif func_name == 'user_exists':
            return await self._test_user_exists(test_instance)
        elif func_name == 'log_entry_exists':
            return await self._test_log_entry_exists(test_instance)
        elif func_name == 'registry_key_exists':
            return await self._test_registry_key_exists(test_instance)
        elif func_name == 'registry_value_matches':
            return await self._test_registry_value_matches(test_instance)
        elif func_name == 'file_permissions':
            return await self._test_file_permissions(test_instance)
        elif func_name == 'file_timestamps':
            return await self._test_file_timestamps(test_instance)
        else:
            return TestResult.error([f"Unknown QGA probe test: {func_name}"])

    async def _test_process_running(self, test_instance: BasicTest) -> TestResult:
        """Check if process is running via QGA."""
        process_name = test_instance.parameter.process_name
        if hasattr(test_instance, 'has_placeholders') and test_instance.has_placeholders(process_name):
            process_name = test_instance.resolve_variables(process_name)

        is_running = await self.guest_command.is_process_running(process_name)

        if is_running:
            return TestResult.success([f'process {process_name} is running'])
        else:
            return TestResult.failed([f'process {process_name} is not running'])

    async def _test_service_status(self, test_instance: BasicTest) -> TestResult:
        """Check service status via QGA."""
        service_name = test_instance.parameter.service_name
        expected_status = test_instance.parameter.expected_status

        if hasattr(test_instance, 'has_placeholders'):
            if test_instance.has_placeholders(service_name):
                service_name = test_instance.resolve_variables(service_name)
            if test_instance.has_placeholders(expected_status):
                expected_status = test_instance.resolve_variables(expected_status)

        actual_status = await self.guest_command.get_service_status(service_name)

        if actual_status == expected_status:
            return TestResult.success([f'service {service_name} is {actual_status}'])
        else:
            return TestResult.failed([
                f'service {service_name} status mismatch. Expected: {expected_status}, Got: {actual_status}'
            ])

    async def _test_user_exists(self, test_instance: BasicTest) -> TestResult:
        """Check if user exists via QGA."""
        username = test_instance.parameter.username
        if hasattr(test_instance, 'has_placeholders') and test_instance.has_placeholders(username):
            username = test_instance.resolve_variables(username)

        exists = await self.guest_command.user_exists(username)

        if exists:
            return TestResult.success([f'user {username} exists'])
        else:
            return TestResult.failed([f'user {username} does not exist'])

    async def _test_log_entry_exists(self, test_instance: BasicTest) -> TestResult:
        """Search for log entries matching a pattern via QGA."""
        log_file = test_instance.parameter.log_file
        pattern = test_instance.parameter.pattern
        max_lines = getattr(test_instance.parameter, 'max_lines', 1000)

        if hasattr(test_instance, 'has_placeholders'):
            if test_instance.has_placeholders(log_file):
                log_file = test_instance.resolve_variables(log_file)
            if test_instance.has_placeholders(pattern):
                pattern = test_instance.resolve_variables(pattern)

        found, matches = await self.guest_command.search_log_file(log_file, pattern, max_lines)

        if found:
            return TestResult.success([f'found {len(matches)} log entries matching pattern in {log_file}'])
        else:
            return TestResult.failed([f'no log entries matching pattern found in {log_file}'])

    async def _test_registry_key_exists(self, test_instance: BasicTest) -> TestResult:
        """Check if a Windows registry key exists via QGA PowerShell."""
        key_path = test_instance.parameter.key_path
        if hasattr(test_instance, 'has_placeholders') and test_instance.has_placeholders(key_path):
            key_path = test_instance.resolve_variables(key_path)

        exists = await self.guest_command.registry_key_exists(key_path)

        if exists:
            return TestResult.success([f'registry key exists: {key_path}'])
        else:
            return TestResult.failed([f'registry key does not exist: {key_path}'])

    async def _test_registry_value_matches(self, test_instance: BasicTest) -> TestResult:
        """Check if a Windows registry value matches expected value via QGA PowerShell."""
        key_path = test_instance.parameter.key_path
        value_name = test_instance.parameter.value_name
        expected_value = test_instance.parameter.expected_value
        expected_type = getattr(test_instance.parameter, 'value_type', None)

        if hasattr(test_instance, 'has_placeholders'):
            if test_instance.has_placeholders(key_path):
                key_path = test_instance.resolve_variables(key_path)
            if test_instance.has_placeholders(value_name):
                value_name = test_instance.resolve_variables(value_name)
            if isinstance(expected_value, str) and test_instance.has_placeholders(expected_value):
                expected_value = test_instance.resolve_variables(expected_value)

        found, actual_value, actual_type = await self.guest_command.registry_value_get(key_path, value_name)

        if not found:
            return TestResult.failed([f'registry key or value does not exist: {key_path}\\{value_name}'])

        # Type check if requested
        if expected_type:
            expected_type_upper = expected_type.upper()
            # PowerShell type names: String, DWord, Binary, etc. Map to REG_ names
            ps_to_reg = {
                'STRING': 'REG_SZ', 'EXPANDSTRING': 'REG_EXPAND_SZ',
                'BINARY': 'REG_BINARY', 'DWORD': 'REG_DWORD',
                'MULTISTRING': 'REG_MULTI_SZ', 'QWORD': 'REG_QWORD',
            }
            actual_type_mapped = ps_to_reg.get(actual_type.upper(), actual_type.upper()) if actual_type else 'UNKNOWN'
            if expected_type_upper != actual_type_mapped:
                return TestResult.failed([
                    f'registry value type mismatch. Expected: {expected_type_upper}, Got: {actual_type_mapped}'
                ])

        # Value comparison (compare as strings since QGA returns strings)
        if str(actual_value) == str(expected_value):
            return TestResult.success([f'registry value matches: {actual_value}'])
        else:
            return TestResult.failed([
                f'registry value mismatch. Expected: {expected_value}, Got: {actual_value}'
            ])

    async def _test_file_permissions(self, test_instance: BasicTest) -> TestResult:
        """Check file permissions, owner, and group via QGA stat."""
        dst = test_instance.parameter.dst
        expected_permissions = test_instance.parameter.expected_permissions
        check_owner = getattr(test_instance.parameter, 'check_owner', None)
        check_group = getattr(test_instance.parameter, 'check_group', None)

        if hasattr(test_instance, 'has_placeholders') and test_instance.has_placeholders(dst):
            dst = test_instance.resolve_variables(dst)

        perm_info = await self.guest_command.get_file_permissions(dst)

        if not perm_info:
            return TestResult.failed([f'could not get permissions for {dst} (file may not exist)'])

        results = []
        success = True

        # Check permissions (octal comparison)
        actual_perms = perm_info.get('permissions', '')
        if actual_perms:
            # Normalize: both as 3-digit octal strings
            try:
                actual_octal = actual_perms.lstrip('0') or '0'
                if expected_permissions.isdigit():
                    expected_octal = expected_permissions.lstrip('0') or '0'
                    if actual_octal == expected_octal:
                        results.append(f'permissions match: {actual_perms}')
                    else:
                        results.append(f'permission mismatch. Expected: {expected_permissions}, Got: {actual_perms}')
                        success = False
                else:
                    # Symbolic notation — convert actual octal to int for comparison
                    actual_int = int(actual_perms, 8)
                    expected_int = self._parse_symbolic_permissions(expected_permissions)
                    if actual_int == expected_int:
                        results.append(f'permissions match: {actual_perms}')
                    else:
                        results.append(f'permission mismatch. Expected: {expected_permissions}, Got: {actual_perms}')
                        success = False
            except ValueError as e:
                results.append(f'permission comparison error: {e}')
                success = False
        else:
            results.append(f'could not determine permissions for {dst}')
            success = False

        # Check owner
        if check_owner:
            actual_owner = perm_info.get('owner', '')
            if actual_owner == check_owner:
                results.append(f'owner matches: {actual_owner}')
            else:
                results.append(f'owner mismatch. Expected: {check_owner}, Got: {actual_owner}')
                success = False

        # Check group
        if check_group:
            actual_group = perm_info.get('group', '')
            if actual_group == check_group:
                results.append(f'group matches: {actual_group}')
            else:
                results.append(f'group mismatch. Expected: {check_group}, Got: {actual_group}')
                success = False

        if success:
            return TestResult.success(results)
        else:
            return TestResult.failed(results)

    @staticmethod
    def _parse_symbolic_permissions(perm_str: str) -> int:
        """Parse symbolic permission string like 'rwxr-xr-x' to integer."""
        import stat
        if len(perm_str) != 9:
            raise ValueError(f"Invalid symbolic permission format: {perm_str}")
        perms = 0
        if perm_str[0] == 'r': perms |= stat.S_IRUSR
        if perm_str[1] == 'w': perms |= stat.S_IWUSR
        if perm_str[2] == 'x': perms |= stat.S_IXUSR
        if perm_str[3] == 'r': perms |= stat.S_IRGRP
        if perm_str[4] == 'w': perms |= stat.S_IWGRP
        if perm_str[5] == 'x': perms |= stat.S_IXGRP
        if perm_str[6] == 'r': perms |= stat.S_IROTH
        if perm_str[7] == 'w': perms |= stat.S_IWOTH
        if perm_str[8] == 'x': perms |= stat.S_IXOTH
        return perms

    async def _test_file_timestamps(self, test_instance: BasicTest) -> TestResult:
        """Check file timestamps via QGA stat."""
        dst = test_instance.parameter.dst
        timestamp_type = getattr(test_instance.parameter, 'timestamp_type', 'modified')
        comparison_type = getattr(test_instance.parameter, 'comparison_type', 'equals')

        if hasattr(test_instance, 'has_placeholders') and test_instance.has_placeholders(dst):
            dst = test_instance.resolve_variables(dst)

        timestamps = await self.guest_command.get_file_timestamps(dst)

        if not timestamps:
            return TestResult.failed([f'could not get timestamps for {dst} (file may not exist)'])

        # Map timestamp_type to stat key
        type_to_key = {'modified': 'mtime', 'accessed': 'atime', 'created': 'ctime'}
        stat_key = type_to_key.get(timestamp_type)
        if not stat_key or stat_key not in timestamps:
            return TestResult.error([f'timestamp type {timestamp_type} not available for {dst}'])

        actual_time = timestamps[stat_key]

        if comparison_type == 'equals':
            expected_time = self._parse_test_timestamp(
                test_instance.parameter.expected_time,
                getattr(test_instance.parameter, 'time_format', None)
            )
            tolerance = getattr(test_instance.parameter, 'tolerance_seconds', 0) or 0
            if abs(actual_time - expected_time) <= tolerance:
                return TestResult.success([
                    f'{timestamp_type} timestamp matches (±{tolerance}s): {datetime.fromtimestamp(actual_time)}'
                ])
            else:
                return TestResult.failed([
                    f'{timestamp_type} timestamp mismatch. '
                    f'Expected: {datetime.fromtimestamp(expected_time)}, Got: {datetime.fromtimestamp(actual_time)}'
                ])

        elif comparison_type == 'before':
            expected_time = self._parse_test_timestamp(
                test_instance.parameter.expected_time,
                getattr(test_instance.parameter, 'time_format', None)
            )
            if actual_time < expected_time:
                return TestResult.success([f'{timestamp_type} timestamp is before {datetime.fromtimestamp(expected_time)}'])
            else:
                return TestResult.failed([f'{timestamp_type} timestamp is not before {datetime.fromtimestamp(expected_time)}'])

        elif comparison_type == 'after':
            expected_time = self._parse_test_timestamp(
                test_instance.parameter.expected_time,
                getattr(test_instance.parameter, 'time_format', None)
            )
            if actual_time > expected_time:
                return TestResult.success([f'{timestamp_type} timestamp is after {datetime.fromtimestamp(expected_time)}'])
            else:
                return TestResult.failed([f'{timestamp_type} timestamp is not after {datetime.fromtimestamp(expected_time)}'])

        elif comparison_type == 'between':
            start_time = self._parse_test_timestamp(
                test_instance.parameter.start_time,
                getattr(test_instance.parameter, 'time_format', None)
            )
            end_time = self._parse_test_timestamp(
                test_instance.parameter.end_time,
                getattr(test_instance.parameter, 'time_format', None)
            )
            if start_time <= actual_time <= end_time:
                return TestResult.success([
                    f'{timestamp_type} timestamp is between '
                    f'{datetime.fromtimestamp(start_time)} and {datetime.fromtimestamp(end_time)}'
                ])
            else:
                return TestResult.failed([
                    f'{timestamp_type} timestamp is not between '
                    f'{datetime.fromtimestamp(start_time)} and {datetime.fromtimestamp(end_time)}'
                ])

        elif comparison_type == 'within_last':
            within_duration = test_instance.parameter.within_duration
            duration_seconds = self._parse_duration(within_duration)
            current_time = datetime.now().timestamp()
            threshold_time = current_time - duration_seconds
            if actual_time >= threshold_time:
                return TestResult.success([f'{timestamp_type} timestamp is within last {within_duration}'])
            else:
                return TestResult.failed([f'{timestamp_type} timestamp is not within last {within_duration}'])

        else:
            return TestResult.error([f'Unsupported comparison type: {comparison_type}'])

    @staticmethod
    def _parse_test_timestamp(timestamp, time_format=None) -> float:
        """Parse a timestamp value to Unix epoch seconds."""
        if isinstance(timestamp, (int, float)):
            return float(timestamp)

        timestamp = str(timestamp)
        try:
            return float(timestamp)
        except (ValueError, TypeError):
            pass

        if time_format:
            try:
                return datetime.strptime(timestamp, time_format).timestamp()
            except ValueError:
                pass

        common_formats = [
            '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%SZ',
            '%Y-%m-%d', '%m/%d/%Y %H:%M:%S', '%m/%d/%Y',
        ]
        for fmt in common_formats:
            try:
                return datetime.strptime(timestamp, fmt).timestamp()
            except ValueError:
                continue

        raise ValueError(f"Cannot parse timestamp: {timestamp}")

    @staticmethod
    def _parse_duration(duration_str: str) -> float:
        """Parse duration string like '1h', '30m', '2d' to seconds."""
        units = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}
        if not duration_str or duration_str[-1] not in units:
            raise ValueError(f"Invalid duration format: {duration_str}")
        try:
            value = int(duration_str[:-1])
            return value * units[duration_str[-1]]
        except ValueError:
            raise ValueError(f"Invalid duration format: {duration_str}")

    async def _run_test(self, test_instance) -> TestResult:
        """Run a test method, handling both sync and async test() methods."""
        test_method = test_instance.test
        if asyncio.iscoroutinefunction(test_method):
            return await test_method()
        else:
            # Run sync test in thread pool to avoid blocking the event loop
            return await asyncio.to_thread(test_method)

    def cleanup(self):
        """Clean up temp files."""
        self.guest_file.cleanup()
