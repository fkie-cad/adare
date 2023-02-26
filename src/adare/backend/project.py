# external imports
import cattrs
import attr
from pathlib import Path
import pkg_resources
import shutil
import prettytable

# internal imports
from adare.backend.exceptions import ProjectCreationFailied, ProjectCleanupFailed, ProjectDeletionError, \
    ProjectEnvironmentCantBeCreated, ProjectNotRepairable, ProjectNotFound, ProjectInformationCouldNotBeRead, \
    ProjectInformationMissing, ProjectDirectoryParentDirectoryMissing, ProjectDirectoryAlreadyExists, \
    ProgramFolderMissingInInstallation, EnvironmentAlreadyExists, EnvironmentCreationError, \
    ScenarioDoesNotExistInEnvironment, EnvironmentDoesNotExist
from adare.backend.attrs_classes import ProjectInformation, UsbDevice, NetworkDrive
import adare.config as config
from adare.helperFunctions.yaml import yaml_to_dict, dict_to_yaml
from adare.backend.environment import Environment

# configure logging
import logging
log = logging.getLogger(__name__)


class Project:
    """
    this class is used to represent a project and to perform actions on this project such as creating an environment
    it is also used to access the environments stored inside the project
    """
    name: str
    base_directory: Path
    information: ProjectInformation or None
    information_file: Path

    def __init__(self, path: str, create: bool = False):
        self.information = None
        self.base_directory = Path(path).absolute()
        self.name = self.base_directory.name
        self.information_file = self.base_directory / '.projconf.yml'
        if create:
            log.info(f'project in path {self.base_directory} will be created')
            if self.base_directory.exists():
                raise ProjectDirectoryAlreadyExists(self.base_directory.as_posix())
            elif not self.base_directory.parent.exists():
                raise ProjectDirectoryParentDirectoryMissing(self.base_directory.as_posix())
            self.__create()
        if not create:
            log.info(f'project in path {self.base_directory} will be loaded')
            if not Path(path).exists():
                raise ProjectNotFound(self.base_directory.as_posix())
            self.__repair_if_broken()
            self.__load()

    def __read_information(self) -> ProjectInformation:
        """
        reads the information file store in the project (directory)

        :return: class containing project information
        """
        data = yaml_to_dict(self.information_file)
        if not data:
            raise ProjectInformationCouldNotBeRead
        self.information = cattrs.structure(data, ProjectInformation)
        return self.information

    def __write_information(self):
        """
        write (updated) project information to the project information file
        """
        dict_to_yaml(self.information_file, attr.asdict(self.information))

    def __load(self):
        """
        load an existing project
        """
        self.information_file = self.base_directory / '.projconf.yml'
        self.__read_information()
        log.info(f'loading project ({self.base_directory}) was successful')

    def __create(self):
        """
        create a new project
        """
        programs_in_installation = pkg_resources.resource_filename(config.PACKAGE, config.PCK_PROGRAMS)
        templates_in_installation = pkg_resources.resource_filename(config.PACKAGE, config.PCK_TEMPLATES)
        if not Path(programs_in_installation).is_dir():
            raise ProgramFolderMissingInInstallation(programs_in_installation)

        try:
            self.base_directory.mkdir()
        except FileNotFoundError or OSError as e:
            log.error(e, exc_info=True)
            self.__cleanup()
            raise ProjectCreationFailied(self.base_directory)

        try:
            shutil.copytree(programs_in_installation, self.base_directory / 'programs')
        except OSError as e:
            log.error(e, exc_info=True)
            self.__cleanup()
            raise ProjectCreationFailied(self.base_directory)

        try:
            shutil.copytree(templates_in_installation, self.base_directory / 'programs' / 'templates')
        except OSError as e:
            log.error(e, exc_info=True)
            self.__cleanup()
            raise ProjectCreationFailied(self.base_directory)

        self.__get_tessdata()

        for directoryname in ['setup', 'environments', 'additional_tools']:
            try:
                (self.base_directory / directoryname).mkdir()
            except OSError as e:
                log.error(e, exc_info=True)
                self.__cleanup()
                raise ProjectCreationFailied(self.base_directory)

        project_information_file = self.base_directory / '.projconf.yml'
        project_information = ProjectInformation(name=self.name)
        project_information_dict = attr.asdict(project_information)
        try:
            dict_to_yaml(project_information_file, project_information_dict)
        except OSError as e:
            log.error(e, exc_info=True)
            self.__cleanup()
            raise ProjectCreationFailied(self.base_directory)
        self.information = project_information
        self.information_file = project_information_file

        log.info(f'project ({self.base_directory}) creation was successful')

    def __get_tessdata(self):
        """
        copy tessdata needed for text recognition in the gui automation to the project
        """
        tessdata_dir = pkg_resources.resource_filename(config.PACKAGE, '/data/tessdata')
        try:
            shutil.copytree(tessdata_dir, self.base_directory/'tessdata')
        except OSError as e:
            log.error(e, exc_info=True)
            self.__cleanup()
            raise ProjectCreationFailied(self.base_directory)

    def __repair_if_broken(self):
        project_children = [f.name for f in self.base_directory.iterdir()]
        broken_element_found = False
        for mandatory_children in ['setup', 'environments', 'programs',
                                   '.projconf.yml']:
            if mandatory_children not in project_children:
                broken_element_found = True
                log.warning(f'needed directory/file {mandatory_children} is not a child of the project folder -> '
                            f'try to recreate the missing directory/file if possible')
                if not self.__repair_element(mandatory_children):
                    log.error(f'directory/file {mandatory_children} could NOT be recreated')
                    raise ProjectNotRepairable(self.name)
                else:
                    log.info(f'directory/file {mandatory_children} is successfully recreated')
        if broken_element_found:
            log.info(f'project ({self.base_directory}) repair was successful')
        else:
            log.debug(f'project ({self.base_directory}) contains all necessary elements')

    def list_environments(self, details=False):
        """
        list the environments (and possibly additional details about it) existing in the project

        :param details: show more details about the environments if set to True
        :return:
        """
        if self.information:
            table = prettytable.PrettyTable()
            if details:
                table.field_names = ["name", "description", "scenarios"]
            else:
                table.field_names = ["name", "description"]

            for env in self.information.environments:
                row = [env, "-"]
                if details:
                    Env = Environment(env, self.base_directory)
                    row.append(",".join([e.name for e in Env.configuration.scenarios]))
                table.add_row(row)
            print(f'\n\nList of all environments in project {self.information.name}:')
            print(table)
        else:
            raise ProjectInformationMissing

    # todo: add repair functions
    def __repair_element(self, element: str) -> bool:
        return False

    def __is_valid_project_directory(self) -> bool:
        """
        checks whether the project directory is a valid project directory
        this is done by checking for files that need to be in a project directory

        :return: bool that shows whether the project directory is a valid project
        """
        if not self.base_directory.is_dir():
            return False
        files_in_directory = [f.name for f in self.base_directory.iterdir() if f.is_file()]
        expected_files = ['.projconf.yml']
        for file in expected_files:
            if file not in files_in_directory:
                log.info(f'{file} is missing in the provided directory -> project can\'t be removed')
                return False
        return True

    def __cleanup(self):
        """
        clean up / delete the project directory
        """
        try:
            shutil.rmtree(self.base_directory.as_posix())
        except OSError as e:
            log.error(e, exc_info=True)
            raise ProjectCleanupFailed(self.base_directory)
        log.info(f'project ({self.base_directory}) cleanup was successful')

    def remove(self):
        """
        remove the project
        """
        if not self.__is_valid_project_directory():
            raise ProjectDeletionError(self.base_directory)
        try:
            self.__cleanup()
        except ProjectCleanupFailed:
            raise ProjectDeletionError(self.base_directory)
        log.info(f'project ({self.base_directory}) remove was successful')

    def __is_environment(self, name: str) -> bool:
        """
        checks if an specific environment (name) exists

        :param name: name of the environment
        :return: True if environment exists False if not
        """
        return name in self.information.environments

    def add_environment(self, setupfile: str = None, name=None):
        """
        create a new environment in the project

        :param setupfile: file with the setup configuration for the environment
        :param name: chosen name for the new environment
        :return: Environment instance which can be used in order to perform operations on the environment
        """
        if not name and not setupfile:
            raise ProjectEnvironmentCantBeCreated(self.name)
        if not name:
            name = Path(setupfile).stem
        if self.__is_environment(name):
            raise EnvironmentAlreadyExists

        Env = Environment(name, self.base_directory, create=True, setupfile=setupfile)
        if not Env:
            raise EnvironmentCreationError

        Env.add_examples()
        Env_info = Env.configuration
        project_information = self.information
        project_information.environments.append(Env_info.name)
        self.information = project_information
        self.__write_information()
        return Env

    def run_scenario(self, environment_name: str, scenario: str, debug=False):
        """
        run a scenario in a specified scenario

        :param environment_name: name of the environment
        :param scenario: name of the scenario that should be run
        :param debug: preventing vms from shutting down immediately after the scenario is done to enable a user to
                        check for possible errors or to test different things
        """
        if not self.__is_environment(environment_name):
            log.info(f'provided environment ({environment_name}) is not existing -> will be created if possible')
            Env = self.add_environment(name=environment_name)
        else:
            Env = Environment(environment_name, self.base_directory)
        environment_configuration = Env.configuration

        if scenario not in [s.name for s in environment_configuration.scenarios]:
            raise ScenarioDoesNotExistInEnvironment(environment_name, scenario)
        Env.run(scenario, debug=debug)

    # def add_input_to_environment(self, environment: str, input_files_path: str):
    #     """
    #     add input files to an environment
    #
    #     :param environment: name of the environment
    #     :param input_files_path: path to the input files/file (can be a file or a directory)
    #     """
    #     if not self.__is_environment(environment):
    #         raise EnvironmentDoesNotExist(environment)
    #     Env = Environment(environment, self.base_directory)
    #     Env.add_input_files(input_files_path)
    #     log.debug(f'input files in path {input_files_path} got added successfully to the environment {environment}')

    # def remove_input_from_environment(self, environment: str, input_file_name: str):
    #     if not self.__is_environment(environment):
    #         raise EnvironmentDoesNotExist(environment)
    #     Env = Environment(environment, self.path)
    #     Env.remove_input_file(input_file_name)

    # def create_guiscenario(self, environment: str, scenario: str):
    #     if not self.__is_environment(environment):
    #         raise EnvironmentDoesNotExist(environment)
    #     Env = Environment(environment, self.path)
    #     Env.create_gui_scenario_skeleton(scenario)
    #     log.debug(f'gui scenario file got create successfully')

    def create_scenario(self, environment_name: str, scenario_name: str, usb: str or None, networkdrive: str or None):
        """
        creates a new scenario in a specified environment

        :param environment_name: name of the environment
        :param scenario_name: name of the newly created scenario
        :param usb: name of a usb device if needed by the scenario
        :param networkdrive: name of a network drive if needed by the scenario
        """
        if not self.__is_environment(environment_name):
            raise EnvironmentDoesNotExist(environment_name)
        Env = Environment(environment_name, self.base_directory)
        Env.create_scenario(scenario_name, usb_name=usb, networkdrive_name=networkdrive)

    def remove_scenario(self, environment_name: str, scenario_name: str):
        """
        remove a scenario from an environment

        :param environment_name: name of the environment
        :param scenario_name: name of the scenario
        """
        if not self.__is_environment(environment_name):
            raise EnvironmentDoesNotExist(environment_name)
        Env = Environment(environment_name, self.base_directory)
        Env.remove_scenario(scenario_name)

    def add_usb_to_environment(self, environment_name: str, details: dict):
        """
        add an usb device to an environment, which can be used by scenario if specified in the scenario information

        :param environment_name: name of the environment
        :param details: information about the usb device
        """
        if not self.__is_environment(environment_name):
            raise EnvironmentDoesNotExist(environment_name)
        Env = Environment(environment_name, self.base_directory)
        Usb = cattrs.structure(details, UsbDevice)
        Env.add_usb(Usb)

    def add_networkdrive_to_environment(self, environment_name: str, details: dict):
        """
        add a network drive to an environment, which can be used by scenario if specified in the scenario information

        :param environment_name: name of the environment
        :param details: information about the network drive
        """
        if not self.__is_environment(environment_name):
            raise EnvironmentDoesNotExist(environment_name)
        Env = Environment(environment_name, self.base_directory)
        Networkdrive = cattrs.structure(details, NetworkDrive)
        Env.add_networkdrive(Networkdrive)

    def remove_environment(self, environment_name: str):
        """
        remove an environment from the project

        :param environment_name: name of the environment
        """
        if not self.__is_environment(environment_name):
            raise EnvironmentDoesNotExist(environment_name)
        Env = Environment(environment_name, self.base_directory)
        Env.remove()
        project_information = self.information
        for env in self.information.environments:
            if env == environment_name:
                project_information.environments.remove(env)
        self.information = project_information
        self.__write_information()
        log.debug(f'environment {environment_name} got removed successfully')
        print(f'\n\nenvironment {environment_name} got removed successfully')
