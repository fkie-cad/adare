# external imports
import yaml
import yaml.constructor
from typing import Union, Literal, Optional
import attrs as attr
from pathlib import Path

# internal imports
from adare.testsetfile.parser import parse_testsetfile
import adare.config as config
from adare.networkdrive.attrs_classes import SMBShare, NFSShare, SMBConfiguration, NFSConfiguration

# configure logging
import logging
log = logging.getLogger(__name__)


@attr.define
class Experiment:
    """
    class to store information about an experiment
    """
    name: str
    description: str = ''
    directory: str = ''
    tags: list[str] = attr.Factory(list)

    # todo: maybe not only check if valid yaml also check if the custom syntax used by the project is correct
    def testset_file_is_valid(self) -> bool:
        """
        checks whether the provided input file for the experiment is valid

        :return: bool
        """
        testsetfile = Path(self.directory)/f'{self.name}.yml'
        if not testsetfile.is_file():
            return False
        try:
            data = parse_testsetfile(testsetfile)
            if not data:
                return False
        except (yaml.constructor.ConstructorError, ValueError, yaml.YAMLError, FileNotFoundError) as e:
            log.error(f'input file {testsetfile} couldn\'t be read because of the following exception')
            log.error(e, exc_info=True)
            return False
        log.debug(f'testset file {testsetfile} is valid')
        return True


@attr.define
class ProjectInformation:
    """
    class to store basic information about a project
    """
    name: str
    version: str = config.VERSION
    environments: list = attr.Factory(list)
    description: str = ''


@attr.define
class UsbDevice:
    """
    class to store information about a usb device
    """
    name: str
    VendorId: Union[str, None] = None
    ProductId: Union[str, None] = None
    Manufacturer: Union[str, None] = None
    Product: Union[str, None] = None
    SerialNumber: Union[str, None] = None


@attr.define
class PostsetupInstallations:
    """
    class to store information about installations that should be done after boot but before the experiment
    """
    name: str
    command: str
    description: Optional[str] = ''


@attr.define
class EnvironmentConfiguration:
    """
    class to store the configuration of an environment
    """
    name: Optional[str]
    vagrantbox: str
    os_platform: Literal['windows', 'linux']
    os: str
    os_distribution: str
    os_version: str = ''
    os_language: str = ''
    os_architecture: str = ''
    os_details: str = attr.Factory(str)
    # resolution: str = config.DEFAULT_RESOLUTION
    pause_after_gui_automation: str = config.DEFAULT_PAUSE_AFTERGUIAUTOMATION
    idle_after_os_starts: str = config.DEFAULT_START_OS_IDLE
    # settings: list = attr.Factory(list)
    experiments: list[Experiment] = attr.Factory(list)
    usbdevices: list[UsbDevice] = attr.Factory(list)
    postsetupinstallations: list[PostsetupInstallations] = attr.Factory(list)
    # gui: bool = True
    description: str = attr.Factory(str)


@attr.define
class EnvironmentSetup:
    """
    class to store the configuration needed when setting up an environment
    """
    vagrantbox: str
    os_platform: Literal['windows', 'linux']
    os: str
    os_distribution: str
    os_version: str = ''
    os_language: str = ''
    os_architecture: str = ''
    name: Optional[str] = None
    os_details: str = attr.Factory(str)
    description: str = attr.Factory(str)
    # resolution: str = config.DEFAULT_RESOLUTION
    # pause_after_gui_automation: str = config.DEFAULT_PAUSE_AFTERGUIAUTOMATION
    # idle_after_os_starts: str = config.DEFAULT_START_OS_IDLE
    # settings: list = attr.Factory(list)
    experiments: list[Experiment] = attr.Factory(list)
    usbdevices: list[UsbDevice] = attr.Factory(list)
    postsetupinstallations: list[PostsetupInstallations] = attr.Factory(list)
    # gui: bool = True


@attr.define
class ExperimentMetadata:
    """
    class to store the metadata of an experiment
    """
    smb: Optional[SMBConfiguration] = None
    nfs: Optional[NFSConfiguration] = None
    usb: list[UsbDevice] = attr.Factory(list)

    def fix_smb_users(self):
        """
        add all users of the smb shares to the smb users
        """
        if self.smb:
            for share in self.smb.shares:
                if share.user not in self.smb.users:
                    self.smb.add_user(share.user)