# external imports
import yaml
import yaml.constructor
from typing import Union, Literal, Optional
import attrs as attr

# internal imports
import adare.helperFunctions.yaml as yml
from adare.networkdrive.attrs_classes import SMBShare, SMBUser, NFSShare
import adare.config as config

# configure logging
import logging
log = logging.getLogger(__name__)


@attr.define
class NetworkDriveUser:
    """
    class to store information about a network drive user
    """
    name: str = 'networkdriveuser'
    password: str = ''


@attr.define
class NetworkDrive:
    """
    class to store information about a network drive
    """
    name: str
    type: str
    local_path: Optional[str or None] = None
    remote_path: Optional[str or None] = None
    scenarios: Optional[list] = attr.Factory(list)
    # nfs specific
    options: Optional[list] = attr.Factory(list)  # currently not implemented
    allowed_hosts: Optional[str or None] = None
    # smb specific
    user: Optional[NetworkDriveUser] = attr.Factory(NetworkDriveUser)
    comment: Optional[str] = None
    writable: Optional[bool] = None

    def to_smb_share(self) -> SMBShare:
        share = SMBShare()
        if self.local_path:
            share.local_path = self.local_path
        if self.remote_path:
            share.remote_path = self.remote_path
        if self.user:
            user = SMBUser(self.user.name, self.user.password)
            share.user = user
        if self.comment:
            share.comment = self.comment
        if self.writable:
            share.writable = self.writable
        return share

    def to_nfs_share(self) -> NFSShare:
        share = NFSShare(self.name)
        if self.local_path:
            share.local_path = self.local_path
        if self.remote_path:
            share.remote_path = self.remote_path
        if self.allowed_hosts:
            share.allowed_hosts = self.allowed_hosts
        # if self.options:
        #     share.options = self.options
        return share


@attr.define
class Scenario:
    """
    class to store information about a scenario
    """
    name: str
    description: str = ''
    inputfile: Union[str, None] = None
    guiscenariofile: Union[str, None] = None

    # todo: maybe not only check if valid yaml also check if the custom syntax used by the project is correct
    def input_is_valid(self) -> bool:
        """
        checks whether the provided input file for the scenario is valid

        :return: bool
        """
        if not self.inputfile:
            return False
        try:
            loader, dumper = yml.create_yaml_loader_dumper_inputfiles()
            log.debug(f'input file check - parsed input file: {yml.yaml_to_dict(self.inputfile, loader=loader)}')
        except (yaml.constructor.ConstructorError, ValueError, yaml.YAMLError, FileNotFoundError) as e:
            log.error(f'input file {self.inputfile} couldn\'t be read because of the following exception')
            log.error(e, exc_info=True)
            return False
        return True

    # todo: find a way to check if gui scenario file is a valid python file
    def guiscenario_is_valid(self) -> bool:
        """
        (not implemented so far) checks whether the provided gui scenario file for the scenario is valid

        :return:
        """
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
    scenarios: list = attr.Factory(list)


@attr.define
class PostsetupInstallations:
    """
    class to store information about installations that should be done after boot but before the scenario
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
    os: Literal['windows', 'linux']
    resolution: str = config.DEFAULT_RESOLUTION
    pause_after_gui_automation: str = config.DEFAULT_PAUSE_AFTERGUIAUTOMATION
    idle_after_os_starts: str = config.DEFAULT_START_OS_IDLE
    settings: list = attr.Factory(list)
    scenarios: list[Scenario] = attr.Factory(list)
    usbdevices: list[UsbDevice] = attr.Factory(list)
    networkdrives: list[NetworkDrive] = attr.Factory(list)
    postsetupinstallations: list[PostsetupInstallations] = attr.Factory(list)
    gui: bool = True


@attr.define
class EnvironmentSetup:
    """
    class to store the configuration needed when setting up an environment
    """
    name: Optional[str]
    vagrantbox: str
    os: Literal['windows', 'linux']
    resolution: str = config.DEFAULT_RESOLUTION
    pause_after_gui_automation: str = config.DEFAULT_PAUSE_AFTERGUIAUTOMATION
    idle_after_os_starts: str = config.DEFAULT_START_OS_IDLE
    settings: list = attr.Factory(list)
    scenarios: list[Scenario] = attr.Factory(list)
    usbdevices: list[UsbDevice] = attr.Factory(list)
    networkdrives: list[NetworkDrive] = attr.Factory(list)
    postsetupinstallations: list[PostsetupInstallations] = attr.Factory(list)
    gui: bool = True


@attr.define
class ExamplesConfig:
    """
    class to store details for example scenarios
    """
    networkdrives: list[NetworkDrive] = attr.Factory(list)
    usbdevices: list[UsbDevice] = attr.Factory(list)
