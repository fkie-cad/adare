"""
Show Service - Business logic for data display operations.

This service handles data retrieval operations for display and returns Result[T] objects
that can be consumed by any frontend (CLI, Web UI, REST API).
"""
import logging
from collections.abc import Callable
from pathlib import Path

from adare.config.database import get_project_database_location
from adare.core.dto.show import (
    EnvironmentDetail,
    EnvironmentListItem,
    ExperimentDetail,
    ExperimentListItem,
    ProjectListItem,
    RunDetail,
    RunListItem,
    RunListRequest,
    RunRemoveRequest,
    RunRemoveResult,
    TestfunctionDetail,
    TestfunctionListItem,
)
from adare.core.result import Result

log = logging.getLogger(__name__)


class ShowService:
    """
    Service for data display operations.

    All methods return Result[T] objects for consistent error handling
    across different frontends.
    """

    def _query_across_projects(self, query_fn: Callable) -> list:
        """Run a StructuredDataApi query across all project databases, aggregating results."""
        from adare.database.api.structured_data import StructuredDataApi

        all_results = []
        with StructuredDataApi() as global_api:
            projects = global_api.get_projects_structured()

        for project in projects:
            project_path = Path(project.path) if project.path else None
            if not project_path:
                continue
            db_path = get_project_database_location(project_path)
            if not db_path.exists():
                continue
            try:
                with StructuredDataApi(db_path=db_path) as project_api:
                    all_results.extend(query_fn(project_api, project.name))
            except FileNotFoundError:
                log.warning(f"Project database not found for {project.name}")
            except OSError as e:
                log.warning(f"Failed to query project {project.name}: {e}")

        return all_results

    # =========================================================================
    # Run Operations
    # =========================================================================

    def list_runs(self, request: RunListRequest = None) -> Result[list[RunListItem]]:
        """
        List runs with optional filtering.

        Queries across all project databases to aggregate runs.

        Args:
            request: Optional filters for project, environment, experiment

        Returns:
            Result[List[RunListItem]] with list of runs.
        """
        try:
            project_filter = request.project if request else None
            environment_filter = request.environment if request else None
            experiment_filter = request.experiment if request else None

            runs = self._query_across_projects(
                lambda api, name: api.get_runs_structured(
                    project_name=name,
                    experiment_name=experiment_filter,
                )
            )

            items = [
                RunListItem(
                    ulid=run.ulid,
                    experiment_name=run.experiment_name,
                    experiment_ulid=run.experiment_ulid,
                    environment_name=run.environment_name,
                    environment_ulid=run.environment_ulid,
                    project_name=run.project_name,
                    start_time=run.start_time,
                    end_time=run.end_time,
                    duration_seconds=run.duration_seconds,
                    status=run.status,
                    result_status=run.overall_result,
                    published=run.published,
                    fake=run.fake,
                )
                for run in runs
            ]

            # Apply remaining filters after aggregation
            if project_filter:
                items = [item for item in items if item.project_name == project_filter]
            if environment_filter:
                items = [item for item in items if item.environment_name == environment_filter]

            return Result.ok(items)

        except FileNotFoundError as e:
            log.error(f"Failed to list runs: {e}")
            return Result.fail(
                code="RunListError",
                message=f"Failed to list runs: {e}",
                solutions=['Check database connection']
            )
        except OSError as e:
            log.error(f"Failed to list runs: {e}")
            return Result.fail(
                code="RunListError",
                message=f"Failed to list runs: {e}",
                solutions=['Check database connection']
            )

    def get_run(self, ulid: str = None, latest_in_project: bool = False, project_path: Path = None) -> Result[RunDetail]:
        """
        Get detailed information about a specific run.

        Searches across all project databases when looking up by ULID.

        Args:
            ulid: Run ULID to retrieve
            latest_in_project: If True, get the latest run in current project
            project_path: Optional project path for latest run lookup

        Returns:
            Result[RunDetail] with run details.
        """
        from adare.database.api.frontend import DataRetrievalApi

        try:
            if latest_in_project:
                with DataRetrievalApi() as api:
                    latest_run_data = api.get_latest_run_in_project()
                    if latest_run_data is None or latest_run_data.empty:
                        return Result.fail(
                            code="RunNotFoundError",
                            message="No runs found in current project",
                            solutions=['Run an experiment first', 'Check if you are in a project directory']
                        )
                    ulid = latest_run_data['id'].iloc[0]

            # Search across all project databases for the run
            all_runs = self._query_across_projects(
                lambda api, name: api.get_runs_structured(project_name=name)
            )

            run = next((r for r in all_runs if r.ulid == ulid), None)
            if not run:
                return Result.fail(
                    code="RunNotFoundError",
                    message=f"Run with ULID {ulid} not found",
                    solutions=['Use `adare show runs` to find valid run ULIDs']
                )

            detail = RunDetail(
                ulid=run.ulid,
                experiment_name=run.experiment_name,
                experiment_ulid=run.experiment_ulid,
                environment_name=run.environment_name,
                environment_ulid=run.environment_ulid,
                project_name=run.project_name,
                start_time=run.start_time,
                end_time=run.end_time,
                duration_seconds=run.duration_seconds,
                status=run.status,
                result_status=run.overall_result,
                published=run.published,
                fake=run.fake,
            )

            return Result.ok(detail)

        except FileNotFoundError as e:
            log.error(f"Failed to get run {ulid}: {e}")
            return Result.fail(
                code="RunRetrievalError",
                message=f"Failed to get run: {e}",
                solutions=['Check database connection', 'Verify the ULID is correct']
            )
        except OSError as e:
            log.error(f"Failed to get run {ulid}: {e}")
            return Result.fail(
                code="RunRetrievalError",
                message=f"Failed to get run: {e}",
                solutions=['Check database connection', 'Verify the ULID is correct']
            )

    def remove_run(self, request: RunRemoveRequest) -> Result[RunRemoveResult]:
        """
        Remove a single experiment run.

        Args:
            request: RunRemoveRequest with ULID and optional project path

        Returns:
            Result[RunRemoveResult] with removal status.
        """
        from adare.backend.basics import determine_projectdirectory
        from adare.database.api.experiment import ExperimentApi
        from adare.database.models.project_models import ExperimentRun
        from adare.exceptions import ArgumentsError, NoProjectFoundError

        try:
            if not request.ulid:
                return Result.fail(
                    code="ArgumentsError",
                    message="No run ULID provided",
                    solutions=['Use `adare show runs` to find the ULID of the run to remove']
                )

            # Get project path for database context
            project_path = request.project_path or determine_projectdirectory(None)
            if not project_path:
                return Result.fail(
                    code="NoProjectFoundError",
                    message="No project found in current directory or parent directories",
                    solutions=['Run this command from within a project directory']
                )

            with ExperimentApi(project_path) as api:
                # Get the run first to check if it exists
                run = api._session.query(ExperimentRun).filter(ExperimentRun.id == request.ulid).first()
                if not run:
                    return Result.fail(
                        code="RunNotFoundError",
                        message=f"Run with ULID {request.ulid} not found",
                        solutions=['Use `adare show runs` to find valid run ULIDs']
                    )

                was_fake = run.fake

                # Delete the run
                api.delete_experiment_run(run)
                api._session.commit()

                return Result.ok(RunRemoveResult(
                    removed=True,
                    ulid=request.ulid,
                    was_fake=was_fake,
                ))

        except NoProjectFoundError as e:
            return Result.from_exception(e)
        except ArgumentsError as e:
            return Result.from_exception(e)
        except Exception as e:
            log.error(f"Failed to remove run {request.ulid}: {e}")
            return Result.fail(
                code="RunRemovalError",
                message=f"Failed to remove run: {e}",
                solutions=['Check database permissions', 'Ensure the run exists']
            )

    # =========================================================================
    # Project Operations
    # =========================================================================

    def list_projects(self) -> Result[list[ProjectListItem]]:
        """
        List all projects.

        Returns:
            Result[List[ProjectListItem]] with list of projects.
        """
        from adare.database.api.structured_data import StructuredDataApi

        try:
            with StructuredDataApi() as api:
                projects = api.get_projects_structured()

            items = [
                ProjectListItem(
                    name=proj.name,
                    description=proj.description,
                    created_at=proj.created_at,
                    experiment_count=proj.experiment_count,
                    environment_count=proj.environment_count,
                )
                for proj in projects
            ]

            return Result.ok(items)

        except Exception as e:
            log.error(f"Failed to list projects: {e}")
            return Result.fail(
                code="ProjectListError",
                message=f"Failed to list projects: {e}",
                solutions=['Check database connection']
            )

    # =========================================================================
    # Environment Operations
    # =========================================================================

    def list_environments(self) -> Result[list[EnvironmentListItem]]:
        """
        List all environments.

        Returns:
            Result[List[EnvironmentListItem]] with list of environments.
        """
        from adare.database.api.structured_data import StructuredDataApi

        try:
            with StructuredDataApi() as api:
                environments = api.get_environments_structured()

            items = [
                EnvironmentListItem(
                    ulid=env.ulid,
                    name=env.name,
                    display_name=env.display_name,
                    dotnotation=env.dotnotation,
                    project=env.project,
                    description=env.description,
                    vm_name=env.vm_box,
                    vm_id=env.vm_id,
                    os_info=env.os_info,
                    osinfo_os=env.osinfo_os,
                    osinfo_distribution=env.osinfo_distribution,
                    osinfo_version=env.osinfo_version,
                    osinfo_language=env.osinfo_language,
                    published=env.published,
                    in_request=env.in_request,
                    created_at=env.created_at,
                    file=env.file,
                )
                for env in environments
            ]

            return Result.ok(items)

        except Exception as e:
            log.error(f"Failed to list environments: {e}")
            return Result.fail(
                code="EnvironmentListError",
                message=f"Failed to list environments: {e}",
                solutions=['Check database connection']
            )

    def get_environment(self, name: str) -> Result[EnvironmentDetail]:
        """
        Get detailed information about a specific environment.

        Args:
            name: Environment name to retrieve

        Returns:
            Result[EnvironmentDetail] with environment details.
        """
        from adare.database.api.structured_data import StructuredDataApi

        try:
            with StructuredDataApi() as api:
                environments = api.get_environments_structured()

            # Find the environment by name
            env = next((e for e in environments if e.name == name), None)
            if not env:
                return Result.fail(
                    code="EnvironmentNotFoundError",
                    message=f"Environment '{name}' not found",
                    solutions=['Use `adare show environments` to list available environments']
                )

            detail = EnvironmentDetail(
                ulid=env.ulid,
                name=env.name,
                display_name=env.display_name,
                dotnotation=env.dotnotation,
                project=env.project,
                description=env.description,
                vm_name=env.vm_box,
                vm_id=env.vm_id,
                os_info=env.os_info,
                osinfo_os=env.osinfo_os,
                osinfo_distribution=env.osinfo_distribution,
                osinfo_version=env.osinfo_version,
                osinfo_language=env.osinfo_language,
                published=env.published,
                in_request=env.in_request,
                created_at=env.created_at,
                file=env.file,
            )

            return Result.ok(detail)

        except Exception as e:
            log.error(f"Failed to get environment {name}: {e}")
            return Result.fail(
                code="EnvironmentRetrievalError",
                message=f"Failed to get environment: {e}",
                solutions=['Check database connection']
            )

    # =========================================================================
    # Experiment Operations
    # =========================================================================

    def list_experiments(self, tags: list[str] | None = None) -> Result[list[ExperimentListItem]]:
        """
        List all experiments, optionally filtered by tags.

        Queries across all project databases to aggregate experiments.

        Args:
            tags: Optional list of tag names to filter by (AND matching)

        Returns:
            Result[List[ExperimentListItem]] with list of experiments.
        """
        try:
            experiments = self._query_across_projects(
                lambda api, name: api.get_experiments_structured(project_name=name)
            )

            items = [
                ExperimentListItem(
                    ulid=exp.ulid,
                    name=exp.name,
                    display_name=exp.display_name,
                    dotnotation=exp.dotnotation,
                    project=exp.project,
                    environment=exp.environment,
                    environments=exp.environments,
                    description=exp.description,
                    tags=exp.tags,
                    published=exp.published,
                    in_request=exp.in_request,
                    created_at=exp.created_at,
                    run_count=exp.run_count,
                    last_run=exp.last_run,
                )
                for exp in experiments
            ]

            if tags:
                from adare.database.api.tag import TagApi
                with TagApi() as tag_api:
                    result = tag_api.get_entities_by_tags(
                        tag_names=tags,
                        entity_type='experiments',
                        match_all=True,
                    )
                matching_ids = {exp.id for exp in result.get('experiments', [])}
                items = [item for item in items if item.ulid in matching_ids]

            return Result.ok(items)

        except FileNotFoundError as e:
            log.error(f"Failed to list experiments: {e}")
            return Result.fail(
                code="ExperimentListError",
                message=f"Failed to list experiments: {e}",
                solutions=['Check database connection']
            )
        except OSError as e:
            log.error(f"Failed to list experiments: {e}")
            return Result.fail(
                code="ExperimentListError",
                message=f"Failed to list experiments: {e}",
                solutions=['Check database connection']
            )

    def get_experiment(self, name: str = None, ulid: str = None, dotnotation: str = None) -> Result[ExperimentDetail]:
        """
        Get detailed information about a specific experiment.

        Searches across all project databases.

        Args:
            name: Experiment name to retrieve
            ulid: Experiment ULID to retrieve
            dotnotation: Experiment dotnotation to retrieve

        Returns:
            Result[ExperimentDetail] with experiment details.
        """
        try:
            experiments = self._query_across_projects(
                lambda api, proj_name: api.get_experiments_structured(project_name=proj_name)
            )

            # Find the experiment by name, ulid, or dotnotation
            exp = None
            if ulid:
                exp = next((e for e in experiments if e.ulid == ulid), None)
            elif dotnotation:
                exp = next((e for e in experiments if e.dotnotation == dotnotation), None)
            elif name:
                exp = next((e for e in experiments if e.name == name), None)

            if not exp:
                identifier = ulid or dotnotation or name
                return Result.fail(
                    code="ExperimentNotFoundError",
                    message=f"Experiment '{identifier}' not found",
                    solutions=['Use `adare show experiments` to list available experiments']
                )

            detail = ExperimentDetail(
                ulid=exp.ulid,
                name=exp.name,
                display_name=exp.display_name,
                dotnotation=exp.dotnotation,
                project=exp.project,
                environment=exp.environment,
                environments=exp.environments,
                description=exp.description,
                tags=exp.tags,
                published=exp.published,
                in_request=exp.in_request,
                created_at=exp.created_at,
                run_count=exp.run_count,
                last_run=exp.last_run,
            )

            return Result.ok(detail)

        except FileNotFoundError as e:
            log.error(f"Failed to get experiment: {e}")
            return Result.fail(
                code="ExperimentRetrievalError",
                message=f"Failed to get experiment: {e}",
                solutions=['Check database connection']
            )
        except OSError as e:
            log.error(f"Failed to get experiment: {e}")
            return Result.fail(
                code="ExperimentRetrievalError",
                message=f"Failed to get experiment: {e}",
                solutions=['Check database connection']
            )

    # =========================================================================
    # Testfunction Operations
    # =========================================================================

    def list_testfunctions(self, file_name: str = None) -> Result[list[TestfunctionListItem]]:
        """
        List all testfunctions, optionally filtered by file.

        Args:
            file_name: Optional file name to filter testfunctions

        Returns:
            Result[List[TestfunctionListItem]] with list of testfunctions.
        """
        from adare.database.api.structured_data import StructuredDataApi

        try:
            with StructuredDataApi() as api:
                testfunctions = api.get_testfunctions_structured(
                    include_parameters=True,
                    testfunction_file=file_name
                )

            items = [
                TestfunctionListItem(
                    id=tf.id,
                    name=tf.name,
                    dotnotation=tf.dotnotation,
                    display_name=tf.display_name,
                    description=tf.description,
                    parameter_count=tf.parameter_count,
                    parameters=tf.parameters,
                    file_id=tf.file_id,
                    file_name=tf.file_name,
                    file_path=tf.file_path,
                    full_file_path=tf.full_file_path,
                    file_sha256=tf.file_sha256,
                    file_description=tf.file_description,
                )
                for tf in testfunctions
            ]

            return Result.ok(items)

        except Exception as e:
            log.error(f"Failed to list testfunctions: {e}")
            return Result.fail(
                code="TestfunctionListError",
                message=f"Failed to list testfunctions: {e}",
                solutions=['Check database connection']
            )

    def get_testfunction(self, dotnotation: str) -> Result[TestfunctionDetail]:
        """
        Get detailed information about a specific testfunction.

        Args:
            dotnotation: Testfunction dotnotation to retrieve

        Returns:
            Result[TestfunctionDetail] with testfunction details.
        """
        from adare.database.api.structured_data import StructuredDataApi

        try:
            with StructuredDataApi() as api:
                testfunctions = api.get_testfunctions_structured(include_parameters=True)

            # Find the testfunction by dotnotation
            tf = next((t for t in testfunctions if t.dotnotation == dotnotation), None)
            if not tf:
                return Result.fail(
                    code="TestfunctionNotFoundError",
                    message=f"Testfunction '{dotnotation}' not found",
                    solutions=['Use `adare show testfunctions` to list available testfunctions']
                )

            detail = TestfunctionDetail(
                id=tf.id,
                name=tf.name,
                dotnotation=tf.dotnotation,
                display_name=tf.display_name,
                description=tf.description,
                parameter_count=tf.parameter_count,
                parameters=tf.parameters,
                file_id=tf.file_id,
                file_name=tf.file_name,
                file_path=tf.file_path,
                full_file_path=tf.full_file_path,
                file_sha256=tf.file_sha256,
                file_description=tf.file_description,
            )

            return Result.ok(detail)

        except Exception as e:
            log.error(f"Failed to get testfunction {dotnotation}: {e}")
            return Result.fail(
                code="TestfunctionRetrievalError",
                message=f"Failed to get testfunction: {e}",
                solutions=['Check database connection']
            )
