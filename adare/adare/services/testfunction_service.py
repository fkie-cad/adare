"""
Testfunction Service - Business logic for testfunction operations.

This service handles testfunction-related operations and returns Result[T] objects
that can be consumed by any frontend (CLI, Web UI, REST API).
"""

import logging

from sqlalchemy.exc import SQLAlchemyError

from adare.backend.testfunction import database as testfunction_database
from adare.backend.testfunction.commands import (
    testfunction_create as backend_testfunction_create,
)
from adare.backend.testfunction.commands import (
    testfunction_load_global as backend_testfunction_load_global,
)
from adare.backend.testfunction.commands import (
    testfunction_remove as backend_testfunction_remove,
)
from adare.backend.testfunction.exceptions import TestfunctionMissingFileError
from adare.core.dto.testfunction import (
    TestfunctionCreateRequest,
    TestfunctionExistsResult,
    TestfunctionInfo,
    TestfunctionListItem,
    TestfunctionLoadRequest,
    TestfunctionRemoveResult,
    TestfunctionUsage,
)
from adare.core.result import Result
from adare.database.api.testfunction import TestfunctionDbApi

log = logging.getLogger(__name__)


class TestfunctionService:
    """
    Service for testfunction management operations.

    All methods return Result[T] objects for consistent error handling
    across different frontends.
    """

    def create(self, request: TestfunctionCreateRequest) -> Result[TestfunctionInfo]:
        """
        Create a new testfunction template.

        Args:
            request: TestfunctionCreateRequest with project path and name

        Returns:
            Result[TestfunctionInfo] with created testfunction info on success.
        """
        try:
            backend_testfunction_create(request.project_path, request.name)

            next_steps = [
                'Edit the testfunction Python file to define your test logic',
                'Add dependencies to requirements.txt if needed',
                f'Load the testfunction with: adare testfunction load {request.name}',
            ]

            return Result.ok(TestfunctionInfo(
                id='',  # Not in database yet
                name=request.name,
                file_path=request.project_path / 'testfunctions' / request.name,
                is_published=False,
                next_steps=next_steps,
                tip='Testfunctions define test assertions for experiment execution',
            ))

        except TestfunctionMissingFileError as e:
            return Result.from_exception(e)

    def load(self, request: TestfunctionLoadRequest) -> Result[TestfunctionInfo]:
        """
        Load a testfunction from file into the system.

        Args:
            request: TestfunctionLoadRequest with path and options

        Returns:
            Result[TestfunctionInfo] with loaded testfunction info on success.
        """
        try:
            testfunction_id = backend_testfunction_load_global(
                request.path,
                force=request.force
            )

            # Get testfunction name from path
            if request.path.is_file():
                name = request.path.stem
            else:
                name = request.path.name

            next_steps = [
                f'Testfunction "{name}" is now available for experiments',
                'Reference it in your experiment playbook tests section',
            ]

            return Result.ok(TestfunctionInfo(
                id=str(testfunction_id) if testfunction_id else '',
                name=name,
                file_path=request.path,
                is_published=False,
                next_steps=next_steps,
                tip='Loaded testfunctions are available globally across projects',
            ))

        except TestfunctionMissingFileError as e:
            return Result.from_exception(e)

    def remove(self, name: str, force: bool = False) -> Result[TestfunctionRemoveResult]:
        """
        Remove a testfunction from the system.

        Note: This operation is interactive in CLI (asks for confirmation).
        For API/Web use, force=True skips confirmation.

        Args:
            name: Testfunction name
            force: Skip confirmation and force removal

        Returns:
            Result[TestfunctionRemoveResult] on success.
        """
        try:
            # Check if testfunction exists
            if not testfunction_database.testfunction_file_exists(name):
                return Result.fail(
                    code="TestfunctionNotFoundError",
                    message=f'Testfunction "{name}" does not exist',
                    solutions=[
                        'Use `adare testfunction list` to see available testfunctions',
                        'Check if the testfunction name is spelled correctly',
                    ]
                )

            # Get usage info
            usage = testfunction_database.get_testfunction_usage(name)

            if not force and not usage.get('can_safely_delete', True):
                return Result.fail(
                    code="TestfunctionInUseError",
                    message=f'Testfunction "{name}" is in use by {len(usage.get("experiments", []))} experiments',
                    solutions=[
                        'Use --force to remove the testfunction and delete associated data',
                        'Remove experiments using this testfunction first',
                    ]
                )

            # Remove testfunction (this handles cleanup)
            backend_testfunction_remove(name)

            return Result.ok(TestfunctionRemoveResult(
                name=name,
                was_removed=True,
                experiments_affected=len(usage.get('experiments', [])),
                runs_deleted=len(usage.get('runs', [])),
            ))

        except TestfunctionMissingFileError as e:
            return Result.from_exception(e)

    def list_all(self) -> Result[list[TestfunctionListItem]]:
        """
        List all testfunctions in the system.

        Returns:
            Result[List[TestfunctionListItem]] with all testfunctions.
        """
        try:
            with TestfunctionDbApi() as api:
                testfunction_files = api.get_testfunction_files()

                items = []
                for tf_file in testfunction_files:
                    # Get testfunctions within this file
                    testfunctions = api.get_testfunctions_by_file(tf_file.id)

                    for tf in testfunctions:
                        items.append(TestfunctionListItem(
                            id=str(tf.id),
                            name=tf.name,
                            dotnotation=f"{tf_file.name}.{tf.name}",
                            is_published=getattr(tf_file, 'is_published', False),
                        ))

                return Result.ok(items)

        except (SQLAlchemyError, OSError) as e:
            log.error(f"Failed to list testfunctions: {e}")
            return Result.fail(
                code="TestfunctionListError",
                message=f"Failed to list testfunctions: {e}",
                solutions=['Check database connectivity', 'Try again']
            )

    def get_usage(self, name: str) -> Result[TestfunctionUsage]:
        """
        Get usage information for a testfunction.

        Args:
            name: Testfunction name

        Returns:
            Result[TestfunctionUsage] with usage info.
        """
        try:
            usage = testfunction_database.get_testfunction_usage(name)

            return Result.ok(TestfunctionUsage(
                exists=usage.get('exists', False),
                testfunction_file_id=usage.get('testfunction_file_id'),
                can_safely_delete=usage.get('can_safely_delete', True),
                projects_affected=[p['name'] for p in usage.get('projects_affected', [])],
                experiments=[e['name'] for e in usage.get('experiments', [])],
                runs_count=len(usage.get('runs', [])),
            ))

        except (SQLAlchemyError, OSError) as e:
            log.error(f"Failed to get testfunction usage: {e}")
            return Result.fail(
                code="TestfunctionUsageError",
                message=f"Failed to get testfunction usage: {e}",
                solutions=['Check if testfunction exists']
            )

    def exists(self, name: str) -> Result[TestfunctionExistsResult]:
        """
        Check if a testfunction exists.

        Args:
            name: Testfunction name

        Returns:
            Result[TestfunctionExistsResult] with existence status.
        """
        try:
            exists = testfunction_database.testfunction_exists(name)

            return Result.ok(TestfunctionExistsResult(
                name=name,
                exists=exists,
            ))

        except (SQLAlchemyError, OSError) as e:
            log.error(f"Failed to check testfunction existence: {e}")
            return Result.fail(
                code="TestfunctionExistsError",
                message=f"Failed to check testfunction existence: {e}",
                solutions=['Check database connectivity']
            )
