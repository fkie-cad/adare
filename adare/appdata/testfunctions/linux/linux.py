# external imports
import collections
import platform
import re
import shlex
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
from adarelib.testset.content import open_text

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
    """Pass when ``systemctl is-active <service_name>`` prints exactly ``expected_status``.

    Use for: checking a systemd unit was started/stopped by an action. Linux guests only
    (other OSes, a missing ``systemctl`` or a 10 s timeout are execution errors).

    Args:
        service_name: Unit name as given to systemctl, e.g. ``ssh`` or ``cups.service``.
        expected_status: Exact, case-sensitive ``is-active`` output: ``active``, ``inactive``,
            ``failed``, ``activating``, ``deactivating`` ... (unknown units usually print ``inactive``).

    Example:
        function: linux.system_service_status
        parameter:
          service_name: ssh
          expected_status: active
    """
    if platform.system() != 'Linux':
        return TestResult.execution_error(None, "This test only runs on Linux")
    # Handle variables
    if ctx.has_placeholders(service_name):
        service_name = ctx.resolve_variables(service_name)
    if ctx.has_placeholders(expected_status):
        expected_status = ctx.resolve_variables(expected_status)

    # Check service status using systemctl
    try:
        result = subprocess.run(['systemctl', 'is-active', service_name], capture_output=True, text=True, timeout=10)

        actual_status = result.stdout.strip()

        if actual_status == expected_status:
            return TestResult.success([f'service {service_name} is {actual_status}'])
        return TestResult.failed(
            [f'service {service_name} status mismatch. Expected: {expected_status}, Got: {actual_status}']
        )

    except subprocess.TimeoutExpired:
        return TestResult.execution_error(None, f"Timeout checking service status for {service_name}")
    except (subprocess.SubprocessError, OSError, FileNotFoundError) as e:
        return TestResult.execution_error(e, f"Failed to check service status for {service_name}")


@testfunction(
    name='process_running',
    description='tests if a process is running with expected number of instances (Linux only)',
    category=HostModeCategory.QGA_PROBE,
)
def process_running(ctx: TestContext, process_name: str, min_instances: int = 1):
    """Pass when ``pgrep -f process_name`` finds at least ``min_instances`` processes.

    Use for: checking an application/daemon is (still) running after an action. Linux only.
    No matching process always fails, even with ``min_instances: 0``.

    Args:
        process_name: Extended regex matched against each process's FULL command line
            (``pgrep -f``), so ``someapp`` also matches ``/usr/lib/someapp/someapp --worker``.
        min_instances: Minimum number of matching PIDs (default 1).

    Example:
        function: linux.process_running
        parameter:
          process_name: someapp
    """
    if platform.system() != 'Linux':
        return TestResult.execution_error(None, "This test only runs on Linux")
    # Handle variables
    if ctx.has_placeholders(process_name):
        process_name = ctx.resolve_variables(process_name)

    # Check running processes using pgrep
    try:
        result = subprocess.run(['pgrep', '-f', process_name], capture_output=True, text=True, timeout=10)

        if result.returncode == 0:
            # Count process instances
            pids = [pid.strip() for pid in result.stdout.splitlines() if pid.strip()]
            instance_count = len(pids)

            if instance_count >= min_instances:
                return TestResult.success(
                    [f'process {process_name} running with {instance_count} instances (PIDs: {", ".join(pids)})']
                )
            return TestResult.failed(
                [f'process {process_name} has {instance_count} instances, expected at least {min_instances}']
            )
        return TestResult.failed([f'process {process_name} is not running'])

    except subprocess.TimeoutExpired:
        return TestResult.execution_error(None, f"Timeout checking process {process_name}")
    except (subprocess.SubprocessError, OSError, FileNotFoundError) as e:
        return TestResult.execution_error(e, f"Failed to check process {process_name}")


@testfunction(
    name='user_exists',
    description='tests if a user account exists with optional UID and home directory checks (Linux only)',
    category=HostModeCategory.QGA_PROBE,
)
def user_exists(ctx: TestContext, username: str, uid: int = None, home_dir: str = None):
    """Pass when local user ``username`` exists (``pwd.getpwnam``) and optional UID/home match.

    Use for: verifying an account was created by an installer or admin action. Linux only.

    Args:
        username: Login name, exact and case-sensitive.
        uid: Expected numeric UID; ``None`` skips the check.
        home_dir: Expected home directory, compared as an exact string (a trailing ``/``
            matters); ``None`` skips the check.

    Example:
        function: linux.user_exists
        parameter:
          username: alice
          home_dir: /home/alice
    """
    if platform.system() != 'Linux':
        return TestResult.execution_error(None, "This test only runs on Linux")

    if not UNIX_MODULES_AVAILABLE:
        return TestResult.execution_error(None, "Unix modules (pwd, grp) not available")

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
            return TestResult.failed(
                [f'user {username} UID mismatch. Expected: {expected_uid}, Got: {user_info.pw_uid}']
            )

        # Check home directory if specified
        if expected_home is not None and user_info.pw_dir != expected_home:
            return TestResult.failed(
                [f'user {username} home directory mismatch. Expected: {expected_home}, Got: {user_info.pw_dir}']
            )

        return TestResult.success(details)

    except KeyError:
        return TestResult.failed([f'user {username} does not exist'])


def _last_lines(path: str, max_lines: int) -> list[str]:
    """The last ``max_lines`` lines of text file ``path`` (encoding auto-detected; bad bytes replaced)."""
    with open_text(path, errors='replace') as f:
        return [line.rstrip('\r\n') for line in collections.deque(f, maxlen=max_lines)]


@testfunction(
    name='log_entry_exists',
    description='tests if one of the last lines of a text log contains a string or matches a regex',
    category=HostModeCategory.FILE_CONTENT,
)
def log_entry_exists(ctx: TestContext, dst: str, content: str, regex_match: bool = True, max_lines: int = 1000):
    """Pass when one of the last ``max_lines`` lines of text log ``dst`` matches ``content``.

    Use for: checking an action left a trace in a plain-text log (syslog, auth.log, app
    logs; not the binary journal). To count entries, or to search the whole file, use
    text.line_count.

    Args:
        dst: Guest path of the log; a glob must match exactly one path, ``archive!member``
            reads a rotated, compressed log (``/var/log/syslog.2.gz!``). A missing file is an
            error. The encoding is detected (BOM, UTF-16, else UTF-8); undecodable bytes are
            replaced, so binary garbage does not stop the search.
        content: With ``regex_match`` (default) a Python regex searched in each line
            (``re.search``, case-sensitive; ``(?i)`` for case-insensitive); an invalid regex, a
            POSIX class (``[[:space:]]``) or a ``!re``/``!timestamp`` tag is an error. Otherwise
            a substring a line must contain.
        regex_match: ``True`` (default): ``content`` is a regex; ``False``: a plain substring.
        max_lines: How many trailing lines to search (default 1000); must be positive.

    Example:
        function: linux.log_entry_exists
        parameter:
          dst: /var/log/auth.log
          content: 'session opened for user alice'
    """
    if isinstance(max_lines, bool) or not isinstance(max_lines, int) or max_lines < 1:
        return TestResult.error([f'max_lines must be a positive integer, got {max_lines!r}'])
    if ctx.has_placeholders(content):
        return TestResult.error(
            [
                f'content {content!r} holds a !re or !timestamp placeholder, which is not supported here; '
                'write the pattern as plain content with regex_match: true'
            ]
        )
    if regex_match and '[[:' in content:
        # grep -E syntax from before the rewrite: Python reads it as a plain character set and
        # would silently never match
        return TestResult.error([f'content {content!r} uses a POSIX class ([[:...:]]); write \\s, \\d or [a-z]'])
    try:
        regex = re.compile(content) if regex_match else None
    except re.error as e:
        return TestResult.error([f'invalid regex {content!r}: {e}'])
    path, status = ctx.resolve_globfilepath(dst)
    if not path:
        return TestResult.error([f'log file {dst} not found ({status})'])
    try:
        lines = _last_lines(path, max_lines)
    except FileNotFoundError:
        return TestResult.error([f'log file {dst} does not exist'])
    except IsADirectoryError:
        return TestResult.error([f'log file {dst} is a directory'])
    except OSError as e:
        return TestResult.execution_error(e, f'Cannot read log file {dst}')
    if regex is not None:
        matches = [line for line in lines if regex.search(line)]
    else:
        matches = [line for line in lines if content in line]
    if matches:
        return TestResult.success(
            [f'found {len(matches)} log entries matching {content!r} in {dst}', f'first: {matches[0][:300]}']
        )
    return TestResult.failed([f'no log entry matching {content!r} in the last {len(lines)} line(s) of {dst}'])
