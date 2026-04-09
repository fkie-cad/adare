# external imports
import platform
import subprocess
from pathlib import Path

# Check if Unix modules are available (Linux/Unix only)
try:
    import pwd
    import grp
    UNIX_MODULES_AVAILABLE = True
except ImportError:
    UNIX_MODULES_AVAILABLE = False
    pwd = None
    grp = None

# internal imports
from adarelib.testset.api import testfunction, TestContext
from adarelib.testset.basictest import HostModeCategory
from adarelib.event.event import TestResult

# configure logging
import logging
log = logging.getLogger(__name__)


# Linux-only system tests
@testfunction(
    name='system_service_status',
    description='tests if a systemd service has expected status (Linux only)',
    category=HostModeCategory.QGA_PROBE,
)
def system_service_status(ctx: TestContext, service_name: str, expected_status: str):
    if platform.system() != 'Linux':
        return TestResult.execution_error(None, "This test only runs on Linux")
    try:
        # Handle variables
        if ctx.has_placeholders(service_name):
            service_name = ctx.resolve_variables(service_name)
        if ctx.has_placeholders(expected_status):
            expected_status = ctx.resolve_variables(expected_status)

        # Check service status using systemctl
        try:
            result = subprocess.run(
                ['systemctl', 'is-active', service_name],
                capture_output=True,
                text=True,
                timeout=10
            )

            actual_status = result.stdout.strip()

            if actual_status == expected_status:
                return TestResult.success([f'service {service_name} is {actual_status}'])
            else:
                return TestResult.failed([f'service {service_name} status mismatch. Expected: {expected_status}, Got: {actual_status}'])

        except subprocess.TimeoutExpired:
            return TestResult.execution_error(None, f"Timeout checking service status for {service_name}")
        except (subprocess.SubprocessError, OSError, FileNotFoundError) as e:
            return TestResult.execution_error(e, f"Failed to check service status for {service_name}")

    except Exception as e:
        return TestResult.execution_error(e, "Unexpected error in system service status test")


@testfunction(
    name='process_running',
    description='tests if a process is running with expected number of instances (Linux only)',
    category=HostModeCategory.QGA_PROBE,
)
def process_running(ctx: TestContext, process_name: str, min_instances: int = 1):
    if platform.system() != 'Linux':
        return TestResult.execution_error(None, "This test only runs on Linux")
    try:
        # Handle variables
        if ctx.has_placeholders(process_name):
            process_name = ctx.resolve_variables(process_name)

        # Check running processes using pgrep
        try:
            result = subprocess.run(
                ['pgrep', '-f', process_name],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                # Count process instances
                pids = [pid.strip() for pid in result.stdout.splitlines() if pid.strip()]
                instance_count = len(pids)

                if instance_count >= min_instances:
                    return TestResult.success([f'process {process_name} running with {instance_count} instances (PIDs: {", ".join(pids)})'])
                else:
                    return TestResult.failed([f'process {process_name} has {instance_count} instances, expected at least {min_instances}'])
            else:
                return TestResult.failed([f'process {process_name} is not running'])

        except subprocess.TimeoutExpired:
            return TestResult.execution_error(None, f"Timeout checking process {process_name}")
        except (subprocess.SubprocessError, OSError, FileNotFoundError) as e:
            return TestResult.execution_error(e, f"Failed to check process {process_name}")

    except Exception as e:
        return TestResult.execution_error(e, "Unexpected error in process running test")


@testfunction(
    name='user_exists',
    description='tests if a user account exists with optional UID and home directory checks (Linux only)',
    category=HostModeCategory.QGA_PROBE,
)
def user_exists(ctx: TestContext, username: str, uid: int = None, home_dir: str = None):
    if platform.system() != 'Linux':
        return TestResult.execution_error(None, "This test only runs on Linux")

    if not UNIX_MODULES_AVAILABLE:
        return TestResult.execution_error(None, "Unix modules (pwd, grp) not available")

    try:
        expected_uid = uid
        expected_home = home_dir

        # Handle variables
        if ctx.has_placeholders(username):
            username = ctx.resolve_variables(username)
        if expected_home and ctx.has_placeholders(expected_home):
            expected_home = ctx.resolve_variables(expected_home)

        try:
            # Get user information
            user_info = pwd.getpwnam(username)

            details = [f'user {username} exists (UID: {user_info.pw_uid}, Home: {user_info.pw_dir})']

            # Check UID if specified
            if expected_uid is not None and user_info.pw_uid != expected_uid:
                return TestResult.failed([f'user {username} UID mismatch. Expected: {expected_uid}, Got: {user_info.pw_uid}'])

            # Check home directory if specified
            if expected_home is not None and user_info.pw_dir != expected_home:
                return TestResult.failed([f'user {username} home directory mismatch. Expected: {expected_home}, Got: {user_info.pw_dir}'])

            return TestResult.success(details)

        except KeyError:
            return TestResult.failed([f'user {username} does not exist'])

    except Exception as e:
        return TestResult.execution_error(e, "Unexpected error in user exists test")


@testfunction(
    name='log_entry_exists',
    description='tests if a log file contains entries matching a pattern (Linux only)',
    category=HostModeCategory.QGA_PROBE,
)
def log_entry_exists(ctx: TestContext, log_file: str, pattern: str, max_lines: int = 1000):
    if platform.system() != 'Linux':
        return TestResult.execution_error(None, "This test only runs on Linux")
    try:
        # Handle variables
        if ctx.has_placeholders(log_file):
            log_file = ctx.resolve_variables(log_file)
        if ctx.has_placeholders(pattern):
            pattern = ctx.resolve_variables(pattern)

        # Check if log file exists
        if not Path(log_file).exists():
            return TestResult.failed([f'log file {log_file} does not exist'])

        try:
            # Use tail to get last N lines and grep for pattern
            result = subprocess.run(
                ['bash', '-c', f'tail -n {max_lines} "{log_file}" | grep -E "{pattern}"'],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                matches = result.stdout.strip().splitlines()
                return TestResult.success([f'found {len(matches)} log entries matching pattern in {log_file}'])
            else:
                return TestResult.failed([f'no log entries matching pattern found in {log_file}'])

        except subprocess.TimeoutExpired:
            return TestResult.execution_error(None, f"Timeout searching log file {log_file}")
        except (subprocess.SubprocessError, OSError) as e:
            return TestResult.execution_error(e, f"Failed to search log file {log_file}")

    except Exception as e:
        return TestResult.execution_error(e, "Unexpected error in log entry exists test")
