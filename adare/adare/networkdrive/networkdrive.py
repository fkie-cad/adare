# external imports
# configure logging
import logging
import shutil
from pathlib import Path

import jinja2

# internal imports
from adare.config.configdirectory import NETWORKDRIVE_TEMPLATES_DIR
from adare.helperFunctions.jinja.jinjafeatures import init_jinja_environment
from adare.networkdrive.attrs_classes import (
    NetworkdriveVMConfiguration,
    NFSConfiguration,
    NFSShare,
    SMBConfiguration,
    SMBShare,
    SMBUser,
)
from adare.networkdrive.exceptions import NetworkdriveCreationError
from adare.vagrantapi.vagrantbox import VagrantBoxVM
from adare.vagrantapi.vagrantfile import VagrantMachine
from adare.vagrantapi.vagrantutils import is_box

log = logging.getLogger(__name__)


class NetworkDrive:
    """
        class that creates a virtual machine, which consists of network drives such as smb and nfs
        (therefore vagrant, virtualbox as well as and ubuntu server vagrant box with installed nfs and smb server is required)
    """
    box_name: str
    box_vm: VagrantBoxVM
    vg_directory: Path

    vm_config: NetworkdriveVMConfiguration

    smb: SMBConfiguration or None = None
    nfs: NFSConfiguration or None = None
    shares: list

    __jinja: jinja2.Environment

    def __init__(self, vg_directory: Path, box_name: str):
        self.shares = []
        self.box_name = box_name
        if not is_box(self.box_name):
            log.error(f'class networkdrive vm could NOT be created due to the fact that the given vagrant box ({self.box_name}) does NOT exist')
            raise NetworkdriveCreationError

        self.vg_directory = vg_directory
        if not vg_directory.is_dir():
            try:
                vg_directory.mkdir()
                log.debug(f'directory for network drive ({vg_directory}) was created successfully')
            except OSError or FileExistsError as e:
                log.error(e)
                raise NetworkdriveCreationError from e

        self.vm_config = NetworkdriveVMConfiguration()

    def create_smb(self, smb_configuration: SMBConfiguration or None = None) -> int:
        """
            creates a smb network drive (shares can be added with add_smb_share)
        """
        if self.smb:
            log.warning('smb drive is already existing in the network drive vm')
            return -1
        if smb_configuration:
            self.smb = smb_configuration
        else:
            self.smb = SMBConfiguration()
        return 0

    def create_nfs(self, nfs_configuration: NFSConfiguration or None = None) -> int:
        """
            creates a nfs network drive (shares can be added with add_nfs_share)
        """
        if self.nfs:
            log.info('nfs drive is already existing in the network drive vm')
            return -1
        if nfs_configuration:
            self.nfs = nfs_configuration
        else:
            self.nfs = NFSConfiguration()
        return 0

    def add_smb_share(self, smb_share: SMBShare or None = None):
        """
            adds a smb share to a smb server (and creates a smb server if not already existing)
        """
        if not self.smb:
            self.smb = SMBConfiguration()
            log.warning('no smb configuration for the network drive vm is set so far -> smb configuration with default parameters will be used')
        if not smb_share:
            smb_share = SMBShare()
            log.debug('no details for smb share provided -> default smb share will be used')
        self.smb.add_share(smb_share)
        self.shares.append(smb_share)
        log.info(f'smb share {smb_share.name} got added successfully to the network drive vm')

    def add_smb_user(self, smb_user: SMBUser | None = None):
        """
            adds a user to your smb config
        """
        if not self.smb:
            log.error('no smb config for the network drive vm is set so far, therefore no smb user could be added')
            return
        if not smb_user:
            smb_user = SMBUser()
        self.smb.add_user(smb_user)
        log.info(f'smb user {smb_user.name} got added successfully to the network drive vm')

    def is_smb_user(self, smb_user: SMBUser) -> bool:
        """
            checks whether smb user does already exist
        """
        return self.smb.is_user(smb_user)

    def add_nfs_share(self, nfs_share: NFSShare or None = None):
        """
            adds a nfs share to a smb server (and creates a smb server if not already existing)
        """
        if not self.nfs:
            self.nfs = NFSConfiguration()
            log.warning('no nfs configuration for the network drive vm is set so far -> nfs configuration with default parameters will be used')
        if not nfs_share:
            nfs_share = NFSShare()
            log.debug('no details for nfs share provided -> default nfs share will be used')
        self.nfs.add_share(nfs_share)
        self.shares.append(nfs_share)
        log.info(f'nfs share {nfs_share.name} got added successfully to the network drive vm')

    def __write_smb_files(self):
        """
            creates a smb.conf file as well as a setup_smb.sh which is used by the VM to setup the smb server and the corresponding shares
        """
        setup_smb_template = self.__jinja.get_template('setup_smb.sh')
        smb_conf_template = self.__jinja.get_template('smb.conf')
        try:
            f_path = (self.vg_directory/"setup_smb.sh")
            f = open(f_path.as_posix(), mode="w")
            f.write(setup_smb_template.render({'configuration': self.smb}))
        except FileNotFoundError or OSError as e:
            log.error(e)
            return -1
        log.info(f'setup_smb.sh was created successfully in network drive directory ({self.vg_directory})')

        try:
            f_path = (self.vg_directory / "config" / "smb.conf")
            f = open(f_path.as_posix(), mode="w")
            f.write(smb_conf_template.render({'configuration': self.smb}))
        except FileNotFoundError or OSError as e:
            log.error(e)
            return -1
        log.info(f'smb.conf was created successfully in network drive directory ({self.vg_directory})')
        return None

    def __write_nfs_files(self):
        """
         creates a setup_nfs.sh which is used by the VM to setup the nfs server and the corresponding shares
        """
        setup_nfs_template = self.__jinja.get_template('setup_nfs.sh')
        try:
            f_path = self.vg_directory/"setup_nfs.sh"
            f = open(f_path.as_posix(), mode="w")
            f.write(setup_nfs_template.render({
                'configuration': self.nfs
            }))
        except FileNotFoundError or OSError or KeyError as e:
            log.error(e)
            return -1
        log.info(f'setup_nfs.sh was created successfully in network drive directory ({self.vg_directory})')
        return None

    def get_vg_machine(self) -> VagrantMachine:
        """
            create the vagrant machine for the network drive
        """
        vg_machine = VagrantMachine('networkdrive')
        vg_machine.set_box(self.box_name)
        vg_machine.add_network_private(ip=self.vm_config.ip)
        vg_machine.set_cpus(self.vm_config.cpu)
        vg_machine.set_memory(self.vm_config.memory)
        vg_machine.add_file_provisioner(self.vg_directory/"config", "/home/vagrant/config")

        if self.smb:
            vg_machine.add_shell_provisioner_path(self.vg_directory/"setup_smb.sh")
        if self.nfs:
            vg_machine.add_shell_provisioner_path(self.vg_directory/"setup_nfs.sh")
        vg_machine.change_ssh_port(3022)
        log.info('vagrant machine for network drive got created successfully')
        return vg_machine

    def get_vm_ip(self):
        return self.vm_config.ip

    def create(self) -> VagrantMachine or None:
        """
            creates the network drive vagrant machine
        """
        self.__jinja = init_jinja_environment(NETWORKDRIVE_TEMPLATES_DIR)
        if not self.__jinja:
            log.error('jinja environment could NOT be initialized successfully')
            return None

        try:
            (self.vg_directory/"config").mkdir()
            log.debug(f'config directory was created successfully in network drive directory ({self.vg_directory})')
        except FileExistsError:
            log.debug(f'config directory already exists in network drive directory ({self.vg_directory})')
        except OSError as e:
            log.error(e)
            return None

        if not self.smb and not self.nfs:
            log.warning("vm for network drive didn't get started because whether a smb nor a nfs share was configured")
            return None

        vg_machine = self.get_vg_machine()

        if self.smb:
            self.__write_smb_files()
        if self.nfs:
            self.__write_nfs_files()

        log.info('network drive vagrant machine got created successfully')

        return vg_machine

    def cleanup(self):
        """
        clean up the files/directory's in order to create the networkdrive VM

        :return:
        """
        try:
            shutil.rmtree(self.vg_directory)
        except OSError as e:
            log.error(e)
            log.error('not all network drive vm files couldn\'t be deleted while cleanup')
        log.info(f'all files in folder ({self.vg_directory}) got deleted')
