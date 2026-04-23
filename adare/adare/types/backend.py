"""
Backend configuration types for ADARE.

This module contains types for VM configurations, USB devices, network shares,
and other backend infrastructure components.

Moved from adare.types.backend to consolidate application-specific types.
"""

# external imports
# configure logging
import logging
from abc import abstractmethod

import attrs

import adare.config as config

log = logging.getLogger(__name__)


@attrs.define
class UsbDevice:
    """
    Class to store information about a USB device.
    """
    name: str
    VendorId: str | None = None
    ProductId: str | None = None
    Manufacturer: str | None = None
    Product: str | None = None
    SerialNumber: str | None = None


# PostsetupInstallations and OsInfo are imported from environment.py when needed
# To avoid circular imports, we'll import them in the classes that need them


@attrs.define
class CopyData:
    """
    Configuration for copying data to VM.
    """
    source: str
    destination: str


@attrs.define
class DownloadData:
    """
    Configuration for downloading data to VM.
    """
    url: str
    destination: str


@attrs.define
class Disk:
    """
    Disk configuration for VM.
    """
    name: str
    size: int
    mountpoint: str
    filesystem: str


@attrs.define
class Share:
    """
    Base class for network shares used by the network drive VM.
    """
    name: str

    @abstractmethod
    def get_fstab_entry(self, ip: str) -> str:
        pass

    @abstractmethod
    def get_windows_mount_command(self, ip: str) -> str:
        pass


@attrs.define
class NetworkdriveVMConfiguration:
    """
    Configuration of the network drive VM (such as used CPU's, memory and the IP in the internal VM network, where the VM can be found).
    """
    cpu: int = config.DEFAULT_NETWORKSHARES_VM['cpu']
    memory: int = config.DEFAULT_NETWORKSHARES_VM['memory']
    ip: str = config.DEFAULT_NETWORKSHARES_VM['ip']


@attrs.define
class NFSShare(Share):
    """
    Configuration of an NFS share.

    remote_path: name (remote path) of the NFS share
    local_path: local path where the NFS share will be mounted
    allowed_hosts: allowed hosts to connect to the NFS share
    """
    name: str = config.DEFAULT_NFS_CONF['share']['name']
    # used for server setup and client mount
    remote_path: str = config.DEFAULT_NFS_CONF['share']['remote_path']

    # used for server setup only
    allowed_hosts: str = config.DEFAULT_NFS_CONF['share']['host']

    # used for client mount only
    local_path: str = config.DEFAULT_NFS_CONF['share']['path']
    read_only: bool = False

    def get_fstab_entry(self, ip: str) -> str:
        fstab_entry = {
            'file_system': f'{ip}:{self.remote_path}',
            'mount_point': self.local_path,
            'type': 'nfs',
            'options': 'defaults',
            'dump': 0,
            'pass': 0,
        }
        return '\t'.join([str(x) for x in fstab_entry.values()])

    def get_mount_option_string(self) -> str:
        options = []
        if self.read_only:
            options.append('ro')
        else:
            options.append('rw')
        return ','.join(options)

    def get_windows_mount_command(self, ip: str) -> str:
        remote_path_windows_style = self.remote_path.replace('/', '\\')
        mount_info = {
            'local_path': self.local_path,
            'remote_path': f'\\\\{ip}{remote_path_windows_style}',
            'options': ['-u:vagrant', '-p:vagrant']
        }
        options = ''
        if mount_info['options']:
            options = ' ' + ' '.join(mount_info['options'])
        return f'mount "{mount_info["remote_path"]}" "{mount_info["local_path"]}"{options}'


@attrs.define
class NFSConfiguration:
    """
    Configuration of an NFS server.
    """
    name: str = config.DEFAULT_NFS_CONF['name']
    shares: list[NFSShare] = attrs.Factory(list)

    def __check_share(self, share: NFSShare) -> bool:
        """
        Check whether a provided NFS share can be added.

        :param share: NFS share that should be checked
        """
        if share.local_path in [s.local_path for s in self.shares]:
            log.debug(f'path {share.local_path} is already used by another share in the configuration')
            return False
        return True

    def add_share(self, share: NFSShare):
        """
        Add an NFS share to the NFS configuration.

        :param share: NFS share that should be added
        """
        if self.__check_share(share):
            self.shares.append(share)
        else:
            log.error(f'share ({share.name}) could not be added to the NFS configuration successfully')


@attrs.define
class SMBUser:
    """
    Configuration of an SMB user.
    """
    name: str = config.DEFAULT_SMB_CONF['user']['name']
    password: str = config.DEFAULT_SMB_CONF['user']['password']


@attrs.define
class SMBShare(Share):
    """
    Configuration of an SMB share.
    """
    name: str = config.DEFAULT_SMB_CONF['share']['name']
    # used for server setup and client mount
    remote_path: str = config.DEFAULT_SMB_CONF['share']['remote_path']

    # used for server setup only
    comment: str = config.DEFAULT_SMB_CONF['share']['comment']
    user: SMBUser = attrs.Factory(SMBUser)
    guest_ok: bool = False
    browseable_no: bool = False
    writable: bool = config.DEFAULT_SMB_CONF['share']['writable']

    # used for client mount only
    local_path: str = config.DEFAULT_SMB_CONF['share']['path']
    # used for linux mount only
    uid: int = config.DEFAULT_SMB_CONF['share']['uid']
    gid: int = config.DEFAULT_SMB_CONF['share']['gid']
    read_only: bool = not writable

    def get_fstab_entry(self, ip: str) -> str:
        mode = 'ro' if self.read_only else 'rw'
        fstab_entry = {
            'file_system': f'//{ip}/{self.name}',
            'mount_point': self.local_path,
            'type': 'cifs',
            'options': f'{mode},auto,user={self.user.name},password={self.user.password},uid={self.uid},gid={self.gid}',
            'dump': 0,
            'pass': 0,
        }
        return '\t'.join([str(x) for x in fstab_entry.values()])

    def get_windows_mount_command(self, ip: str):
        mount_info = {
            'local_path': self.local_path,
            'remote_path': f'\\\\{ip}\\{self.name}',
            'options': [f'/u:{self.user.name} {self.user.password}']
        }
        options = ' '
        if mount_info['options']:
            options += ' '.join(mount_info['options'])

        return f'net use "{mount_info["local_path"]}" "{mount_info["remote_path"]}"{options}'


@attrs.define
class SMBConfiguration:
    """
    Configuration of an SMB server.
    """
    name: str = config.DEFAULT_SMB_CONF['name']
    shares: list[SMBShare] = attrs.Factory(list)
    users: list[SMBUser] = attrs.Factory(list)
    workgroup: str = config.DEFAULT_SMB_CONF['workgroup']

    def __check_share(self, share: SMBShare) -> bool:
        """
        Check whether a provided share can be added.

        :param share: SMB share that should be checked
        """
        if not self.is_user(share.user):
            log.debug(f'user {share.user} does not exist in the SMB configuration')
            return False
        if share.local_path in [s.local_path for s in self.shares]:
            log.debug(f'path {share.local_path} is already used by another share in the configuration')
            return False
        return True

    def add_share(self, share: SMBShare):
        """
        Add an SMB share to the SMB configuration.

        :param share: SMB share that should be added
        """
        if self.__check_share(share):
            self.shares.append(share)
            # add the user to the SMB configuration
            if not self.is_user(share.user):
                self.add_user(share.user)
        else:
            log.error(f'share {share.name} could not be added to the SMB configuration successfully')

    def is_user(self, user: SMBUser) -> bool:
        return user.name in [u.name for u in self.users]

    def add_user(self, user: SMBUser):
        """
        Add an SMB user to the configuration.

        :param user: SMB user
        """
        if not self.is_user(user):
            self.users.append(user)
        else:
            log.error(
                f'user {user.name} does already exist in the SMB configuration and could therefore not be added to the SMB configuration')

    def get_user_by_name(self, name: str) -> SMBUser | None:
        for u in self.users:
            if u.name == name:
                return u
        log.error(f'user with name {name} is not existing the in the SMB configuration')
        return None


@attrs.define
class NetworkdriveMountData:
    """
    Configuration for mounting network drives.
    """
    nfs: list[NFSShare] = attrs.Factory(list)
    smb: list[SMBShare] = attrs.Factory(list)

    @property
    def all_shares(self) -> list[Share]:
        """Get all shares (NFS and SMB combined)."""
        return self.nfs + self.smb

    def get_fstab_entries(self, ip: str) -> list[str]:
        """Get all fstab entries for mounting shares."""
        entries = []
        for share in self.all_shares:
            entries.append(share.get_fstab_entry(ip))
        return entries

    def get_windows_mount_commands(self, ip: str) -> list[str]:
        """Get all Windows mount commands for shares."""
        commands = []
        for share in self.all_shares:
            commands.append(share.get_windows_mount_command(ip))
        return commands
