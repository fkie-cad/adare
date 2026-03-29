# external imports
import attrs
import platform
import subprocess
from pathlib import Path
from typing import ClassVar, Optional, List

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
from adarelib.testset.basictest import BasicTest, Parameter, HostModeCategory
from adarelib.event.event import TestResult

# configure logging
import logging
log = logging.getLogger(__name__)


# Linux-only system tests
@attrs.define
class SystemServiceStatusParameter(Parameter):
    service_name: str
    expected_status: str  # active, inactive, failed, etc.

@attrs.define
class SystemServiceStatus(BasicTest):
    testname: ClassVar[str] = 'system_service_status'
    testdescription: ClassVar[str] = 'tests if a systemd service has expected status (Linux only)'
    host_mode_category: ClassVar[HostModeCategory] = HostModeCategory.QGA_PROBE

    name: str
    parameter: SystemServiceStatusParameter
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    def test(self):
        if platform.system() != 'Linux':
            return TestResult.execution_error(None, "This test only runs on Linux")
        try:
            service_name = self.parameter.service_name
            expected_status = self.parameter.expected_status
            
            # Handle variables
            if self.has_placeholders(service_name):
                service_name = self.resolve_variables(service_name)
            if self.has_placeholders(expected_status):
                expected_status = self.resolve_variables(expected_status)
            
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

@attrs.define
class ProcessRunningParameter(Parameter):
    process_name: str
    min_instances: int = 1  # Minimum number of instances expected

@attrs.define
class ProcessRunning(BasicTest):
    testname: ClassVar[str] = 'process_running'
    testdescription: ClassVar[str] = 'tests if a process is running with expected number of instances (Linux only)'
    host_mode_category: ClassVar[HostModeCategory] = HostModeCategory.QGA_PROBE

    name: str
    parameter: ProcessRunningParameter
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    def test(self):
        if platform.system() != 'Linux':
            return TestResult.execution_error(None, "This test only runs on Linux")
        try:
            process_name = self.parameter.process_name
            min_instances = self.parameter.min_instances
            
            # Handle variables
            if self.has_placeholders(process_name):
                process_name = self.resolve_variables(process_name)
            
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

@attrs.define
class UserExistsParameter(Parameter):
    username: str
    uid: Optional[int] = None
    home_dir: Optional[str] = None

@attrs.define
class UserExists(BasicTest):
    testname: ClassVar[str] = 'user_exists'
    testdescription: ClassVar[str] = 'tests if a user account exists with optional UID and home directory checks (Linux only)'
    host_mode_category: ClassVar[HostModeCategory] = HostModeCategory.QGA_PROBE

    name: str
    parameter: UserExistsParameter
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    def test(self):
        if platform.system() != 'Linux':
            return TestResult.execution_error(None, "This test only runs on Linux")
        
        if not UNIX_MODULES_AVAILABLE:
            return TestResult.execution_error(None, "Unix modules (pwd, grp) not available")
            
        try:
            username = self.parameter.username
            expected_uid = self.parameter.uid
            expected_home = self.parameter.home_dir
            
            # Handle variables
            if self.has_placeholders(username):
                username = self.resolve_variables(username)
            if expected_home and self.has_placeholders(expected_home):
                expected_home = self.resolve_variables(expected_home)
            
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

@attrs.define
class LogEntryExistsParameter(Parameter):
    log_file: str
    pattern: str
    max_lines: int = 1000  # Maximum lines to search from end of file

@attrs.define
class LogEntryExists(BasicTest):
    testname: ClassVar[str] = 'log_entry_exists'
    testdescription: ClassVar[str] = 'tests if a log file contains entries matching a pattern (Linux only)'
    host_mode_category: ClassVar[HostModeCategory] = HostModeCategory.QGA_PROBE

    name: str
    parameter: LogEntryExistsParameter
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    def test(self):
        if platform.system() != 'Linux':
            return TestResult.execution_error(None, "This test only runs on Linux")
        try:
            log_file = self.parameter.log_file
            pattern = self.parameter.pattern
            max_lines = self.parameter.max_lines
            
            # Handle variables
            if self.has_placeholders(log_file):
                log_file = self.resolve_variables(log_file)
            if self.has_placeholders(pattern):
                pattern = self.resolve_variables(pattern)
            
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