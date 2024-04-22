# external imports
from typing import Literal
from pathlib import Path

# internal imports
from adare.networkdrive.networkdrive import NetworkDrive
from adare.networkdrive.attrs_classes import SMBConfiguration, NFSConfiguration, SMBUser, SMBShare, NFSShare
from adare.database.models.experiment import Experiment
from adare.vagrantapi.vagrantfile import VagrantMachine

# configure logging
import logging
log = logging.getLogger(__name__)


class NetworkDriveContainer:
    """
    contains multiple network drives and creates interface to network drive vm
    """
    vm: NetworkDrive
    directory: Path
    experiment: Experiment

    def __init__(self, experiment: Experiment, box: str, directory: Path):
        self.vm = NetworkDrive(directory, box_name=box)
        self.directory = directory
        self.experiment = experiment


    def is_emtpy(self) -> bool:
        if not self.experiment.smbdrive and not self.experiment.nfsdrive:
            return True
        drive_exists = False
        if self.experiment.smbdrive:
            if len(self.experiment.smbdrive.shares) != 0:
                drive_exists = True
        if self.experiment.nfsdrive:
            if len(self.experiment.nfsdrive.shares) != 0:
                drive_exists = True
        return not drive_exists

    def __supports_smb(self) -> bool:
        return True

    def __supports_nfs(self) -> bool:
        if str(self.experiment.os_info.distribution).lower().strip() not in ['pro', 'enterprise', 'ultimate']:
            return False
        return True

    def setup(self) -> VagrantMachine or None:
        """
            setup the network drive vagrant machine
        """
        if self.is_emtpy():
            log.error('no network drives provided')
            return None

        if self.experiment.smbdrive:
            if not self.__supports_smb():
                log.fatal('smb is not supported for this os')
                exit(-1)

            if not len(self.experiment.smbdrive.shares) == 0:
                self.vm.create_smb(smb_configuration=SMBConfiguration(
                    name=self.experiment.smbdrive.name,
                    workgroup=self.experiment.smbdrive.workgroup,
                    users=[], # will be added later due to add_smb_user method
                    shares=[],
                ))

                user = None
                for smb_share_obj in self.experiment.smbdrive.shares:
                    if smb_share_obj.user:
                        user = SMBUser(
                            name=smb_share_obj.user.username,
                            password=smb_share_obj.user.password
                        )
                        self.vm.add_smb_user(user)

                    smb_share = SMBShare(
                        name=smb_share_obj.name,
                    )
                    if smb_share_obj.local_path:
                        smb_share.local_path = smb_share_obj.local_path
                    if smb_share_obj.remote_path:
                        smb_share.remote_path = smb_share_obj.remote_path
                    if user:
                        smb_share.user = user
                    self.vm.add_smb_share(smb_share)

        if self.experiment.nfsdrive:
            if not self.__supports_nfs():
                log.fatal('nfs is not supported for this os')
                exit(-1)

            if not len(self.experiment.nfsdrive.shares) == 0:
                self.vm.create_nfs(nfs_configuration=NFSConfiguration(
                    name=self.experiment.nfsdrive.name,
                    shares=[],
                ))

                for nfs_share_obj in self.experiment.nfsdrive.shares:
                    nfs_share = NFSShare(
                        name=nfs_share_obj.name,
                    )
                    if nfs_share_obj.local_path:
                        nfs_share.local_path = nfs_share_obj.local_path
                    if nfs_share_obj.remote_path:
                        nfs_share.remote_path = nfs_share_obj.remote_path
                    if nfs_share_obj.allowed_hosts:
                        nfs_share.allowed_hosts = nfs_share_obj.allowed_hosts
                    self.vm.add_nfs_share(nfs_share)

        vg_machine: VagrantMachine = self.vm.create()
        return vg_machine

    def get_share_information_list(self, guest_os: Literal['windows', 'unix']):
        """
            return a dictionary with mandatory information for mounting the network drive shares
        """
        if self.is_emtpy():
            return []

        share_information_list = []
        for share in self.vm.shares:
            share_info = {
                'local_path': share.local_path,
                'type': type(share).__name__,
            }
            if guest_os == 'windows':
                share_info['command'] = share.get_windows_mount_command(self.vm.get_vm_ip())
            elif guest_os == 'unix':
                share_info['fstab'] = share.get_fstab_entry(self.vm.get_vm_ip())
            share_information_list.append(share_info)
        return share_information_list
