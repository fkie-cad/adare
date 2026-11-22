"""Comprehensive unit tests for Linux testfunctions."""

import pytest
import sys
import subprocess
import shlex
from pathlib import Path
from unittest.mock import MagicMock, patch

pytestmark = pytest.mark.unit

# Add paths for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
ADARELIB_ROOT = PROJECT_ROOT.parent / "adarelib"

# Add to sys.path if not already there
if str(ADARELIB_ROOT) not in sys.path:
    sys.path.insert(0, str(ADARELIB_ROOT))

# Import from adarelib.constants as required
from adarelib.constants import StatusEnum

# Import testfunctions dynamically
from adarelib.helper.module import import_module_from_pyfile

# Load Linux testfunctions module
linux_module_path = PROJECT_ROOT / "appdata" / "testfunctions" / "linux" / "linux.py"
linux_module = import_module_from_pyfile(linux_module_path)

# Extract testfunctions from module (decorator pattern: access generated classes via decorated function)
SystemServiceStatus = linux_module.system_service_status._test_class
SystemServiceStatusParameter = linux_module.system_service_status._parameter_class
ProcessRunning = linux_module.process_running._test_class
ProcessRunningParameter = linux_module.process_running._parameter_class
UserExists = linux_module.user_exists._test_class
UserExistsParameter = linux_module.user_exists._parameter_class
LogEntryExists = linux_module.log_entry_exists._test_class
LogEntryExistsParameter = linux_module.log_entry_exists._parameter_class

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
        mock_subprocess_run.return_value = MagicMock(returncode=0, stdout='active\n', stderr='')

        test = SystemServiceStatus(
            name="test_service", parameter=SystemServiceStatusParameter(service_name="nginx", expected_status="active")
        )
        result = test.test()

        assert_test_success(result)
        assert 'nginx' in result.details[0]
        assert 'active' in result.details[0]
        mock_subprocess_run.assert_called_once_with(
            ['systemctl', 'is-active', 'nginx'], capture_output=True, text=True, timeout=10
        )

    @patch('platform.system', return_value='Linux')
    def test_service_status_success_inactive(self, mock_platform, mock_subprocess_run):
        """Test successful service status check with inactive status."""
        mock_subprocess_run.return_value = MagicMock(returncode=3, stdout='inactive\n', stderr='')

        test = SystemServiceStatus(
            name="test_service",
            parameter=SystemServiceStatusParameter(service_name="apache2", expected_status="inactive"),
        )
        result = test.test()

        assert_test_success(result)
        assert 'apache2' in result.details[0]
        assert 'inactive' in result.details[0]

    @patch('platform.system', return_value='Linux')
    def test_service_status_failure_mismatch(self, mock_platform, mock_subprocess_run):
        """Test failure when service status doesn't match expected."""
        mock_subprocess_run.return_value = MagicMock(returncode=3, stdout='inactive\n', stderr='')

        test = SystemServiceStatus(
            name="test_service", parameter=SystemServiceStatusParameter(service_name="nginx", expected_status="active")
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
            name="test_service", parameter=SystemServiceStatusParameter(service_name="nginx", expected_status="active")
        )
        result = test.test()

        assert_test_execution_error(result)
        assert 'only runs on Linux' in result.details[0]

    @patch('platform.system', return_value='Linux')
    def test_service_status_timeout(self, mock_platform, mock_subprocess_run):
        """Test execution error when subprocess times out."""
        mock_subprocess_run.side_effect = subprocess.TimeoutExpired('systemctl', 10)

        test = SystemServiceStatus(
            name="test_service", parameter=SystemServiceStatusParameter(service_name="nginx", expected_status="active")
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
            name="test_service", parameter=SystemServiceStatusParameter(service_name="nginx", expected_status="active")
        )
        result = test.test()

        assert_test_execution_error(result)
        assert 'Failed to check service status' in result.details[0]

    @patch('platform.system', return_value='Linux')
    def test_service_status_with_placeholder(self, mock_platform, mock_subprocess_run, variable_metadata_simple):
        """Test service status check with placeholder in service name."""
        mock_subprocess_run.return_value = MagicMock(returncode=0, stdout='active\n', stderr='')

        test = SystemServiceStatus(
            name="test_service",
            parameter=SystemServiceStatusParameter(service_name="{{VAR1}}", expected_status="active"),
            variable_metadata=variable_metadata_simple,
        )
        result = test.test()

        assert_test_success(result)
        mock_subprocess_run.assert_called_once_with(
            ['systemctl', 'is-active', 'value1'], capture_output=True, text=True, timeout=10
        )


# ============================================================================
# ProcessRunning Tests
# ============================================================================


class TestProcessRunning:
    """Tests for ProcessRunning testfunction."""

    @patch('platform.system', return_value='Linux')
    def test_process_running_success_single_instance(self, mock_platform, mock_subprocess_run):
        """Test successful process check with single instance."""
        mock_subprocess_run.return_value = MagicMock(returncode=0, stdout='1234\n', stderr='')

        test = ProcessRunning(
            name="test_process", parameter=ProcessRunningParameter(process_name="nginx", min_instances=1)
        )
        result = test.test()

        assert_test_success(result)
        assert 'nginx' in result.details[0]
        assert '1 instances' in result.details[0]
        assert '1234' in result.details[0]
        mock_subprocess_run.assert_called_once_with(
            ['pgrep', '-f', 'nginx'], capture_output=True, text=True, timeout=10
        )

    @patch('platform.system', return_value='Linux')
    def test_process_running_success_multiple_instances(self, mock_platform, mock_subprocess_run):
        """Test successful process check with multiple instances."""
        mock_subprocess_run.return_value = MagicMock(returncode=0, stdout='1234\n1235\n1236\n', stderr='')

        test = ProcessRunning(
            name="test_process", parameter=ProcessRunningParameter(process_name="nginx", min_instances=2)
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
        mock_subprocess_run.return_value = MagicMock(returncode=1, stdout='', stderr='')

        test = ProcessRunning(
            name="test_process", parameter=ProcessRunningParameter(process_name="nonexistent", min_instances=1)
        )
        result = test.test()

        assert_test_failed(result)
        assert 'not running' in result.details[0]
        assert 'nonexistent' in result.details[0]

    @patch('platform.system', return_value='Linux')
    def test_process_running_failure_insufficient_instances(self, mock_platform, mock_subprocess_run):
        """Test failure when insufficient process instances."""
        mock_subprocess_run.return_value = MagicMock(returncode=0, stdout='1234\n', stderr='')

        test = ProcessRunning(
            name="test_process", parameter=ProcessRunningParameter(process_name="nginx", min_instances=3)
        )
        result = test.test()

        assert_test_failed(result)
        assert 'has 1 instances' in result.details[0]
        assert 'expected at least 3' in result.details[0]

    @patch('platform.system', return_value='Darwin')
    def test_process_running_not_linux(self, mock_platform):
        """Test execution error when not running on Linux."""
        test = ProcessRunning(
            name="test_process", parameter=ProcessRunningParameter(process_name="nginx", min_instances=1)
        )
        result = test.test()

        assert_test_execution_error(result)
        assert 'only runs on Linux' in result.details[0]

    @patch('platform.system', return_value='Linux')
    def test_process_running_timeout(self, mock_platform, mock_subprocess_run):
        """Test execution error when subprocess times out."""
        mock_subprocess_run.side_effect = subprocess.TimeoutExpired('pgrep', 10)

        test = ProcessRunning(
            name="test_process", parameter=ProcessRunningParameter(process_name="nginx", min_instances=1)
        )
        result = test.test()

        assert_test_execution_error(result)
        assert 'Timeout' in result.details[0]
        assert 'nginx' in result.details[0]

    @patch('platform.system', return_value='Linux')
    def test_process_running_with_placeholder(self, mock_platform, mock_subprocess_run, variable_metadata_simple):
        """Test process check with placeholder in process name."""
        mock_subprocess_run.return_value = MagicMock(returncode=0, stdout='1234\n', stderr='')

        test = ProcessRunning(
            name="test_process",
            parameter=ProcessRunningParameter(process_name="{{VAR2}}", min_instances=1),
            variable_metadata=variable_metadata_simple,
        )
        result = test.test()

        assert_test_success(result)
        mock_subprocess_run.assert_called_once_with(
            ['pgrep', '-f', 'value2'], capture_output=True, text=True, timeout=10
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

                test = UserExists(name="test_user", parameter=UserExistsParameter(username="testuser"))
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

                test = UserExists(name="test_user", parameter=UserExistsParameter(username="testuser", uid=1000))
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
                    name="test_user", parameter=UserExistsParameter(username="testuser", home_dir="/home/testuser")
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

                test = UserExists(name="test_user", parameter=UserExistsParameter(username="nonexistent"))
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

                test = UserExists(name="test_user", parameter=UserExistsParameter(username="testuser", uid=1000))
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
                    name="test_user", parameter=UserExistsParameter(username="testuser", home_dir="/opt/testuser")
                )
                result = test.test()

                assert_test_failed(result)
                assert 'home directory mismatch' in result.details[0]
                assert 'Expected: /opt/testuser' in result.details[0]
                assert 'Got: /home/testuser' in result.details[0]

    @patch('platform.system', return_value='Windows')
    def test_user_exists_not_linux(self, mock_platform):
        """Test execution error when not running on Linux."""
        test = UserExists(name="test_user", parameter=UserExistsParameter(username="testuser"))
        result = test.test()

        assert_test_execution_error(result)
        assert 'only runs on Linux' in result.details[0]

    @patch('platform.system', return_value='Linux')
    def test_user_exists_modules_not_available(self, mock_platform):
        """Test execution error when Unix modules not available."""
        with patch.object(linux_module, 'UNIX_MODULES_AVAILABLE', False):
            test = UserExists(name="test_user", parameter=UserExistsParameter(username="testuser"))
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
                    parameter=UserExistsParameter(username="{{VAR1}}"),
                    variable_metadata=variable_metadata_simple,
                )
                result = test.test()

                assert_test_success(result)
                mock_pwd.getpwnam.assert_called_once_with('value1')


# ============================================================================
# LogEntryExists Tests
# ============================================================================


class TestLogEntryExists:
    """linux.log_entry_exists reads the log in Python: dst/globs/archives, regex or substring."""

    @staticmethod
    def _run(variable_metadata=None, **params):
        return LogEntryExists(
            name="test_log", parameter=LogEntryExistsParameter(**params), variable_metadata=variable_metadata or {}
        ).test()

    def test_regex_match_found(self, tmp_path):
        log = tmp_path / "auth.log"
        log.write_text("boot\nsession opened for user alice by (uid=0)\n")

        result = self._run(dst=str(log), content=r"session opened for user \w+")

        assert_test_success(result)
        assert "1 log entries" in result.details[0]

    def test_substring_mode_takes_content_literally(self, tmp_path):
        log = tmp_path / "app.log"
        log.write_text("price: $(5) [x]\n")

        assert_test_success(self._run(dst=str(log), content="$(5) [x]", regex_match=False))
        assert_test_failed(self._run(dst=str(log), content="$(6)", regex_match=False))

    def test_shell_metacharacters_are_not_executed(self, tmp_path):
        marker = tmp_path / "pwned"
        log = tmp_path / "app.log"
        log.write_text("nothing here\n")

        result = self._run(dst=str(log), content=f"x'; touch {marker}; echo '")

        assert_test_failed(result)
        assert not marker.exists()

    def test_no_match_fails(self, tmp_path):
        log = tmp_path / "app.log"
        log.write_text("all good\n")

        result = self._run(dst=str(log), content="error")

        assert_test_failed(result)
        assert "no log entry" in result.details[0]

    def test_only_the_last_max_lines_are_searched(self, tmp_path):
        log = tmp_path / "app.log"
        log.write_text("error early\n" + "ok\n" * 5)

        assert_test_failed(self._run(dst=str(log), content="error", max_lines=5))
        assert_test_success(self._run(dst=str(log), content="error", max_lines=6))

    def test_missing_log_is_an_error(self, tmp_path):
        result = self._run(dst=str(tmp_path / "missing.log"), content="error")

        assert result.status == StatusEnum.ERROR, result.details

    def test_invalid_regex_is_an_error(self, tmp_path):
        log = tmp_path / "app.log"
        log.write_text("x\n")

        result = self._run(dst=str(log), content="[unclosed")

        assert result.status == StatusEnum.ERROR, result.details
        assert "invalid regex" in result.details[0]

    @pytest.mark.parametrize("max_lines", [0, -1, True])
    def test_bad_max_lines_is_an_error(self, tmp_path, max_lines):
        log = tmp_path / "app.log"
        log.write_text("x\n")

        result = self._run(dst=str(log), content="x", max_lines=max_lines)

        assert result.status == StatusEnum.ERROR, result.details

    def test_glob_dst(self, tmp_path):
        (tmp_path / "app.2026.log").write_text("error here\n")

        assert_test_success(self._run(dst=str(tmp_path / "app.*.log"), content="error"))

    def test_compressed_rotated_log_via_archive_path(self, tmp_path):
        import gzip

        rotated = tmp_path / "syslog.2.gz"
        rotated.write_bytes(gzip.compress(b"kernel: usb disconnect\n"))

        assert_test_success(self._run(dst=f"{rotated}!", content="usb disconnect"))

    def test_utf16_log_and_undecodable_bytes(self, tmp_path):
        utf16 = tmp_path / "win.log"
        utf16.write_bytes("\ufeffevent: login\n".encode("utf-16-le"))
        broken = tmp_path / "bin.log"
        broken.write_bytes(b"\x80\x81\xfa garbage\nevent: login\n")

        assert_test_success(self._run(dst=str(utf16), content="event: login"))
        assert_test_success(self._run(dst=str(broken), content="event: login"))

    def test_placeholder_in_content_is_an_error(self, tmp_path, variable_metadata_simple):
        # a !re/!timestamp placeholder would be searched as text: ERROR, like text.* does
        log = tmp_path / "app.log"
        log.write_text("user value2 logged in\n")

        for content in ("user {{VAR2}}", "{{ NOPE }}"):
            result = self._run(variable_metadata=variable_metadata_simple, dst=str(log), content=content)
            assert result.status == StatusEnum.ERROR, result.details

    def test_posix_class_is_an_error(self, tmp_path):
        log = tmp_path / "auth.log"
        log.write_text("user alice\n")

        result = self._run(dst=str(log), content="user[[:space:]]alice")

        assert result.status == StatusEnum.ERROR, result.details
        assert "POSIX class" in result.details[0]
