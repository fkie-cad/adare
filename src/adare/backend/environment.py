# external imports
import shutil
import cattrs
from cattrs.errors import ClassValidationError
from datetime import datetime
import pkg_resources
import glob
import attr
from pathlib import Path
import jinja2
import os

# internal imports
import adare.config as config
from adare.backend.attrs_classes import Experiment, UsbDevice, ExamplesConfig, NetworkDrive, \
    EnvironmentConfiguration, EnvironmentSetup
from adare.backend.networkdrive import NetworkDriveContainer
from adare.helperFunctions.yaml import yaml_to_dict, dict_to_yaml
from adare.helperFunctions.csv import csv_to_dict
from adare.helperFunctions.hash import hash_file_sha256, combine_hashes
from adare.helperFunctions.jinja.jinjafeatures import init_jinja_environment
from adare.backend.script_creation.scripts import PostsetupInstallationsScript, RunExperimentScript, SaveInstalledPackagesScript, MountNetworkDriveScript
from adare.backend.script_creation.Scriptmanager import ScriptManager
from adare.backend.script_creation.Script import Script
from adare.vagrantapi.vagrantbox import VagrantBoxVM
from adare.vagrantapi.vagrantfile import VagrantFile
from adare.database.database import ExperimentApi
from adare.inputparser.YAMLInputParser import YAMLInputParser

# configure logging
import logging
log = logging.getLogger(__name__)


class Environment:
    """
    This class in used in order to maintain and change an environment.
    It contains functions to create, run, list and remove a experiment.
    """
    name: str

    project_directory: Path

    base_directory: Path
    programs_directory: Path
    guiexperiment_directory: Path
    log_directory: Path

    configuration_file: str
    configuration: EnvironmentConfiguration or None

    setupfile: str
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

    def __init__(self, name: str, project_directory: Path, create=False, setupfile: str = None):
        self.name = name
        self.setup = None

        self.project_directory = project_directory
        self.project_setup_directory = project_directory / 'setup'

        self.base_directory = (self.project_directory / 'environments' / name)
        if create:
            self.setupfile = self.__find_setup_file(setupfile)
            if self.base_directory.exists():
                log.error(f'environment {name} already exists')
                exit(-1)
            self.setup = self.__load_setup()
            self.__script_suffix = config.SCRIPTS_SUFFIX[self.setup.os_platform]
            self.project_scripts_directory = project_directory / 'programs' / 'templates' / self.setup.os_platform

        # load configuration file and create environment if needed
        self.configuration_file = (self.base_directory/'.envconf.yml').as_posix()
        self.configuration = None

        if create:
            self.__create()
        else:
            self.__load()

        if not self.configuration:
            log.error(f'environment {name} initialization failed')
            exit(-1)

        # set up paths used in project an environment
        self.project_scripts_directory = project_directory/'programs'/'templates'/self.configuration.os_platform
        self.project_additional_tools_directory = project_directory/'additional_tools'
        self.project_guiautomation_program = project_directory/'programs'/'GUIAutomation'
        self.project_parseandtest_program = project_directory/'programs' /'ParseAndTest'

        self.log_directory = self.base_directory / 'logs'
        self.result_directory = self.base_directory / 'result'
        self.run_directory = self.base_directory / 'run'
        self.experiment_directory = self.base_directory / 'experiment'

        # set up paths from the view of the guest/vm
        vm_root_path = Path(r'/')
        if self.configuration.os_platform == 'windows':
            vm_root_path = Path(r'C:/')

        self.vm_project_directory = vm_root_path/'project'
        self.vm_project_programs_directory = self.vm_project_directory/'programs'
        self.vm_project_additional_tools_directory = self.vm_project_directory / 'additional_tools'
        self.vm_environment_directory = self.vm_project_directory/'environments'/self.name
        self.vm_environment_logs_directory = self.vm_project_directory / 'environments' / self.name / 'logs'
        self.vm_environment_result_directory = self.vm_project_directory / 'environments' / self.name / 'result'
        self.vm_environment_run_directory = self.vm_project_directory / 'environments' / self.name / 'run'
        self.vm_environment_experiment_directory = self.vm_project_directory / 'environments' / self.name / 'experiment'

        self.vm_tessdata_directory = self.vm_project_directory/'tessdata'

        self.__script_manager = ScriptManager(
            script_directory_vm_view=self.vm_environment_run_directory,
            wrapper_template=self.project_scripts_directory/f'run_script_wrapper{self.__script_suffix}'
        )

    def __find_setup_file(self, setupfile: str or None):
        """
        try to find a setup file in the setup folder of the project

        :param setupfile: path of the provided setupfile or None if no setupfile was provided
        :return: path of the setupfile
        """
        if not setupfile:
            setup_files_storage_in_project = self.project_setup_directory
            for file in setup_files_storage_in_project.iterdir():
                if file.stem == self.name:
                    setupfile = file.as_posix()
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
        try:
            setup_dict = yaml_to_dict(self.setupfile)
        except FileNotFoundError:
            log.error(f'setup file {self.setupfile} for the environment not found')
            exit(-1)
        try:
            setup = cattrs.structure(setup_dict, EnvironmentSetup)
        except ClassValidationError as e:
            log.error('environment setup file could not be read because of the following exception')
            log.error(e, exc_info=True)
            exit(-1)
        return setup

    def __load_configuration(self) -> EnvironmentConfiguration:
        """
        load the environment configuration from the environment configuration file (.envconf.yml) located in the environment directory

        :return: dataclass containing the configuration of the environment
        """
        data = yaml_to_dict(self.configuration_file)
        if not data:
            log.error(f'environment configuration file {self.configuration_file} not found')
            exit(-1)
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
        template_folder = self.project_scripts_directory.as_posix()
        self.__jinja_project = init_jinja_environment(template_folder)

    def __create(self):
        """
        function to create an environment (should be only used in the __init__ function of this class)
        """
        self.__create_jinja_project()
        if not self.__jinja_project:
            log.error(f'jinja env could not be created')
            exit(-1)

        self.base_directory.mkdir()

        for folder in ['logs', 'result', 'networkdrives', 'experiment', 'run']:
            (self.base_directory / folder).mkdir()

        # todo: optionally add option to provide experiments via setup file
        self.configuration = EnvironmentConfiguration(name=self.name,
                                                      vagrantbox=self.setup.vagrantbox,
                                                      os_platform=self.setup.os_platform,
                                                      os=self.setup.os,
                                                      os_distribution=self.setup.os_distribution,
                                                      os_version=self.setup.os_version,
                                                      os_language=self.setup.os_language,
                                                      os_architecture=self.setup.os_architecture,
                                                      os_details=self.setup.os_architecture,
                                                      resolution=self.setup.resolution,
                                                      pause_after_gui_automation=self.setup.pause_after_gui_automation,
                                                      idle_after_os_starts=self.setup.idle_after_os_starts,
                                                      settings=self.setup.settings,
                                                      experiments=[],
                                                      usbdevices=self.setup.usbdevices,
                                                      networkdrives=self.setup.networkdrives,
                                                      postsetupinstallations=self.setup.postsetupinstallations)
        self.__save_configuration()

    def __load(self):
        """
        function to load an already existing environment
        """
        self.__load_configuration()
        self.__script_suffix = config.SCRIPTS_SUFFIX[self.configuration.os_platform]

    def remove(self):
        """
        function to remove this environment (removes all associated files/directory)
        """
        shutil.rmtree(self.base_directory.as_posix())

    def __check_if_gui_experiment_exists(self, experiment_name: str) -> str or None:
        """
        check if a gui experiment file to a provided experiment is existing

        :param experiment_name: name of the experiment
        :return: path of the gui experiment file; None if no matching gui experiment file found
        """
        guiexperiment_path = None
        for obj in glob.glob((self.guiexperiment_directory / '**' / '*.yml').as_posix()):
            if Path(obj).stem == experiment_name:
                guiexperiment_path = Path(obj).absolute().as_posix()
        return guiexperiment_path

    def __create_gui_experiment_skeleton(self, experiment_name: str):
        """
        creates a gui experiment skeleton file for a given experiment name
        """
        template_directory = Path(pkg_resources.resource_filename(config.PACKAGE, '/data/templates'))
        if not Path(template_directory).is_dir():
            log.error(f'template directory {template_directory} is missing')
            exit(-1)
        jinja = init_jinja_environment(template_directory.as_posix())
        template = jinja.get_template('ExperimentTemplate')
        filepath = self.experiment_directory/experiment_name/f'{experiment_name}.py'
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
        template_directory = Path(pkg_resources.resource_filename(config.PACKAGE, '/data/templates'))
        if not Path(template_directory).is_dir():
            log.error(f'template directory {template_directory} is missing')
            exit(-1)
        jinja = init_jinja_environment(template_directory.as_posix())
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

    def create_experiment(self, experiment_name: str, usb_name: str or None = None, networkdrive_name: str or None = None):
        """
        create experiment skeleton files (testset file and gui experiment file)

        :param usb_name: name of usb device that is used in the experiment
        :param experiment_name: name of the experiment to be created
        """
        if self.__find_experiment(experiment_name):
            log.error(f'experiment with name {experiment_name} is already existing -> choose another name or delete the old experiment')
            return
        filepath = self.experiment_directory / experiment_name
        filepath.mkdir()
        self.__create_gui_experiment_skeleton(experiment_name)
        self.__create_testsetfile_skeleton(experiment_name)
        img_dir = filepath/'img'
        img_dir.mkdir()
        if usb_name:
            self.__add_usb_to_experiment(experiment_name, usb_name)
        if networkdrive_name:
            self.__add_networkdrive_to_experiment(experiment_name, networkdrive_name)
        print('\n\n')
        print(f'new experiment skeleton created (path:{filepath})')
        log.debug(f'skeleton for experiment {experiment_name} created')

    def remove_experiment(self, experiment_name: str):
        """
        removes a experiment (includes both testset file and gui experiment file as well as the experiment class)

        :param experiment_name: name of the experiment to be removed
        """
        experiment_dataclass = self.__find_experiment(experiment_name)
        if not experiment_dataclass:
            log.error(f'experiment with name {experiment_name} does NOT exist in environment')
            return
        shutil.rmtree(experiment_dataclass.directory)
        self.__remove_experiment_class(experiment_name)
        log.info(f'experiment {experiment_name} got deleted')

    def __add_usb_to_experiment(self, experiment_name: str, usb_name: str):
        """
        add a usb device to a experiment

        :param experiment_name: name of the experiment
        :param usb_name: name of the usb, that should be added to the experiment
        """
        Usb = self.__find_usb(usb_name)
        if not Usb:
            log.error(
                f'usb device {usb_name} is not existing in environment -> add a usb device to the environment first')
        if experiment_name not in Usb.experiments:
            Usb.experiments.append(experiment_name)
            log.info(f'usb device {Usb.name} got added successfully to experiment {experiment_name}')
        else:
            log.warning(f'experiment {experiment_name} does already use usb device {usb_name}')
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

    def __add_networkdrive_to_experiment(self, experiment_name: str, networkdrive_name: str):
        Networkdrive = self.__find_networkdrive(networkdrive_name)
        if not Networkdrive:
            log.error(
                f'network drive {networkdrive_name} is not existing in environment -> add this network drive to the environment first')
        if experiment_name not in Networkdrive.experiments:
            Networkdrive.experiments.append(experiment_name)
            log.info(f'network drive {Networkdrive.name} got added successfully to experiment {experiment_name}')
        else:
            log.warning(f'experiment {experiment_name} does already use network drive {networkdrive_name}')
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


    def __find_experiment(self, experiment_name: str) -> Experiment or None:
        """
        find config for the experiment in the environment configuration file

        :param experiment_name: name of the experiment
        :return dataclass for experiment if experiment was found and None in all other cases
        """
        for sce in self.configuration.experiments:
            if sce.name == experiment_name:
                return sce
        return None

    def __remove_experiment_class(self, experiment_name: str):
        """
        removes the dataclass for an experiment

        :param experiment_name: name of the experiment
        :return:
        """
        for sce in self.configuration.experiments:
            if sce.name == experiment_name:
                self.configuration.experiments.remove(sce)

    def __create_experiment_class(self, experiment_name: str, description='') -> Experiment or None:
        """
        creates a new dataclass for experiment and adds it to the environment configuration

        :param experiment_name: name of the experiment
        :param description: description for the experiment
        :return:
        """
        if self.__find_experiment(experiment_name):
            log.error(f'experiment with name {experiment_name} is already existing -> choose another name or delete the old experiment')
            exit(-1)
        experiment_dataclass = Experiment(experiment_name, description)
        self.configuration.experiments.append(
            experiment_dataclass
        )
        return experiment_dataclass


    def add_experiment_to_config(self, experiment_name: str, experiment_path: Path):
        experiment_class = self.__create_experiment_class(experiment_name)
        experiment_class.directory = experiment_path.absolute().as_posix()
        self.__save_configuration()

    def add_examples(self):
        """
        ask the user if examples should be included and includes them if wished
        """
        include_examples = False
        experiment_directory_in_package = Path(pkg_resources.resource_filename(config.PACKAGE, '/data/examples/experiments'))
        if 'ubuntu' in self.configuration.vagrantbox:
            example_class_name = 'Ubuntu Trash Bin'
            experiment_directory = experiment_directory_in_package / 'UbuntuTrashBin'
        elif 'linuxmint' in self.configuration.vagrantbox:
            example_class_name = 'Linux Mint Trash Bin'
            experiment_directory = experiment_directory_in_package / 'LinuxMintTrashBin'
        elif 'win' in self.configuration.vagrantbox:
            example_class_name = 'Windows Trash Bin'
            experiment_directory = experiment_directory_in_package / 'WindowsTrashBin'
            rbcmd_tool = Path(pkg_resources.resource_filename(config.PACKAGE, '/data/programs/additional_tools'))/'RBCmd.exe'
            shutil.copy(rbcmd_tool.as_posix(), self.project_additional_tools_directory)
        else:
            return
        include_examples_inp = input(f'Should examples (for {example_class_name}) should be included? (Yes or No)?  ')
        if include_examples_inp in ['Yes', 'Y', 'y']:
            include_examples = True
            log.info('examples will be included')
        else:
            log.info('examples will be NOT included')

        if include_examples:
            example_config = (experiment_directory / 'config.yml').as_posix()
            example_config_dict = yaml_to_dict(example_config)
            Example_Config = cattrs.structure(example_config_dict, ExamplesConfig)
            existing_network_drives = [d.name for d in self.configuration.networkdrives]
            for network_drive in Example_Config.networkdrives:
                if network_drive.name not in existing_network_drives:
                    self.configuration.networkdrives.append(network_drive)
                else:
                    log.warning(f'{network_drive.name} is already existing in the environment and will not be added')

            for experiment in experiment_directory.iterdir():
                if experiment.is_dir():
                    experiment_path = self.experiment_directory/experiment.name
                    shutil.copytree(experiment.as_posix(), experiment_path.as_posix(), ignore=shutil.ignore_patterns('*.pyc', '__pycache__'))
                    self.add_experiment_to_config(experiment.name, experiment_path)





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

    def __create_experiment_config_file(self, experiment: str, vm_environment_experiment_log_directory: Path, vm_experiment_status_file: Path) -> (Path, Path):
        data = {
            'img_folder': (self.vm_environment_experiment_directory/experiment/'img').as_posix(),
            'tessdata_folder': self.vm_tessdata_directory.as_posix(),
            'logfile': (vm_environment_experiment_log_directory/'gui.log').as_posix(),
            'statusfile': vm_experiment_status_file.as_posix()
        }
        filename = 'experiment_config.yml'
        filepath = self.run_directory/filename
        vm_filepath = self.vm_environment_run_directory/filename
        dict_to_yaml(filepath, data)
        return filepath, vm_filepath

    def create_Vagrantfile(self, experiment_name: str, hostonly: bool = False, networkdrive_active=False):
        conf = self.configuration
        Vagrant_creator = VagrantFile()

        vgbox = conf.vagrantbox
        Vagrant_creator.set_box(vgbox)
        Vagrant_creator.set_vbox_name('testvgbox')

        if conf.os_platform == 'windows':
            Vagrant_creator.change_communicator('winrm')

        if hostonly:
            Vagrant_creator.add_network_private(config.DEFAULT_VM_IP)

        Vagrant_creator.enable_gui()
        Vagrant_creator.disable_virtualbox_guestautoupdate()

        usbdevices = []
        for usbdevice in conf.usbdevices:
            if experiment_name in usbdevice.experiments:
                usbdevices.append(usbdevice)

        Vagrant_creator.add_synced_folder(self.project_directory, Path('/project'))

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

        postsetup_installations = self.run_directory / f'wrapper_postsetup_installations{self.__script_suffix}'
        mount_networkdrives = self.run_directory / f'wrapper_mount_networkdrives{self.__script_suffix}'
        run_experiment = self.run_directory / f'wrapper_run_experiment{self.__script_suffix}'
        save_installed_packages = self.run_directory / f'wrapper_save_installed_packages{self.__script_suffix}'

        if conf.os_platform == 'linux':
            Vagrant_creator.add_shell_provisioner_inline("sleep " + idle_after_os_starts)
            Vagrant_creator.add_shell_provisioner_path(postsetup_installations.absolute())
            if networkdrive_active:
                Vagrant_creator.add_shell_provisioner_path(mount_networkdrives.absolute())
            Vagrant_creator.add_shell_provisioner_path(run_experiment.absolute())
            Vagrant_creator.add_shell_provisioner_path(save_installed_packages.absolute())
        elif conf.os_platform == 'windows':
            Vagrant_creator.add_shell_provisioner_inline("sleep " + idle_after_os_starts, privileged=True,
                                                         powershell_elevated_interactive=False)
            Vagrant_creator.add_shell_provisioner_path(postsetup_installations.absolute(), privileged=True,
                                                       powershell_elevated_interactive=False)
            if networkdrive_active:
                Vagrant_creator.add_shell_provisioner_path(mount_networkdrives.absolute(), privileged=True,
                                                           powershell_elevated_interactive=True)
            Vagrant_creator.add_shell_provisioner_path(run_experiment.absolute(), privileged=True,
                                                       powershell_elevated_interactive=True)
            Vagrant_creator.add_shell_provisioner_path(save_installed_packages.absolute(), privileged=True,
                                                       powershell_elevated_interactive=True)
        else:
            log.error(f'os platform {conf.os_platform} not supported')
            return
        return Vagrant_creator

    def __save_results_in_database(self, experiment: str, result_file: Path, timestamps: dict, vg_exitcode: int, experiment_log_directory: Path):
        action_file = self.experiment_directory / experiment / (experiment + ".py")
        if not action_file.is_file():
            log.error(f'action file is missing')
            return

        testset_file = self.experiment_directory / experiment / (experiment + ".yml")
        if not testset_file.is_file():
            log.error(f'testset file is missing')
            return

        parser = YAMLInputParser(testset_file)
        testsetdata = parser.parse()

        result_data = None
        if not result_file.is_file():
            log.warning(f'result file is missing')
        else:
            result_data = yaml_to_dict(result_file)

        logfiledata = {
            'logfile_vagrant': (experiment_log_directory/'vagrant.log').absolute().as_posix() if (experiment_log_directory/'vagrant.log').is_file() else None,
            'logfile_gui_automation': (experiment_log_directory/'gui.log').absolute().as_posix() if (experiment_log_directory/'gui.log').is_file() else None,
            'logfile_parse_and_test': (experiment_log_directory/'parseandtest.log').absolute().as_posix() if (experiment_log_directory/'parseandtest.log').is_file() else None,
            'logfile_postsetup_installations': (experiment_log_directory/'postsetup_installations.log').absolute().as_posix() if (experiment_log_directory/'postsetup_installations.log').is_file() else None,
            'logfile_installed_packages': (experiment_log_directory/'save_installed_packages.log').absolute().as_posix() if (experiment_log_directory/'save_installed_packages.log').is_file() else None,
            'logfile_run_experiment': (experiment_log_directory/'run_experiment.log').absolute().as_posix() if (experiment_log_directory/'run_experiment.log').is_file() else None,
        }

        VAGRANT_EXITCODE_STATUS_MAPPING = {
            'default': 'failed',
            0: 'success'
        }
        if vg_exitcode in VAGRANT_EXITCODE_STATUS_MAPPING.keys():
            vagrant_status = VAGRANT_EXITCODE_STATUS_MAPPING[vg_exitcode]
        else:
            vagrant_status = VAGRANT_EXITCODE_STATUS_MAPPING['default']

        status_file = experiment_log_directory/'status.csv'
        statusdata = {}
        if status_file.is_file():
            statusdata = csv_to_dict(status_file)
        else:
            log.error(f'status file {status_file} is missing')
        statusdata['VAGRANT'] = vagrant_status

        status_total = 'failed'
        if statusdata['VAGRANT'] == 'success':
            if 'RUN_gui' and 'RUN_parseandtest' in statusdata.keys():
                if statusdata['RUN_gui'] == 'success' and statusdata['RUN_parseandtest'] == 'success':
                    status_total = 'success'
        statusdata['TOTAL'] = status_total

        os_info = {
            'os': self.configuration.os,
            'distribution': self.configuration.os_distribution,
            'version': self.configuration.os_version,
            'language': self.configuration.os_language,
            'architecture': self.configuration.os_architecture
        }

        # calculate sha256 hash of the action file and the testset file
        action_file_hash = hash_file_sha256(action_file)
        testset_file_hash = hash_file_sha256(testset_file)
        sha256_validation_hash = combine_hashes([action_file_hash, testset_file_hash])

        with ExperimentApi() as db:
            db.add_experiment_run(
                testset_data=testsetdata,
                action_file=action_file,
                testset_file=testset_file,
                result_data=result_data,
                logfile_data=logfiledata,
                status_data=statusdata,
                timestamps=timestamps,
                os_info=os_info,
                sha256_validation_hash=sha256_validation_hash,
            )
        log.debug(f'results of experiment {experiment} got saved in database')

    def run(self, experiment: str, debug=False):
        """
        run an experiment

        :param experiment: name of the experiment
        :param debug: if True the vm will be not shutdown (immediately) after the experiment but instead wait for a user input to shutdown and clean up
        """
        experiment_class: Experiment = self.__find_experiment(experiment)

        if not experiment_class:
            log.error(f'experiment {experiment} does not exist in environment configuration')
            return
        if not experiment_class.directory:
            log.error(f'experiment metadata for experiment {experiment} (in environment config file) is missing the directory')
            return
        if not experiment_class.testset_file_is_valid():
            log.error(
                f'experiment {experiment} can NOT be started because the testset file has an error in format (as shown in the exception above)')
            return

        # not implemented so far
        if not experiment_class.action_file_is_valid():
            log.error(
                f'experiment {experiment} can NOT be started because the gui experiment file has an error in format (as shown in the exception above)')
            return

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

        experiment_config_file, vm_experiment_config_file = self.__create_experiment_config_file(experiment, vm_experiment_log_directory, vm_experiment_status_file)

        script_postinstall = PostsetupInstallationsScript(f'postsetup_installations{self.__script_suffix}',
                                                          self.project_scripts_directory,
                                                          configuration=self.configuration,
                                                          render_wrapper=True)
        self.__script_manager.add_script(script_postinstall)

        script_run = RunExperimentScript(f'run_experiment{self.__script_suffix}',
                                         self.project_scripts_directory,
                                         experiment_path=self.vm_environment_experiment_directory/experiment,
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

        if self.configuration.os_platform == 'windows':
            helperfunctions = Script(f'helperfunctions{self.__script_suffix}',
                                     self.project_scripts_directory)
            self.__script_manager.add_script(helperfunctions)

        # start network drives
        publicnetwork = False
        networkdrive_container = None
        networkdrive_active = False
        for drive in self.configuration.networkdrives:
            if experiment in drive.experiments:
                networkdrive_active = True
        if networkdrive_active:
            networkdrive_dir = self.base_directory / 'networkdrives'

            networkdrive_container = NetworkDriveContainer(config.DEFAULT_NETWORKSHARE_BOX, self.configuration.networkdrives, experiment, networkdrive_dir)

            share_information_list = networkdrive_container.get_share_information_list(self.configuration.os_platform)
            script_mount_networkdrive = MountNetworkDriveScript(f'mount_networkdrives{self.__script_suffix}', self.project_scripts_directory, share_information_list=share_information_list, render_wrapper=True)
            self.__script_manager.add_script(script_mount_networkdrive)

            if not networkdrive_container:
                log.error(f'experiment {experiment} will not start because the network drive vm couldn\'t get created')
            networkdrive_container.start()

            if networkdrive_container:
                publicnetwork = True

        self.__script_manager.render_to_environment(self.run_directory)

        log_file_path = experiment_log_directory/'vagrant.log'
        log.debug(f'log path for vagrant log: {log_file_path.absolute()}')

        vagrantfile = self.create_Vagrantfile(experiment, hostonly=publicnetwork, networkdrive_active=networkdrive_active)
        box = VagrantBoxVM.fromVagrantFileObject(self.run_directory, vagrantfile, log_file=log_file_path)
        vg_exitcode = box.run(debug=debug)

        # remove temporary created scripts
        self.__script_manager.remove_scripts_from_environment()

        # delete Vagrantfile
        os.remove((self.run_directory / 'Vagrantfile').as_posix())

        # stop network drives
        if networkdrive_active:
            if networkdrive_container:
                if networkdrive_container.VM.is_alive():
                    networkdrive_container.stop()
                else:
                    log.error("network drive was shutdown early")

        # get timestamp for end of experiment
        timestamp_end = datetime.now()

        # save timestamps in dict
        timestamps = {
            'timestamp_start': timestamp_start,
            'timestamp_end': timestamp_end
        }

        # write results and log information to database
        self.__save_results_in_database(experiment, experiment_resultfile, timestamps, vg_exitcode, experiment_log_directory)

