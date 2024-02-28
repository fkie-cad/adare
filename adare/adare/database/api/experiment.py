# external imports
import sqlalchemy
from pathlib import Path
from datetime import datetime
import json

# internal imports
from adarelib.helperfunctions.pyfileanalyze import PyModuleAnalyzer
from adarelib.helperfunctions.hash import combine_hashes
from adare.config.configdirectory import PROG_PARSEANDTEST_DIR
import adare.config.database as config_database
from adare.database.models.experiments import Tag, USBDrive, NFSDrive, SMBDrive, NFSShare, SMBShare, NetworkDriveUser, PostSetupInstallation, TestParameter, TestParameterEntry, Experiment, ExperimentRun, Status, TestFunction, AbstractTest, Test, Command, Result, OsInfo, LogFile, Environment, Project, Base as ExperimentsBase
from adare.database.api.project import ProjectDbApi
from adarelib.parsers import parse_testsetfile
from adarelib.types import TestsetFile as FTestsetFile, Test as FTest
from adarelib.types import UsbDevice as SetupUsbDevice, SMBConfiguration as SetupSMBConfiguration, NFSConfiguration as SetupNFSConfiguration, NFSShare as SetupNFSShare, SMBShare as SetupSMBShare, ExperimentMetadata
from adare.backend.experiment.directory import ExperimentDirectory
from adarelib.exceptions import TestSetFormatError

# configure logging
import logging
log = logging.getLogger(__name__)


class ExperimentApi(ProjectDbApi):
    testfunction_locations: dict[str, Path] = {
        'default': PROG_PARSEANDTEST_DIR/'src'/'parseandtest'/'testfunctions',
    }

    def __init__(self, db_path: Path = config_database.get_database_location()):
        super().__init__(db_path)
        ExperimentsBase.metadata.create_all(self.engine)

    def __enter__(self):
        super().__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        super().__exit__(exc_type, exc_val, exc_tb)

    def delete_experiment_run(self, experiment_run: ExperimentRun):
        """
            Deletes the experiment run from the database.
        """
        self._session.delete(experiment_run)

    def get_latest_experiment_by_project_and_name(self, project_path: Path, experiment_name: str) -> Experiment:
        project = self.get_project_by_path(project_path)
        return (
            self._session.query(Experiment)
            .filter_by(
                name=experiment_name,
                project=project
            )
            .order_by(sqlalchemy.desc(Experiment.created_at))
            .first()
        )

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
                raise ValueError(f'environment {name} not found in database')
        return environments

    def create_experiment(self, name: str, project_path: Path, experiment_directory: ExperimentDirectory) -> Experiment:
        project = self.get_project_by_path(project_path)
        testset = experiment_directory.load_testset()
        metadata = experiment_directory.load_metadata()

        abstract_test_objects: list = self.__get_abstracttests_from_testsetfile(testset)
        tags = self.get_or_create_tags(metadata.tags)
        environments = self.get_environments_by_name(metadata.environments)

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
            sha256_hash=experiment_directory.sha256,
            project=project,
        )
        experiment.environments = environments
        experiment.tags = tags
        for obj in abstract_test_objects:
            if obj:
                experiment.abstract_tests.append(obj)
        self._session.add(experiment)

        log.debug(f'added experiment {experiment.uuid} to database')

        return experiment

    def remove_experiment_by_uuid(self, experiment_uuid: str):
        if (
            experiment := self._session.query(Experiment)
            .filter_by(uuid=experiment_uuid)
            .first()
        ):
            self.remove_experiment(experiment)
        else:
            raise ValueError(f'experiment with uuid {experiment_uuid} not found')

    def remove_experiment(self, experiment: Experiment):
        # delete all experiment runs
        for run in experiment.runs:
            self._session.delete(run)
        self._session.delete(experiment)

    def experiment_sha256_equals(self, experiment_uuid: str, sha256: str) -> bool:
        experiment = self._session.query(Experiment).filter_by(uuid=experiment_uuid).first()
        return experiment.sha256_hash == sha256

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
            test_parameter_entry_q = self._session.query(TestParameterEntry).filter_by(parameter=parameter, value=str(p_val))
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

