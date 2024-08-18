# external imports
import sqlalchemy
from pathlib import Path
from datetime import datetime

# internal imports
from adare.config.configdirectory import PROG_PARSEANDTEST_DIR
import adare.config.database as config_database
from adare.database.models.experiment import ExperimentRunFiles, Tag, TestParameter, TestParameterEntry, Experiment, \
    ExperimentRun, TestFunction, AbstractTest, Command, LogFile, Environment, Base as ExperimentsBase
from adare.database.api.project import ProjectDbApi
from adarelib.types.testset import TestsetFile as FTestsetFile, Test as FTest
from adare.backend.experiment.directory import ExperimentDirectory
from adarelib.exceptions import TestSetFormatError, EnvironmentNotFoundError
from adare.database.exceptions import EnvironmentMissingError
from adare.database.fixtures import fixture_stages, fixture_status
from adarelib.config import StatusEnum

# configure logging
import logging

log = logging.getLogger(__name__)


class ExperimentApi(ProjectDbApi):
    testfunction_locations: dict[str, Path] = {
        'default': PROG_PARSEANDTEST_DIR / 'src' / 'parseandtest' / 'testfunctions',
    }

    def __init__(self, db_path: Path = config_database.get_database_location()):
        super().__init__(db_path)
        ExperimentsBase.metadata.create_all(self.engine)

    def __enter__(self):
        super().__enter__()
        self.__fixtures()
        return self

    def __fixtures(self):
        fixture_status(self._session)
        fixture_stages(self._session)

    def __exit__(self, exc_type, exc_val, exc_tb):
        super().__exit__(exc_type, exc_val, exc_tb)

    def delete_experiment_run(self, experiment_run: ExperimentRun):
        """
            Deletes the experiment run from the database.
        """
        self._session.delete(experiment_run)

    def get_experiment_by_project_and_name(self, project_path: Path, environment_name:str, experiment_name: str) -> Experiment:
        project = self.get_project_by_path(project_path)
        environment = self._session.query(Environment).filter_by(name=environment_name, project=project).first()
        if not environment:
            raise EnvironmentNotFoundError(
                log,
                message=f'environment with name {environment_name} not found in project {project_path}',
                possible_solutions=[
                    'load the environment with [i]adare environment load[/i]',
                    'create a new environment with [i]adare environment create[/i] and then load it'
                ]
            )
        # filter the experiment and check that environment in experiment.environments
        experiments = self._session.query(Experiment).filter_by(name=experiment_name).filter(Experiment.environments.any(ulid=environment.ulid))

        # check if multiple experiments with the same name exist
        if experiments.count() > 1:
            raise ValueError(f'multiple experiments with name {experiment_name} found')
        return experiments.first()

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

    def get_environments_by_name(self, names: list[str]) -> list[Environment]:
        environments = [
        ]
        for name in names:
            if (
                    env := self._session.query(Environment)
                            .filter_by(name=name)
                            .first()
            ):
                environments.append(env)
            else:
                return []
        return environments

    def create_experiment(self, name: str, experiment_directory: ExperimentDirectory) -> Experiment:
        testset = experiment_directory.load_testset()
        metadata = experiment_directory.load_metadata()

        abstract_test_objects: list = self.__get_abstracttests_from_testsetfile(testset)
        tags = self.get_or_create_tags(metadata.tags)
        environments = self.get_environments_by_name(metadata.environments)
        if not environments:
            raise EnvironmentMissingError(
                log,
                message='no environment found for experiment',
                possible_solutions=[
                    'load the environment with [i]adare environment load[/i]',
                    'create a new environment with [i]adare environment create[/i] and then load it'
                ]
            )

        experiment = Experiment(
            name=name,
            description=metadata.description,
            action_file=experiment_directory.actionfile.as_posix(),
            testset_file=experiment_directory.testsetfile.as_posix(),
            metadata_file=experiment_directory.metadatafile.as_posix(),
            bibtex_file=experiment_directory.bibtexfile.as_posix(),
            markdown_file=experiment_directory.markdownfile.as_posix(),
            sha256_action=experiment_directory.sha256_action,
            sha256_testset=experiment_directory.sha256_testset,
            sha256_metadata=experiment_directory.sha256_metadata,
            sha256_bibtex=experiment_directory.sha256_bibtex,
            sha256_markdown=experiment_directory.sha256_markdown,
            sha256=experiment_directory.sha256,
        )
        experiment.environments = environments
        experiment.tags = tags
        for obj in abstract_test_objects:
            if obj:
                experiment.abstract_tests.append(obj)
        self._session.add(experiment)
        self._session.commit()

        log.debug(f'added experiment {experiment.ulid} to database')
        return experiment

    def get_experiment(self, name: str, environment: Environment) -> Experiment:
        return (
            self._session.query(Experiment)
            .filter(Experiment.name == name, Experiment.environments.any(ulid=environment.ulid))
            .first()
        )

    def get_experiment_by_ulid(self, experiment_ulid: str) -> Experiment:
        return self._session.query(Experiment).filter_by(ulid=experiment_ulid).first()

    def __create_logfile(self, path: Path) -> LogFile:
        logfile = LogFile(
            name=path.name,
            path=path.as_posix()
        )
        self._session.add(logfile)
        return logfile

    def update_experiment_run(
            self, run_ulid: str, experiment: Experiment, environment: Environment, path: Path,
            logfile_vagrant: Path, logfile_installed_packages: Path, logfile_postsetup_installations: Path,
            logfile_run_experiment: Path, logfile_adarevm: Path, status: int
    ) -> ExperimentRun:
        experiment_run_files = ExperimentRunFiles(
            log_vagrant=self.__create_logfile(logfile_vagrant),
            package_dump=self.__create_logfile(logfile_installed_packages),
            log_installations=self.__create_logfile(logfile_postsetup_installations),
            log_run=self.__create_logfile(logfile_run_experiment),
            log_adarevm=self.__create_logfile(logfile_adarevm),
        )
        self._session.add(experiment_run_files)
        experiment_run = self._session.query(ExperimentRun).filter_by(ulid=run_ulid).first()
        experiment_run.environment = environment
        experiment_run.experiment = experiment
        experiment_run.path = path.as_posix()
        experiment_run.files = experiment_run_files
        experiment_run.status = status
        self._session.commit()
        return experiment_run

    def initialize_experiment_run(self) -> ExperimentRun:
        experiment_run = ExperimentRun()
        self._session.add(experiment_run)
        self._session.commit()
        return experiment_run

    def update_experiment_run_start(self, experiment_run_ulid: str, timestamp: datetime):
        experiment_run = self._session.query(ExperimentRun).filter_by(ulid=experiment_run_ulid).first()
        experiment_run.timestamp_start = timestamp

    def finish_experiment_run(self, experiment_run_ulid: str, timestamp: datetime):
        experiment_run = self._session.query(ExperimentRun).filter_by(ulid=experiment_run_ulid).first()
        experiment_run.timestamp_end = timestamp

    def remove_experiment_by_ulid(self, experiment_ulid: str):
        if (
                experiment := self._session.query(Experiment)
                        .filter_by(ulid=experiment_ulid)
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

    def experiment_sha256_equals(self, experiment_ulid: str, sha256: str) -> bool:
        experiment = self._session.query(Experiment).filter_by(ulid=experiment_ulid).first()
        return experiment.sha256 == sha256

    def __get_abstract_test(self, test: FTest, command_list: list[Command]) -> AbstractTest or None:
        all_commands_exist = all(
            cmd for cmd in test.depends_on if cmd in [cmd.name for cmd in command_list]
        )
        if not all_commands_exist:
            raise TestSetFormatError(
                log,
                message='test [b]{test.name}[/b] mentions a command that does not exist in the database.',
            )

        testfunction = self._session.query(TestFunction).filter_by(name=test.type).first()
        if not testfunction:
            raise TestSetFormatError(
                log,
                message=f'testfunction [b]{test.type}[/b] mentioned in test [b]{test.name}[/b] does not exist in the database.',
                possible_solutions=[
                    'ensure spelling and check if the testfunction is loaded by running: [i]adare testfunction list --filter type={test.type}[/i]',
                ]
            )

        parameter_entries = []
        for p_key, p_val in test.params.items():
            parameter = self._session.query(TestParameter).filter_by(name=p_key).first()
            # check if TestParameterEntry already exists
            test_parameter_entry_q = self._session.query(TestParameterEntry).filter_by(parameter=parameter,
                                                                                       value=str(p_val))
            test_parameter_entry_obj = test_parameter_entry_q.first()
            if not test_parameter_entry_obj:
                # create an TestParameterEntry object for the parameter
                test_parameter_entry_obj = TestParameterEntry(parameter=parameter, value=str(p_val))
                self._session.add(test_parameter_entry_obj)
                self._session.commit()
            parameter_entries.append(test_parameter_entry_obj)

        commands = [cmd for cmd in command_list if cmd.name in test.depends_on]
        parameter_entry_ids_data = [p.id for p in parameter_entries]
        abstract_test_obj = (
            self._session.query(AbstractTest)
            .join(AbstractTest.parameters)
            .join(AbstractTest.depends_on_tool)
            .filter(
                AbstractTest.name == test.name,
                AbstractTest.description == test.description,
                AbstractTest.testfunction == testfunction,
                Command.id.in_([c.id for c in commands]),
                TestParameterEntry.id.in_(parameter_entry_ids_data)
            )
            .first()
        )

        # if abstract test does not exist, create it
        if not abstract_test_obj:
            abstract_test_obj = AbstractTest(
                name=test.name,
                description=test.description,
                testfunction=testfunction,
                depends_on_tool=commands
            )
            abstract_test_obj.parameters = parameter_entries
            self._session.add(abstract_test_obj)

        return abstract_test_obj

    def __get_command_list(self, testset: FTestsetFile) -> list[Command]:
        command_list = []
        for cmd in testset.commands:
            command = self._session.query(Command).filter_by(
                name=cmd.name,
                command=cmd.command
            ).first()
            if not command:
                command = Command(
                    name=cmd.name,
                    command=cmd.command)
                self._session.add(command)
            command_list.append(command)
        return command_list

    def __get_abstracttests_from_testsetfile(self, testset: FTestsetFile) -> list[AbstractTest]:
        """
            Get/Creates the tests from the testset file.
        """
        command_list = self.__get_command_list(testset)
        return [self.__get_abstract_test(test, command_list) for test in testset.tests]

    def update_experiment_run_status(self, experiment_run_ulid: str, status: int):
        experiment_run = self._session.query(ExperimentRun).filter_by(ulid=experiment_run_ulid).first()
        experiment_run.status = status
        if status == StatusEnum.FINISHED or status == StatusEnum.INTERRUPTED:
            experiment_run.timestamp_end = datetime.utcnow()

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
                             .filter(AbstractTest.name == test_name, Experiment.ulid == experiment.ulid)
                             .first())
            if abstract_test:
                abstract_test.remote_ulid = test_ulid

        # Commit the changes to the session
        self._session.commit()

        return experiment

    def get_experiments(self, project_path: Path = None):
        if project_path:
            project = self.get_project_by_path(project_path)
            environments = self._session.query(Environment).filter_by(project=project).all()
            experiments = [experiment for environment in environments for experiment in environment.experiments]
            return experiments
        return self._session.query(Experiment).all()
