"""
Database API for VM management.

This package provides functions for managing VMs in both global and project scopes,
including loading, validation, and database operations.
"""

import logging
from pathlib import Path

from adare.config.configdirectory import VMS_DIR
from adare.database.api.base import GlobalDatabaseApi

from .core import VmCrudMixin
from .exceptions import VMLoadError, VMNameConflictError, VMNotFoundError, VMValidationError
from .instances import VmInstanceMixin
from .snapshots import VmSnapshotMixin
from .validation import VmValidationMixin

log = logging.getLogger(__name__)


class VmApi(VmCrudMixin, VmValidationMixin, VmInstanceMixin, VmSnapshotMixin, GlobalDatabaseApi):
    """
    Database API for global VM management operations.

    Handles globally shared VMs with validation and loading capabilities.
    All VMs are now stored in the global database and shared across projects.
    """

    def __init__(self):
        super().__init__()
        self._start_session()
        # VM table is automatically created by GlobalDatabaseApi


def ensure_vm_directories():
    """
    Ensure VM storage directories exist.

    Creates the global VM directory if it doesn't exist.
    """
    VMS_DIR.mkdir(parents=True, exist_ok=True)
    log.info(f"Ensured global VM directory exists: {VMS_DIR}")


def load_vm_from_file(project_path: Path, file_path: Path, name: str = None, description: str = '',
                     os_platform: str = '', os_type: str = '', os_distribution: str = '',
                     os_version: str = '', os_language: str = '', os_architecture: str = 'x86_64',
                     silent: bool = False):
    """
    Load a VM from file into the database.

    Args:
        project_path: Project path
        file_path: Path to VM file
        name: VM name (defaults to filename without extension)
        description: VM description
        os_platform: OS platform (windows, linux, etc.)
        os_type: OS type
        os_distribution: OS distribution
        os_version: OS version
        os_language: OS language
        os_architecture: Architecture (default: x86_64)
        silent: If True, suppress progress bars during validation

    Returns:
        Created VM instance

    Raises:
        VMLoadError: If loading fails
    """
    if not name:
        name = file_path.stem

    api = VMDatabaseApi()
    return api.create_vm(
        project_path=project_path,
        name=name,
        file_path=file_path,
        file_hash=api._calculate_file_hash(file_path, quiet=silent),
        description=description,
        os_platform=os_platform,
        os_type=os_type,
        os_distribution=os_distribution,
        os_version=os_version,
        os_language=os_language,
        os_architecture=os_architecture,
        silent=silent
    )


# Convenience alias for backward compatibility
VMDatabaseApi = VmApi

__all__ = [
    'VmApi',
    'VMDatabaseApi',
    'VMNotFoundError',
    'VMValidationError',
    'VMLoadError',
    'VMNameConflictError',
    'ensure_vm_directories',
    'load_vm_from_file',
]
