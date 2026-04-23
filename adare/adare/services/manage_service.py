"""
Manage Service - Business logic for database and system management operations.

This service handles database management operations and returns Result[T] objects
that can be consumed by any frontend (CLI, Web UI, REST API).
"""
import logging
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from adare.config.database import get_global_database_location
from adare.core.dto.manage import (
    DbCleanInstallResult,
    DbInitResult,
    DbRepairResult,
    DbResetResult,
    DbStatusResult,
    VmResetResult,
    VmRuntimeBuildResult,
    VmRuntimeRefreshResult,
)
from adare.core.result import Result
from adare.database.init import (
    clean_install_database_system,
    initialize_database_system,
    repair_database_system,
    validate_database_integrity,
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

        except (SQLAlchemyError, OSError) as e:
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

        except (SQLAlchemyError, OSError) as e:
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

        except (SQLAlchemyError, OSError) as e:
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

        except (SQLAlchemyError, OSError) as e:
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
            return Result.ok(DbResetResult(
                was_reset=False,
                location=database_location,
            ))

        except OSError as e:
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
        from adare.backend.vm.commands import clear_all_vms

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

        except (OSError, SQLAlchemyError, RuntimeError) as e:
            log.error(f"Failed to reset VMs: {e}")
            return Result.fail(
                code="VmResetError",
                message=f"Failed to reset VMs: {e}",
                solutions=['Check if VMs are in use', 'Try stopping running VMs first']
            )

    def refresh_vm_runtime(self, project_path: Path | None = None) -> Result[VmRuntimeRefreshResult]:
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
        except OSError as e:
            log.error(f"Failed to refresh VM runtime: {e}")
            return Result.fail(
                code="VmRuntimeRefreshError",
                message=f"Failed to refresh VM runtime: {e}",
                solutions=['Check project directory permissions']
            )

    def build_vm_runtime_wheels(self, project_path: Path | None = None) -> Result[VmRuntimeBuildResult]:
        """
        Build fresh wheels for VM runtime in a project.

        This will:
        1. Ensure vm_runtime directory exists with source files
        2. Clean any existing wheels
        3. Build fresh adarelib and adarevm wheels

        Args:
            project_path: Optional project path. If None, uses current project.

        Returns:
            Result[VmRuntimeBuildResult] with build results.
        """
        import re
        import subprocess

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
            wheels_dir = project_vm_runtime / 'wheels'
            adarelib_target = project_vm_runtime / 'adarelib'
            adarevm_target = project_vm_runtime / 'adarevm'

            # Ensure vm_runtime exists with source files
            if not project_vm_runtime.exists() or not adarelib_target.exists() or not adarevm_target.exists():
                log.info("VM runtime source files not found, copying fresh files...")
                project_dir = ProjectDirectory(project_path)
                project_dir.copy_vm_runtime_files()

            # Create wheels directory
            wheels_dir.mkdir(exist_ok=True)

            # Clean old wheels
            for old_wheel in wheels_dir.glob('*.whl'):
                old_wheel.unlink()
                log.info(f"Removed old wheel: {old_wheel.name}")

            # Build adarelib wheel first (it has no path dependencies)
            log.info("Building adarelib wheel...")
            result = subprocess.run(
                ["uv", "build", "--wheel", "--out-dir", str(wheels_dir)],
                cwd=adarelib_target,
                check=True,
                capture_output=True
            )

            # Build adarevm wheel without path dependency
            log.info("Building adarevm wheel...")

            # Temporarily modify pyproject.toml to use version dependency instead of path
            adarevm_pyproject = adarevm_target / 'pyproject.toml'
            original_content = adarevm_pyproject.read_text()

            # Replace workspace source with version dependency for wheel build
            modified_content = re.sub(
                r'adarelib\s*=\s*\{\s*workspace\s*=\s*true\s*\}',
                '',
                original_content
            )
            adarevm_pyproject.write_text(modified_content)

            try:
                subprocess.run(
                    ["uv", "build", "--wheel", "--out-dir", str(wheels_dir)],
                    cwd=adarevm_target,
                    check=True,
                    capture_output=True
                )
            finally:
                # Restore original pyproject.toml
                adarevm_pyproject.write_text(original_content)

            # Find built wheels
            adarelib_wheels = list(wheels_dir.glob('adarelib-*.whl'))
            adarevm_wheels = list(wheels_dir.glob('adarevm-*.whl'))

            log.info(f"Wheels built successfully in {wheels_dir}")

            return Result.ok(VmRuntimeBuildResult(
                built=True,
                project_path=project_path,
                wheels_dir=wheels_dir,
                adarelib_wheel=adarelib_wheels[0].name if adarelib_wheels else None,
                adarevm_wheel=adarevm_wheels[0].name if adarevm_wheels else None,
            ))

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode() if e.stderr else str(e)
            log.error(f"Failed to build wheels: {error_msg}")
            return Result.fail(
                code="VmRuntimeBuildError",
                message=f"Failed to build wheels: {error_msg}",
                solutions=[
                    'Ensure uv is installed',
                    'Check that adarelib and adarevm have valid pyproject.toml files',
                    'Run "adare manage vm-runtime refresh" first to get fresh source files'
                ]
            )
        except NoProjectFoundError as e:
            return Result.from_exception(e)
        except FileNotFoundError as e:
            log.error(f"Failed to build wheels - file not found: {e}")
            return Result.fail(
                code="VmRuntimeBuildError",
                message=f"Required file not found: {e}",
                solutions=[
                    'Run "adare manage vm-runtime refresh" first to copy source files',
                    'Ensure uv is installed and in PATH'
                ]
            )
