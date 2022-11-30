# external imports
import shutil
import pkg_resources
import jinja2
from pathlib import Path

# internal imports
import adare.config as config
from adare.vagrantapi import VagrantFile, Vagrant, run_vagrant
from adare.helperFunctions.jinja.jinjafeatures import init_jinja_environment
from adare.networkdrive.exceptions import NetworkdriveCreationError
from adare.networkdrive.attrs_classes import NFSConfiguration, NFSShare, SMBConfiguration, SMBShare, SMBUser, NetworkdriveVMConfiguration

# configure logging
import logging
log = logging.getLogger(__name__)


class NetworkdriveVM:
    """
    class that creates a virtual machine, which consists of network drives such as smb and nfs
    (therefore vagrant, virtualbox as well as and ubuntu server vagrant box with installed nfs and smb server is required)

    """
    smb: SMBConfiguration or None = None
    nfs: NFSConfiguration or None = None
    shares: list
    active: bool = False
    __jinja: jinja2.Environment
    vagrantdirectory: str
    vagrantbox: str
    vmconfiguration: NetworkdriveVMConfiguration

    def __init__(self, drivedir, vagrantbox="networkshares", networkdrive_vm_conf: NetworkdriveVMConfiguration or None = None):
        self.vagrantbox = vagrantbox
        self.vmconfiguration = networkdrive_vm_conf
        self.shares = []
        if not self.vmconfiguration:
            self.vmconfiguration = NetworkdriveVMConfiguration()
            log.debug('network drive vm will be started with default configuration')
        vagrant = Vagrant()
        if not vagrant.is_box(self.vagrantbox):
            log.error(f'class networkdrive vm could NOT be created due to the fact that the given vagrant box ({self.vagrantbox}) does NOT exist')
            raise NetworkdriveCreationError
        self.__jinja = init_jinja_environment(pkg_resources.resource_filename(config.PACKAGE, 'data/networkdrive/templates'))
        if not self.__jinja:
            log.error('jinja environment could NOT be initialized successfully')
            raise NetworkdriveCreationError
        if not Path(drivedir).is_dir():
            try:
                Path(drivedir).mkdir()
                log.debug(f'directory for network drive ({drivedir}) was created successfully')
            except OSError or FileExistsError as e:
                log.error(e)
                raise NetworkdriveCreationError
        self.vagrantdirectory = drivedir
        try:
            Path(drivedir + "/config").mkdir()
            log.debug(f'config directory was created successfully in network drive directory ({drivedir})')
        except OSError or FileExistsError as e:
            log.error(e)
            raise NetworkdriveCreationError

    def create_smb(self, smb_configuration: SMBConfiguration or None = None) -> int:
        """
        creates an smb network drive (shares can be added with add_smb_share)

        :param smb_configuration: configuration used for the the smb server
        :return:
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

        :param nfs_configuration: configuration used for the nfs server
        :return:
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
        adds an smb share to an smb server (and creates a smb server if not already existing)

        :param smb_share: configuration of the smb share
        :return:
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

    def add_smb_user(self, smb_user: SMBUser or None = None):
        if not self.smb:
            log.error('no smb configuration for the network drive vm is set so far, therefore no smb user could be added')
            return
        if not smb_user:
            smb_user = SMBUser()
        self.smb.add_user(smb_user)

    def is_smb_user(self, smb_user: SMBUser):
        return self.smb.is_user(smb_user)

    def add_nfs_share(self, nfs_share: NFSShare or None = None):
        """
        adds an nfs share to an smb server (and creates a smb server if not already existing)

        :param nfs_share: configuration of the nfs share
        :return:
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
        creates a smb.conf file as well as an setup_smb.sh which is used by the VM to correctly setup the smb server and the corresponding shares

        :return:
        """
        setup_smb_template = self.__jinja.get_template('setup_smb.sh')
        smb_conf_template = self.__jinja.get_template('smb.conf')
        try:
            f = open(self.vagrantdirectory + "/setup_smb.sh", mode="w")
            f.write(setup_smb_template.render({'configuration': self.smb}))
        except FileNotFoundError or OSError as e:
            log.error(e)
            return -1

        try:
            f = open(self.vagrantdirectory + "/config/smb.conf", mode="w")
            f.write(smb_conf_template.render({'configuration': self.smb}))
        except FileNotFoundError or OSError as e:
            log.error(e)
            return -1

    def __write_nfs_files(self):
        """
        creates a setup_nfs.sh which is used by the VM to correctly setup the nfs server and the corresponding shares

        :return:
        """
        setup_nfs_template = self.__jinja.get_template('setup_nfs.sh')
        try:
            f = open(self.vagrantdirectory + "/setup_nfs.sh", mode="w")
            f.write(setup_nfs_template.render({
                'configuration': self.nfs
            }))
        except FileNotFoundError or OSError or KeyError as e:
            log.error(e)
            return -1

    def __write_vagrantfile(self):
        """
        create the Vagrantfile used for starting the VM

        :return:
        """
        vg_creator = VagrantFile()
        vg_creator.set_box(self.vagrantbox)
        vg_creator.add_network_private(ip=self.vmconfiguration.ip)
        vg_creator.set_cpus(self.vmconfiguration.cpu)
        vg_creator.set_memory(self.vmconfiguration.memory)
        vg_creator.disable_virtualbox_guestautoupdate()
        vg_creator.add_file_provisioner("./config", "/home/vagrant/config")
        if self.smb:
            vg_creator.add_shell_provisioner_path("./setup_smb.sh")
        if self.nfs:
            vg_creator.add_shell_provisioner_path("./setup_nfs.sh")
        vg_creator.change_ssh_port(3022)
        vg_creator.create_vagrant_file(self.vagrantdirectory+"/Vagrantfile")

    def start(self) -> dict:
        """
        starts the network drive VM (vagrant up)

        :return: dict that contain the return code, stdout and stderr of the vagrant process
        """
        if not self.smb and not self.nfs:
            log.warning("vm for network drive didn't get started because whether a smb nor a nfs share was configured")
            return {}
        self.__write_vagrantfile()
        if self.smb:
            self.__write_smb_files()
        if self.nfs:
            self.__write_nfs_files()
        ret = run_vagrant(["up"], cwd=self.vagrantdirectory)
        self.active = True
        return ret

    def stop(self):
        """
        stops the network drive VM (vagrant destroy)

        :return: dict that contain the return code, stdout and stderr of the vagrant process
        """
        ret = run_vagrant(["destroy", "-f"], cwd=self.vagrantdirectory)
        self.active = False
        return ret

    def is_alive(self):
        """
        check if a network drive vm is still existing

        :return: True if it exists and False if not
        """
        return self.active

    def cleanup(self):
        """
        clean up the files/directory's in order to create the networkdrive VM

        :return:
        """
        try:
            shutil.rmtree(self.vagrantdirectory)
        except OSError as e:
            log.error(e)
            log.error('not all network drive vm files couldn\'t be deleted while cleanup')
        log.info(f'all files in folder ({self.vagrantdirectory}) got deleted')
