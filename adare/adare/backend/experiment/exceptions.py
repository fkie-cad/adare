# internal imports
import logging

from adare.exceptions import LoggedErrorException, LoggedException

# ---------------------------------------------------------------------------
# Root exception for all experiment errors
# ---------------------------------------------------------------------------

class ExperimentException(LoggedErrorException):
    """Base class for all experiment-related errors."""
    pass


# ---------------------------------------------------------------------------
# File system group
# ---------------------------------------------------------------------------

class ExperimentFileSystemError(ExperimentException):
    """Group base for file/directory errors within experiments."""
    pass


class ExperimentFileCreationError(ExperimentFileSystemError):
    pass


class ExperimentDirectoryCreationError(ExperimentFileSystemError):
    pass


class ExperimentRemovalError(ExperimentFileSystemError):
    pass


class ExperimentDirectoryAlreadyExistsError(ExperimentFileSystemError):
    pass


class ExperimentDirectoryDoesNotExistError(ExperimentFileSystemError):
    pass


class ExperimentFileMissingError(ExperimentFileSystemError):
    pass


# ---------------------------------------------------------------------------
# Integrity group
# ---------------------------------------------------------------------------

class ExperimentIntegrityError(ExperimentException):
    """Integrity check failures (hash mismatches, modified files, etc.)."""

    @classmethod
    def file_modified(cls, log: logging.Logger, file_type: str, file_name: str,
                      reload_command: str):
        """For 'file was modified after loading' errors."""
        return cls(
            log,
            f'{file_type} "{file_name}" has been modified after loading into the experiment',
            possible_solutions=[
                f'Reload with: {reload_command}',
                'Check for unauthorized file modifications',
            ],
        )

    @classmethod
    def file_not_found(cls, log: logging.Logger, file_type: str, file_path: str,
                       is_external: bool = False):
        """For missing file errors."""
        solutions = [f'Check that the {file_type} file exists at: {file_path}']
        if is_external:
            solutions.append('Verify the external path is accessible')
        else:
            solutions.append(
                f'Ensure the {file_type} was properly loaded into the experiment'
            )
        return cls(log, f'{file_type} not found: {file_path}',
                   possible_solutions=solutions)

    @classmethod
    def files_changed_after_load(cls, log: logging.Logger, file_type: str,
                                  changed_files: list, remove_command: str,
                                  load_command: str):
        """For 'files changed, need re-load' errors."""
        files_str = ', '.join(str(f) for f in changed_files[:5])
        if len(changed_files) > 5:
            files_str += f' (and {len(changed_files) - 5} more)'
        return cls(
            log,
            f'{file_type} files have changed since they were loaded: {files_str}',
            possible_solutions=[
                f'Remove changed files: {remove_command}',
                f'Reload: {load_command}',
            ],
        )

    @classmethod
    def hash_mismatch(cls, log: logging.Logger, file_type: str, file_name: str):
        """For integrity hash mismatch errors."""
        return cls(
            log,
            f'{file_type} "{file_name}" integrity check failed - content hash does not match stored hash',
            possible_solutions=[
                f'Reload the {file_type} to update the stored hash',
                'Check for unauthorized modifications to the file',
            ],
        )

    @classmethod
    def vm_integrity_failed(cls, log: logging.Logger, vm_name: str, detail: str):
        """For VM integrity failures."""
        return cls(
            log,
            f'VM "{vm_name}" integrity check failed: {detail}',
            possible_solutions=[
                'Verify the VM file exists and is not corrupted',
                'Re-import the VM file',
            ],
        )


class EnvironmentIntegrityError(ExperimentIntegrityError):
    pass


class TestfunctionIntegrityError(ExperimentIntegrityError):
    pass


# ---------------------------------------------------------------------------
# Config group
# ---------------------------------------------------------------------------

class ExperimentConfigError(ExperimentException):
    """Group base for experiment configuration errors."""
    pass


class NoEnvironmentError(ExperimentConfigError):
    pass


class MultipleEnvironmentsError(ExperimentConfigError):
    pass


# ---------------------------------------------------------------------------
# Direct children of ExperimentException (no sub-group)
# ---------------------------------------------------------------------------

class ExperimentAlreadyExistsError(ExperimentException):
    pass


class ExperimentCommandError(ExperimentException):
    def __init__(self, log: logging.Logger, command: str, exit_code: int,
                 stdout: str = '', stderr: str = ''):
        msg = (f'Command "{command}" failed with exit code {exit_code}.'
               f'\nstdout: {stdout}\nstderr: {stderr}')
        super().__init__(log, msg)


class VMSetupError(ExperimentException):
    def __init__(self, log: logging.Logger, vm_name: str, command: str,
                 exit_code: int, stdout: str = '', stderr: str = ''):
        msg = (f'VM setup failed for "{vm_name}". Command "{command}" failed '
               f'with exit code {exit_code}.\nstdout: {stdout}\nstderr: {stderr}')
        super().__init__(log, msg)


class AdareVMProcessDiedError(ExperimentException):
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
                "Log location: /adare/run/logs/adarevm.log (Linux) or C:\\adare\\run\\logs\\adarevm.log (Windows)",
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


# ---------------------------------------------------------------------------
# Non-error exception (kept separate from ExperimentException)
# ---------------------------------------------------------------------------

class ExperimentNotChanged(LoggedException):
    pass
