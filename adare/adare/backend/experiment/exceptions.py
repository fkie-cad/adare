# internal imports
from adare.exceptions import LoggedException, LoggedErrorException
import logging


class ExperimentFileCreationError(LoggedErrorException):
    pass


class ExperimentDirectoryCreationError(LoggedErrorException):
    pass


class ExperimentRemovalError(LoggedErrorException):
    pass


class ExperimentDirectoryAlreadyExistsError(LoggedErrorException):
    pass


class ExperimentDirectoryDoesNotExistError(LoggedErrorException):
    pass


class ExperimentFileMissingError(LoggedErrorException):
    pass


class ExperimentIntegrityError(LoggedErrorException):
    pass


class EnvironmentIntegrityError(LoggedErrorException):
    pass


class TestfunctionIntegrityError(LoggedErrorException):
    pass


class NoEnvironmentError(LoggedErrorException):
    pass


class MultipleEnvironmentsError(LoggedErrorException):
    pass


class ExperimentAlreadyExistsError(LoggedErrorException):
    pass


class ExperimentNotChanged(LoggedException):
    pass


class ExperimentCommandError(LoggedErrorException):
    def __init__(self, log: logging.Logger, command: str, exit_code: int, stdout: str = '', stderr: str = ''):
        msg = f'Command "{command}" failed with exit code {exit_code}.\nstdout: {stdout}\nstderr: {stderr}'
        super().__init__(log, msg)


class VMSetupError(LoggedErrorException):
    def __init__(self, log: logging.Logger, vm_name: str, command: str, exit_code: int, stdout: str = '', stderr: str = ''):
        msg = f'VM setup failed for "{vm_name}". Command "{command}" failed with exit code {exit_code}.\nstdout: {stdout}\nstderr: {stderr}'
        super().__init__(log, msg)


class AdareVMProcessDiedError(LoggedErrorException):
    """Raised when adarevm process dies immediately after launch."""

    def __init__(
        self,
        log: logging.Logger,
        exit_code: int,
        app_log_excerpt: str = None,
        app_log_fetch_error: str = None,
        startup_log_excerpt: str = None,
        startup_log_fetch_error: str = None
    ):
        """
        Create error message with diagnostic information.

        Args:
            log: Logger instance
            exit_code: Process exit code
            app_log_excerpt: Content from adarevm.log if available
            app_log_fetch_error: Error message if app log fetch failed
            startup_log_excerpt: Content from adarevmstartup.log (stderr) if available
            startup_log_fetch_error: Error message if startup log fetch failed
        """
        msg_parts = [
            f"AdareVM process died immediately after launch (exit code: {exit_code})",
            "",
            "This usually indicates a startup error such as:",
            "  - Missing Python dependencies (numpy, opencv-python, etc.)",
            "  - Import errors in adarevm code",
            "  - Permission denied accessing /adare/run/logs/",
            "  - Port 18765 already in use",
            ""
        ]

        # Show startup error log FIRST (has Python stacktraces and stderr)
        if startup_log_excerpt:
            msg_parts.extend([
                "AdareVM startup errors (stdout/stderr):",
                "=" * 60,
                startup_log_excerpt,
                "=" * 60,
                ""
            ])
        elif startup_log_fetch_error:
            msg_parts.extend([
                f"Could not fetch startup error log: {startup_log_fetch_error}",
                ""
            ])

        # Then show application log (if available)
        if app_log_excerpt:
            msg_parts.extend([
                "AdareVM application log (last 100 lines):",
                "NOTE: If timestamps are old, the process crashed before logging",
                "=" * 60,
                app_log_excerpt,
                "=" * 60,
                ""
            ])
        elif app_log_fetch_error:
            msg_parts.extend([
                f"Could not fetch application log: {app_log_fetch_error}",
                f"Log location: /adare/run/logs/adarevm.log (Linux) or C:\\adare\\run\\logs\\adarevm.log (Windows)",
                ""
            ])

        message = "\n".join(msg_parts)

        solutions = [
            "Check the startup error log (adarevmstartup.log) for Python stacktraces",
            "Verify all Python dependencies are installed in the VM",
            "Ensure /adare/run/logs/ directory exists and is writable",
            "Check if port 18765 is already in use by another process",
            "Try running the adarevm command manually in the VM to see errors"
        ]

        super().__init__(log, message, possible_solutions=solutions)