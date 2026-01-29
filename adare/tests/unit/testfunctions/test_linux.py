"""Comprehensive unit tests for Linux testfunctions."""

import pytest
import sys
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add paths for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
ADARELIB_ROOT = PROJECT_ROOT.parent / "adarelib"

# Add to sys.path if not already there
if str(ADARELIB_ROOT) not in sys.path:
    sys.path.insert(0, str(ADARELIB_ROOT))

# Import from adarelib.constants as required
from adarelib.constants import StatusEnum

# Import testfunctions dynamically
from adare.helperfunctions.module import import_module_from_pyfile

# Load Linux testfunctions module
linux_module_path = PROJECT_ROOT / "appdata" / "testfunctions" / "linux" / "linux.py"
linux_module = import_module_from_pyfile(linux_module_path)

# Extract testfunctions from module
SystemServiceStatus = linux_module.SystemServiceStatus
SystemServiceStatusParameter = linux_module.SystemServiceStatusParameter
ProcessRunning = linux_module.ProcessRunning
ProcessRunningParameter = linux_module.ProcessRunningParameter
UserExists = linux_module.UserExists
UserExistsParameter = linux_module.UserExistsParameter
LogEntryExists = linux_module.LogEntryExists
LogEntryExistsParameter = linux_module.LogEntryExistsParameter

# Import test helpers
import importlib.util
helpers_path = Path(__file__).parent / "helpers.py"
spec = importlib.util.spec_from_file_location("helpers", helpers_path)
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)

assert_test_success = helpers.assert_test_success
assert_test_failed = helpers.assert_test_failed
assert_test_error = helpers.assert_test_error
assert_test_execution_error = helpers.assert_test_execution_error


# ============================================================================
# SystemServiceStatus Tests
# ============================================================================

class TestSystemServiceStatus:
    """Tests for SystemServiceStatus testfunction."""

    @patch('platform.system', return_value='Linux')
    def test_service_status_success_active(self, mock_platform, mock_subprocess_run):
        """Test successful service status check with active status."""
        mock_subprocess_run.return_value = MagicMock(
            returncode=0,
            stdout='active\n',
            stderr=''
        )

        test = SystemServiceStatus(
            name="test_service",
            parameter=SystemServiceStatusParameter(
                service_name="nginx",
                expected_status="active"
            )
        )
        result = test.test()

        assert_test_success(result)
        assert 'nginx' in result.details[0]
        assert 'active' in result.details[0]
        mock_subprocess_run.assert_called_once_with(
            ['systemctl', 'is-active', 'nginx'],
            capture_output=True,
            text=True,
            timeout=10
        )

    @patch('platform.system', return_value='Linux')
    def test_service_status_success_inactive(self, mock_platform, mock_subprocess_run):
        """Test successful service status check with inactive status."""
        mock_subprocess_run.return_value = MagicMock(
            returncode=3,
            stdout='inactive\n',
            stderr=''
        )

        test = SystemServiceStatus(
            name="test_service",
            parameter=SystemServiceStatusParameter(
                service_name="apache2",
                expected_status="inactive"
            )
        )
        result = test.test()

        assert_test_success(result)
        assert 'apache2' in result.details[0]
        assert 'inactive' in result.details[0]

    @patch('platform.system', return_value='Linux')
    def test_service_status_failure_mismatch(self, mock_platform, mock_subprocess_run):
        """Test failure when service status doesn't match expected."""
        mock_subprocess_run.return_value = MagicMock(
            returncode=3,
            stdout='inactive\n',
            stderr=''
        )

        test = SystemServiceStatus(
            name="test_service",
            parameter=SystemServiceStatusParameter(
                service_name="nginx",
                expected_status="active"
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert 'status mismatch' in result.details[0]
        assert 'Expected: active' in result.details[0]
        assert 'Got: inactive' in result.details[0]

    @patch('platform.system', return_value='Windows')
    def test_service_status_not_linux(self, mock_platform):
        """Test execution error when not running on Linux."""
        test = SystemServiceStatus(
            name="test_service",
            parameter=SystemServiceStatusParameter(
                service_name="nginx",
                expected_status="active"
            )
        )
        result = test.test()

        assert_test_execution_error(result)
        assert 'only runs on Linux' in result.details[0]

    @patch('platform.system', return_value='Linux')
    def test_service_status_timeout(self, mock_platform, mock_subprocess_run):
        """Test execution error when subprocess times out."""
        mock_subprocess_run.side_effect = subprocess.TimeoutExpired('systemctl', 10)

        test = SystemServiceStatus(
            name="test_service",
            parameter=SystemServiceStatusParameter(
                service_name="nginx",
                expected_status="active"
            )
        )
        result = test.test()

        assert_test_execution_error(result)
        assert 'Timeout' in result.details[0]
        assert 'nginx' in result.details[0]

    @patch('platform.system', return_value='Linux')
    def test_service_status_command_not_found(self, mock_platform, mock_subprocess_run):
        """Test execution error when systemctl command not found."""
        mock_subprocess_run.side_effect = FileNotFoundError("systemctl not found")

        test = SystemServiceStatus(
            name="test_service",
            parameter=SystemServiceStatusParameter(
                service_name="nginx",
                expected_status="active"
            )
        )
        result = test.test()

        assert_test_execution_error(result)
        assert 'Failed to check service status' in result.details[0]

    @patch('platform.system', return_value='Linux')
    def test_service_status_with_placeholder(self, mock_platform, mock_subprocess_run, variable_metadata_simple):
        """Test service status check with placeholder in service name."""
        mock_subprocess_run.return_value = MagicMock(
            returncode=0,
            stdout='active\n',
            stderr=''
        )

        test = SystemServiceStatus(
            name="test_service",
            parameter=SystemServiceStatusParameter(
                service_name="{{VAR1}}",
                expected_status="active"
            ),
            variable_metadata=variable_metadata_simple
        )
        result = test.test()

        assert_test_success(result)
        mock_subprocess_run.assert_called_once_with(
            ['systemctl', 'is-active', 'value1'],
            capture_output=True,
            text=True,
            timeout=10
        )


# ============================================================================
# ProcessRunning Tests
# ============================================================================

class TestProcessRunning:
    """Tests for ProcessRunning testfunction."""

    @patch('platform.system', return_value='Linux')
    def test_process_running_success_single_instance(self, mock_platform, mock_subprocess_run):
        """Test successful process check with single instance."""
        mock_subprocess_run.return_value = MagicMock(
            returncode=0,
            stdout='1234\n',
            stderr=''
        )

        test = ProcessRunning(
            name="test_process",
            parameter=ProcessRunningParameter(
                process_name="nginx",
                min_instances=1
            )
        )
        result = test.test()

        assert_test_success(result)
        assert 'nginx' in result.details[0]
        assert '1 instances' in result.details[0]
        assert '1234' in result.details[0]
        mock_subprocess_run.assert_called_once_with(
            ['pgrep', '-f', 'nginx'],
            capture_output=True,
            text=True,
            timeout=10
        )

    @patch('platform.system', return_value='Linux')
    def test_process_running_success_multiple_instances(self, mock_platform, mock_subprocess_run):
        """Test successful process check with multiple instances."""
        mock_subprocess_run.return_value = MagicMock(
            returncode=0,
            stdout='1234\n1235\n1236\n',
            stderr=''
        )

        test = ProcessRunning(
            name="test_process",
            parameter=ProcessRunningParameter(
                process_name="nginx",
                min_instances=2
            )
        )
        result = test.test()

        assert_test_success(result)
        assert 'nginx' in result.details[0]
        assert '3 instances' in result.details[0]
        assert '1234' in result.details[0]
        assert '1235' in result.details[0]
        assert '1236' in result.details[0]

    @patch('platform.system', return_value='Linux')
    def test_process_running_failure_not_running(self, mock_platform, mock_subprocess_run):
        """Test failure when process is not running."""
        mock_subprocess_run.return_value = MagicMock(
            returncode=1,
            stdout='',
            stderr=''
        )

        test = ProcessRunning(
            name="test_process",
            parameter=ProcessRunningParameter(
                process_name="nonexistent",
                min_instances=1
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert 'not running' in result.details[0]
        assert 'nonexistent' in result.details[0]

    @patch('platform.system', return_value='Linux')
    def test_process_running_failure_insufficient_instances(self, mock_platform, mock_subprocess_run):
        """Test failure when insufficient process instances."""
        mock_subprocess_run.return_value = MagicMock(
            returncode=0,
            stdout='1234\n',
            stderr=''
        )

        test = ProcessRunning(
            name="test_process",
            parameter=ProcessRunningParameter(
                process_name="nginx",
                min_instances=3
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert 'has 1 instances' in result.details[0]
        assert 'expected at least 3' in result.details[0]

    @patch('platform.system', return_value='Darwin')
    def test_process_running_not_linux(self, mock_platform):
        """Test execution error when not running on Linux."""
        test = ProcessRunning(
            name="test_process",
            parameter=ProcessRunningParameter(
                process_name="nginx",
                min_instances=1
            )
        )
        result = test.test()

        assert_test_execution_error(result)
        assert 'only runs on Linux' in result.details[0]

    @patch('platform.system', return_value='Linux')
    def test_process_running_timeout(self, mock_platform, mock_subprocess_run):
        """Test execution error when subprocess times out."""
        mock_subprocess_run.side_effect = subprocess.TimeoutExpired('pgrep', 10)

        test = ProcessRunning(
            name="test_process",
            parameter=ProcessRunningParameter(
                process_name="nginx",
                min_instances=1
            )
        )
        result = test.test()

        assert_test_execution_error(result)
        assert 'Timeout' in result.details[0]
        assert 'nginx' in result.details[0]

    @patch('platform.system', return_value='Linux')
    def test_process_running_with_placeholder(self, mock_platform, mock_subprocess_run, variable_metadata_simple):
        """Test process check with placeholder in process name."""
        mock_subprocess_run.return_value = MagicMock(
            returncode=0,
            stdout='1234\n',
            stderr=''
        )

        test = ProcessRunning(
            name="test_process",
            parameter=ProcessRunningParameter(
                process_name="{{VAR2}}",
                min_instances=1
            ),
            variable_metadata=variable_metadata_simple
        )
        result = test.test()

        assert_test_success(result)
        mock_subprocess_run.assert_called_once_with(
            ['pgrep', '-f', 'value2'],
            capture_output=True,
            text=True,
            timeout=10
        )


# ============================================================================
# UserExists Tests
# ============================================================================

class TestUserExists:
    """Tests for UserExists testfunction."""

    @patch('platform.system', return_value='Linux')
    def test_user_exists_success_basic(self, mock_platform):
        """Test successful user existence check."""
        with patch.object(linux_module, 'UNIX_MODULES_AVAILABLE', True):
            with patch.object(linux_module, 'pwd') as mock_pwd:
                mock_user = MagicMock()
                mock_user.pw_uid = 1000
                mock_user.pw_dir = '/home/testuser'
                mock_pwd.getpwnam.return_value = mock_user

                test = UserExists(
                    name="test_user",
                    parameter=UserExistsParameter(
                        username="testuser"
                    )
                )
                result = test.test()

                assert_test_success(result)
                assert 'testuser exists' in result.details[0]
                assert 'UID: 1000' in result.details[0]
                assert '/home/testuser' in result.details[0]
                mock_pwd.getpwnam.assert_called_once_with('testuser')

    @patch('platform.system', return_value='Linux')
    def test_user_exists_success_with_uid_check(self, mock_platform):
        """Test successful user existence with UID verification."""
        with patch.object(linux_module, 'UNIX_MODULES_AVAILABLE', True):
            with patch.object(linux_module, 'pwd') as mock_pwd:
                mock_user = MagicMock()
                mock_user.pw_uid = 1000
                mock_user.pw_dir = '/home/testuser'
                mock_pwd.getpwnam.return_value = mock_user

                test = UserExists(
                    name="test_user",
                    parameter=UserExistsParameter(
                        username="testuser",
                        uid=1000
                    )
                )
                result = test.test()

                assert_test_success(result)
                assert 'testuser exists' in result.details[0]

    @patch('platform.system', return_value='Linux')
    def test_user_exists_success_with_home_check(self, mock_platform):
        """Test successful user existence with home directory verification."""
        with patch.object(linux_module, 'UNIX_MODULES_AVAILABLE', True):
            with patch.object(linux_module, 'pwd') as mock_pwd:
                mock_user = MagicMock()
                mock_user.pw_uid = 1000
                mock_user.pw_dir = '/home/testuser'
                mock_pwd.getpwnam.return_value = mock_user

                test = UserExists(
                    name="test_user",
                    parameter=UserExistsParameter(
                        username="testuser",
                        home_dir="/home/testuser"
                    )
                )
                result = test.test()

                assert_test_success(result)
                assert 'testuser exists' in result.details[0]

    @patch('platform.system', return_value='Linux')
    def test_user_exists_failure_user_not_found(self, mock_platform):
        """Test failure when user doesn't exist."""
        with patch.object(linux_module, 'UNIX_MODULES_AVAILABLE', True):
            with patch.object(linux_module, 'pwd') as mock_pwd:
                mock_pwd.getpwnam.side_effect = KeyError("getpwnam(): name not found")

                test = UserExists(
                    name="test_user",
                    parameter=UserExistsParameter(
                        username="nonexistent"
                    )
                )
                result = test.test()

                assert_test_failed(result)
                assert 'does not exist' in result.details[0]
                assert 'nonexistent' in result.details[0]

    @patch('platform.system', return_value='Linux')
    def test_user_exists_failure_uid_mismatch(self, mock_platform):
        """Test failure when user UID doesn't match expected."""
        with patch.object(linux_module, 'UNIX_MODULES_AVAILABLE', True):
            with patch.object(linux_module, 'pwd') as mock_pwd:
                mock_user = MagicMock()
                mock_user.pw_uid = 1001
                mock_user.pw_dir = '/home/testuser'
                mock_pwd.getpwnam.return_value = mock_user

                test = UserExists(
                    name="test_user",
                    parameter=UserExistsParameter(
                        username="testuser",
                        uid=1000
                    )
                )
                result = test.test()

                assert_test_failed(result)
                assert 'UID mismatch' in result.details[0]
                assert 'Expected: 1000' in result.details[0]
                assert 'Got: 1001' in result.details[0]

    @patch('platform.system', return_value='Linux')
    def test_user_exists_failure_home_mismatch(self, mock_platform):
        """Test failure when home directory doesn't match expected."""
        with patch.object(linux_module, 'UNIX_MODULES_AVAILABLE', True):
            with patch.object(linux_module, 'pwd') as mock_pwd:
                mock_user = MagicMock()
                mock_user.pw_uid = 1000
                mock_user.pw_dir = '/home/testuser'
                mock_pwd.getpwnam.return_value = mock_user

                test = UserExists(
                    name="test_user",
                    parameter=UserExistsParameter(
                        username="testuser",
                        home_dir="/opt/testuser"
                    )
                )
                result = test.test()

                assert_test_failed(result)
                assert 'home directory mismatch' in result.details[0]
                assert 'Expected: /opt/testuser' in result.details[0]
                assert 'Got: /home/testuser' in result.details[0]

    @patch('platform.system', return_value='Windows')
    def test_user_exists_not_linux(self, mock_platform):
        """Test execution error when not running on Linux."""
        test = UserExists(
            name="test_user",
            parameter=UserExistsParameter(
                username="testuser"
            )
        )
        result = test.test()

        assert_test_execution_error(result)
        assert 'only runs on Linux' in result.details[0]

    @patch('platform.system', return_value='Linux')
    def test_user_exists_modules_not_available(self, mock_platform):
        """Test execution error when Unix modules not available."""
        with patch.object(linux_module, 'UNIX_MODULES_AVAILABLE', False):
            test = UserExists(
                name="test_user",
                parameter=UserExistsParameter(
                    username="testuser"
                )
            )
            result = test.test()

            assert_test_execution_error(result)
            assert 'Unix modules' in result.details[0]
            assert 'not available' in result.details[0]

    @patch('platform.system', return_value='Linux')
    def test_user_exists_with_placeholder(self, mock_platform, variable_metadata_simple):
        """Test user check with placeholder in username."""
        with patch.object(linux_module, 'UNIX_MODULES_AVAILABLE', True):
            with patch.object(linux_module, 'pwd') as mock_pwd:
                mock_user = MagicMock()
                mock_user.pw_uid = 1000
                mock_user.pw_dir = '/home/value1'
                mock_pwd.getpwnam.return_value = mock_user

                test = UserExists(
                    name="test_user",
                    parameter=UserExistsParameter(
                        username="{{VAR1}}"
                    ),
                    variable_metadata=variable_metadata_simple
                )
                result = test.test()

                assert_test_success(result)
                mock_pwd.getpwnam.assert_called_once_with('value1')


# ============================================================================
# LogEntryExists Tests
# ============================================================================

class TestLogEntryExists:
    """Tests for LogEntryExists testfunction."""

    @patch('platform.system', return_value='Linux')
    def test_log_entry_exists_success_found(self, mock_platform, mock_subprocess_run, tmp_path):
        """Test successful log entry search with matches found."""
        log_file = tmp_path / "test.log"
        log_file.write_text("line1\nerror occurred\nline3\n")

        mock_subprocess_run.return_value = MagicMock(
            returncode=0,
            stdout='error occurred\n',
            stderr=''
        )

        test = LogEntryExists(
            name="test_log",
            parameter=LogEntryExistsParameter(
                log_file=str(log_file),
                pattern="error",
                max_lines=1000
            )
        )
        result = test.test()

        assert_test_success(result)
        assert 'found 1 log entries' in result.details[0]
        assert str(log_file) in result.details[0]

        # Verify bash command construction
        call_args = mock_subprocess_run.call_args
        assert call_args[0][0] == ['bash', '-c', f'tail -n 1000 "{log_file}" | grep -E "error"']
        assert call_args[1]['timeout'] == 30

    @patch('platform.system', return_value='Linux')
    def test_log_entry_exists_success_multiple_matches(self, mock_platform, mock_subprocess_run, tmp_path):
        """Test successful log entry search with multiple matches."""
        log_file = tmp_path / "test.log"
        log_file.write_text("error1\nerror2\nerror3\n")

        mock_subprocess_run.return_value = MagicMock(
            returncode=0,
            stdout='error1\nerror2\nerror3\n',
            stderr=''
        )

        test = LogEntryExists(
            name="test_log",
            parameter=LogEntryExistsParameter(
                log_file=str(log_file),
                pattern="error",
                max_lines=1000
            )
        )
        result = test.test()

        assert_test_success(result)
        assert 'found 3 log entries' in result.details[0]

    @patch('platform.system', return_value='Linux')
    def test_log_entry_exists_failure_no_match(self, mock_platform, mock_subprocess_run, tmp_path):
        """Test failure when log pattern not found."""
        log_file = tmp_path / "test.log"
        log_file.write_text("line1\nline2\nline3\n")

        mock_subprocess_run.return_value = MagicMock(
            returncode=1,
            stdout='',
            stderr=''
        )

        test = LogEntryExists(
            name="test_log",
            parameter=LogEntryExistsParameter(
                log_file=str(log_file),
                pattern="notfound",
                max_lines=1000
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert 'no log entries matching pattern' in result.details[0]

    @patch('platform.system', return_value='Linux')
    def test_log_entry_exists_failure_log_not_found(self, mock_platform, tmp_path):
        """Test failure when log file doesn't exist."""
        log_file = tmp_path / "nonexistent.log"

        test = LogEntryExists(
            name="test_log",
            parameter=LogEntryExistsParameter(
                log_file=str(log_file),
                pattern="error",
                max_lines=1000
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert 'does not exist' in result.details[0]
        assert str(log_file) in result.details[0]

    @patch('platform.system', return_value='Windows')
    def test_log_entry_exists_not_linux(self, mock_platform):
        """Test execution error when not running on Linux."""
        test = LogEntryExists(
            name="test_log",
            parameter=LogEntryExistsParameter(
                log_file="/var/log/syslog",
                pattern="error",
                max_lines=1000
            )
        )
        result = test.test()

        assert_test_execution_error(result)
        assert 'only runs on Linux' in result.details[0]

    @patch('platform.system', return_value='Linux')
    def test_log_entry_exists_timeout(self, mock_platform, mock_subprocess_run, tmp_path):
        """Test execution error when subprocess times out."""
        log_file = tmp_path / "test.log"
        log_file.write_text("test\n")

        mock_subprocess_run.side_effect = subprocess.TimeoutExpired('bash', 30)

        test = LogEntryExists(
            name="test_log",
            parameter=LogEntryExistsParameter(
                log_file=str(log_file),
                pattern="error",
                max_lines=1000
            )
        )
        result = test.test()

        assert_test_execution_error(result)
        assert 'Timeout' in result.details[0]
        assert str(log_file) in result.details[0]

    @patch('platform.system', return_value='Linux')
    def test_log_entry_exists_with_placeholder_log_file(self, mock_platform, mock_subprocess_run, tmp_path, variable_metadata_simple):
        """Test log search with placeholder in log file path."""
        log_file = tmp_path / "value1.log"
        log_file.write_text("error\n")

        mock_subprocess_run.return_value = MagicMock(
            returncode=0,
            stdout='error\n',
            stderr=''
        )

        test = LogEntryExists(
            name="test_log",
            parameter=LogEntryExistsParameter(
                log_file=str(tmp_path / "{{VAR1}}.log"),
                pattern="error",
                max_lines=1000
            ),
            variable_metadata=variable_metadata_simple
        )
        result = test.test()

        assert_test_success(result)
        # Verify bash command uses resolved path
        call_args = mock_subprocess_run.call_args
        assert 'value1.log' in call_args[0][0][2]

    @patch('platform.system', return_value='Linux')
    def test_log_entry_exists_with_placeholder_pattern(self, mock_platform, mock_subprocess_run, tmp_path, variable_metadata_simple):
        """Test log search with placeholder in search pattern."""
        log_file = tmp_path / "test.log"
        log_file.write_text("value2\n")

        mock_subprocess_run.return_value = MagicMock(
            returncode=0,
            stdout='value2\n',
            stderr=''
        )

        test = LogEntryExists(
            name="test_log",
            parameter=LogEntryExistsParameter(
                log_file=str(log_file),
                pattern="{{VAR2}}",
                max_lines=1000
            ),
            variable_metadata=variable_metadata_simple
        )
        result = test.test()

        assert_test_success(result)
        # Verify bash command uses resolved pattern
        call_args = mock_subprocess_run.call_args
        assert 'value2' in call_args[0][0][2]

    @patch('platform.system', return_value='Linux')
    def test_log_entry_exists_custom_max_lines(self, mock_platform, mock_subprocess_run, tmp_path):
        """Test log search with custom max_lines parameter."""
        log_file = tmp_path / "test.log"
        log_file.write_text("error\n")

        mock_subprocess_run.return_value = MagicMock(
            returncode=0,
            stdout='error\n',
            stderr=''
        )

        test = LogEntryExists(
            name="test_log",
            parameter=LogEntryExistsParameter(
                log_file=str(log_file),
                pattern="error",
                max_lines=500
            )
        )
        result = test.test()

        assert_test_success(result)
        # Verify bash command uses custom max_lines
        call_args = mock_subprocess_run.call_args
        assert 'tail -n 500' in call_args[0][0][2]
