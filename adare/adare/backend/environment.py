# external imports
import random
import shutil
import cattrs
from datetime import datetime
import glob
import attr
from pathlib import Path
import jinja2
import os

# internal imports
import adare.config as config
from adare.config.configdirectory import TEMPLATES_DIR, EXAMPLES_DIR, PROGRAMS_DIR
from adare.backend.attrs_classes import Experiment, UsbDevice, \
    EnvironmentConfiguration, EnvironmentSetup
from adare.backend.networkdrive import NetworkDriveContainer
from adare.helperFunctions.yaml import yaml_to_dict, dict_to_yaml
from adare.helperFunctions.csv import csv_to_dict
from adare.helperFunctions.jinja.jinjafeatures import init_jinja_environment
from adare.backend.script_creation.scripts import PostsetupInstallationsScript, RunExperimentScript, \
    SaveInstalledPackagesScript, MountNetworkDriveScript
from adare.backend.script_creation.Scriptmanager import ScriptManager
from adare.backend.script_creation.Script import Script
from adare.vagrantapi.vagrantbox import VagrantBoxVM
from adare.vagrantapi.vagrantfile import VagrantFile, VagrantMachine
from adare.database.api.experiment import ExperimentApi
from adare.database.api.project import ProjectManagementApi
from adare.database.models.experiment import Environment as EnvironmentModel
from adare.backend.setupfile import load_setupfile, load_experiment_metadata
from adare.networkdrive.attrs_classes import SMBShare, NFSShare

# configure logging
import logging

log = logging.getLogger(__name__)


class Environment:
    """
    This class in used in order to maintain and change an environment.
    It contains functions to create, run, list and remove a experiment.
    """
    name: str

    project: str
    project_directory: Path

    base_directory: Path
    programs_directory: Path
    guiexperiment_directory: Path
    log_directory: Path

    platform: str

    setupfile: Path
    setup: EnvironmentSetup or None

    __jinja_environment: jinja2.Environment = None
    __script_suffix: str = None

    # used only for environment creation (in order to create basics scripts like run_experiment, ...)
    __jinja_project: jinja2.Environment = None

    # scripts directory from VM view
    script_directory_vm_view: Path
    log_directory_vm_view = Path

    # script manager
    __script_manager: ScriptManager = None

    def __init__(self, name: str, project: Path, create=False, setupfile: Path = None):
        self.name = name
        self.setup = None
        self.project = project.name
        self.project_directory = project

        # retrieve project directory from database
        with ProjectManagementApi() as db:
            project_class = db.get_project(self.project)
            if not project_class:
                log.error(f'project {project} not found')
                exit(-1)
            self.project_directory = Path(project_class.path)

        self.project_setup_directory = self.project_directory / 'setup'

        self.base_directory = (self.project_directory / 'environments' / name)

        if create:
            self.setupfile = self.__find_setup_file(setupfile)
            if self.base_directory.exists():
                log.error(f'environment {name} already exists')
                exit(-1)
            self.setup = self.__load_setup()
            self.__script_suffix = config.SCRIPTS_SUFFIX[self.setup.os_platform]
            self.project_scripts_directory = self.project_directory / 'programs' / 'templates' / self.setup.os_platform

        # set up paths used in project an environment
        self.project_additional_tools_directory = self.project_directory / 'additional_tools'
        self.project_guiautomation_program = self.project_directory / 'programs' / 'GUIAutomation'
        self.project_parseandtest_program = self.project_directory / 'programs' / 'ParseAndTest'

        self.log_directory = self.base_directory / 'logs'
        self.result_directory = self.base_directory / 'result'
        self.run_directory = self.base_directory / 'run'
        self.experiment_directory = self.base_directory / 'experiment'

        if create:
            self.__create()
        else:
            self.__load()

        if not self.platform:
            log.error(f'platform of environment {self.name} not set')
            exit(-1)

        self.project_scripts_directory = self.project_directory / 'programs' / 'templates' / self.platform

        # set up paths from the view of the guest/vm
        vm_root_path = Path(r'/')
        if self.platform == 'windows':
            vm_root_path = Path(r'C:/')

        self.vm_project_directory = vm_root_path / 'project'
        self.vm_project_programs_directory = self.vm_project_directory / 'programs'
        self.vm_project_additional_tools_directory = self.vm_project_directory / 'additional_tools'
        self.vm_environment_directory = self.vm_project_directory / 'environments' / self.name
        self.vm_environment_logs_directory = self.vm_project_directory / 'environments' / self.name / 'logs'
        self.vm_environment_result_directory = self.vm_project_directory / 'environments' / self.name / 'result'
        self.vm_environment_run_directory = self.vm_project_directory / 'environments' / self.name / 'run'
        self.vm_environment_experiment_directory = self.vm_project_directory / 'environments' / self.name / 'experiment'

        self.vm_tessdata_directory = self.vm_project_directory / 'tessdata'

        self.__script_manager = ScriptManager(
            script_directory_vm_view=self.vm_environment_run_directory,
            wrapper_template=self.project_scripts_directory / f'run_script_wrapper{self.__script_suffix}'
        )

        # update testfunction -> maybe do only on environment creation and demand
        with ExperimentApi() as db:
            db.update_testfunctions()

    def __find_setup_file(self, setupfile: Path):
        """
        try to find a setup file in the setup folder of the project

        :param setupfile: path of the provided setupfile or None if no setupfile was provided
        :return: path of the setupfile
        """
        if not setupfile:
            setup_files_storage_in_project = self.project_setup_directory
            for file in setup_files_storage_in_project.iterdir():
                if file.stem == self.name:
                    setupfile = file
        if not setupfile:
            log.error(f'no setup file found for environment {self.name} found')
            exit(-1)
        return setupfile

    def __load_setup(self):
        """
        load the setup configuration from the setup file (yaml)
        it therefore creates an EnvironmentSetup instance out of the dict stored in the setup file
        """
        if self.setup:
            log.warning('setup is already loaded')
            return
        setup = load_setupfile(self.setupfile)
        if not setup:
            log.error(f'loading setup file {self.setupfile} failed')
            exit(-1)
        return setup

    def __create_jinja_project(self):
        """
        create a jinja environment for the templates directory which is located in the project programs directory
        """
        self.__jinja_project = init_jinja_environment(self.project_scripts_directory)

    def __create(self):
        """
        function to create an environment (should be only used in the __init__ function of this class)
        """
        self.__create_jinja_project()
        if not self.__jinja_project:
            log.error(f'jinja env could not be created')
            exit(-1)

        self.platform = self.setup.os_platform

        self.base_directory.mkdir()

        for folder in ['logs', 'result', 'networkdrives', 'experiment', 'run']:
            (self.base_directory / folder).mkdir()

        os_info: dict = {
            'platform': self.setup.os_platform,
            'os': self.setup.os,
            'distribution': self.setup.os_distribution,
            'version': self.setup.os_version,
            'language': self.setup.os_language,
            'architecture': self.setup.os_architecture,
        }

        # create entry in database for this environment
        with ProjectManagementApi() as db:
            env = db.add_environment(
                name=self.name,
                path=self.base_directory,
                project_name=self.project,
                description=self.setup.description,
                os_info=os_info,
                vagrant_box=self.setup.vagrantbox,
            )
            for installation in self.setup.postsetupinstallations:
                db.add_postsetup_installation(
                    environment=env,
                    name=installation.name,
                    command=installation.command,
                    description=installation.description,
                )

        log.debug(f'environment {self.name} created in database')

    def __update_experiments(self):
        """
        checks the experiment directory for experiments and adds them to the environment within the database
        :return:
        """
        log.debug(f'updating experiments in environment {self.name}')
        with ProjectManagementApi() as db:
            env = db.get_environment(name=self.name, project_name=self.project)
            for experiment in self.experiment_directory.iterdir():
                experiment_name = experiment.name
                if not db.get_experiment_in_env(self.project, experiment_name, self.name):
                    log.debug(f'experiment {experiment.name} not found in database -> adding it')
                    # check if necessary files are existing
                    action_file = self.__check_if_actionfile_exists(experiment_name)
                    if not action_file:
                        log.warning(
                            f'experiment {experiment_name} is missing the gui automation file -> can\'t add experiment to environment')
                        continue
                    testset_file = self.__check_if_testsetfile_exists(experiment_name)
                    if not testset_file:
                        log.warning(
                            f'experiment {experiment_name} is missing the testset file -> can\'t add experiment to environment')
                        continue
                    experiment_metadata_file = self.__check_if_experimentmetadatafile_exists(experiment_name)
                    if not experiment_metadata_file:
                        # create empty experiment metadata file
                        experiment_metadata_file = self.experiment_directory / experiment_name / 'metadata.yml'
                        experiment_metadata_file.touch()
                        log.warning(
                            f'experiment {experiment_name} is missing the experiment metadata file -> empty file got created')
                    metadata = load_experiment_metadata(experiment_metadata_file)

                    log.debug(f'metadata loaded {metadata}')

                    # add experiment to database
                    os_info = db.get_environment(name=self.name, project_name=self.project).osinfo
                    exp, existed = db.get_experiment(
                        os_info=os_info,
                        action_file=action_file,
                        testset_file=testset_file,
                        environment=env,
                    )

                    if not exp:
                        print(
                            f'could not add experiment {experiment_name} to database -> most likely to an already existing experiment with the same name')
                        continue

                    if metadata:
                        # add network drives to experiment
                        if metadata.smb:
                            db.add_smb_to_experiment(exp, metadata.smb)
                        if metadata.nfs:
                            db.add_nfs_to_experiment(exp, metadata.nfs)
                        # add usb devices to experiment
                        if metadata.usb:
                            db.add_usb_to_experiment(exp, metadata.usb)

                    if existed:
                        log.debug(f'experiment {experiment_name} found in database')
                    else:
                        log.debug(f'experiment {experiment_name} added to environment {self.name}')
            # remove experiments from database which are not existing in the environment
            for experiment in db.get_experiments_in_env(self.project, self.name):
                if not (self.experiment_directory / experiment.name).is_dir():
                    db.remove_experiment(env, experiment.name)
                    log.debug(f'experiment {experiment.name} removed from database')
        log.debug(f'experiments in environment {self.name} updated')

    def __load(self):
        """
        function to load an already existing environment
        """
        with ProjectManagementApi() as db:
            environment: EnvironmentModel = db.get_environment(name=self.name, project_name=self.project)
            if not environment:
                print(f'environment {self.name} does not exist in project {self.project}')
                exit(-1)
            self.platform = environment.osinfo.platform
            self.__script_suffix = config.SCRIPTS_SUFFIX[self.platform]
        self.__update_experiments()

    def remove(self):
        """
        function to remove this environment (removes all associated files/directory)
        """
        # remove directory
        shutil.rmtree(self.base_directory.as_posix())
        # remove entry in database for this environment
        with ProjectManagementApi() as db:
            db.remove_environment(name=self.name, project_name=self.project)

    def __create_actionfile_skeleton(self, experiment_name: str):
        """
        creates an action skeleton file for a given experiment name
        """
        jinja = init_jinja_environment(TEMPLATES_DIR)
        template = jinja.get_template('ExperimentTemplate')
        filepath = self.experiment_directory / experiment_name / f'{experiment_name}.py'
        with open(filepath.as_posix(), mode='w') as f:
            f.write(
                template.render(
                    {
                        'name': experiment_name
                    }
                )
            )

    def __create_testsetfile_skeleton(self, experiment_name: str):
        """
        creates a testset file skeleton file for a given experiment name
        """
        jinja = init_jinja_environment(TEMPLATES_DIR)
        template = jinja.get_template('TestsetfileTemplate')
        filepath = self.experiment_directory / experiment_name / f'{experiment_name}.yml'
        with open(filepath.as_posix(), mode='w') as f:
            f.write(
                template.render(
                    {
                        'name': experiment_name
                    }
                )
            )

    def __check_if_testsetfile_exists(self, experiment_name: str):
        """
        check if a testset file to a provided experiment is existing

        :param experiment_name: name of the experiment
        :return:
        """
        testset_file = self.experiment_directory / experiment_name / (experiment_name + '.yml')
        if not testset_file.is_file():
            log.error(f'testset file for experiment {experiment_name} is missing')
            return None
        return testset_file

    def __check_if_actionfile_exists(self, experiment_name: str):
        """
        check if an action file to a provided experiment is existing

        :param experiment_name: name of the experiment
        :return:
        """
        action_file = self.experiment_directory / experiment_name / (experiment_name + '.py')
        if not action_file.is_file():
            log.error(f'action file for experiment {experiment_name} is missing')
            return None
        return action_file

    def __check_if_experimentmetadatafile_exists(self, experiment_name: str):
        """
        check if an experiment metadata file to a provided experiment is existing

        :param experiment_name: name of the experiment
        :return:
        """
        experiment_metadata_file = self.experiment_directory / experiment_name / 'metadata.yml'
        if not experiment_metadata_file.is_file():
            log.error(f'experiment metadata file for experiment {experiment_name} is missing')
            return None
        return experiment_metadata_file

    def __remove_experiment_from_db(self, experiment_name: str):
        """
        removes the experiment from the database
        """
        with ProjectManagementApi() as db:
            env = db.get_environment(name=self.name, project_name=self.project)
            db.remove_experiment(env, experiment_name)
        log.debug(f'experiment {self.name} removed from database')

    def __remove_experiment_from_filesystem(self, experiment_name: str):
        """
        removes the experiment from the filesystem
        """
        shutil.rmtree(self.experiment_directory / experiment_name)
        log.debug(f'experiment {self.name} removed from filesystem')

    def __is_experiment_existing(self, experiment_name: str) -> bool:
        """
        check if an experiment is existing in the environment

        :param experiment_name: name of the experiment
        :return: True if the experiment is existing and False in all other cases
        """

        # check if experiment with this name already exists
        with ProjectManagementApi() as db:
            exist_in_db = True if db.get_experiment_in_env(self.project, experiment_name, self.name) else False
        exist_in_filesystem = (self.experiment_directory / experiment_name).is_dir()
        if exist_in_db and exist_in_filesystem:
            log.error(f'experiment with name {experiment_name} already exists')
            return True
        elif exist_in_db:
            log.fatal(
                f'experiment with name {experiment_name} already exists in database but not in filesystem -> experiment will be removed from database')
            self.__remove_experiment_from_db(experiment_name)
            return True
        elif exist_in_filesystem:
            log.fatal(
                f'experiment with name {experiment_name} already exists in filesystem but not in database -> experiment will be removed from filesystem')
            self.__remove_experiment_from_filesystem(experiment_name)
            return True
        return False

    def create_experiment(self, experiment_name: str, usb: list[UsbDevice] = None, smb_drives: list[SMBShare] = None,
                          nfs_drives: list[NFSShare] = None):
        """
        create experiment skeleton files (testset file and gui experiment file)

        :param usb_name: name of usb device that is used in the experiment
        :param experiment_name: name of the experiment to be created
        """
        # check if experiment with this name already exists
        if self.__is_experiment_existing(experiment_name):
            print(f'experiment with name {experiment_name} already exists')
            exit(-1)

        # create experiment directory with template files
        experiment_directory = self.experiment_directory / experiment_name
        experiment_directory.mkdir()
        # create an empty img directory
        (experiment_directory / 'img').mkdir()
        # create a template action and testset file
        self.__create_actionfile_skeleton(experiment_name)
        self.__create_testsetfile_skeleton(experiment_name)

        # update database
        self.__update_experiments()
        # add usb devices to experiment
        if usb or smb_drives or nfs_drives:
            with ExperimentApi() as db:
                experiment = db.get_experiment_in_env(self.project, experiment_name, self.name)
                if usb:
                    for usb_device in usb:
                        db.add_usb_to_experiment(experiment, usb_device)
                if smb_drives:
                    for smb_drive in smb_drives:
                        db.add_smb_to_experiment(experiment, smb_drive)
                if nfs_drives:
                    for nfs_drive in nfs_drives:
                        db.add_nfsdrive_to_experiment(experiment, nfs_drive)

    def remove_experiment(self, experiment_name: str):
        """
        removes an experiment (which is existing in the environment)

        :param experiment_name: name of the experiment
        :return:
        """
        self.__remove_experiment_from_db(experiment_name)
        self.__remove_experiment_from_filesystem(experiment_name)

    # def __add_usb_to_experiment(self, experiment_name: str, usb_name: str):
    #     """
    #     add a usb device to a experiment
    #
    #     :param experiment_name: name of the experiment
    #     :param usb_name: name of the usb, that should be added to the experiment
    #     """
    #     Usb = self.__find_usb(usb_name)
    #     if not Usb:
    #         log.error(
    #             f'usb device {usb_name} is not existing in environment -> add a usb device to the environment first')
    #     if experiment_name not in Usb.experiments:
    #         Usb.experiments.append(experiment_name)
    #         log.info(f'usb device {Usb.name} got added successfully to experiment {experiment_name}')
    #     else:
    #         log.warning(f'experiment {experiment_name} does already use usb device {usb_name}')
    #     self.__save_configuration()
    #

    # def add_usb(self, usb: UsbDevice):
    #     """
    #     adds a new usb device to the environment
    #
    #     :param usb: dataclass for a usb device
    #     """
    #     if self.__find_usb(usb.name):
    #         log.error(f'usb with name {usb.name} can\'t be created, because it already exists')
    #         return
    #     self.configuration.usbdevices.append(usb)
    #     self.__save_configuration()
    #     log.info(f'usb {usb.name} got added successfully')
    #
    # def __add_networkdrive_to_experiment(self, experiment_name: str, networkdrive_name: str):
    #     Networkdrive = self.__find_networkdrive(networkdrive_name)
    #     if not Networkdrive:
    #         log.error(
    #             f'network drive {networkdrive_name} is not existing in environment -> add this network drive to the environment first')
    #     if experiment_name not in Networkdrive.experiments:
    #         Networkdrive.experiments.append(experiment_name)
    #         log.info(f'network drive {Networkdrive.name} got added successfully to experiment {experiment_name}')
    #     else:
    #         log.warning(f'experiment {experiment_name} does already use network drive {networkdrive_name}')
    #     self.__save_configuration()
    #
    # def __find_networkdrive(self, networkdrive_name: str) -> NetworkDrive or None:
    #     for Networkdrive in self.configuration.networkdrives:
    #         if Networkdrive.name == networkdrive_name:
    #             return Networkdrive
    #     return None
    #
    # def add_networkdrive(self, networkdrive: NetworkDrive):
    #     if self.__find_usb(networkdrive.name):
    #         log.error(f'network drive with name {networkdrive.name} can\'t be created, because it already exists')
    #         return
    #     self.configuration.networkdrives.append(networkdrive)
    #     self.__save_configuration()
    #     log.info(f'network drive {networkdrive.name} got added successfully')

    #
    # def __find_experiment(self, experiment_name: str) -> Experiment or None:
    #     """
    #     find config for the experiment in the environment configuration file
    #
    #     :param experiment_name: name of the experiment
    #     :return dataclass for experiment if experiment was found and None in all other cases
    #     """
    #     for sce in self.configuration.experiments:
    #         if sce.name == experiment_name:
    #             return sce
    #     return None
    #
    # def __remove_experiment_class(self, experiment_name: str):
    #     """
    #     removes the dataclass for an experiment
    #
    #     :param experiment_name: name of the experiment
    #     :return:
    #     """
    #     for sce in self.configuration.experiments:
    #         if sce.name == experiment_name:
    #             self.configuration.experiments.remove(sce)

    # def __create_experiment_class(self, experiment_name: str, description='') -> Experiment or None:
    #     """
    #     creates a new dataclass for experiment and adds it to the environment configuration
    #
    #     :param experiment_name: name of the experiment
    #     :param description: description for the experiment
    #     :return:
    #     """
    #     if self.__find_experiment(experiment_name):
    #         log.error(f'experiment with name {experiment_name} is already existing -> choose another name or delete the old experiment')
    #         exit(-1)
    #     experiment_dataclass = Experiment(experiment_name, description)
    #     self.configuration.experiments.append(
    #         experiment_dataclass
    #     )
    #     return experiment_dataclass
    #
    #
    # def add_experiment_to_config(self, experiment_name: str, experiment_path: Path):
    #     experiment_class = self.__create_experiment_class(experiment_name)
    #     experiment_class.directory = experiment_path.absolute().as_posix()
    #     self.__save_configuration()

    def add_examples(self):
        pass
        # """
        # ask the user if examples should be included and includes them if wished
        # """
        # include_examples = False
        # experiment_directory_in_package = EXAMPLES_DIR/'Experiments'
        # if not experiment_directory_in_package.is_dir():
        #     log.error(f'directory with examples ({experiment_directory_in_package}) not found')
        #     return
        #
        # if 'ubuntu' in self.configuration.vagrantbox:
        #     example_class_name = 'Ubuntu Trash Bin'
        #     experiment_directory = experiment_directory_in_package / 'UbuntuTrashBin'
        # elif 'linuxmint' in self.configuration.vagrantbox:
        #     example_class_name = 'Linux Mint Trash Bin'
        #     experiment_directory = experiment_directory_in_package / 'LinuxMintTrashBin'
        # elif 'win' in self.configuration.vagrantbox:
        #     example_class_name = 'Windows Trash Bin'
        #     experiment_directory = experiment_directory_in_package / 'WindowsTrashBin'
        #     rbcmd_tool = PROGRAMS_DIR/'additional_tools'/'RBCmd.exe'
        #     shutil.copy(rbcmd_tool.as_posix(), self.project_additional_tools_directory)
        # else:
        #     return
        # include_examples_inp = input(f'Should examples (for {example_class_name}) should be included? (Yes or No)?  ')
        # if include_examples_inp in ['Yes', 'Y', 'y']:
        #     include_examples = True
        #     log.info('examples will be included')
        # else:
        #     log.info('examples will be NOT included')
        #
        # if include_examples:
        #     example_config = (experiment_directory / 'config.yml').as_posix()
        #     example_config_dict = yaml_to_dict(example_config)
        #     Example_Config = cattrs.structure(example_config_dict, ExamplesConfig)
        #     existing_network_drives = [d.name for d in self.configuration.networkdrives]
        #     for network_drive in Example_Config.networkdrives:
        #         if network_drive.name not in existing_network_drives:
        #             self.configuration.networkdrives.append(network_drive)
        #         else:
        #             log.warning(f'{network_drive.name} is already existing in the environment and will not be added')
        #
        #     for experiment in experiment_directory.iterdir():
        #         if experiment.is_dir():
        #             experiment_path = self.experiment_directory/experiment.name
        #             shutil.copytree(experiment.as_posix(), experiment_path.as_posix(), ignore=shutil.ignore_patterns('*.pyc', '__pycache__'))
        #             self.add_experiment_to_config(experiment.name, experiment_path)

    # def setup_network_drives(self, jinja: jinja2.Environment, experiment_name: str, logfolder: str) -> list or None:
    #     P_mountnetworkdrivescript = self.script_directory / f'mount_networkdrives{self.__script_suffix}'
    #     used_network_drives = []
    #     for drive in self.setup.networkdrives:
    #         if experiment_name in drive.experiments:
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

    def __create_experiment_config_file(self, experiment: str, vm_environment_experiment_log_directory: Path,
                                        vm_experiment_status_file: Path) -> (Path, Path):
        data = {
            'img_folder': (self.vm_environment_experiment_directory / experiment / 'img').as_posix(),
            'tessdata_folder': self.vm_tessdata_directory.as_posix(),
            'logfile': (vm_environment_experiment_log_directory / 'gui.log').as_posix(),
            'statusfile': vm_experiment_status_file.as_posix()
        }
        filename = 'experiment_config.yml'
        filepath = self.run_directory / filename
        vm_filepath = self.vm_environment_run_directory / filename
        dict_to_yaml(filepath, data)
        return filepath, vm_filepath

    def create_vagrantfile(self, experiment: str, vm_name: str, hostonly: bool = False,
                           networkdrive_active=False) -> VagrantFile or None:
        with ProjectManagementApi() as db:
            environment: EnvironmentModel = db.get_environment(name=self.name, project_name=self.project)
            if not environment:
                log.error(f'environment {self.name} not found in database')
                exit(-1)

            vg_machine = VagrantMachine(vm_name)
            vg_file = VagrantFile()

            vgbox = environment.vagrant_box
            vg_machine.set_box(vgbox)

            if environment.osinfo.platform == 'windows':
                vg_machine.change_communicator('winrm')

            if hostonly:
                vg_machine.add_network_private(config.DEFAULT_VM_IP)

            vg_machine.enable_gui()
            vg_file.disable_virtualbox_guestautoupdate()

            vg_machine.add_synced_folder(self.project_directory, Path('/project'))

            # set up usb devices
            idle_after_os_starts = "5"
            experiment = db.get_experiment_in_env(self.project, experiment, self.name)
            if len(experiment.usbdrives) > 0:
                for usbdrive in experiment.usbdrives:
                    vg_machine.add_usb_device(
                        name=usbdrive.name,
                        vendor_id=usbdrive.vendor_id if usbdrive.vendor_id else None,
                        product_id=usbdrive.product_id if usbdrive.product_id else None,
                        manufacturer=usbdrive.manufacturer if usbdrive.manufacturer else None,
                        product=usbdrive.product if usbdrive.product else None,
                        serial_number=usbdrive.serial_number if usbdrive.serial_number else None,
                    )

                # idle to ensure that the usb devices are connected
                idle_after_os_starts = "60"

            postsetup_installations = self.run_directory / f'wrapper_postsetup_installations{self.__script_suffix}'
            mount_networkdrives = self.run_directory / f'wrapper_mount_networkdrives{self.__script_suffix}'
            run_experiment = self.run_directory / f'wrapper_run_experiment{self.__script_suffix}'
            save_installed_packages = self.run_directory / f'wrapper_save_installed_packages{self.__script_suffix}'

            if environment.osinfo.platform == 'linux':
                vg_machine.add_shell_provisioner_inline("sleep " + idle_after_os_starts)
                vg_machine.add_shell_provisioner_path(postsetup_installations.absolute())
                if networkdrive_active:
                    # add script that waits till network drives are available
                    vg_machine.add_shell_provisioner_path(mount_networkdrives.absolute())
                vg_machine.add_shell_provisioner_path(run_experiment.absolute())
                vg_machine.add_shell_provisioner_path(save_installed_packages.absolute())
            elif environment.osinfo.platform == 'windows':
                vg_machine.add_shell_provisioner_inline("sleep " + idle_after_os_starts, privileged=True,
                                                        powershell_elevated_interactive=False)
                vg_machine.add_shell_provisioner_path(postsetup_installations.absolute(), privileged=True,
                                                      powershell_elevated_interactive=False)
                if networkdrive_active:
                    vg_machine.add_shell_provisioner_path(mount_networkdrives.absolute(), privileged=True,
                                                          powershell_elevated_interactive=True)
                vg_machine.add_shell_provisioner_path(run_experiment.absolute(), privileged=True,
                                                      powershell_elevated_interactive=True)
                vg_machine.add_shell_provisioner_path(save_installed_packages.absolute(), privileged=True,
                                                      powershell_elevated_interactive=True)
            else:
                log.error(f'os platform {environment.osinfo.platform} not supported')
                return None

            vg_file.add_machine(vg_machine, order=99)

            return vg_file

    def __create_experimentrun_database(self, experiment: str, timestamp_start: datetime, logfile_data: dict):
        with ProjectManagementApi() as db:
            environment: EnvironmentModel = db.get_environment(name=self.name, project_name=self.project)
            if not environment:
                log.error(f'environment {self.name} not found in database')
                exit(-1)

            experiment = db.get_experiment_in_env(self.project, experiment, self.name)
            if not experiment:
                log.error(f'experiment {experiment} not found in database')
                exit(-1)

            run = db.create_experiment_run(experiment=experiment, timestamp_start=timestamp_start,
                                           logfile_data=logfile_data)
            log.debug(f'experiment run {run.uuid} created in database')
            return run.uuid

    def __save_results_in_database(self, run_uuid: str, result_file: Path, timestamp_end: datetime, vg_exitcode: int,
                                   experiment_log_directory: Path):
        result_data = None
        if not result_file.is_file():
            log.warning(f'result file is missing')
        else:
            result_data = yaml_to_dict(result_file)

        # determine status of vagrant
        VAGRANT_EXITCODE_STATUS_MAPPING = {
            'default': 'failed',
            0: 'success'
        }
        if vg_exitcode in VAGRANT_EXITCODE_STATUS_MAPPING.keys():
            vagrant_status = VAGRANT_EXITCODE_STATUS_MAPPING[vg_exitcode]
        else:
            vagrant_status = VAGRANT_EXITCODE_STATUS_MAPPING['default']

        # determine status of experiment -> todo: make this more pretty
        status_file = experiment_log_directory / 'status.csv'
        if status_file.is_file():
            statusdata = csv_to_dict(status_file)
        else:
            log.error(f'status file {status_file} is missing')
            return
        statusdata['vagrant'] = vagrant_status

        status_total = 'failed'
        if statusdata['vagrant'] == 'success':
            if 'RUN_gui' and 'RUN_parseandtest' in statusdata.keys():
                if statusdata['RUN_gui'] == 'success' and statusdata['RUN_parseandtest'] == 'success':
                    status_total = 'success'
        statusdata['total'] = status_total
        statusdata['action'] = statusdata['RUN_gui']
        statusdata['test'] = statusdata['RUN_parseandtest']

        with ExperimentApi() as db:
            db.update_experiment_run(
                uuid=run_uuid,
                timestamp_end=timestamp_end,
                result_data=result_data,
                status_data=statusdata,
            )
        log.debug(f'results of experiment run {run_uuid} got saved in database')

    def check_if_experiment_is_existing(self, experiment: str) -> bool:
        """
        check if an experiment is existing in the environment

        :param experiment: name of the experiment
        :return: True if experiment is existing and False in all other cases
        """
        with ProjectManagementApi() as db:
            experiment = db.get_experiment_in_env(self.project, experiment, self.name)
            if not experiment:
                log.error(f'experiment {experiment} not found in database')
                return False
            # check if in experiment directory action file and testset file are existing
            action_file = self.__check_if_actionfile_exists(experiment.name)
            if not action_file:
                log.error(f'action file for experiment {experiment.name} is missing')
                return False
            testset_file = self.__check_if_testsetfile_exists(experiment.name)
            if not testset_file:
                log.error(f'testset file for experiment {experiment.name} is missing')
                return False
            metadata_file = self.__check_if_experimentmetadatafile_exists(experiment.name)
            if not metadata_file:
                log.error(f'experiment metadata file for experiment {experiment.name} is missing')
                return False
            return True

    def __setup_networkdrives(self, experiment: str) -> VagrantMachine or None:
        with ExperimentApi() as db:
            exp = db.get_experiment_in_env(self.project, experiment, self.name)
            if not exp:
                log.error(f'experiment {experiment} not found in database')
                exit(-1)
            networkdrive_dir = self.base_directory / 'networkdrives'
            networkdrive_container = NetworkDriveContainer(exp, box=config.DEFAULT_NETWORKSHARE_BOX,
                                                           directory=networkdrive_dir)

            if not networkdrive_container.is_emtpy():
                log.info('network drive setup starts')
                vg_machine = networkdrive_container.setup()
                if not vg_machine:
                    log.error(f'network drive setup failed')
                    print(f'network drive setup failed')
                    exit(-1)
                share_information_list = networkdrive_container.get_share_information_list(self.platform)
                script_mount_networkdrive = MountNetworkDriveScript(f'mount_networkdrives{self.__script_suffix}',
                                                                    self.project_scripts_directory,
                                                                    share_information_list=share_information_list,
                                                                    render_wrapper=True)
                self.__script_manager.add_script(script_mount_networkdrive)
                log.info('network drive setup finished')
                return vg_machine
            log.debug('no network drives found in environment -> network drive setup will be skipped')
            return None

    def run(self, experiment: str, debug=False):
        """
        run an experiment

        :param experiment: name of the experiment
        :param debug: if True the vm will be not shutdown (immediately) after the experiment but instead wait for a user input to shutdown and clean up
        """
        # check if experiment is existing
        if not self.check_if_experiment_is_existing(experiment):
            print(f'experiment {experiment} is not existing in environment {self.name}')
            exit(-1)

        # check in database if experiment exists
        timestamp_start = datetime.now()
        timestamp_start_filename_format = timestamp_start.strftime(config.TIMESTAMP_FORMAT).replace(':', '.')

        experiment_log_directory = self.log_directory / f'{experiment}_{timestamp_start_filename_format}'
        vm_experiment_log_directory = self.vm_environment_logs_directory / f'{experiment}_{timestamp_start_filename_format}'
        experiment_log_directory.mkdir()

        self.__script_manager.set_log_directory_vm_view(vm_experiment_log_directory)

        resultfile_name = 'result.yml'
        experiment_result_directory = self.result_directory / f'{experiment}_{timestamp_start_filename_format}'
        experiment_result_directory.mkdir()
        experiment_resultfile = experiment_result_directory / resultfile_name
        vm_experiment_result_file = self.vm_environment_result_directory / f'{experiment}_{timestamp_start_filename_format}' / resultfile_name
        vm_experiment_status_file = self.vm_environment_logs_directory / f'{experiment}_{timestamp_start_filename_format}' / 'status.csv'

        experiment_config_file, vm_experiment_config_file = self.__create_experiment_config_file(experiment,
                                                                                                 vm_experiment_log_directory,
                                                                                                 vm_experiment_status_file)

        with ProjectManagementApi() as db:
            env = db.get_environment(name=self.name, project_name=self.project)
            if not env:
                print(f'environment {self.name} does not exist')
                exit(-1)

            if not env.postsetupinstallations:
                log.debug(f'no postsetup installations found in database')
            else:
                installations = []
                for installation in env.postsetupinstallations:
                    # expunge installation
                    db.expunge(installation)
                    installations.append(installation)

                script_postinstall = PostsetupInstallationsScript(f'postsetup_installations{self.__script_suffix}',
                                                                  self.project_scripts_directory,
                                                                  postsetup_installations=installations,
                                                                  render_wrapper=True)
                self.__script_manager.add_script(script_postinstall)

        script_run = RunExperimentScript(f'run_experiment{self.__script_suffix}',
                                         self.project_scripts_directory,
                                         experiment_path=self.vm_environment_experiment_directory / experiment,
                                         tessdata_directory=self.vm_tessdata_directory,
                                         experiment=experiment,
                                         result_file=vm_experiment_result_file,
                                         experiment_config_file=vm_experiment_config_file,
                                         project_script_directory=self.vm_project_programs_directory,
                                         additional_tool_directory=self.vm_project_additional_tools_directory,
                                         render_wrapper=True)
        self.__script_manager.add_script(script_run)

        script_saveinstalledpackages = SaveInstalledPackagesScript(f'save_installed_packages{self.__script_suffix}',
                                                                   self.project_scripts_directory,
                                                                   render_wrapper=True)
        self.__script_manager.add_script(script_saveinstalledpackages)

        if self.platform == 'windows':
            helperfunctions = Script(f'helperfunctions{self.__script_suffix}',
                                     self.project_scripts_directory)
            self.__script_manager.add_script(helperfunctions)

        # start network drives
        networkdrive_vg_machine = self.__setup_networkdrives(experiment)
        networkdrive: bool = True if networkdrive_vg_machine else False

        # render scripts to environment
        self.__script_manager.render_to_environment(self.run_directory)

        log_file_path = experiment_log_directory / 'vagrant.log'
        log.debug(f'log path for vagrant log: {log_file_path.absolute()}')

        # create a unique name for the vm
        random_number = random.randint(100000, 999999)
        vm_name = f'{self.name}{experiment}{random_number}'

        vagrantfile = self.create_vagrantfile(experiment, vm_name, networkdrive_active=networkdrive)
        if not vagrantfile:
            log.error(f'vagrantfile could not be created')
            exit(-1)
        # add network drive vagrant machine to vagrantfile
        if networkdrive_vg_machine:
            vagrantfile.add_machine(networkdrive_vg_machine, order=0)

        box = VagrantBoxVM.fromVagrantFileObject(self.run_directory, vagrantfile, log_file=log_file_path,
                                                 vm_name=vm_name)

        logfiledata = {
            'vagrant': (experiment_log_directory / 'vagrant.log').absolute().as_posix() if (
                        experiment_log_directory / 'vagrant.log').is_file() else None,
            'action': (experiment_log_directory / 'gui.log').absolute().as_posix() if (
                        experiment_log_directory / 'gui.log').is_file() else None,
            'test': (experiment_log_directory / 'parseandtest.log').absolute().as_posix() if (
                        experiment_log_directory / 'parseandtest.log').is_file() else None,
            'postsetup_installations': (
                        experiment_log_directory / 'postsetup_installations.log').absolute().as_posix() if (
                        experiment_log_directory / 'postsetup_installations.log').is_file() else None,
            'installed_packages': (experiment_log_directory / 'save_installed_packages.log').absolute().as_posix() if (
                        experiment_log_directory / 'save_installed_packages.log').is_file() else None,
            'run_experiment': (experiment_log_directory / 'run_experiment.log').absolute().as_posix() if (
                        experiment_log_directory / 'run_experiment.log').is_file() else None,
        }

        # add experiment run to database
        run_uuid: str = self.__create_experimentrun_database(experiment, timestamp_start, logfiledata)

        # start vm
        vg_exitcode = box.run(debug=debug)

        # remove temporary created scripts
        self.__script_manager.remove_scripts_from_environment()

        # delete Vagrantfile
        os.remove((self.run_directory / 'Vagrantfile').as_posix())
        os.remove(experiment_config_file.as_posix())

        # write results and log information to database
        self.__save_results_in_database(run_uuid, experiment_resultfile, datetime.now(), vg_exitcode,
                                        experiment_log_directory)
