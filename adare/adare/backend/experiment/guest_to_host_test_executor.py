"""
Guest-to-Host Test Executor for ADARE.

Runs inside the VM guest context and bridges test execution to the host
by pulling files from the guest VM via QGA and running testfunctions
locally. This eliminates the need for the in-guest adarevm agent for
test execution.

Strategy:
- File-based tests: Pull target files via QGA, rewrite dst param, run test() locally
- QGA probe tests: Run probe commands via QGA guest-exec, create TestResult on host
- Visual tests: Delegate to existing HostTestExecutor (already host-side)
"""

import asyncio
import glob
import logging
import os
import shutil
import tempfile
from pathlib import Path

from adare.backend.experiment.guest_probe_tests import QgaProbeTests
from adare.backend.experiment.host_services.guest_command_proxy import GuestCommandProxy
from adare.backend.experiment.host_services.guest_file_proxy import GuestFileProxy
from adarelib.event.event import TestResult
from adarelib.testset.archive import has_archive_separator, join_archive_path, split_archive_path
from adarelib.testset.basictest import BasicTest, HostModeCategory
from adarelib.testset.testfunction import get_testclass_from_testfunction

log = logging.getLogger(__name__)


def _replace_paths(detail, display: dict[str, str]):
    """``detail`` with local copies shown by their guest path (longest local path first)."""
    if not isinstance(detail, str):
        return detail
    for local in sorted(display, key=len, reverse=True):
        detail = detail.replace(local, display[local])
    return detail


class GuestToHostTestExecutor(QgaProbeTests):
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
            # By collection.name: several collections share function names (contains_key,
            # value_matches, value_count), so a lookup by short name could pick another one.
            test_cls = get_testclass_from_testfunction(func_name_full, testfunction_collection)

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
        log.info(
            f"GuestToHostTestExecutor: executing '{test_name}' (function={test_function}, category={category.value})"
        )

        try:
            if category == HostModeCategory.QGA_PROBE:
                return await self._execute_qga_probe_test(test_name, test_function, test_instance)
            if category in (HostModeCategory.FILE_BASED, HostModeCategory.FILE_CONTENT):
                return await self._execute_file_based_test(test_name, test_function, test_instance)
            if category == HostModeCategory.HOST_NATIVE:
                # Host-native tests (e.g., visual) already run on host
                # This shouldn't normally reach here (visual tests have execute_on_host=True)
                return TestResult.error([f"Host-native test '{test_name}' should use existing host test executor"])
            if category == HostModeCategory.AGENT_ONLY:
                return TestResult.error([f"Test '{test_function}' requires in-guest agent (category: agent_only)"])
            # Fallback: try file-based approach if parameter has dst
            if hasattr(test_instance, 'parameter') and hasattr(test_instance.parameter, 'dst'):
                return await self._execute_file_based_test(test_name, test_function, test_instance)
            return TestResult.error([f"Unknown test category for '{test_function}' in host mode"])
        except Exception as e:
            log.error(f"GuestToHostTestExecutor: test '{test_name}' failed: {e}", exc_info=True)
            return TestResult.execution_error(e, f"Host-mode test execution failed for '{test_name}'")

    async def _execute_file_based_test(
        self,
        test_name: str,
        test_function: str,
        test_instance: BasicTest,
    ) -> TestResult:
        """Pull the paths of the class's ``host_mode_path_params`` (e.g. ``other_dst``), then dst.

        Each path parameter that is set is pulled like dst (glob, archive member, sidecars)
        and rewritten to its local copy for the run; the guest value is restored afterwards.
        """
        names = getattr(type(test_instance), 'host_mode_path_params', ())
        parameter = getattr(test_instance, 'parameter', None)
        originals = {n: getattr(parameter, n) for n in names if getattr(parameter, n, None)}
        sidecars = getattr(type(test_instance), 'host_mode_sidecars', ())
        display: dict[str, str] = {}
        try:
            for name, guest_value in originals.items():
                local_value, shown, early = await self._pull_path_param(test_name, guest_value, sidecars)
                if early is not None:
                    return early
                display.update(shown)
                object.__setattr__(parameter, name, local_value)
            result = await self._execute_dst_test(test_name, test_function, test_instance)
        finally:
            for name, guest_value in originals.items():
                object.__setattr__(parameter, name, guest_value)
        dst = getattr(parameter, 'dst', None)
        if display and isinstance(dst, str) and not has_archive_separator(dst):
            # details that name both files (values_compare) show dst's local copy too
            display[str(self.guest_file._guest_path_to_local(dst))] = dst
        if display:
            result.details = [_replace_paths(d, display) for d in result.details]
        return result

    async def _pull_path_param(
        self, test_name: str, guest_value: str, sidecars: tuple[str, ...]
    ) -> tuple[str, dict[str, str], TestResult | None]:
        """Pull one path parameter like dst: ``(local value, {local: guest} for display, early result)``.

        A missing plain file is not an early result: the test sees the missing local path and
        reports it (ERROR for content tests), as for dst.
        """
        if has_archive_separator(guest_value):
            archive, members = split_archive_path(guest_value)
            guest_archive, local_archive, early = await self._pull_archive(test_name, archive)
            if early is not None:
                return guest_value, {}, early
            return join_archive_path(local_archive, members), {local_archive: guest_archive}, None
        if any(c in guest_value for c in ('*', '?', '[', ']')):
            try:
                matching_paths = await self.guest_file.resolve_guest_glob(guest_value)
            except RuntimeError as e:
                return guest_value, {}, self._pull_error(test_name, guest_value, e)
            self._drop_stale_copies(guest_value, matching_paths)
            for guest_path in matching_paths:
                try:
                    await self.guest_file.pull_file(guest_path, force=True)
                except FileNotFoundError:
                    self._drop_stale_copies(guest_path, [], literal=True)
                    continue
                except RuntimeError as e:
                    return guest_value, {}, self._pull_error(test_name, guest_path, e)
                missing = await self._pull_sidecars(guest_path, sidecars)
                if missing:
                    return guest_value, {}, self._sidecar_error(missing)
            return str(self.guest_file._guest_path_to_local(guest_value)), {}, None
        local_value, early = await self._pull_plain_path(test_name, '', guest_value, sidecars)
        return local_value, {local_value: guest_value}, early

    async def _execute_dst_test(
        self,
        test_name: str,
        test_function: str,
        test_instance: BasicTest,
    ) -> TestResult:
        """Execute a file-based test by pulling files and rewriting dst.

        Strategy:
        1. Read the original guest path from parameter.dst
        2. Handle glob patterns by resolving on guest first
        3. Pull the file(s) from guest to local temp dir, always fresh: a test reads the
           file as it is now, not a copy an earlier test pulled (before/after tests)
        4. Rewrite parameter.dst to local path
        5. Run test() locally
        """
        if not hasattr(test_instance, 'parameter') or not hasattr(test_instance.parameter, 'dst'):
            return TestResult.error([f"Test '{test_name}' has no parameter.dst — cannot run in host mode"])

        original_dst = test_instance.parameter.dst
        log.debug(f"GuestToHostTestExecutor: original dst='{original_dst}'")

        if has_archive_separator(original_dst) or test_function == 'standard.file_count':
            return await self._execute_without_pull(test_name, test_function, test_instance, original_dst)

        # Check for glob patterns
        has_glob = any(c in original_dst for c in ['*', '?', '[', ']'])
        sidecars = getattr(type(test_instance), 'host_mode_sidecars', ())

        if has_glob:
            # Resolve glob on guest side, then pull matching files
            try:
                matching_paths = await self.guest_file.resolve_guest_glob(original_dst)
            except RuntimeError as e:
                # no answer is not "no match": an absence test must not pass on it
                return self._pull_error(test_name, original_dst, e)
            self._drop_stale_copies(original_dst, matching_paths)
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
                    await self.guest_file.pull_file(guest_path, force=True)
                except FileNotFoundError as e:
                    # Gone between glob and pull: it is absent, like an unmatched path.
                    log.warning(f"GuestToHostTestExecutor: {guest_path} vanished before pull: {e}")
                    self._drop_stale_copies(guest_path, [], literal=True)
                    continue
                except RuntimeError as e:
                    # A file that matched but could not be read must not silently drop out
                    # of the test: an absence/count test would pass on a transport error.
                    return self._pull_error(test_name, guest_path, e)
                missing = await self._pull_sidecars(guest_path, sidecars)
                if missing:
                    return self._sidecar_error(missing)

            # Rewrite dst to local glob pattern
            local_dst = str(self.guest_file._guest_path_to_local(original_dst))
        else:
            local_dst, early = await self._pull_plain_path(test_name, test_function, original_dst, sidecars)
            if early is not None:
                return early

        # Rewrite dst and run test
        object.__setattr__(test_instance.parameter, 'dst', local_dst)
        try:
            result = await self._run_test(test_instance)
        finally:
            # Restore original dst for correct reporting
            object.__setattr__(test_instance.parameter, 'dst', original_dst)

        return result

    async def _pull_plain_path(
        self, test_name: str, test_function: str, original_dst: str, sidecars
    ) -> tuple[str, TestResult | None]:
        """Pull a plain (non-glob) ``dst``; return the local path, or a result that ends the test."""
        local_dst = str(self.guest_file._guest_path_to_local(original_dst))
        try:
            local_dst = str(await self.guest_file.pull_file(original_dst, force=True))
        except FileNotFoundError as e:
            # The guest answered "no such file": a real absence.
            func_name = test_function.split('.')[-1] if '.' in test_function else test_function
            if func_name in ('file_does_not_exist', 'dir_does_not_exist'):
                return local_dst, TestResult.success([f'{original_dst} does not exist on guest'])
            if func_name in ('file_exists', 'dir_exists'):
                return local_dst, TestResult.failed([f'{original_dst} does not exist on guest: {e}'])
            log.warning(f"GuestToHostTestExecutor: {original_dst} not found on guest: {e}")
            # a copy an earlier test pulled must not stand in for the file that is gone
            self._drop_stale_copies(original_dst, [], literal=True)
            return local_dst, None
        except RuntimeError as e:
            # Transport/permission failure: says nothing about whether the file exists,
            # so neither an absence test may pass nor an existence test fail on it.
            return local_dst, self._pull_error(test_name, original_dst, e)
        missing = await self._pull_sidecars(original_dst, sidecars)
        return local_dst, (self._sidecar_error(missing) if missing else None)

    async def _execute_archive_test(self, test_name: str, test_instance: BasicTest, original_dst: str) -> TestResult:
        """Pull only the archive of ``archive!/member``; the test extracts the member locally.

        Unlike a plain path, a missing archive is an ERROR for every test (also
        file_does_not_exist): without the archive nothing can be said about its members.
        Members' sidecars (SQLite -wal) come from the archive, so none are pulled.
        """
        archive, members = split_archive_path(original_dst)
        guest_archive, local_archive, early = await self._pull_archive(test_name, archive)
        if early is not None:
            return early

        object.__setattr__(test_instance.parameter, 'dst', join_archive_path(local_archive, members))
        try:
            result = await self._run_test(test_instance)
        finally:
            object.__setattr__(test_instance.parameter, 'dst', original_dst)

        # report the guest path, not the host's temp copy
        result.details = [d.replace(local_archive, guest_archive) if isinstance(d, str) else d for d in result.details]
        return result

    async def _pull_archive(self, test_name: str, archive: str) -> tuple[str, str, TestResult | None]:
        """Pull the archive of an ``archive!/member`` path: ``(guest archive, local archive, early result)``.

        A glob must match exactly one archive; a missing archive is an ERROR.
        """
        guest_archive = archive
        if any(c in archive for c in ('*', '?', '[', ']')):
            try:
                matches = await self.guest_file.resolve_guest_glob(archive)
            except RuntimeError as e:
                return archive, '', self._pull_error(test_name, archive, e)
            if len(matches) != 1:
                found = 'no file matches' if not matches else f'{len(matches)} files match'
                return archive, '', TestResult.error([f'archive {archive}: {found} the glob (must be exactly one)'])
            guest_archive = matches[0]
        try:
            local_archive = str(await self.guest_file.pull_file(guest_archive, force=True))
        except FileNotFoundError as e:
            return guest_archive, '', TestResult.error([f'archive {guest_archive} does not exist on guest: {e}'])
        except RuntimeError as e:
            return guest_archive, '', self._pull_error(test_name, guest_archive, e)
        return guest_archive, local_archive, None

    def _drop_stale_copies(self, guest_pattern: str, matching_paths: list[str], literal: bool = False) -> None:
        """Remove files from the shared local mirror that match ``guest_pattern`` but are not
        among ``matching_paths`` on the guest any more (``literal``: ``guest_pattern`` is one path).

        The mirror keeps every file an earlier test pulled; the test globs the mirror, so a copy
        of a file since deleted on the guest would still be found (``file_exists`` passing,
        ``file_does_not_exist`` failing on a file that is gone).
        """
        keep = {str(self.guest_file._guest_path_to_local(p)) for p in matching_paths}
        local_pattern = str(self.guest_file._guest_path_to_local(guest_pattern))
        for local in [local_pattern] if literal else glob.glob(local_pattern):
            if local not in keep and (os.path.isfile(local) or os.path.islink(local)):
                try:
                    os.remove(local)
                except OSError as e:
                    log.warning(f"GuestToHostTestExecutor: could not remove stale copy {local}: {e}")

    async def _execute_without_pull(
        self, test_name: str, test_function: str, test_instance: BasicTest, original_dst: str
    ) -> TestResult:
        """Tests whose dst is not pulled as is: an archive path, or a count of guest paths."""
        if has_archive_separator(original_dst):
            return await self._execute_archive_test(test_name, test_instance, original_dst)
        return await self._execute_path_count_test(test_name, test_instance, original_dst)

    async def _execute_path_count_test(self, test_name: str, test_instance: BasicTest, original_dst: str) -> TestResult:
        """Count guest paths (``standard.file_count``) without pulling any file.

        The guest lists the matching paths with their kind; the test then runs on a fresh
        skeleton of exactly those paths (empty files, directories, dangling links). So no copy
        left in the shared mirror by an earlier test is counted, and directories count too.
        """
        try:
            kinds = await self.guest_file.path_kinds(original_dst)
        except RuntimeError as e:
            return self._pull_error(test_name, original_dst, e)
        mirror_root = self.guest_file._temp_root
        skeleton = Path(tempfile.mkdtemp(prefix='adare_count_'))

        def local_of(guest_path: str) -> Path:
            return skeleton / self.guest_file._guest_path_to_local(guest_path).relative_to(mirror_root)

        display = {str(local_of(p)): p for p, _ in kinds}
        try:
            for guest_path, kind in sorted(kinds, key=lambda item: item[1] != 'dir'):
                local = local_of(guest_path)
                local.parent.mkdir(parents=True, exist_ok=True)
                if kind == 'dir':
                    local.mkdir(exist_ok=True)
                elif kind == 'file':
                    local.touch()
                else:
                    local.symlink_to(skeleton / '.missing')
            object.__setattr__(test_instance.parameter, 'dst', str(local_of(original_dst)))
            try:
                result = await self._run_test(test_instance)
            finally:
                object.__setattr__(test_instance.parameter, 'dst', original_dst)
        except OSError as e:
            return TestResult.execution_error(e, f'Cannot build the local listing for {original_dst}')
        finally:
            shutil.rmtree(skeleton, ignore_errors=True)
        details = []
        for detail in result.details:
            if isinstance(detail, str):
                # longest first, so a path is never replaced inside a longer one
                for local_text in sorted(display, key=len, reverse=True):
                    detail = detail.replace(local_text, display[local_text])
                detail = detail.replace(str(local_of(original_dst)), original_dst)
            details.append(detail)
        result.details = details
        return result

    @staticmethod
    def _pull_error(test_name: str, guest_path: str, error: Exception) -> TestResult:
        """ERROR result for a file that could not be read for a reason other than absence."""
        log.error(f"GuestToHostTestExecutor: could not read {guest_path} for '{test_name}': {error}")
        return TestResult.error([f'Could not read {guest_path} from guest (not a "not found"): {error}'])

    async def _pull_sidecars(self, guest_path: str, suffixes: tuple[str, ...]) -> list[str]:
        """Pull the companion files of guest_path (e.g. SQLite -wal/-journal).

        Always re-pulled (no cache) and a local copy is removed when the sidecar
        no longer exists on the guest, so dst and its sidecars come from the same
        moment — a stale -wal next to a fresh database would corrupt the result.

        A dst that is itself a sidecar (``app.db-wal``) has no companions of its own:
        nothing is probed (no ``app.db-wal-wal``).

        Returns:
            Guest paths of sidecars that exist but could not be pulled
        """
        missing: list[str] = []
        if guest_path.endswith(suffixes):
            return missing
        for suffix in suffixes:
            sidecar = guest_path + suffix
            if await self.guest_file.file_exists(sidecar):
                try:
                    await self.guest_file.pull_file(sidecar, force=True)
                except (RuntimeError, FileNotFoundError) as e:
                    log.warning(f"GuestToHostTestExecutor: failed to pull sidecar {sidecar}: {e}")
                    missing.append(sidecar)
            else:
                self.guest_file._guest_path_to_local(sidecar).unlink(missing_ok=True)
        return missing

    @staticmethod
    def _sidecar_error(missing: list[str]) -> TestResult:
        return TestResult.error(
            [f"could not pull {', '.join(missing)} from guest; testing without it would read stale data"]
        )

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
        if func_name == 'system_service_status':
            return await self._test_service_status(test_instance)
        if func_name == 'user_exists':
            return await self._test_user_exists(test_instance)
        if func_name == 'registry_key_exists':
            return await self._test_registry_key_exists(test_instance)
        if func_name == 'registry_value_matches':
            return await self._test_registry_value_matches(test_instance)
        if func_name == 'file_permissions':
            return await self._test_file_permissions(test_name, test_instance)
        if func_name == 'file_timestamps':
            return await self._test_file_timestamps(test_name, test_instance)
        return TestResult.error([f"Unknown QGA probe test: {func_name}"])

    async def _run_test(self, test_instance) -> TestResult:
        """Run a test method, handling both sync and async test() methods."""
        test_method = test_instance.test
        if asyncio.iscoroutinefunction(test_method):
            return await test_method()
        # Run sync test in thread pool to avoid blocking the event loop
        return await asyncio.to_thread(test_method)

    def cleanup(self):
        """Clean up temp files."""
        self.guest_file.cleanup()
