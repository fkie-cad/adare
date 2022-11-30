# external imports
import shutil
import cattrs
from cattrs.errors import ClassValidationError
from typing import Union
from datetime import datetime
import pkg_resources
import glob
import attr
from pathlib import Path
import jinja2
import os

# internal imports
import adare.config as config
from adare.backend.attrs_classes import Scenario, UsbDevice, ExamplesConfig, NetworkDrive, \
    EnvironmentConfiguration, EnvironmentSetup
from adare.backend.networkdrive import NetworkDriveContainer
from adare.helperFunctions.yaml import yaml_to_dict, dict_to_yaml
from adare.helperFunctions.jinja.jinjafeatures import init_jinja_environment
import adare.vagrantapi as vagrantapi
from adare.backend.script_creation import PostsetupInstallationsScript, RunExperimentScript,  \
    RunExperimentTemplateScript, SaveInstalledPackagesScript
from adare.backend.exceptions import EnvironmentInitializationFailed, EnvironmentSetupFileMissing, \
    EnvironmentConfigurationMissing, EnvironmentSetupSyntaxError, EnvironmentAlreadyExists, \
    PackageTemplateFolderMissing, ScenarioAlreadyExists, ScenarioDoesNotExistInEnvironment


# configure logging
import logging
log = logging.getLogger(__name__)


class Environment:
    """
    This class in used in order to maintain and change an environment.
    It contains functions to create, run, list and remove a scenario.
    """
    name: str

    project_directory: Path

    base_directory: Path
    programs_directory: Path
    guiscenario_directory: Path
    input_directory: Path
    log_directory: Path

    configuration_file: str
    configuration: EnvironmentConfiguration or None

    setupfile: str
    setup: EnvironmentSetup or None

    __jinja_environment: jinja2.Environment = None
    __script_suffix: str = None

    # used only for environment creation (in order to create basics scripts like run_experiment, ...)
    __jinja_project: jinja2.Environment = None

    def __init__(self, name: str, project_directory: Path, create=False, setupfile: str = None):
        self.name = name

        self.project_directory = project_directory

        self.base_directory = (self.project_directory/config.ENVDIR_RELPROJ / name)
        self.log_directory = self.base_directory / config.LOGDIR_RELENV
        self.programs_directory = self.base_directory / config.PROGRAMS_RELENV
        self.result_directory = self.base_directory / config.RESULT_RELENV
        self.input_directory = self.base_directory / config.INPUT_RELENV

        self.guiscenario_directory = self.programs_directory / config.GUIAUTOMATIONPROG / config.SCENARIOBASEDIR_IN_GUIAUTOMATION

        self.configuration_file = (self.base_directory / config.ENVCONFIGURATIONFILENAME).as_posix()
        self.configuration = None

        self.setup = None
        if create:
            self.setupfile = self.__find_setup_file(setupfile)
            self.__create()
        else:
            self.__load()
        self.__create_jinja_environment()
        if not self.__jinja_environment:
            raise EnvironmentInitializationFailed(self.name)
        if not self.configuration:
            raise EnvironmentInitializationFailed(self.name)

    def __find_setup_file(self, setupfile: str or None):
        """
        try to find a setup file in the setup folder of the project

        :param setupfile: path of the provided setupfile or None if no setupfile was provided
        :return: path of the setupfile
        """
        if not setupfile:
            P_setup_files_storage_in_project = self.project_directory / config.SETUPDIR_RELPROJ
            for file in P_setup_files_storage_in_project.iterdir():
                if file.stem == self.name:
                    setupfile = file.as_posix()
        if not setupfile:
            raise EnvironmentSetupFileMissing(self.name)
        return setupfile

    def __load_setup(self):
        """
        load the setup configuration from the setup file (yaml)
        it therefore creates an EnvironmentSetup instance out of the dict stored in the setup file
        """
        if self.setup:
            log.warning('setup is already loaded')
            return
        try:
            setup_dict = yaml_to_dict(self.setupfile)
        except FileNotFoundError:
            raise EnvironmentSetupFileMissing(self.name)
        try:
            self.setup = cattrs.structure(setup_dict, EnvironmentSetup)
        except ClassValidationError as e:
            log.error('environment setup file could not be read because of the following exception')
            log.error(e, exc_info=True)
            raise EnvironmentSetupSyntaxError()

    def __load_configuration(self) -> EnvironmentConfiguration:
        """
        load the environment configuration from the environment configuration file (.envconf.yml) located in the environment directory

        :return: dataclass containing the configuration of the environment
        """
        data = yaml_to_dict(self.configuration_file)
        if not data:
            raise EnvironmentConfigurationMissing
        self.configuration = cattrs.structure(data, EnvironmentConfiguration)
        return self.configuration

    def __save_configuration(self):
        """
        save the environment configuration to file (needs to be done after modification of the environment configuration)
        """
        dict_to_yaml(self.configuration_file, attr.asdict(self.configuration))

    def __create_jinja_project(self):
        """
        create a jinja environment for the templates directory which is located in the project programs directory
        """
        P_programs_in_project = self.project_directory / config.PROGRAMS_RELPROJ
        template_folder = (P_programs_in_project / 'templates' / self.setup.os).as_posix()
        self.__jinja_project = init_jinja_environment(template_folder)

    def __create_jinja_environment(self):
        """
        create a jinja environment for the templates directory which is located in the environment programs directory
        """
        template_folder = self.programs_directory.as_posix()
        self.__jinja_environment = init_jinja_environment(template_folder)

    def __create(self):
        """
        function to create an environment (should be only used in the __init__ function of this class)
        """
        if self.base_directory.exists():
            raise EnvironmentAlreadyExists(self.name)
        self.__load_setup()
        self.__script_suffix = config.SCRIPTS_SUFFIX[self.setup.os]

        self.__create_jinja_project()
        if not self.__jinja_project:
            raise EnvironmentInitializationFailed(self.name)

        P_programs_in_project = self.project_directory / config.PROGRAMS_RELPROJ
        P_scripts_in_environment = self.base_directory / config.PROGRAMS_RELENV

        self.base_directory.mkdir()

        for folder in [config.PROGRAMS_RELENV, config.INPUT_RELENV, config.LOGDIR_RELENV, config.RESULT_RELENV,
                       config.NETWORKDRIVE_RELENV, config.EXTERNALPROGRAMS_RELENV]:
            (self.base_directory / folder).mkdir()

        postsetup_installations_template_in_project = \
            (P_programs_in_project / 'templates' / str(self.setup.os) / f'postsetup_installations{self.__script_suffix}').as_posix()
        postsetup_installations_template_in_environment = (P_scripts_in_environment / f'template_postsetup_installations{self.__script_suffix}').as_posix()
        shutil.copy(postsetup_installations_template_in_project, postsetup_installations_template_in_environment)

        P_RunExperimentTemplate = self.base_directory / config.PROGRAMS_RELENV / f'template_run_experiment{self.__script_suffix}'
        script_RunTemplate = RunExperimentTemplateScript(P_RunExperimentTemplate.as_posix(), f'run_experiment{self.__script_suffix}', self.setup, jinja_environment=self.__jinja_project)
        script_RunTemplate.write()

        mount_networkdrives_script_in_project = (P_programs_in_project / 'templates' / str(self.setup.os) / f'mount_networkdrives{self.__script_suffix}').as_posix()
        mount_networkdrives_script_in_environment = (P_scripts_in_environment / f'template_mount_networkdrives{self.__script_suffix}').as_posix()
        shutil.copy(mount_networkdrives_script_in_project, mount_networkdrives_script_in_environment)

        save_installed_packages_script_in_project = (P_programs_in_project / 'templates' / str(self.setup.os) / f'save_installed_packages{self.__script_suffix}').as_posix()
        save_installed_packages_script_in_environment = (P_scripts_in_environment / f'template_save_installed_packages{self.__script_suffix}').as_posix()
        shutil.copy(save_installed_packages_script_in_project, save_installed_packages_script_in_environment)

        ParseAndTest_program_in_project = P_programs_in_project / 'ParseAndTest'
        ParseAndTest_program_in_environment = (P_scripts_in_environment / 'ParseAndTest').as_posix()
        shutil.copytree(ParseAndTest_program_in_project, ParseAndTest_program_in_environment)

        GUIAutomation_program_in_project = P_programs_in_project / 'GUIAutomation'
        GUIAutomation_program_in_environment = (P_scripts_in_environment / 'GUIAutomation').as_posix()
        shutil.copytree(GUIAutomation_program_in_project, GUIAutomation_program_in_environment)

        # copy input files to input directory inside environment directory
        input_in_environment = self.base_directory / config.INPUT_RELENV
        scenario_dict = self.__copy_input_from_setup(self.setup, input_in_environment)
        scenarios = [cattrs.structure(sce, Scenario) for sce in scenario_dict]
        for sce in scenarios:
            guiscenario_path = self.__check_if_gui_scenario_exists(sce.name)
            if guiscenario_path:
                sce.guiscenariofile = guiscenario_path
        self.configuration = EnvironmentConfiguration(name=self.name,
                                                      vagrantbox=self.setup.vagrantbox,
                                                      os=self.setup.os,
                                                      resolution=self.setup.resolution,
                                                      pause_after_gui_automation=self.setup.pause_after_gui_automation,
                                                      idle_after_os_starts=self.setup.idle_after_os_starts,
                                                      settings=self.setup.settings,
                                                      scenarios=scenarios,
                                                      usbdevices=self.setup.usbdevices,
                                                      networkdrives=self.setup.networkdrives,
                                                      postsetupinstallations=self.setup.postsetupinstallations)
        self.__save_configuration()

    def __load(self):
        """
        function to load an already existing environment
        """
        self.__load_configuration()
        self.__script_suffix = config.SCRIPTS_SUFFIX[self.configuration.os]

    def remove(self):
        """
        function to remove this environment (removes all associated files/directory)
        """
        shutil.rmtree(self.base_directory.as_posix())

    def __check_if_gui_scenario_exists(self, scenario_name: str) -> str or None:
        """
        check if a gui scenario file to a provided scenario is existing

        :param scenario_name: name of the scenario
        :return: path of the gui scenario file; None if no matching gui scenario file found
        """
        guiscenario_path = None
        for obj in glob.glob((self.guiscenario_directory / '**' / '*.yml').as_posix()):
            if Path(obj).stem == scenario_name:
                guiscenario_path = Path(obj).absolute().as_posix()
        return guiscenario_path

    def create_scenario(self, scenario_name: str, usb_name: str or None = None, networkdrive_name: str or None = None):
        """
        create scenario skeleton files (input file and gui scenario file)

        :param usb_name: name of usb device that is used in the scenario
        :param scenario_name: name of the scenario to be created
        """
        if self.__find_scenario(scenario_name):
            log.error(
                f'scenario with name {scenario_name} is already existing -> choose another name or delete the old scenario')
            return
        scenario_pyfile_imgfolder = self.create_gui_scenario_skeleton(scenario_name)
        input_file = self.add_input_file_skeleton(scenario_name)
        if usb_name:
            self.__add_usb_to_scenario(scenario_name, usb_name)
        if networkdrive_name:
            self.__add_networkdrive_to_scenario(scenario_name, networkdrive_name)
        print('\n\n')
        if scenario_pyfile_imgfolder:
            print(f'path of the newly created gui scenario file: {scenario_pyfile_imgfolder[0]}')
            print(
                f'path of the image folder (where to place the images for automation): {scenario_pyfile_imgfolder[1]}')
        if input_file:
            print(f'path of the newly created input file: {input_file}')

    def remove_scenario(self, scenario_name: str):
        """
        removes a scenario (includes both input file and gui scenario file as well as the scenario class)

        :param scenario_name: name of the scenario to be removed
        """
        if not self.__find_scenario(scenario_name):
            log.error(f'scenario with name {scenario_name} does NOT exist in environment')
            return
        self.__remove_gui_scenario_file(scenario_name)
        self.__remove_input_file(scenario_name)
        self.__remove_scenario_class(scenario_name)
        log.info(f'scenario {scenario_name} got deleted')

    def __add_usb_to_scenario(self, scenario_name: str, usb_name: str):
        """
        add a usb device to a scenario

        :param scenario_name: name of the scenario
        :param usb_name: name of the usb, that should be added to the scenario
        """
        Usb = self.__find_usb(usb_name)
        if not Usb:
            log.error(
                f'usb device {usb_name} is not existing in environment -> add a usb device to the environment first')
        if scenario_name not in Usb.scenarios:
            Usb.scenarios.append(scenario_name)
            log.info(f'usb device {Usb.name} got added successfully to scenario {scenario_name}')
        else:
            log.warning(f'scenario {scenario_name} does already use usb device {usb_name}')
        self.__save_configuration()

    def __find_usb(self, usb_name: str) -> UsbDevice or None:
        """
        find a usb device in the environment by the name of the usb

        :param usb_name: name of the usb device
        """
        for Usb in self.configuration.usbdevices:
            if Usb.name == usb_name:
                return Usb
        return None

    def add_usb(self, usb: UsbDevice):
        """
        adds a new usb device to the environment

        :param usb: dataclass for a usb device
        """
        if self.__find_usb(usb.name):
            log.error(f'usb with name {usb.name} can\'t be created, because it already exists')
            return
        self.configuration.usbdevices.append(usb)
        self.__save_configuration()
        log.info(f'usb {usb.name} got added successfully')

    def __add_networkdrive_to_scenario(self, scenario_name: str, networkdrive_name: str):
        Networkdrive = self.__find_networkdrive(networkdrive_name)
        if not Networkdrive:
            log.error(
                f'network drive {networkdrive_name} is not existing in environment -> add this network drive to the environment first')
        if scenario_name not in Networkdrive.scenarios:
            Networkdrive.scenarios.append(scenario_name)
            log.info(f'network drive {Networkdrive.name} got added successfully to scenario {scenario_name}')
        else:
            log.warning(f'scenario {scenario_name} does already use network drive {networkdrive_name}')
        self.__save_configuration()

    def __find_networkdrive(self, networkdrive_name: str) -> NetworkDrive or None:
        for Networkdrive in self.configuration.networkdrives:
            if Networkdrive.name == networkdrive_name:
                return Networkdrive
        return None

    def add_networkdrive(self, networkdrive: NetworkDrive):
        if self.__find_usb(networkdrive.name):
            log.error(f'network drive with name {networkdrive.name} can\'t be created, because it already exists')
            return
        self.configuration.networkdrives.append(networkdrive)
        self.__save_configuration()
        log.info(f'network drive {networkdrive.name} got added successfully')

    def __remove_gui_scenario_file(self, scenario_name: str):
        """
        removes the gui scenario file of a scenario

        :param scenario_name: name of the scenario
        """
        scenario_destination = self.programs_directory / config.GUIAUTOMATIONPROG / 'src' / 'guiautomation' / 'Scenario'
        P_scenario_file = scenario_destination / (scenario_name + ".py")
        os.remove(P_scenario_file.as_posix())
        scenario_class = self.__find_scenario(scenario_name)
        scenario_class.guiscenariofile = None
        log.debug(f'gui scenario file for scenario {scenario_name} got deleted')

    def __remove_input_file(self, scenario_name: str):
        """
        removes the input file of a scenario

        :param scenario_name: name of the scenario
        """
        P_input_file = self.input_directory
        P_input_file = P_input_file / (scenario_name + ".yml")
        os.remove(P_input_file.as_posix())
        scenario_class = self.__find_scenario(scenario_name)
        scenario_class.inputfile = None
        log.debug(f'input file for scenario {scenario_name} got deleted')

    def add_gui_scenario_file(self, gui_scenario_file: str, category: str or None = None):
        """
        adds an already existing gui scenario file (python file) to the environment

        :param gui_scenario_file: path of the gui scenario file to be added
        :param category: CURRENTLY NOT IN USE
        """
        scenario_destination = self.programs_directory / config.GUIAUTOMATIONPROG / 'src' / 'guiautomation' / 'Scenario'
        if category:
            # todo: category can't be used because the folder is a own package which would need to be included into the setup.cfg -> very complicated
            pass
        if not Path(gui_scenario_file).is_file() or Path(gui_scenario_file).suffix != '.py':
            log.error(f'the chosen path ({gui_scenario_file}) is not a python file')
            return
        if Path(gui_scenario_file).name in [f.name for f in scenario_destination.iterdir()]:
            log.error(f'the chosen gui scenario python file {gui_scenario_file} is already existing in the environment')
            return

        scenario_name = Path(gui_scenario_file).stem
        scenario_class = self.__find_scenario(scenario_name)
        if not scenario_class:
            scenario_class = self.__create_scenario_class(scenario_name)
        P_scenario_file = scenario_destination / (scenario_name + ".py")
        scenario_class.guiscenariofile = P_scenario_file.absolute().as_posix()

        shutil.copy(gui_scenario_file, scenario_destination.as_posix())

    def add_gui_scenario_img_folder(self, img_folder: str, category: str or None = None):
        """
        adds (image) files from a directory (img_folder) to the img directory of the environment

        :param img_folder: directory, where the image files are located
        :param category: CURRENTLY NOT IN USE
        """
        img_folder_destination = self.programs_directory / config.GUIAUTOMATIONPROG / 'src' / 'guiautomation' / 'Scenario' / 'data' / 'img'
        if category:
            # todo: category can't be used because the folder is a own package which would need to be included into the setup.cfg -> very complicated
            pass
        if not Path(img_folder).is_dir():
            log.error(
                f'the chosen path ({img_folder}) is not a directory -> therefore it can not be a valid gui scenario image folder')
            return
        for file in Path(img_folder).iterdir():
            if file.name not in [f.name for f in img_folder_destination.iterdir()]:
                shutil.copy(file.as_posix(), img_folder_destination.as_posix())
            else:
                log.error(f'the chosen image file {file.name} is already existing')

    def create_gui_scenario_skeleton(self, scenario_name: str) -> tuple or None:
        """
        creates a gui scenario file by a template (also creates scenario class if not already existing)

        :param scenario_name: name of the scenario
        """
        scenario_class = self.__find_scenario(scenario_name)
        if scenario_class and scenario_class.guiscenariofile:
            log.error(f'scenario {scenario_name} already has a gui scenario file')
            return None
        P_scenario_file = self.guiscenario_directory
        P_scenario_file = P_scenario_file / (scenario_name + ".py")
        templatefolder = pkg_resources.resource_filename(config.PACKAGE, config.PCK_TEMPLATES)
        if not Path(templatefolder).is_dir():
            raise PackageTemplateFolderMissing
        jinja = init_jinja_environment(templatefolder)
        template = jinja.get_template('ScenarioTemplate')
        with open(P_scenario_file.as_posix(), mode='w') as f:
            f.write(
                template.render(
                    {
                        'name': scenario_name
                    }
                )
            )
        if not scenario_class:
            scenario_class = self.__create_scenario_class(scenario_name)
        scenario_class.guiscenariofile = P_scenario_file.absolute().as_posix()
        self.__save_configuration()
        return P_scenario_file.as_posix(), self.programs_directory / config.GUIAUTOMATIONPROG / 'src' / 'guiautomation' / 'Scenario' / 'data' / 'img'

    def add_input_file_skeleton(self, scenario_name: str) -> str or None:
        """
        creates a input file by a template (also creates scenario class if not already existing)

        :param scenario_name: name of the scenario
        """
        scenario_class = self.__find_scenario(scenario_name)
        if scenario_class and scenario_class.inputfile:
            log.error(f'scenario {scenario_name} already has an input file')
            return None
        P_input_file = self.input_directory
        P_input_file = P_input_file / (scenario_name + ".yml")
        templatefolder = pkg_resources.resource_filename(config.PACKAGE, config.PCK_TEMPLATES)
        if not Path(templatefolder).is_dir():
            raise PackageTemplateFolderMissing
        jinja = init_jinja_environment(templatefolder)
        template = jinja.get_template('InputfileTemplate')
        with open(P_input_file.as_posix(), mode='w') as f:
            f.write(
                template.render(
                    {
                        'name': scenario_name
                    }
                )
            )
        if not scenario_class:
            scenario_class = self.__create_scenario_class(scenario_name)
        scenario_class.inputfile = P_input_file.absolute().as_posix()
        self.__save_configuration()
        return P_input_file.as_posix()

    def __find_scenario(self, scenario_name: str) -> Scenario or None:
        """
        find the dataclass for a scenario

        :param scenario_name: name of the scenario
        :return dataclass for scenario if scenario was found and None in all other cases
        """
        for sce in self.configuration.scenarios:
            if sce.name == scenario_name:
                return sce
        return None

    def __remove_scenario_class(self, scenario_name: str):
        """
        removes the dataclass for an scenario

        :param scenario_name: name of the scenario
        :return:
        """
        for sce in self.configuration.scenarios:
            if sce.name == scenario_name:
                self.configuration.scenarios.remove(sce)

    def __create_scenario_class(self, scenario_name: str, description='') -> Scenario or None:
        """
        creates a new dataclass for scenario and adds it to the environment configuration

        :param scenario_name: name of the scenario
        :param description: description for the scenario
        :return:
        """
        if self.__find_scenario(scenario_name):
            raise ScenarioAlreadyExists
        scenario_dataclass = Scenario(scenario_name, description)
        self.configuration.scenarios.append(
            scenario_dataclass
        )
        return scenario_dataclass

    def __add_inputfile_to_scenario_class(self, scenario_name: str, inputfile: str):
        """
        adds an input file to an scenario

        :param scenario_name: name of the scenario
        :param inputfile: path of the input file to insert
        """
        scenario_class: Scenario or None = self.__find_scenario(scenario_name)
        if not scenario_class:
            raise ScenarioDoesNotExistInEnvironment
        scenario_class.inputfile = inputfile

    def add_input_files(self, input_to_include: str) -> list:
        """
        add input files to an environment (and creates dataclass if necessary)

        :param input_to_include: path of the files/directory which should be included as input files
        :return: list, that contains the paths of all added input files
        """
        environment_input_files = [f.name for f in self.input_directory.iterdir()]
        if input_to_include[-1] in ['\\', '/']:
            input_to_include = input_to_include[:-1]
        P_input_to_include = Path(input_to_include)
        added_input_scenarios = []
        if P_input_to_include.is_dir():
            for file in P_input_to_include.iterdir():
                if not file.is_file():
                    log.warning(f'{file.as_posix()} gets ignored when copying files to input, because it is not a file')
                elif file.name in environment_input_files:
                    log.warning(
                        f'{file.as_posix()} gets ignored because a file with the same name is already existing in the environments input directory')
                else:
                    shutil.copy(file.as_posix(), self.input_directory)
                    added_input_scenarios.append((self.input_directory / file.name).as_posix())
                    log.info(f'{file.as_posix()} is copied to environments input folder')
        elif P_input_to_include.is_file():
            if P_input_to_include.name in environment_input_files:
                log.warning(
                    f'{P_input_to_include.as_posix()} gets ignored because a file with the same name is already existing in the environments input directory')
            else:
                shutil.copy(P_input_to_include.as_posix(), self.input_directory)
                added_input_scenarios.append((self.input_directory / P_input_to_include.name).as_posix())
                log.info(f'{P_input_to_include.as_posix()} is copied to environments input folder')
        else:
            log.error('the provided path for input files is neither a existing file or directory')
            return []

        for filepath in added_input_scenarios:
            scenario_name = Path(filepath).stem
            scenario_dataclass = self.__find_scenario(scenario_name)
            if not scenario_dataclass:
                scenario_dataclass = self.__create_scenario_class(scenario_name)
                self.configuration.scenarios.append(
                    scenario_dataclass
                )
            self.__add_inputfile_to_scenario_class(scenario_name, filepath)
        self.__save_configuration()
        return added_input_scenarios

    def __copy_input_from_setup(self, setup: EnvironmentSetup, outputdirectory: str) -> Union[list, None]:
        """
        copy input files provided in the environment setup file to the input directory of the environment and return a
        list of the scenarios

        """
        P_outputdirectory = Path(outputdirectory)
        inputdata = setup.scenarios

        scenarios = []
        for inp in inputdata:
            scenario_name = inp.name
            if Path(inp.inputfile).is_file():
                if "\"" in inp.name:
                    log.error("\" is not a allowed character in the name of an input file")
                    continue
                inputfile_in_outputdirectory = (P_outputdirectory / (inp.name + ".yml")).as_posix()
                shutil.copy(inp.inputfile, inputfile_in_outputdirectory)
                scenario_dict = {
                    'name': inp.name,
                    'description': inp.description,
                    'inputfile': inputfile_in_outputdirectory
                }
                scenarios.append(scenario_dict)
            else:
                log.error(f'input file for scenario {scenario_name} not found')
        return scenarios

    def add_examples(self):
        """
        ask the user if examples should be included and includes them if wished
        """
        include_examples = False
        GUIScenarios_in_package = Path(
            pkg_resources.resource_filename(config.PACKAGE, config.PCK_EXAMPLES_GUISCENARIOS))
        Inputfiles_in_package = Path(pkg_resources.resource_filename(config.PACKAGE, config.PCK_EXAMPLES_INPUTFILES))
        if 'ubuntu' in self.configuration.vagrantbox:
            example_class_name = 'Ubuntu Trash Bin'
            guiscenario_folder = GUIScenarios_in_package / 'UbuntuTrashBin'
            scenarioinput_folder = Inputfiles_in_package / 'UbuntuTrashBin'
        elif 'linuxmint' in self.configuration.vagrantbox:
            example_class_name = 'Linux Mint Trash Bin'
            guiscenario_folder = GUIScenarios_in_package / 'LinuxMintTrashBin'
            scenarioinput_folder = Inputfiles_in_package / 'LinuxMintTrashBin'
        elif 'win' in self.configuration.vagrantbox:
            example_class_name = 'Windows Trash Bin'
            guiscenario_folder = GUIScenarios_in_package / 'WindowsTrashBin'
            scenarioinput_folder = Inputfiles_in_package / 'WindowsTrashBin'
        else:
            return
        include_examples_inp = input(f'Should examples (for {example_class_name}) should be included? (Yes or No)?  ')
        if include_examples_inp in ['Yes', 'Y', 'y']:
            include_examples = True
            log.info('examples will be included')
        else:
            log.info('examples will be NOT included')
        if include_examples:
            scenario_files_examples = (guiscenario_folder / '*.py').as_posix()
            img_folder_examples = (guiscenario_folder / 'img').as_posix()
            example_config = (guiscenario_folder / 'config.yml').as_posix()
            example_config_dict = yaml_to_dict(example_config)
            Example_Config = cattrs.structure(example_config_dict, ExamplesConfig)
            existing_network_drives = [d.name for d in self.configuration.networkdrives]
            for network_drive in Example_Config.networkdrives:
                if network_drive.name not in existing_network_drives:
                    self.configuration.networkdrives.append(network_drive)
                else:
                    log.warning(f'{network_drive.name} is already existing in the environment and will not be added')
            for file in glob.glob(scenario_files_examples):
                if Path(file).name != '__init__.py':
                    self.add_gui_scenario_file(Path(file).as_posix())
            for folder in glob.glob(img_folder_examples):
                self.add_gui_scenario_img_folder(Path(folder).as_posix())

            input_files_examples = (scenarioinput_folder / '*.yml').as_posix()
            for file in glob.glob(input_files_examples):
                self.add_input_files(file)
            self.__save_configuration()
            log.info('example file were included successfully')

    # def setup_network_drives(self, jinja: jinja2.Environment, scenario_name: str, logfolder: str) -> list or None:
    #     P_mountnetworkdrivescript = self.programs_directory / f'mount_networkdrives{self.__script_suffix}'
    #     used_network_drives = []
    #     for drive in self.setup.networkdrives:
    #         if scenario_name in drive.scenarios:
    #             used_network_drives.append(drive)
    #
    #     if used_network_drives:
    #         vm_config_directory = (self.base_directory / config.NETWORKDRIVE_RELENV).as_posix()
    #         VM = NetworkdriveVM(vm_config_directory)
    #         for index, drive in enumerate(used_network_drives):
    #             is_valid_drive = True
    #             if drive.type not in config.SUPPORTED_NETWORKDRIVE_TYPES:
    #                 is_valid_drive = False
    #
    #             if is_valid_drive:
    #                 if drive.type == "smb":
    #                     VM.create_smb()
    #                     smb_share = SMBShare(drive.name)
    #                     if drive.path:
    #                         smb_share.path = drive.path
    #                     if drive.user:
    #                         user = SMBUser(drive.user.name, drive.user.password)
    #                         VM.add_smb_user(user)
    #                         smb_share.user = user
    #                     if drive.comment:
    #                         smb_share.comment = drive.comment
    #                     if drive.writable:
    #                         smb_share.writable = drive.writable
    #                     VM.add_smb_share(smb_share)
    #                     log.info(f'smb share {smb_share.name} got added successfully to the network drive vm')
    #                 elif drive.type == "nfs":
    #                     VM.create_nfs()
    #                     nfs_share = NFSShare(drive.name)
    #                     if drive.path:
    #                         nfs_share.path = drive.path
    #                     if drive.host:
    #                         nfs_share.host = drive.host
    #                     if drive.options:
    #                         nfs_share.options = drive.options
    #                     VM.add_nfs_share(nfs_share)
    #                     log.info(f'nfs share {nfs_share.name} got added successfully to the network drive vm')
    #                 else:
    #                     log.error(f'network drive type {drive.type} is not supported')
    #
    #             mount_commands = VM.get_mount_commands(self.configuration.os)
    #             script_mountnetworkdrive = MountNetworkDriveScript(P_mountnetworkdrivescript.as_posix(), f'template_mount_networkdrives{self.__script_suffix}', mount_commands, logfolder, jinja_environment=jinja)
    #             script_mountnetworkdrive.write()
    #
    #         return [VM]
    #     else:
    #         script_mountnetworkdrive = MountNetworkDriveScript(P_mountnetworkdrivescript.as_posix(),
    #                                                            f'template_mount_networkdrives{self.__script_suffix}',
    #                                                            [], logfolder, jinja_environment=jinja)
    #         script_mountnetworkdrive.write()
    #         return []

    def create_Vagrantfile(self, scenario_name: str, hostonly: bool = False, networkdrive_active=False):
        conf = self.configuration
        Vagrant_creator = vagrantapi.VagrantFile()

        vgbox = conf.vagrantbox
        Vagrant_creator.set_box(vgbox)
        Vagrant_creator.set_vbox_name('testvgbox')

        if conf.os == 'windows':
            Vagrant_creator.change_communicator('winrm')

        if hostonly:
            Vagrant_creator.add_network_private(config.DEFAULT_VM_IP)

        Vagrant_creator.enable_gui()
        Vagrant_creator.disable_virtualbox_guestautoupdate()

        usbdevices = []
        for usbdevice in conf.usbdevices:
            if scenario_name in usbdevice.scenarios:
                usbdevices.append(usbdevice)

        at_least_one_usb_device = False
        for device in usbdevices:
            vendor_id = None
            product_id = None
            manufacturer = None
            product = None
            serial_number = None
            name = device.name

            at_least_one_usb_device = True
            if hasattr(device, 'VendorId'):
                vendor_id = device.VendorId
            if hasattr(device, 'ProductId'):
                product_id = device.ProductId
            if hasattr(device, 'Manufacturer'):
                manufacturer = device.Manufacturer
            if hasattr(device, 'Product'):
                product = device.Product
            if hasattr(device, 'SerialNumber'):
                serial_number = device.SerialNumber
            Vagrant_creator.add_usb_device(name, vendor_id=vendor_id, product_id=product_id, manufacturer=manufacturer,
                                           product=product, serial_number=serial_number)

        idle_after_os_starts = conf.idle_after_os_starts

        if at_least_one_usb_device:
            if int(idle_after_os_starts) < 90:
                idle_after_os_starts = "90"

        P_postsetup_installations = self.programs_directory / f'postsetup_installations{self.__script_suffix}'
        P_mount_networkdrives = self.programs_directory / f'mount_networkdrives{self.__script_suffix}'
        P_run_experiment = self.programs_directory / f'run_experiment{self.__script_suffix}'
        P_save_installed_packages = self.programs_directory / f'save_installed_packages{self.__script_suffix}'

        if conf.os == 'linux':
            Vagrant_creator.add_shell_provisioner_inline("sleep " + idle_after_os_starts)
            Vagrant_creator.add_shell_provisioner_path(P_postsetup_installations.absolute().as_posix())
            if networkdrive_active:
                Vagrant_creator.add_shell_provisioner_path(P_mount_networkdrives.absolute().as_posix())
            Vagrant_creator.add_shell_provisioner_path(P_run_experiment.absolute().as_posix())
            Vagrant_creator.add_shell_provisioner_path(P_save_installed_packages.absolute().as_posix())
        elif conf.os == 'windows':
            Vagrant_creator.add_shell_provisioner_inline("sleep " + idle_after_os_starts, privileged=True,
                                                         powershell_elevated_interactive=False)
            Vagrant_creator.add_shell_provisioner_path(P_postsetup_installations.absolute().as_posix(), privileged=True,
                                                       powershell_elevated_interactive=False)
            if networkdrive_active:
                Vagrant_creator.add_shell_provisioner_path(P_mount_networkdrives.absolute().as_posix(), privileged=True,
                                                           powershell_elevated_interactive=True)
            Vagrant_creator.add_shell_provisioner_path(P_run_experiment.absolute().as_posix(), privileged=True,
                                                       powershell_elevated_interactive=True)
            Vagrant_creator.add_shell_provisioner_path(P_save_installed_packages.absolute().as_posix(), privileged=True,
                                                       powershell_elevated_interactive=True)
        else:
            log.error(f'os {conf.os} not supported')
            return
        return Vagrant_creator

    def run(self, scenario: str, debug=False):
        """
        run a scenario

        :param scenario: name of the scenario
        :param debug: if True the vm will be not shutdown (immediately) after the scenario but instead wait for a user input to shutdown and clean up
        """

        scenario_class: Scenario = self.__find_scenario(scenario)

        if not scenario_class:
            log.error(f'scenario {scenario} does not exist in environment configuration')
            return
        if not scenario_class.inputfile:
            log.error(f'scenario {scenario} missing a valid input file')
            return
        if not scenario_class.guiscenariofile:
            log.error(f'scenario {scenario} missing a valid gui scenario file')
            return
        if not scenario_class.input_is_valid():
            log.error(
                f'scenario {scenario} can\'t be started because the input file has an error in format (as shown in the exception above)')
            return
        # not implemented so far
        if not scenario_class.guiscenario_is_valid():
            log.error(
                f'scenario {scenario} can\'t be started because the gui scenario file has an error in format (as shown in the exception above)')
            return
        timestamp = datetime.now().strftime(config.TIMESTAMP_FORMAT).replace(':', '.')

        scenario_log_directory = self.log_directory / f'{scenario}_{timestamp}'
        scenario_log_directory.mkdir()
        scenario_log_directory_vm_view = (Path('/vagrant') / scenario_log_directory.relative_to(self.base_directory)).as_posix()

        resultfile_name = 'result.yml'
        scenario_result_directory = self.result_directory / f'{scenario}_{timestamp}'
        scenario_result_directory.mkdir()
        scenario_resultfile = scenario_result_directory / resultfile_name
        scenario_result_directory_vm_view = Path('/vagrant') / scenario_result_directory.relative_to(self.base_directory)
        scenario_resultfile_vm_view = (scenario_result_directory_vm_view / resultfile_name).as_posix()

        path_postsetupinstallation = self.programs_directory / f'postsetup_installations{self.__script_suffix}'
        path_runexperiment = self.programs_directory / f'run_experiment{self.__script_suffix}'
        path_saveinstalledpackages = self.programs_directory / f'save_installed_packages{self.__script_suffix}'
        path_mountnetworkdrives = self.programs_directory / f'mount_networkdrives{self.__script_suffix}'

        script_postinstall = PostsetupInstallationsScript(path_postsetupinstallation.as_posix(),
                                                          f'template_postsetup_installations{self.__script_suffix}',
                                                          self.configuration,
                                                          scenario_log_directory_vm_view,
                                                          jinja_environment=self.__jinja_environment)
        script_run = RunExperimentScript(path_runexperiment.as_posix(),
                                         f'template_run_experiment{self.__script_suffix}',
                                         scenario,
                                         scenario_resultfile_vm_view,
                                         scenario_log_directory_vm_view,
                                         jinja_environment=self.__jinja_environment)
        script_saveinstalledpackages = SaveInstalledPackagesScript(path_saveinstalledpackages.as_posix(),
                                                                   f'template_save_installed_packages{self.__script_suffix}',
                                                                   scenario_log_directory_vm_view,
                                                                   jinja_environment=self.__jinja_environment)

        script_postinstall.write()
        script_run.write()
        script_saveinstalledpackages.write()

        # start network drives
        publicnetwork = False
        networkdrive_container = None
        networkdrive_active = False
        for drive in self.configuration.networkdrives:
            if scenario in drive.scenarios:
                networkdrive_active = True
        if networkdrive_active:
            networkdrive_dir = (self.base_directory / config.NETWORKDRIVE_RELENV).as_posix()

            networkdrive_container = NetworkDriveContainer(self.configuration.networkdrives, scenario, networkdrive_dir)

            networkdrive_container.write_mount_script(path_mountnetworkdrives.as_posix(),
                                                      self.configuration.os,
                                                      f'template_mount_networkdrives{self.__script_suffix}',
                                                      scenario_log_directory_vm_view,
                                                      jinja_environment=self.__jinja_environment)

            if not networkdrive_container:
                log.error(f'scenario {scenario} will not start because the network drive vm couldn\'t get created')
            networkdrive_container.start()

            if networkdrive_container:
                publicnetwork = True

        log_file_path = scenario_log_directory/'vagrant.log'
        log.debug(f'log path for vagrant log: {log_file_path.absolute()}')

        vagrantfile = self.create_Vagrantfile(scenario, hostonly=publicnetwork, networkdrive_active=networkdrive_active)
        box = vagrantapi.VagrantBox.fromVagrantFileObject(self.base_directory, vagrantfile, log_file=log_file_path)
        vg_success = box.run(debug=debug)

        # remove temporary created scripts todo: create a safe delete function that catches cases where exception occur
        script_postinstall.remove()
        script_run.remove()
        script_saveinstalledpackages.remove()
        if networkdrive_active and (
                self.programs_directory / f'mount_networkdrives{self.__script_suffix}').is_file():
            os.remove((self.programs_directory / f'mount_networkdrives{self.__script_suffix}').as_posix())

        # delete Vagrantfile
        os.remove((self.base_directory / 'Vagrantfile').as_posix())

        # stop network drives
        if networkdrive_active:
            if networkdrive_container:
                if networkdrive_container.VM.is_alive():
                    networkdrive_container.stop()
                else:
                    log.error("network drive was shutdown early")

        if vg_success == 0:
            print('\n\ntest result can be found in the following path:')
            print(scenario_resultfile.as_posix())
        elif vg_success == 1:
            print('\n\nan error during execution occurred - please check the logs and the above log messages')
        elif vg_success == 2:
            print('\n\nan error during the destroy process of the vagrant box occurred - please try to clean it up manually')
