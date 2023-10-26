# external imports
import cattrs
import attr
from pathlib import Path
import pkg_resources
import shutil
import prettytable

# internal imports
from adare.backend.attrs_classes import ProjectInformation, UsbDevice, NetworkDrive
import adare.config as config
from adare.helperFunctions.yaml import yaml_to_dict, dict_to_yaml
from adare.backend.environment import Environment
from adare.helperFunctions.web.download import download

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
                log.error(f'project in path {self.base_directory} already exists')
                exit(-1)
            elif not self.base_directory.parent.exists():
                log.error(f'parent directory of project in path {self.base_directory} does not exist')
                exit(-1)
            self.__create()
        if not create:
            log.info(f'project in path {self.base_directory} will be loaded')
            if not Path(path).exists():
                log.error(f'project in path {self.base_directory} does not exist')
                exit(-1)
            self.__repair_if_broken()
            self.__load()

    def __read_information(self) -> ProjectInformation:
        """
        reads the information file store in the project (directory)

        :return: class containing project information
        """
        data = yaml_to_dict(self.information_file)
        if not data:
            log.error(f'project information file ({self.information_file}) could not be read')
            exit(-1)
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
            log.error(f'programs directory ({programs_in_installation}) does not exist')
            exit(-1)

        try:
            self.base_directory.mkdir()
        except FileNotFoundError or OSError as e:
            log.error(e, exc_info=True)
            self.__cleanup()
            log.error(f'project ({self.base_directory}) creation failed')
            exit(-1)

        try:
            shutil.copytree(programs_in_installation, self.base_directory / 'programs', ignore=shutil.ignore_patterns('*.pyc', '__pycache__'))
        except OSError as e:
            log.error(e, exc_info=True)
            self.__cleanup()
            log.error(f'project ({self.base_directory}) creation failed')
            exit(-1)

        try:
            shutil.copytree(templates_in_installation, self.base_directory / 'programs' / 'templates', ignore=shutil.ignore_patterns('*.pyc', '__pycache__'))
        except OSError as e:
            log.error(e, exc_info=True)
            self.__cleanup()
            log.error(f'project ({self.base_directory}) creation failed')
            exit(-1)

        self.__get_tessdata()

        for directoryname in ['setup', 'environments', 'additional_tools']:
            try:
                (self.base_directory / directoryname).mkdir()
            except OSError as e:
                log.error(e, exc_info=True)
                self.__cleanup()
                log.error(f'project ({self.base_directory}) creation failed')
                exit(-1)

        project_information_file = self.base_directory / '.projconf.yml'
        project_information = ProjectInformation(name=self.name)
        project_information_dict = attr.asdict(project_information)
        try:
            dict_to_yaml(project_information_file, project_information_dict)
        except OSError as e:
            log.error(e, exc_info=True)
            self.__cleanup()
            log.error(f'project ({self.base_directory}) creation failed')
            exit(-1)
        self.information = project_information
        self.information_file = project_information_file

        log.info(f'project ({self.base_directory}) creation was successful')

    def __get_tessdata(self, tessdata_directory: Path = None):
        """
            copy tessdata needed for text recognition in the gui automation to the project
        """
        if not tessdata_directory:
            tessdata_directory = self.base_directory/'tessdata'
            tessdata_directory.mkdir()
            tessdata_github_link = r'https://github.com/tesseract-ocr/tessdata/blob/main/eng.traineddata?raw=true'
            tessdata_file = tessdata_directory/'eng.traineddata'
            download(tessdata_github_link, tessdata_file)
        else:
            shutil.copytree(tessdata_directory, self.base_directory / 'tessdata')

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
                    exit(-1)
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
                table.field_names = ["name", "description", "experiments"]
            else:
                table.field_names = ["name", "description"]

            for env in self.information.environments:
                row = [env, "-"]
                if details:
                    Env = Environment(env, self.base_directory)
                    row.append(",".join([e.name for e in Env.configuration.experiments]))
                table.add_row(row)
            print(f'\n\nList of all environments in project {self.information.name}:')
            print(table)
        else:
            log.error('project information is not loaded')
            exit(-1)

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
            log.error(f'project ({self.base_directory}) cleanup failed')
            exit(-1)
        log.info(f'project ({self.base_directory}) cleanup was successful')

    def remove(self):
        """
        remove the project
        """
        if not self.__is_valid_project_directory():
            log.error(f'project deletion failed because the project directory ({self.base_directory}) is not valid')
            exit(-1)
        self.__cleanup()
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
            log.error('either a setupfile or a name for the environment needs to be provided')
            exit(-1)
        if not name:
            name = Path(setupfile).stem
        if self.__is_environment(name):
            log.error(f'environment ({name}) already exists')
            exit(-1)

        Env = Environment(name, self.base_directory, create=True, setupfile=setupfile)
        if not Env:
            log.error(f'environment ({name}) creation failed')
            exit(-1)

        Env.add_examples()
        Env_info = Env.configuration
        project_information = self.information
        project_information.environments.append(Env_info.name)
        self.information = project_information
        self.__write_information()
        return Env

    def run_experiment(self, environment_name: str, experiment: str, debug=False):
        """
        run a experiment in a specified experiment

        :param environment_name: name of the environment
        :param experiment: name of the experiment that should be run
        :param debug: preventing vms from shutting down immediately after the experiment is done to enable a user to
                        check for possible errors or to test different things
        """
        if not self.__is_environment(environment_name):
            log.info(f'provided environment ({environment_name}) is not existing -> will be created if possible')
            Env = self.add_environment(name=environment_name)
        else:
            Env = Environment(environment_name, self.base_directory)
        environment_configuration = Env.configuration

        if experiment not in [s.name for s in environment_configuration.experiments]:
            log.error(f'provided experiment ({experiment}) is not existing in environment ({environment_name})')
            exit(-1)
        Env.run(experiment, debug=debug)

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

    # def create_guiexperiment(self, environment: str, experiment: str):
    #     if not self.__is_environment(environment):
    #         raise EnvironmentDoesNotExist(environment)
    #     Env = Environment(environment, self.path)
    #     Env.create_gui_experiment_skeleton(experiment)
    #     log.debug(f'gui experiment file got create successfully')

    def create_experiment(self, environment_name: str, experiment_name: str, usb: str or None, networkdrive: str or None):
        """
        creates a new experiment in a specified environment

        :param environment_name: name of the environment
        :param experiment_name: name of the newly created experiment
        :param usb: name of a usb device if needed by the experiment
        :param networkdrive: name of a network drive if needed by the experiment
        """
        if not self.__is_environment(environment_name):
            log.error(f'provided environment ({environment_name}) is not existing')
            exit(-1)
        Env = Environment(environment_name, self.base_directory)
        Env.create_experiment(experiment_name, usb_name=usb, networkdrive_name=networkdrive)

    def remove_experiment(self, environment_name: str, experiment_name: str):
        """
        remove a experiment from an environment

        :param environment_name: name of the environment
        :param experiment_name: name of the experiment
        """
        if not self.__is_environment(environment_name):
            log.error(f'provided environment ({environment_name}) is not existing')
            exit(-1)
        Env = Environment(environment_name, self.base_directory)
        Env.remove_experiment(experiment_name)

    def add_usb_to_environment(self, environment_name: str, details: dict):
        """
        add an usb device to an environment, which can be used by experiment if specified in the experiment information

        :param environment_name: name of the environment
        :param details: information about the usb device
        """
        if not self.__is_environment(environment_name):
            log.error(f'provided environment ({environment_name}) is not existing')
            exit(-1)
        Env = Environment(environment_name, self.base_directory)
        Usb = cattrs.structure(details, UsbDevice)
        Env.add_usb(Usb)

    def add_networkdrive_to_environment(self, environment_name: str, details: dict):
        """
        add a network drive to an environment, which can be used by experiment if specified in the experiment information

        :param environment_name: name of the environment
        :param details: information about the network drive
        """
        if not self.__is_environment(environment_name):
            log.error(f'provided environment ({environment_name}) is not existing')
            exit(-1)
        Env = Environment(environment_name, self.base_directory)
        Networkdrive = cattrs.structure(details, NetworkDrive)
        Env.add_networkdrive(Networkdrive)

    def remove_environment(self, environment_name: str):
        """
        remove an environment from the project

        :param environment_name: name of the environment
        """
        if not self.__is_environment(environment_name):
            log.error(f'provided environment ({environment_name}) is not existing')
            exit(-1)
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
