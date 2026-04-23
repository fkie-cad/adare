"""
VM storage directory management.

Handles creating and managing VM storage directories for both global and project scopes.
"""

import logging
from pathlib import Path

from adare.backend.vm.exceptions import VMStorageError
from adare.config.configdirectory import VMS_DIR

log = logging.getLogger(__name__)


def ensure_global_vm_directory() -> Path:
    """
    Ensure the global VM storage directory exists.

    Returns:
        Path to global VM directory

    Raises:
        VMStorageError: If directory creation fails
    """
    try:
        VMS_DIR.mkdir(parents=True, exist_ok=True)
        log.info(f"Ensured global VM directory exists: {VMS_DIR}")
        return VMS_DIR
    except Exception as e:
        raise VMStorageError(log, f"Failed to create global VM directory: {e}") from e


def ensure_project_vm_directory(project_path: Path) -> Path:
    """
    Ensure the project VM storage directory exists.

    Args:
        project_path: Path to the project directory

    Returns:
        Path to project VM directory

    Raises:
        VMStorageError: If directory creation fails
    """
    try:
        vm_dir = project_path / "vm" # todo: maybe there is some way to get the place dynamically from directory class without providing it everywhere here via args?
        vm_dir.mkdir(parents=True, exist_ok=True)
        log.info(f"Ensured project VM directory exists: {vm_dir}")
        return vm_dir
    except Exception as e:
        raise VMStorageError(log, f"Failed to create project VM directory: {e}") from e


def get_vm_storage_directory(scope: str, project_path: Path = None) -> Path:
    """
    Get the appropriate VM storage directory based on scope.

    Args:
        scope: 'global' or 'project'
        project_path: Required if scope is 'project'

    Returns:
        Path to VM storage directory

    Raises:
        VMStorageError: If scope is invalid or directory creation fails
    """
    if scope == 'global':
        return ensure_global_vm_directory()
    if scope == 'project':
        if not project_path:
            raise VMStorageError(log, "project_path required for project-scoped VM storage")
        return ensure_project_vm_directory(project_path)
    raise VMStorageError(log, f"Invalid scope '{scope}'. Must be 'global' or 'project'")


def generate_vm_filename(name: str, source_path: Path, target_dir: Path) -> Path:
    """
    Generate a unique VM filename in the target directory.

    Args:
        name: VM name
        source_path: Original file path (for extension)
        target_dir: Target directory

    Returns:
        Path to target file (unique name if necessary)
    """
    # Generate target filename with VM name
    target_filename = f"{name}{source_path.suffix}"
    target_path = target_dir / target_filename

    # Generate unique name if target already exists
    if target_path.exists():
        counter = 1
        while target_path.exists():
            target_filename = f"{name}_{counter}{source_path.suffix}"
            target_path = target_dir / target_filename
            counter += 1

    return target_path
