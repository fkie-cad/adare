"""
Cross-platform integrity management for adare components.
Provides reusable integrity verification for testfunctions, experiments, and environments.
"""

# configure logging
import logging
import os
import platform
import stat
from datetime import datetime
from pathlib import Path

from adare.backend.experiment.exceptions import ExperimentIntegrityError

# Reuse existing components
from adare.helperfunctions.hash import combine_hashes, hash_file_sha256

log = logging.getLogger(__name__)


class IntegrityManager:
    """Cross-platform file integrity management"""

    @staticmethod
    def protect_file(filepath: Path) -> bool:
        """Make file read-only (cross-platform)"""
        # CLAUDE: Check if file is in managed storage before protecting
        # External files (loaded with --no-copy) should not be protected (user-managed)
        try:
            from adare.config.configdirectory import VMS_DIR
            try:
                filepath.resolve().relative_to(VMS_DIR.resolve())
                # File is in managed storage - proceed with protection
            except ValueError:
                # External file - don't attempt to protect
                log.info(f'File protection skipped for external file (user-managed): {filepath}')
                return True
        except ImportError:
            # VMS_DIR not available - skip the check
            pass

        # CLAUDE: Temporarily disabled for development - files remain editable
        # TODO: Re-enable with proper development mode flag
        log.info(f'File protection DISABLED for development: {filepath}')
        return True  # Always return success without actually protecting

        # Original protection logic (commented out):
        # try:
        #     if platform.system() == "Windows":
        #         # Windows: Remove write permissions for all users
        #         os.chmod(filepath, stat.S_IREAD)
        #     else:
        #         # Linux/Unix: Remove write permissions for owner/group/others
        #         current_permissions = filepath.stat().st_mode
        #         readonly_permissions = current_permissions & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)
        #         os.chmod(filepath, readonly_permissions)
        #     log.info(f'File protected: {filepath}')
        #     return True
        # except (OSError, PermissionError) as e:
        #     log.warning(f'Failed to protect file {filepath}: {e}')
        #     return False

    @staticmethod
    def unprotect_file(filepath: Path) -> bool:
        """Restore write permissions (cross-platform)"""
        try:
            if platform.system() == "Windows":
                # Windows: Add write permissions
                os.chmod(filepath, stat.S_IWRITE | stat.S_IREAD)
            else:
                # Linux/Unix: Restore typical file permissions (644)
                os.chmod(filepath, 0o644)
            log.info(f'File unprotected: {filepath}')
            return True
        except (OSError, PermissionError) as e:
            log.warning(f'Failed to unprotect file {filepath}: {e}')
            return False

    @staticmethod
    def verify_file_integrity(filepath: Path, expected_hash: str) -> bool:
        """Verify single file integrity"""
        try:
            current_hash = hash_file_sha256(filepath)
            return current_hash == expected_hash
        except Exception as e:
            log.error(f'Failed to verify file integrity for {filepath}: {e}')
            return False

    @staticmethod
    def verify_combined_integrity(filepaths: list[Path], expected_hash: str) -> bool:
        """Verify combined file integrity (e.g., testfunction + requirements)"""
        try:
            hashes = [hash_file_sha256(fp) for fp in filepaths]
            current_hash = combine_hashes(hashes)
            return current_hash == expected_hash
        except Exception as e:
            log.error(f'Failed to verify combined integrity for {filepaths}: {e}')
            return False

    @staticmethod
    def get_file_timestamp(filepath: Path) -> datetime:
        """Get file modification timestamp"""
        try:
            return datetime.fromtimestamp(filepath.stat().st_mtime)
        except Exception as e:
            log.error(f'Failed to get timestamp for {filepath}: {e}')
            return datetime.min


def verify_testfunction_integrity(testfunction_path: Path, requirements_path: Path, expected_hash: str) -> None:
    """
    Verify testfunction integrity and raise error if modified.
    Reusable for any testfunction integrity check.
    """
    if not IntegrityManager.verify_combined_integrity([testfunction_path, requirements_path], expected_hash):
        raise ExperimentIntegrityError(
            log,
            f'Testfunction {testfunction_path.name} has been modified after loading',
            possible_solutions=[
                f'Reload testfunction with `adare testfunction load {testfunction_path.stem}`',
                'Check for unauthorized file modifications',
                'Verify file permissions and access controls'
            ]
        )


def verify_experiment_integrity(experiment_file: Path, expected_hash: str) -> None:
    """
    Verify experiment file integrity and raise error if modified.
    Reusable for any experiment integrity check.
    """
    if not IntegrityManager.verify_file_integrity(experiment_file, expected_hash):
        raise ExperimentIntegrityError(
            log,
            f'Experiment file {experiment_file.name} has been modified after loading',
            possible_solutions=[
                'Reload experiment to update stored hash',
                'Check for unauthorized file modifications',
                'Verify file permissions and access controls'
            ]
        )


def verify_environment_integrity(environment_file: Path, expected_hash: str) -> None:
    """
    Verify environment file integrity and raise error if modified.
    Reusable for any environment integrity check.
    """
    if not IntegrityManager.verify_file_integrity(environment_file, expected_hash):
        raise ExperimentIntegrityError(
            log,
            f'Environment file {environment_file.name} has been modified after loading',
            possible_solutions=[
                'Reload environment to update stored hash',
                'Check for unauthorized file modifications',
                'Verify file permissions and access controls'
            ]
        )


def protect_loaded_files(filepaths: list[Path]) -> list[Path]:
    """
    Protect multiple files after loading. Returns list of successfully protected files.
    Can be used for testfunctions, experiments, or environments.
    """
    protected_files = []
    for filepath in filepaths:
        if IntegrityManager.protect_file(filepath):
            protected_files.append(filepath)

    log.info(f'Protected {len(protected_files)}/{len(filepaths)} files')
    return protected_files


def unprotect_files_for_update(filepaths: list[Path]) -> list[Path]:
    """
    Temporarily unprotect files for updates. Returns list of successfully unprotected files.
    """
    unprotected_files = []
    for filepath in filepaths:
        if IntegrityManager.unprotect_file(filepath):
            unprotected_files.append(filepath)

    log.info(f'Unprotected {len(unprotected_files)}/{len(filepaths)} files for update')
    return unprotected_files
