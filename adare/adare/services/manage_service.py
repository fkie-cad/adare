"""
Manage Service - Business logic for database and system management operations.

This service handles database management operations and returns Result[T] objects
that can be consumed by any frontend (CLI, Web UI, REST API).
"""
from pathlib import Path
from typing import Optional

import logging

from adare.config.database import get_global_database_location
from adare.database.init import (
    initialize_database_system,
    validate_database_integrity,
    repair_database_system,
    clean_install_database_system,
)
from adare.core.result import Result
from adare.core.dto.manage import (
    DbStatusResult,
    DbInitResult,
    DbRepairResult,
    DbCleanInstallResult,
    DbResetResult,
    VmResetResult,
    VmRuntimeRefreshResult,
)

log = logging.getLogger(__name__)


class ManageService:
    """
    Service for database and system management operations.

    All methods return Result[T] objects for consistent error handling
    across different frontends.
    """

    # =========================================================================
    # Database Operations
    # =========================================================================

    def get_db_status(self) -> Result[DbStatusResult]:
        """
        Check database system status.

        Returns:
            Result[DbStatusResult] with database status info.
        """
        try:
            status = validate_database_integrity()

            return Result.ok(DbStatusResult(
                global_db_exists=status.get('global_db_exists', False),
                global_db_accessible=status.get('global_db_accessible', False),
                global_db_location=Path(status['global_db_location']) if status.get('global_db_location') else None,
                valid=status.get('valid', False),
                errors=status.get('errors', []),
            ))

        except Exception as e:
            log.error(f"Failed to check database status: {e}")
            return Result.fail(
                code="DbStatusError",
                message=f"Failed to check database status: {e}",
                solutions=['Check if database files are accessible']
            )

    def init_db(self) -> Result[DbInitResult]:
        """
        Initialize the database system.

        Returns:
            Result[DbInitResult] with initialization results.
        """
        try:
            results = initialize_database_system()

            return Result.ok(DbInitResult(
                global_db_initialized=results.get('global_db_initialized', False),
                global_db_location=Path(results['global_db_location']) if results.get('global_db_location') else None,
                errors=results.get('errors', []),
            ))

        except Exception as e:
            log.error(f"Failed to initialize database: {e}")
            return Result.fail(
                code="DbInitError",
                message=f"Failed to initialize database: {e}",
                solutions=['Check file system permissions', 'Ensure config directory is writable']
            )

    def repair_db(self) -> Result[DbRepairResult]:
        """
        Repair the database system.

        Returns:
            Result[DbRepairResult] with repair results.
        """
        try:
            results = repair_database_system()

            return Result.ok(DbRepairResult(
                repaired=results.get('repaired', False),
                actions_taken=results.get('actions_taken', []),
                errors=results.get('errors', []),
            ))

        except Exception as e:
            log.error(f"Failed to repair database: {e}")
            return Result.fail(
                code="DbRepairError",
                message=f"Failed to repair database: {e}",
                solutions=['Try running with elevated permissions', 'Check file system health']
            )

    def clean_install_db(self, force: bool = False) -> Result[DbCleanInstallResult]:
        """
        Perform clean database installation.

        Note: This deletes ALL existing data. Use with caution.
        For API/Web use, force=True skips confirmation.

        Args:
            force: Skip confirmation and force clean install

        Returns:
            Result[DbCleanInstallResult] with installation results.
        """
        if not force:
            return Result.fail(
                code="ConfirmationRequired",
                message="Clean installation requires confirmation",
                solutions=['Use force=True to confirm deletion of all data']
            )

        try:
            results = clean_install_database_system()

            return Result.ok(DbCleanInstallResult(
                installed=results.get('installed', False),
                actions_taken=results.get('actions_taken', []),
                errors=results.get('errors', []),
            ))

        except Exception as e:
            log.error(f"Failed clean database installation: {e}")
            return Result.fail(
                code="DbCleanInstallError",
                message=f"Failed clean database installation: {e}",
                solutions=['Check file system permissions', 'Ensure no processes are using the database']
            )

    def reset_db(self) -> Result[DbResetResult]:
        """
        Reset the global database.

        Returns:
            Result[DbResetResult] with reset results.
        """
        try:
            database_location = get_global_database_location()

            if database_location.exists():
                database_location.unlink()
                log.info(f'Removed global database: {database_location}')

                return Result.ok(DbResetResult(
                    was_reset=True,
                    location=database_location,
                ))
            else:
                return Result.ok(DbResetResult(
                    was_reset=False,
                    location=database_location,
                ))

        except Exception as e:
            log.error(f"Failed to reset database: {e}")
            return Result.fail(
                code="DbResetError",
                message=f"Failed to reset database: {e}",
                solutions=['Check file permissions', 'Ensure database is not in use']
            )

    # =========================================================================
    # VM Management Operations
    # =========================================================================

    def reset_all_vms(self, force: bool = False) -> Result[VmResetResult]:
        """
        Reset all VMs in the system.

        Args:
            force: Skip confirmation and force reset

        Returns:
            Result[VmResetResult] with reset results.
        """
        from adare.backend.vm.commands import clear_all_vms, list_all_vms

        if not force:
            return Result.fail(
                code="ConfirmationRequired",
                message="VM reset requires confirmation",
                solutions=['Use force=True to confirm deletion of all VMs']
            )

        try:
            results = clear_all_vms(force=True)

            return Result.ok(VmResetResult(
                deleted_count=results.get('deleted_count', 0),
                failed_count=results.get('failed_count', 0),
                deleted_vms=results.get('deleted_vms', []),
                failed_vms=results.get('failed_vms', []),
            ))

        except Exception as e:
            log.error(f"Failed to reset VMs: {e}")
            return Result.fail(
                code="VmResetError",
                message=f"Failed to reset VMs: {e}",
                solutions=['Check if VMs are in use', 'Try stopping running VMs first']
            )

    def refresh_vm_runtime(self, project_path: Optional[Path] = None) -> Result[VmRuntimeRefreshResult]:
        """
        Refresh VM runtime files in a project.

        Args:
            project_path: Optional project path. If None, uses current project.

        Returns:
            Result[VmRuntimeRefreshResult] with refresh results.
        """
        import shutil
        from adare.backend.basics import determine_projectdirectory
        from adare.backend.project.directory import ProjectDirectory
        from adare.exceptions import NoProjectFoundError

        try:
            # Resolve project path
            if project_path is None:
                project_path = determine_projectdirectory(project_name=None)
                if not project_path:
                    return Result.fail(
                        code="NoProjectFoundError",
                        message="No project directory found",
                        solutions=[
                            'Run this command from within a project directory',
                            'Specify a project path explicitly'
                        ]
                    )

            project_vm_runtime = project_path / 'vm_runtime'

            # Remove existing vm_runtime if it exists
            if project_vm_runtime.exists():
                shutil.rmtree(project_vm_runtime)
                log.info(f'Removed existing VM runtime cache: {project_vm_runtime}')

            # Initialize/recreate vm_runtime with fresh files
            project_dir = ProjectDirectory(project_path)
            project_dir.copy_vm_runtime_files()

            return Result.ok(VmRuntimeRefreshResult(
                refreshed=True,
                project_path=project_path,
            ))

        except NoProjectFoundError as e:
            return Result.from_exception(e)
        except Exception as e:
            log.error(f"Failed to refresh VM runtime: {e}")
            return Result.fail(
                code="VmRuntimeRefreshError",
                message=f"Failed to refresh VM runtime: {e}",
                solutions=['Check project directory permissions']
            )
