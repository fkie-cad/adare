# external imports
import attr
from typing import Optional

# internal imports
import adare.config as config

# configure logging
import logging
log = logging.getLogger(__name__)


@attr.define
class Share:
    """
    base class for network shares used by the network drive vm
    """
    name: str

    def get_fstab_entry(self, ip: str) -> str:
        pass

    def get_windows_mount_command(self, ip: str) -> str:
        pass


@attr.define
class NetworkdriveVMConfiguration:
    """
        configuration of the network drive  VM (such as used cpu's, memory and the ip in the internal vm network, where the VM can be found)
    """
    cpu: int = config.DEFAULT_NETWORKSHARES_VM['cpu']
    memory: int = config.DEFAULT_NETWORKSHARES_VM['memory']
    ip: str = config.DEFAULT_NETWORKSHARES_VM['ip']


@attr.define
class NFSShare(Share):
    """
        configuration of an nfs share

        remote_path: name (remote path) of the nfs share
        local_path: local path where the nfs share will be mounted
        allowed_hosts: allowed hosts to connect to the nfs share
        options:
    """
    name: str = config.DEFAULT_NFS_CONF['share']['name']
    # used for server setup and client mount
    remote_path: str = config.DEFAULT_NFS_CONF['share']['remote_path']

    # used for server setup only
    allowed_hosts: str = config.DEFAULT_NFS_CONF['share']['host']

    # used for client mount only
    local_path: str = config.DEFAULT_NFS_CONF['share']['path']
    read_only: bool = False
    # mount options
    # port: Optional[str] = None
    # rsize: Optional[str] = None
    # wsize: Optional[str] = None

    def get_fstab_entry(self, ip: str) -> str:
        fstab_entry = {
            'file_system': f'{ip}:{self.remote_path}',
            'mount_point': self.local_path,
            'type': 'nfs',
            'options': 'defaults',
            'dump': 0,
            'pass': 0,
        }
        fstab_str = '\t'.join([str(x) for x in fstab_entry.values()])
        return fstab_str

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
        command = f'mount "{mount_info["remote_path"]}" "{mount_info["local_path"]}"{options}'
        return command


@attr.define
class NFSConfiguration:
    """
        configuration of an nfs server
    """
    name: str = config.DEFAULT_NFS_CONF['name']
    shares: list[NFSShare] = attr.Factory(list)

    def __check_share(self, share: NFSShare) -> bool:
        """
        check whether a provided nfs share can be added

        :param share: nfs share that should be checked
        """
        if share.local_path in [s.local_path for s in self.shares]:
            log.debug(f'path {share.local_path} is already used by another share in the configuration')
            return False
        return True

    def add_share(self, share: NFSShare):
        """
        add a nfs share to the nfs configuration

        :param share: nfs share that should be added
        """
        if self.__check_share(share):
            self.shares.append(share)
        else:
            log.error(f'share ({share.name}) could not be added to the smb configuration successfully')


@attr.define
class SMBUser:
    """
        configuration of an smb user
    """
    name: str = config.DEFAULT_SMB_CONF['user']['name']
    password: str = config.DEFAULT_SMB_CONF['user']['password']


@attr.define
class SMBShare(Share):
    """
        configuration of an smb share
    """
    name: str = config.DEFAULT_SMB_CONF['share']['name']
    # used for server setup and client mount
    remote_path: str = config.DEFAULT_SMB_CONF['share']['remote_path']

    # used for server setup only
    comment: str = config.DEFAULT_SMB_CONF['share']['comment']
    user: SMBUser = attr.Factory(SMBUser)
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
        if self.read_only:
            mode = 'ro'
        else:
            mode = 'rw'
        fstab_entry = {
            'file_system': f'//{ip}/{self.name}',
            'mount_point': self.local_path,
            'type': 'cifs',
            'options': f'{mode},auto,user={self.user.name},password={self.user.password},uid={self.uid},gid={self.gid}',
            'dump': 0,
            'pass': 0,
        }
        fstab_str = '\t'.join([str(x) for x in fstab_entry.values()])
        return fstab_str

    def get_windows_mount_command(self, ip: str):
        mount_info = {
            'local_path': self.local_path,
            'remote_path': f'\\\\{ip}\\{self.name}',
            'options': [f'/u:{self.user.name} {self.user.password}']
        }
        options = ' '
        if mount_info['options']:
            options += ' '.join(mount_info['options'])

        command = f'net use "{mount_info["local_path"]}" "{mount_info["remote_path"]}"{options}'
        return command


@attr.define
class SMBConfiguration:
    """
        configuration of an smb server
    """
    name: str = config.DEFAULT_SMB_CONF['name']
    shares: list[SMBShare] = attr.Factory(list)
    users: list[SMBUser] = attr.Factory(lambda: [SMBUser()])
    workgroup: str = config.DEFAULT_SMB_CONF['workgroup']

    def __check_share(self, share: SMBShare) -> bool:
        """
        check whether a provided share can be added

        :param share: smb share that should be checked
        """
        if not self.is_user(share.user):
            log.debug(f'user {share.user} does not exist in the smb configuration')
            return False
        if share.local_path in [s.local_path for s in self.shares]:
            log.debug(f'path {share.local_path} is already used by another share in the configuration')
            return False
        return True

    def add_share(self, share: SMBShare):
        """
        add a smb share to the smb configuration

        :param share: smb share that should be added
        """
        if self.__check_share(share):
            self.shares.append(share)
        else:
            log.error(f'share {share.name} could not be added to the smb configuration successfully')

    def is_user(self, user: SMBUser) -> bool:
        if user.name in [u.name for u in self.users]:
            return True
        return False

    def add_user(self, user: SMBUser):
        """
        add a smb user to the configuration

        :param user: smb user
        """
        if not self.is_user(user):
            self.users.append(user)
        else:
            log.error(f'user {user.name} does already exist in the smb configuration and could therefore not be added to the smb configuration')

    def get_user_by_name(self, name: str) -> Optional[SMBUser]:
        for u in self.users:
            if u.name == name:
                user = u
                return user
        log.error(f'user with name {name} is not existing the in the smb configuration')
        return None
