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

SHARE_POINT_VM = {
    'linux': '/adare/',
    'windows': 'C:/adare/'
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
    BREAKPOINT_HIT = 10
    BREAKPOINT_RESOLVED = 11
    TEST_MISSING = 12
    TEST_FAILED = 13

    @staticmethod
    def from_string(status_string: str):
        status_string = status_string.strip().lower()
        if status_string == 'success':
            return StatusEnum.SUCCESS
        elif status_string == 'failed':
            return StatusEnum.FAILED
        elif status_string == 'warning':
            return StatusEnum.WARNING
        elif status_string == 'error':
            return StatusEnum.ERROR
        elif status_string == 'running':
            return StatusEnum.RUNNING
        elif status_string == 'pending':
            return StatusEnum.PENDING
        elif status_string == 'interrupted':
            return StatusEnum.INTERRUPTED
        elif status_string == 'finished':
            return StatusEnum.FINISHED
        elif status_string == 'breakpoint_hit':
            return StatusEnum.BREAKPOINT_HIT
        elif status_string == 'breakpoint_resolved':
            return StatusEnum.BREAKPOINT_RESOLVED
        elif status_string == 'test_missing':
            return StatusEnum.TEST_MISSING
        elif status_string == 'test_failed':
            return StatusEnum.TEST_FAILED
        return StatusEnum.NONE

    @staticmethod
    def get_icon(value: int, color=False):
        colorname = StatusEnum.get_color(value) if color else ''
        icon = ''
        if value == StatusEnum.SUCCESS:
            icon = ':heavy_check_mark:'
        elif value == StatusEnum.WARNING:
            icon = ':warning:'
        elif value == StatusEnum.FAILED:
            icon = ':heavy_multiplication_x:'
        elif value == StatusEnum.ERROR:
            icon = ':x:'
        elif value == StatusEnum.FINISHED:
            icon = ':black_small_square:'
        elif value == StatusEnum.INTERRUPTED:
            icon = ':high_voltage:'
        elif value == StatusEnum.RUNNING:
            icon = ':arrow_forward:'
        elif value == StatusEnum.PENDING:
            icon = ':hourglass:'
        elif value == StatusEnum.BREAKPOINT_HIT:
            icon = ':stop_sign:'
        elif value == StatusEnum.BREAKPOINT_RESOLVED:
            icon = ':checkered_flag:'
        elif value == StatusEnum.TEST_MISSING:
            icon = ':question:'
        elif value == StatusEnum.TEST_FAILED:
            icon = ':no_entry_sign:'
        from rich.text import Text
        return f'[{colorname}]{Text.from_markup(icon)}[/{colorname}]' if colorname else icon

    @staticmethod
    def get_color(value: int):
        if value == StatusEnum.SUCCESS:
            return 'green'
        elif value == StatusEnum.WARNING:
            return 'yellow'
        elif value == StatusEnum.FAILED:
            return 'red'
        elif value == StatusEnum.ERROR:
            return 'red'
        elif value == StatusEnum.FINISHED:
            return 'green'
        elif value == StatusEnum.INTERRUPTED:
            return 'yellow'
        elif value == StatusEnum.RUNNING:
            return 'blue'
        elif value == StatusEnum.PENDING:
            return 'yellow'
        elif value == StatusEnum.BREAKPOINT_HIT:
            return 'red'
        elif value == StatusEnum.BREAKPOINT_RESOLVED:
            return 'green'
        elif value == StatusEnum.TEST_MISSING:
            return 'blue'
        elif value == StatusEnum.TEST_FAILED:
            return 'red'
        return ''





