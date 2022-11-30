# external imports
from typing import Optional, Literal
from pathlib import Path
import jinja2

# internal imports
from adare.backend.attrs_classes import NetworkDrive
from adare.networkdrive.Networkdrive import NetworkdriveVM
from adare.networkdrive.attrs_classes import Share, SMBConfiguration, NFSConfiguration, SMBUser
from adare.backend.script_creation import MountNetworkDriveScript
from adare.backend.exceptions import SafeDeletionError

# configure logging
import logging
log = logging.getLogger(__name__)


class NetworkDriveContainer:
    """
    contains multiple network drives and creates interface to network drive vm
    """
    Drives: list[NetworkDrive]
    VM: NetworkdriveVM
    directory: str

    def __init__(self, drives: list, scenario: str, networkdrive_directory: str, smb_conf: SMBConfiguration = None, nfs_conf: NFSConfiguration = None):
        self.Drives = []
        self.directory = networkdrive_directory
        for drive in drives:
            if scenario in drive.scenarios:
                self.Drives.append(drive)
        if not self.Drives:
            return
        self.VM = NetworkdriveVM(networkdrive_directory)
        for drive in self.Drives:
            if drive.type == 'smb' and not self.VM.smb:
                self.VM.create_smb(smb_conf)
            elif drive.type == 'nfs' and not self.VM.nfs:
                self.VM.create_nfs(nfs_conf)
            self.add_NetworkDrive_to_VM(drive)

    def add_NetworkDrive_to_VM(self, drive: NetworkDrive) -> Optional[Share]:
        """
        add a network drive provided by an NetworkDrive class instance to the network drive vm

        :param drive: NetworkDrive class instance
        :return:
        """
        if drive.type == 'smb':
            smb_user = SMBUser(drive.user.name, drive.user.password)
            if not self.VM.is_smb_user(smb_user):
                self.VM.add_smb_user(smb_user)
            share = drive.to_smb_share()
            self.VM.add_smb_share(share)
        elif drive.type == 'nfs':
            share = drive.to_nfs_share()
            self.VM.add_nfs_share(share)
        else:
            return None
        log.info(f'share {share.name} got added to the network drive vm successfully')
        return share

    def start(self):
        """
        start the network drive VM

        :return:
        """
        if not self.Drives:
            return
        ret = self.VM.start()
        if ret['returncode'] != 0:
            log.error("network drive vm couldn't be started")
            self.VM.stop()
            self.VM.cleanup()

    def stop(self):
        """
        stop the network drive VM (if running)

        :return:
        """
        if self.VM.is_alive():
            self.VM.stop()
            if Path(self.directory).parent.parent.name == "environments":
                self.VM.cleanup()
            else:
                raise SafeDeletionError(self.directory)
        else:
            log.warning('network drive vm can not be stopped because it is not running')

    # todo: maybe rewrite it so that less parameters like jinja/template are needed
    def write_mount_script(self, destination: str, guest_os: Literal['windows', 'linux'], template: str, logfolder: str,
                           jinja_environment: jinja2.Environment = None):
        """
        write a script to mount the network shares represented within this class

        :param destination: destination folder of the script
        :param guest_os: os used by the guest
        :param template: template used to create the script
        :param logfolder: logfolder used within the script
        :param jinja_environment: jinja environment where the template can be found
        :return:
        """
        if not self.Drives:
            return
        share_information_list = []
        for share in self.VM.shares:
            share_info = {
                'local_path': share.local_path
            }
            if guest_os == 'windows':
                share_info['command'] = share.get_windows_mount_command(self.VM.vmconfiguration.ip)
            elif guest_os == 'linux':
                share_info['fstab'] = share.get_fstab_entry(self.VM.vmconfiguration.ip)
            share_information_list.append(share_info)
        script = MountNetworkDriveScript(destination, template, share_information_list, logfolder, jinja_environment=jinja_environment)
        script.write()
