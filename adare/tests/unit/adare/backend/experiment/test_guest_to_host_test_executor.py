"""Tests for GuestToHostTestExecutor refactored to use HostModeCategory ClassVar."""

from typing import ClassVar
from unittest.mock import AsyncMock, MagicMock, patch

import attrs
import pytest

pytestmark = pytest.mark.unit

from adare.backend.experiment.guest_to_host_test_executor import GuestToHostTestExecutor
from adarelib.constants import StatusEnum
from adarelib.event.event import TestResult
from adarelib.testset.basictest import BasicTest, HostModeCategory, Parameter

# ============================================================================
# Test fixtures: minimal attrs-based test classes
# ============================================================================

@attrs.define
class DummyParam(Parameter):
    dst: str = '/tmp/testfile'


@attrs.define
class FileBasedTest(BasicTest):
    """A test that uses FILE_BASED category."""
    testname: ClassVar[str] = 'file_exists'
    testdescription: ClassVar[str] = 'dummy file_exists'
    host_mode_category: ClassVar[HostModeCategory] = HostModeCategory.FILE_BASED

    name: str = 'test_file_exists'
    parameter: DummyParam = attrs.Factory(DummyParam)
    description: str | None = ''
    variable_metadata: dict | None = None


@attrs.define
class FileContentTest(BasicTest):
    """A test that uses FILE_CONTENT category."""
    testname: ClassVar[str] = 'contains_key'
    testdescription: ClassVar[str] = 'dummy contains_key'
    host_mode_category: ClassVar[HostModeCategory] = HostModeCategory.FILE_CONTENT

    name: str = 'test_contains_key'
    parameter: DummyParam = attrs.Factory(DummyParam)
    description: str | None = ''
    variable_metadata: dict | None = None


@attrs.define
class SidecarParam(Parameter):
    dst: str = '/home/user/places.sqlite'


@attrs.define
class SidecarTest(BasicTest):
    """A FILE_CONTENT test whose dst comes with companion files (like SQLite)."""
    testname: ClassVar[str] = 'query_result'
    testdescription: ClassVar[str] = 'dummy query_result'
    host_mode_category: ClassVar[HostModeCategory] = HostModeCategory.FILE_CONTENT
    host_mode_sidecars: ClassVar[tuple[str, ...]] = ('-wal', '-journal')

    name: str = 'test_query_result'
    parameter: SidecarParam = attrs.Factory(SidecarParam)
    description: str | None = ''
    variable_metadata: dict | None = None


@attrs.define
class QGAProbeParam(Parameter):
    process_name: str = 'nginx'


@attrs.define
class QGAProbeTest(BasicTest):
    """A test that uses QGA_PROBE category."""
    testname: ClassVar[str] = 'process_running'
    testdescription: ClassVar[str] = 'dummy process_running'
    host_mode_category: ClassVar[HostModeCategory] = HostModeCategory.QGA_PROBE

    name: str = 'test_process_running'
    parameter: QGAProbeParam = attrs.Factory(QGAProbeParam)
    description: str | None = ''
    variable_metadata: dict | None = None


@attrs.define
class HostNativeTest(BasicTest):
    """A test that uses HOST_NATIVE category."""
    testname: ClassVar[str] = 'visual.exists'
    testdescription: ClassVar[str] = 'dummy visual'
    execute_on_host: ClassVar[bool] = True
    host_mode_category: ClassVar[HostModeCategory] = HostModeCategory.HOST_NATIVE

    name: str = 'test_visual'
    parameter: DummyParam = attrs.Factory(DummyParam)
    description: str | None = ''
    variable_metadata: dict | None = None


@attrs.define
class AgentOnlyTest(BasicTest):
    """A test with default AGENT_ONLY category."""
    testname: ClassVar[str] = 'custom_agent_test'
    testdescription: ClassVar[str] = 'requires agent'

    name: str = 'test_agent_only'
    parameter: DummyParam = attrs.Factory(DummyParam)
    description: str | None = ''
    variable_metadata: dict | None = None


@attrs.define
class NoCategoryTest(BasicTest):
    """A test that does NOT override host_mode_category (inherits AGENT_ONLY)."""
    testname: ClassVar[str] = 'no_category'
    testdescription: ClassVar[str] = 'no explicit category'

    name: str = 'test_no_category'
    parameter: DummyParam = attrs.Factory(DummyParam)
    description: str | None = ''
    variable_metadata: dict | None = None


# ============================================================================
# Test _get_test_category
# ============================================================================

class TestGetTestCategory:
    """Test _get_test_category reads ClassVar from test instance type."""

    def _make_executor(self):
        guest_file = MagicMock()
        guest_command = MagicMock()
        return GuestToHostTestExecutor(
            guest_file=guest_file,
            guest_command=guest_command,
            testfunction_collection={},
        )

    def test_file_based_category(self):
        executor = self._make_executor()
        instance = FileBasedTest()
        category = executor._get_test_category('standard.file_exists', instance)
        assert category == HostModeCategory.FILE_BASED

    def test_file_content_category(self):
        executor = self._make_executor()
        instance = FileContentTest()
        category = executor._get_test_category('json.contains_key', instance)
        assert category == HostModeCategory.FILE_CONTENT

    def test_qga_probe_category(self):
        executor = self._make_executor()
        instance = QGAProbeTest()
        category = executor._get_test_category('linux.process_running', instance)
        assert category == HostModeCategory.QGA_PROBE

    def test_host_native_category(self):
        executor = self._make_executor()
        instance = HostNativeTest()
        category = executor._get_test_category('visual.exists', instance)
        assert category == HostModeCategory.HOST_NATIVE

    def test_agent_only_category(self):
        executor = self._make_executor()
        instance = AgentOnlyTest()
        category = executor._get_test_category('custom.agent_test', instance)
        assert category == HostModeCategory.AGENT_ONLY

    def test_returns_agent_only_for_missing_classvar(self):
        """Test without host_mode_category ClassVar gets AGENT_ONLY default."""
        executor = self._make_executor()
        instance = NoCategoryTest()
        category = executor._get_test_category('unknown.test', instance)
        assert category == HostModeCategory.AGENT_ONLY


# ============================================================================
# Test execute_test dispatch
# ============================================================================

class TestExecuteTestDispatch:
    """Test dispatch to correct execution path based on category."""

    def _make_executor(self):
        guest_file = MagicMock()
        guest_command = MagicMock()
        return GuestToHostTestExecutor(
            guest_file=guest_file,
            guest_command=guest_command,
            testfunction_collection={},
        )

    @pytest.mark.asyncio
    async def test_dispatches_file_based_to_file_handler(self):
        executor = self._make_executor()
        instance = FileBasedTest()

        with patch.object(executor, '_execute_file_based_test', new_callable=AsyncMock) as mock_fb:
            mock_fb.return_value = TestResult.success(['ok'])
            result = await executor.execute_test('t1', 'standard.file_exists', instance)
            mock_fb.assert_called_once_with('t1', 'standard.file_exists', instance)
            assert result.status == StatusEnum.SUCCESS

    @pytest.mark.asyncio
    async def test_dispatches_file_content_to_file_handler(self):
        executor = self._make_executor()
        instance = FileContentTest()

        with patch.object(executor, '_execute_file_based_test', new_callable=AsyncMock) as mock_fb:
            mock_fb.return_value = TestResult.success(['ok'])
            result = await executor.execute_test('t2', 'json.contains_key', instance)
            mock_fb.assert_called_once_with('t2', 'json.contains_key', instance)
            assert result.status == StatusEnum.SUCCESS

    @pytest.mark.asyncio
    async def test_dispatches_qga_probe_to_probe_handler(self):
        executor = self._make_executor()
        instance = QGAProbeTest()

        with patch.object(executor, '_execute_qga_probe_test', new_callable=AsyncMock) as mock_qga:
            mock_qga.return_value = TestResult.success(['running'])
            result = await executor.execute_test('t3', 'linux.process_running', instance)
            mock_qga.assert_called_once_with('t3', 'linux.process_running', instance)
            assert result.status == StatusEnum.SUCCESS

    @pytest.mark.asyncio
    async def test_host_native_returns_error(self):
        """HOST_NATIVE tests should use existing host test executor, not this one."""
        executor = self._make_executor()
        instance = HostNativeTest()

        result = await executor.execute_test('t4', 'visual.exists', instance)
        assert result.status == StatusEnum.ERROR
        assert 'host test executor' in result.details[0].lower() or 'Host-native' in result.details[0]

    @pytest.mark.asyncio
    async def test_agent_only_returns_error(self):
        """AGENT_ONLY tests should return error in host mode."""
        executor = self._make_executor()
        instance = AgentOnlyTest()

        result = await executor.execute_test('t5', 'custom.agent_test', instance)
        assert result.status == StatusEnum.ERROR
        assert 'agent_only' in result.details[0]


# ============================================================================
# Test validate_playbook_tests
# ============================================================================

class TestValidatePlaybookTests:
    """Test validate_playbook_tests uses ClassVar instead of hard-coded sets."""

    def _make_test_def(self, name, function):
        """Create a mock test definition."""
        test_def = MagicMock()
        test_def.name = name
        test_def.function = function
        return test_def

    def test_supported_tests_pass_validation(self):
        """FILE_BASED, FILE_CONTENT, QGA_PROBE, HOST_NATIVE tests pass validation."""
        testfunction_collection = {
            'standard': {
                'file_exists': FileBasedTest,
            },
            'json': {
                'contains_key': FileContentTest,
            },
            'linux': {
                'process_running': QGAProbeTest,
            },
            'visual': {
                'visual.exists': HostNativeTest,
            },
        }

        playbook_tests = [
            self._make_test_def('t1', 'standard.file_exists'),
            self._make_test_def('t2', 'json.contains_key'),
            self._make_test_def('t3', 'linux.process_running'),
        ]

        ok, issues = GuestToHostTestExecutor.validate_playbook_tests(
            playbook_tests, testfunction_collection
        )
        assert ok is True
        assert issues == []

    def test_agent_only_tests_reported(self):
        """AGENT_ONLY tests should be reported as unsupported."""
        testfunction_collection = {
            'custom': {
                'custom_agent_test': AgentOnlyTest,
            },
        }

        playbook_tests = [
            self._make_test_def('t_agent', 'custom.custom_agent_test'),
        ]

        ok, issues = GuestToHostTestExecutor.validate_playbook_tests(
            playbook_tests, testfunction_collection
        )
        assert ok is False
        assert len(issues) == 1
        assert 'agent_only' in issues[0]
        assert 't_agent' in issues[0]

    def test_unknown_test_reported(self):
        """Unknown test function (not in collection) is reported as unsupported."""
        testfunction_collection = {}

        playbook_tests = [
            self._make_test_def('t_unknown', 'custom.nonexistent_func'),
        ]

        ok, issues = GuestToHostTestExecutor.validate_playbook_tests(
            playbook_tests, testfunction_collection
        )
        assert ok is False
        assert len(issues) == 1
        assert 'unknown test type' in issues[0]

    def test_mixed_supported_and_unsupported(self):
        """Mix of supported and unsupported tests: only unsupported reported."""
        testfunction_collection = {
            'standard': {
                'file_exists': FileBasedTest,
            },
            'custom': {
                'custom_agent_test': AgentOnlyTest,
            },
        }

        playbook_tests = [
            self._make_test_def('t_ok', 'standard.file_exists'),
            self._make_test_def('t_bad', 'custom.custom_agent_test'),
        ]

        ok, issues = GuestToHostTestExecutor.validate_playbook_tests(
            playbook_tests, testfunction_collection
        )
        assert ok is False
        assert len(issues) == 1
        assert 't_bad' in issues[0]

    def test_no_category_test_defaults_to_agent_only(self):
        """Test class without explicit host_mode_category defaults to AGENT_ONLY."""
        testfunction_collection = {
            'misc': {
                'no_category': NoCategoryTest,
            },
        }

        playbook_tests = [
            self._make_test_def('t_nocategory', 'misc.no_category'),
        ]

        ok, issues = GuestToHostTestExecutor.validate_playbook_tests(
            playbook_tests, testfunction_collection
        )
        assert ok is False
        assert len(issues) == 1
        assert 'agent_only' in issues[0]

    def test_empty_playbook_passes(self):
        """Empty playbook test list passes validation."""
        ok, issues = GuestToHostTestExecutor.validate_playbook_tests([], {})
        assert ok is True
        assert issues == []


# ============================================================================
# Test sidecar pulling in _execute_file_based_test
# ============================================================================

class TestSidecarPulling:
    """dst companion files (host_mode_sidecars) are pulled fresh alongside dst."""

    def _make_executor(self, tmp_path, existing):
        guest_file = MagicMock()
        guest_file.pull_file = AsyncMock(side_effect=lambda p, force=False: tmp_path / p.lstrip('/'))
        guest_file.file_exists = AsyncMock(side_effect=lambda p: p in existing)
        guest_file._guest_path_to_local = lambda p: tmp_path / p.lstrip('/')
        executor = GuestToHostTestExecutor(
            guest_file=guest_file,
            guest_command=MagicMock(),
            testfunction_collection={},
        )
        executor._run_test = AsyncMock(return_value=TestResult.success(['ok']))
        return executor, guest_file

    @pytest.mark.asyncio
    async def test_pulls_existing_sidecars_without_cache(self, tmp_path):
        executor, guest_file = self._make_executor(tmp_path, {'/home/user/places.sqlite-wal'})

        result = await executor._execute_file_based_test('t', 'sqlite.query_result', SidecarTest())

        assert result.status == StatusEnum.SUCCESS
        assert guest_file.pull_file.await_args_list == [
            (('/home/user/places.sqlite',), {'force': True}),
            (('/home/user/places.sqlite-wal',), {'force': True}),
        ]

    @pytest.mark.asyncio
    async def test_removes_stale_local_sidecar_gone_from_guest(self, tmp_path):
        stale = tmp_path / 'home/user/places.sqlite-wal'
        stale.parent.mkdir(parents=True)
        stale.write_bytes(b'from an earlier pull')
        executor, _ = self._make_executor(tmp_path, set())

        await executor._execute_file_based_test('t', 'sqlite.query_result', SidecarTest())

        assert not stale.exists()

    @pytest.mark.asyncio
    async def test_sidecar_pull_failure_is_an_error(self, tmp_path):
        executor, guest_file = self._make_executor(tmp_path, {'/home/user/places.sqlite-wal'})

        async def pull(path, force=False):
            if path.endswith('-wal'):
                raise RuntimeError('transfer failed')
            return tmp_path / path.lstrip('/')
        guest_file.pull_file.side_effect = pull

        result = await executor._execute_file_based_test('t', 'sqlite.query_result', SidecarTest())

        assert result.status == StatusEnum.ERROR
        assert 'places.sqlite-wal' in result.details[0]
        executor._run_test.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_glob_pulls_sidecars_of_each_match(self, tmp_path):
        executor, guest_file = self._make_executor(tmp_path, {'/home/user/places.sqlite-journal'})
        guest_file.resolve_guest_glob = AsyncMock(return_value=['/home/user/places.sqlite'])
        instance = SidecarTest(parameter=SidecarParam(dst='/home/*/places.sqlite'))

        await executor._execute_file_based_test('t', 'sqlite.query_result', instance)

        pulled = [c.args[0] for c in guest_file.pull_file.await_args_list]
        assert pulled == ['/home/user/places.sqlite', '/home/user/places.sqlite-journal']

    @pytest.mark.asyncio
    async def test_tests_without_sidecars_keep_cached_pull(self, tmp_path):
        executor, guest_file = self._make_executor(tmp_path, set())

        await executor._execute_file_based_test('t', 'json.contains_key', FileContentTest())

        guest_file.pull_file.assert_awaited_once_with('/tmp/testfile', force=False)
        guest_file.file_exists.assert_not_awaited()
