# external imports
import yaml
import yaml.constructor
from typing import Union, Literal, Optional
import attrs
from pathlib import Path

# internal imports
import adare.config as config
from adare.networkdrive.attrs_classes import SMBShare, NFSShare, SMBConfiguration, NFSConfiguration

# configure logging
import logging
log = logging.getLogger(__name__)


@attrs.define
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


@attrs.define
class PostsetupInstallations:
    """
    class to store information about installations that should be done after boot but before the experiment
    """
    name: str
    command: str
    description: Optional[str] = ''


@attrs.define
class OsInfo:
    os: str
    platform: Literal['windows', 'linux']
    distribution: str
    version: str = ''
    language: str = ''
    architecture: str = ''
    details: str = ''


@attrs.define
class EnvironmentConfiguration:
    """
    class to store the configuration of an environment
    """
    name: Optional[str]
    vagrantbox: str
    os: OsInfo
    # resolution: str = config.DEFAULT_RESOLUTION
    pause_after_gui_automation: str = config.DEFAULT_PAUSE_AFTERGUIAUTOMATION
    idle_after_os_starts: str = config.DEFAULT_START_OS_IDLE
    # settings: list = attrs.Factory(list)
    usbdevices: list[UsbDevice] = attrs.Factory(list)
    postsetupinstallations: list[PostsetupInstallations] = attrs.Factory(list)
    # gui: bool = True
    description: str = attrs.Factory(str)


@attrs.define
class ExperimentMetadata:
    """
    class to store the metadata of an experiment
    """
    smb: Optional[SMBConfiguration] = None
    nfs: Optional[NFSConfiguration] = None
    usb: list[UsbDevice] = attrs.Factory(list)

    def fix_smb_users(self):
        """
        add all users of the smb shares to the smb users
        """
        if self.smb:
            for share in self.smb.shares:
                if share.user not in self.smb.users:
                    self.smb.add_user(share.user)