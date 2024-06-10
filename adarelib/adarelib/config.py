from enum import IntEnum

NAME = 'adarelib'
# timestamp format
TIMESTAMP_FORMAT = '%Y-%m-%dT%H:%M:%S.%f'

# LOGGING DEFAULTS
CONSOLEHANDLER = '%(levelprefix)s %(name)s - %(message)s'
CONSOLEHANDLER_SHORT = '%(levelprefix)s %(message)s'
FILEHANDLER = '[%(asctime)s]: %(name)s: %(levelname)s - %(message)s'
ABBREV_DEBUG = ['DEBUG', 'debug', 'Debug', 'd', 'D']
ABBREV_INFO = ['INFO', 'info', 'Info', 'i', 'I']
ABBREV_WARNING = ['WARNING', 'warning', 'Warning', 'w', 'W']
ABBREV_ERROR = ['ERROR', 'error', 'Error', 'e', 'E']
ABBREV_CRITICAL = ['CRITICAL', 'critical', 'Critical', 'c', 'C']


DEFAULT_RESOLUTION = "1920x1080"
DEFAULT_VM_IP = "192.168.142.10"
DEFAULT_GUI_LOGLEVEL = "info"
DEFAULT_PAUSE_AFTERGUIAUTOMATION = "30"
DEFAULT_START_OS_IDLE = "60"

# default variables for network drives
SUPPORTED_NETWORKDRIVE_TYPES = ["smb", "nfs"]

DEFAULT_NETWORKSHARES_VM = {
    'cpu': "2",
    'memory': "1024",
    'ip': "192.168.142.100"
}

DEFAULT_NETWORKSHARE_BOX = "networkshares"

DEFAULT_SMB_CONF = {
    'name': 'SMB share',
    'workgroup': 'WORKGROUP',
    'share':
        {
            'name': 'SMBshare',
            'remote_path': '/mnt/smb_share_0',
            'path': '/mnt/smb',
            'comment': 'This is an SMB share',
            'user': 'vagrant',
            'writable': True,
            'uid': 1000,
            'gid': 1000
        },
    'user':
        {
            'name': 'vagrant',
            'password': 'vagrant',
        }
}

DEFAULT_NFS_CONF = {
    'name': 'NFS share',
    'share':
        {
            'name': 'NFSshare',
            'remote_path': '/mnt/nfs_share_0',
            'path': '/mnt/nfs',
            'host': '*',
            'options': ["rw"]
        }

}

DEFAULT_NETWORKDRIVE_SHARENAME = "share"

# maximum time for a breakpoint to be active
BREAKPOINT_LIMIT_SECONDS = 60*5


class StatusEnum(IntEnum):
    NONE = 1
    SUCCESS = 2
    FAILED = 3
    WARNING = 4
    ERROR = 5
    RUNNING = 6
    PENDING = 7
    INTERRUPTED = 8
    FINISHED = 9

    @staticmethod
    def is_valid(value: int):
        return value in StatusEnum.__members__






