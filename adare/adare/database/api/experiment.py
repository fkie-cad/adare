# external imports
import sqlalchemy
from pathlib import Path
from datetime import datetime, timezone

# internal imports
from adare.config.configdirectory import PROG_PARSEANDTEST_DIR
import adare.config.database as config_database
from adare.database.models.project_models import ExperimentRunFiles, TestParameterEntry, Experiment, \
    ExperimentRun, AbstractTest, Tool, LogFile
from adare.database.models.global_models import TestFunctionFile, TestFunction, TestParameter, Tag
from adare.database.api.base import ProjectDatabaseApi
from adare.database.api.project import ProjectDbApi
from adarelib.testset.type import TestsetFile as FTestsetFile, Test as FTest
from adare.backend.experiment.directory import ExperimentDirectory
from adare.exceptions import TestSetFormatError, EnvironmentNotFoundError
from adare.database.exceptions import EnvironmentMissingError
from adare.database.fixtures import fixture_stages, fixture_status
from adarelib.constants import StatusEnum

# configure logging
import logging

log = logging.getLogger(__name__)


class ExperimentApi(ProjectDatabaseApi):
    testfunction_locations: dict[str, Path] = {
        'default': PROG_PARSEANDTEST_DIR / 'src' / 'parseandtest' / 'testfunctions',
    }

    def __init__(self, project_path: Path):
        super().__init__(project_path)

    def __enter__(self):
        super().__enter__()
        self.__fixtures()
        return self

    def __fixtures(self):
        fixture_status(self._session)
        fixture_stages(self._session)

    def __exit__(self, exc_type, exc_val, exc_tb):
        super().__exit__(exc_type, exc_val, exc_tb)

    def get_project_by_path(self, project_path: Path):
        """
        Get project by path using the global database API.
        """
        with ProjectDbApi() as project_api:
            return project_api.get_project_by_path(project_path)

    def delete_experiment_run(self, experiment_run: ExperimentRun):
        """
            Deletes the experiment run from the database.
        """
        self._session.delete(experiment_run)

    def get_experiment_by_project_and_name(self, project_path: Path, experiment_name: str) -> Experiment:
        # In the new architecture, experiments are stored per-project
        # We simply query the experiment by name in the current project database
        experiment = self._session.query(Experiment).filter_by(name=experiment_name).first()

        if not experiment:
            return None

        return experiment

    def get_or_create_tags(self, tags: list[str]) -> list:
        """
            Returns the tag objects for the given tag names.
        """
        tag_objects = []
        for tag in tags:
            tag_obj = self._session.query(Tag).filter_by(name=tag).first()
            if not tag_obj:
                tag_obj = Tag(name=tag)
                self._session.add(tag_obj)
            tag_objects.append(tag_obj)
        return tag_objects

    def get_environments_by_name(self, names: list[str]) -> list:
        """
        Get environment IDs for the given environment names from the global database.
        Returns environment IDs that can be stored in experiment.environment_ids
        """
        from adare.database.api.base import GlobalDatabaseApi
        from adare.database.models.global_models import Environment
        from sqlalchemy.exc import SQLAlchemyError

        environment_ids = []
        try:
            with GlobalDatabaseApi() as global_api:
                # Fix N+1 query: Use single query with IN clause
                environments = global_api._session.query(Environment).filter(
                    Environment.name.in_(names)
                ).all()

                # Preserve order from input names
                env_map = {env.name: env.id for env in environments}
                environment_ids = [env_map[name] for name in names if name in env_map]
        except SQLAlchemyError as e:
            log.error(f"Database error querying global environments: {e}")

        return environment_ids

    def get_environment(self, environment_name: str, project_name: str = None):
        """
        Get environment by name from the global database.
        project_name is ignored since environments are now global.
        """
        from adare.database.api.base import GlobalDatabaseApi
        from adare.database.models.global_models import Environment
        from sqlalchemy.exc import SQLAlchemyError

        try:
            with GlobalDatabaseApi() as global_api:
                environment = global_api._session.query(Environment).filter_by(name=environment_name).first()
                return environment
        except SQLAlchemyError as e:
            log.error(f"Database error querying global environment '{environment_name}': {e}")
            return None

    def create_experiment(self, name: str, experiment_directory: ExperimentDirectory, auto_commit: bool = True) -> Experiment:
        testset = experiment_directory.load_testset()
        metadata = experiment_directory.load_metadata()

        abstract_test_objects: list = self.__get_abstracttests_from_testsetfile(testset)
        environment_ids = self.get_environments_by_name(metadata.environments)
        if not environment_ids:
            log.info('no environments found for experiment - environments can be added later with: adare experiment add-env')

        experiment = Experiment(
            name=name,
            description=metadata.description,
            sha256=experiment_directory.sha256,
            sha256_playbook=experiment_directory.sha256_playbook,
            sha256_metadata=experiment_directory.sha256_metadata,
            environment_ids=environment_ids
        )
        for obj in abstract_test_objects:
            if obj:
                experiment.abstract_tests.append(obj)
        self._session.add(experiment)

        # Flush to get ULID assigned without committing
        self._session.flush()

        # Handle tags from metadata
        if metadata.tags:
            from adare.database.models.project_models import Tag as ProjectTag

            for tag_name in metadata.tags:
                # Create or get existing project-specific tag
                tag = self._session.query(ProjectTag).filter(ProjectTag.name == tag_name.strip().lower()).first()
                if not tag:
                    tag = ProjectTag(name=tag_name.strip().lower())
                    self._session.add(tag)

                if tag not in experiment.tags:
                    experiment.tags.append(tag)

        # Populate playbook models from YAML file
        if experiment_directory.playbookfile.exists():
            from adare.database.api.playbook import PlaybookApi

            # Create a PlaybookApi that reuses our existing session
            playbook_api = PlaybookApi(self.project_path)
            playbook_api._session = self._session  # Reuse the current session
            playbook_api._engine = self._engine    # Reuse the current engine

            try:
                playbook_api.populate_playbook_from_file(experiment, experiment_directory.playbookfile)
                log.debug(f'populated playbook models for experiment {experiment.id}')
            except (SQLAlchemyError, OSError, IOError) as e:
                log.error(f'failed to populate playbook models for experiment {experiment.id}: {e}')
                raise

        if auto_commit:
            self._session.commit()

        log.debug(f'added experiment {experiment.id} to database')
        return experiment

    def get_experiment(self, name: str, environment_id: str) -> Experiment:
        """Get experiment by name that uses the specified environment ID."""
        experiment = self._session.query(Experiment).filter(Experiment.name == name).first()
        if experiment and experiment.environment_ids and environment_id in experiment.environment_ids:
            return experiment
        return None

    def get_experiment_by_ulid(self, experiment_ulid: str) -> Experiment:
        return self._session.query(Experiment).filter(Experiment.id == experiment_ulid).first()

    def get_experiment_environment_names(self, experiment_ulid: str) -> list[str]:
        """Get current environment names from experiment's environment_ids."""
        from adare.database.api.base import GlobalDatabaseApi
        from adare.database.models.global_models import Environment
        from sqlalchemy.exc import SQLAlchemyError

        experiment = self.get_experiment_by_ulid(experiment_ulid)
        if not experiment or not experiment.environment_ids:
            return []

        environment_names = []
        try:
            with GlobalDatabaseApi() as global_api:
                # Fix N+1 query: Use single query with IN clause instead of loop
                environments = global_api._session.query(Environment).filter(
                    Environment.id.in_(experiment.environment_ids)
                ).all()

                # Preserve original order from environment_ids
                env_map = {env.id: env.name for env in environments}
                environment_names = [env_map[env_id] for env_id in experiment.environment_ids if env_id in env_map]
        except SQLAlchemyError as e:
            log.error(f"Database error querying environment names for experiment {experiment_ulid}: {e}")

        return environment_names

    def update_experiment_environments(self, experiment_ulid: str, new_env_names: list[str], auto_commit: bool = True):
        """Update experiment's environment_ids based on new environment names."""
        experiment = self.get_experiment_by_ulid(experiment_ulid)
        if not experiment:
            raise ValueError(f"Experiment {experiment_ulid} not found")

        # Get new environment IDs from names
        new_environment_ids = self.get_environments_by_name(new_env_names)
        if not new_environment_ids and new_env_names:
            raise EnvironmentMissingError(
                log,
                message=f'Environments not found: {new_env_names}',
                possible_solutions=[
                    'Load the environment with [i]adare environment load[/i]',
                    'Create a new environment with [i]adare environment create[/i]'
                ]
            )

        # Update environment_ids
        experiment.environment_ids = new_environment_ids

        if auto_commit:
            self._session.commit()

        log.debug(f"Updated experiment {experiment_ulid} environments to: {new_env_names}")

    def __create_logfile(self, path: Path) -> LogFile:
        logfile = LogFile(
            name=path.name,
            path=path.as_posix()
        )
        self._session.add(logfile)
        return logfile

    def update_experiment_run(
            self, run_ulid: str, path: Path,
            logfile_adare: Path, logfile_adarevm: Path, status: int
    ) -> ExperimentRun:
        """
        Update experiment run with VM-specific data (path, logfiles, status).
        The experiment and environment should already be set via set_experiment_run_base_info().
        """
        experiment_run_files = ExperimentRunFiles(
            log_adare=self.__create_logfile(logfile_adare),
            log_adarevm=self.__create_logfile(logfile_adarevm),
        )
        self._session.add(experiment_run_files)
        experiment_run = self._session.query(ExperimentRun).filter(ExperimentRun.id == run_ulid).first()
        experiment_run.path = path.as_posix()
        experiment_run.files = experiment_run_files
        experiment_run.status = status
        self._session.commit()
        return experiment_run

    def initialize_experiment_run(self, fake: bool = False) -> ExperimentRun:
        experiment_run = ExperimentRun(fake=fake)
        self._session.add(experiment_run)
        self._session.commit()
        return experiment_run

    def set_experiment_run_base_info(self, run_ulid: str, experiment: Experiment, environment_id: str) -> ExperimentRun:
        """
        Set the basic experiment and environment information early in the process.
        This prevents orphaned experiment runs if the process is interrupted early.
        """
        experiment_run = self._session.query(ExperimentRun).filter(ExperimentRun.id == run_ulid).first()
        if experiment_run:
            experiment_run.experiment = experiment
            experiment_run.environment_id = environment_id
            self._session.commit()
        return experiment_run

    def update_experiment_run_start(self, experiment_run_ulid: str, timestamp: datetime):
        experiment_run = self._session.query(ExperimentRun).filter(ExperimentRun.id == experiment_run_ulid).first()
        if experiment_run:
            experiment_run.start_time = timestamp
            self._session.commit()

    def update_experiment_run_end(self, experiment_run_ulid: str, timestamp: datetime):
        experiment_run = self._session.query(ExperimentRun).filter(ExperimentRun.id == experiment_run_ulid).first()
        if experiment_run:
            experiment_run.end_time = timestamp
            self._session.commit()

    def remove_experiment_by_ulid(self, experiment_ulid: str):
        if (
                experiment := self._session.query(Experiment)
                        .filter(Experiment.id == experiment_ulid)
                        .first()
        ):
            self.remove_experiment(experiment)
        else:
            raise ValueError(f'experiment with ulid {experiment_ulid} not found')

    def remove_experiment(self, experiment: Experiment):
        # delete all experiment runs
        for run in experiment.runs:
            self._session.delete(run)
        self._session.delete(experiment)

    def remove_fake_experiment_run(self, experiment_run_ulid: str):
        experiment_run = self._session.query(ExperimentRun).filter(ExperimentRun.id == experiment_run_ulid, ExperimentRun.fake == True).first()
        if experiment_run:
            # Query already filtered for fake == True, so if it exists, it's guaranteed to be fake
            self._session.delete(experiment_run)
        else:
            # Experiment run not found or not fake - log and continue (may have been already deleted)
            log.debug(f'Fake experiment run with ulid {experiment_run_ulid} not found (may have been already deleted)')

    def experiment_sha256_equals(self, experiment_ulid: str, sha256: str) -> bool:
        experiment = self._session.query(Experiment).filter(Experiment.id == experiment_ulid).first()
        return experiment.sha256 == sha256 if experiment else False

    def __get_abstract_test(self, test: FTest) -> AbstractTest | None:
        """
        Create or get an abstract test for the new architecture.
        Uses global database lookups for test functions and stores only IDs.
        """
        from adare.database.api.base import GlobalDatabaseApi

        # Parse the test function name
        if '.' in test.function:
            testfunction_set, testfunction_type = test.function.split('.', maxsplit=1)
        else:
            testfunction_set = 'standard'
            testfunction_type = test.function

        # Look up the global test function
        testfunction_id = None

        with GlobalDatabaseApi() as global_api:
            testfunction_file = global_api._session.query(TestFunctionFile).filter_by(name=testfunction_set).first()
            if testfunction_file:
                testfunction = global_api._session.query(TestFunction).filter_by(
                    name=testfunction_type,
                    file_id=testfunction_file.id
                ).first()
                if testfunction:
                    testfunction_id = testfunction.id

        if not testfunction_id:
            raise TestSetFormatError(
                log,
                message=f'testfunction [b]{test.function}[/b] mentioned in test [b]{test.name}[/b] does not exist in the database.',
                possible_solutions=[
                    'ensure spelling and check if the testfunction is loaded by running: [i]adare testfunction list --filter type={test.function}[/i]',
                ]
            )

        # Create parameter entries for this test (project-specific)
        # Fix N+1 query: Batch load all parameters at once
        parameter_entries = []
        parameter_names = list(test.parameter.keys())

        with GlobalDatabaseApi() as global_api:
            from adare.database.models.global_models import TestParameter

            # Single query for all parameters
            global_parameters = global_api._session.query(TestParameter).filter(
                TestParameter.name.in_(parameter_names)
            ).all()

            # Create lookup map
            param_map = {p.name: p.id for p in global_parameters}

            # Validate all parameters exist
            missing_params = set(parameter_names) - set(param_map.keys())
            if missing_params:
                raise TestSetFormatError(
                    log,
                    message=f'Test parameters {missing_params} used in test [b]{test.name}[/b] do not exist in the global database.',
                    possible_solutions=[
                        f'Ensure parameter names are correct',
                        f'Check available parameters with: adare testfunction info {test.function}',
                    ]
                )

            # Create parameter entries using batched lookup
            for p_key, p_val in test.parameter.items():
                test_parameter_entry_obj = TestParameterEntry(
                    parameter_id=param_map[p_key],
                    value=str(p_val)
                )
                self._session.add(test_parameter_entry_obj)
                parameter_entries.append(test_parameter_entry_obj)

        # Check if abstract test already exists
        abstract_test_obj = self._session.query(AbstractTest).filter_by(
            name=test.name,
            testfunction_id=testfunction_id
        ).first()

        # If abstract test doesn't exist, create it
        if not abstract_test_obj:
            abstract_test_obj = AbstractTest(
                name=test.name,
                testfunction_id=testfunction_id
            )
            self._session.add(abstract_test_obj)

        # Add parameter entries
        for param_entry in parameter_entries:
            if param_entry not in abstract_test_obj.parameters:
                abstract_test_obj.parameters.append(param_entry)

        return abstract_test_obj

    def __get_abstracttests_from_testsetfile(self, testset: FTestsetFile) -> list[AbstractTest]:
        """
            Get/Creates the tests from the testset file.
        """
        return [self.__get_abstract_test(test) for test in testset.tests]

    def update_experiment_run_status(self, experiment_run_ulid: str, status: int):
        experiment_run = self._session.query(ExperimentRun).filter(ExperimentRun.id == experiment_run_ulid).first()
        if experiment_run:
            experiment_run.status = status
            if status == StatusEnum.FINISHED or status == StatusEnum.INTERRUPTED:
                experiment_run.end_time = datetime.now(timezone.utc)
            self._session.commit()

    def update_experiment_run_vm_instance(self, experiment_run_ulid: str, vm_instance_id: str):
        experiment_run = self._session.query(ExperimentRun).filter(ExperimentRun.id == experiment_run_ulid).first()
        if experiment_run:
            experiment_run.vm_instance_id = vm_instance_id
            self._session.commit()

    def sync_experiment(self, ulid: str, remote_ulid: str, abstract_tests_ulids: dict, remote_url: str, is_published: bool):
        # Retrieve the experiment by its ULID
        experiment = self.get_experiment_by_ulid(ulid)

        # Update the experiment properties
        experiment.remote_ulid = remote_ulid
        experiment.remote_url = remote_url
        experiment.published = is_published

        # Iterate through the abstract tests ULIDs and update each corresponding AbstractTest object
        for test_name, test_ulid in abstract_tests_ulids.items():
            abstract_test = (self._session.query(AbstractTest)
                             .select_from(Experiment)
                             .join(Experiment.abstract_tests)
                             .filter(AbstractTest.name == test_name, Experiment.id == experiment.id)
                             .first())
            if abstract_test:
                abstract_test.remote_ulid = test_ulid

        # Commit the changes to the session
        self._session.commit()

        return experiment

    def get_experiments(self, project_path: Path = None):
        # In the new architecture, experiments are already stored per-project
        # So we just return all experiments from the current project database
        return self._session.query(Experiment).all()

    def remove_fake_experiment_runs_by_experiment_name(self, project_path: Path, experiment_name: str) -> int:
        """
        Remove all fake experiment runs for a given experiment by name.

        Args:
            project_path: Path to the project containing the experiment
            experiment_name: Name of the experiment to clean fake runs for

        Returns:
            Number of fake runs removed
        """
        # Get the experiment
        experiment = self.get_experiment_by_project_and_name(project_path, experiment_name)
        if not experiment:
            raise ValueError(f'experiment "{experiment_name}" not found in project {project_path}')

        # Find all fake runs for this experiment
        fake_runs = self._session.query(ExperimentRun).filter(
            ExperimentRun.experiment_id == experiment.id,
            ExperimentRun.fake == True
        ).all()

        # Count and delete them
        count = len(fake_runs)
        for fake_run in fake_runs:
            self._session.delete(fake_run)

        self._session.commit()
        return count

    def mark_run_as_published(self, run_ulid: str):
        """
        Mark an experiment run as published to the server.

        Args:
            run_ulid: ULID of the experiment run

        Returns:
            The updated ExperimentRun object
        """
        run = self._session.query(ExperimentRun).filter(ExperimentRun.id == run_ulid).first()
        if not run:
            from adare.exceptions import ExperimentRunNotFoundError
            raise ExperimentRunNotFoundError(
                log,
                f'Experiment run {run_ulid} not found',
                possible_solutions=['Check the run ULID']
            )

        run.published = True
        self._session.commit()
        log.info(f'Marked run {run_ulid} as published')
        return run
