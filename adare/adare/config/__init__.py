# set program details
NAME = "Adare"
VERSION = "0.0.1"
PACKAGE = 'adare'

# timestamp format
TIMESTAMP_FORMAT = '%Y-%m-%dT%H:%M:%S.%f'

# LOGGING DEFAULTS
CONSOLEHANDLER = '%(levelprefix)s %(name)s - %(message)s'
CONSOLEHANDLER_SHORT = '%(levelprefix)s %(message)s'
FILEHANDLER = '[%(asctime)s]: %(threadName)s - %(name)s: %(levelname)s - %(message)s'
ABBREV_DEBUG = ['DEBUG', 'debug', 'Debug', 'd', 'D']
ABBREV_INFO = ['INFO', 'info', 'Info', 'i', 'I']
ABBREV_WARNING = ['WARNING', 'warning', 'Warning', 'w', 'W']
ABBREV_ERROR = ['ERROR', 'error', 'Error', 'e', 'E']
ABBREV_CRITICAL = ['CRITICAL', 'critical', 'Critical', 'c', 'C']


# default values for VM and VM scripts
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
            'user': 'adare',
            'writable': True,
            'uid': 1000,
            'gid': 1000
        },
    'user':
        {
            'name': 'adare',
            'password': 'adare',
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


SCRIPTS_SUFFIX = {
    'linux': '.sh',
    'windows': '.ps1'
}


# WEBAPP
PORT_WEBAPP = 8000



# Additional constants needed by adarevm
SHARE_POINT_VM = {
    'linux': '/adare/',
    'windows': 'C:/adare/'
}

# VM Guest Credentials
DEFAULT_VM_CREDENTIALS = {
    'linux': {'username': 'adare', 'password': 'adare'},
    'windows': {'username': 'adare', 'password': 'adare'}
}


def get_vm_credentials(guest_os: str) -> tuple[str, str]:
    """
    Get default username and password for a guest OS.

    Args:
        guest_os: Guest OS type (e.g., 'windows', 'linux')

    Returns:
        Tuple of (username, password)
    """
    if 'windows' in guest_os.lower():
        return (DEFAULT_VM_CREDENTIALS['windows']['username'],
                DEFAULT_VM_CREDENTIALS['windows']['password'])
    else:
        return (DEFAULT_VM_CREDENTIALS['linux']['username'],
                DEFAULT_VM_CREDENTIALS['linux']['password'])


# Hypervisor Configuration
DEFAULT_HYPERVISOR = "virtualbox"
SUPPORTED_HYPERVISORS = ["virtualbox", "qemu"]

HYPERVISOR_CONFIGS = {
    'virtualbox': {
        'vboxmanage_exe': 'VBoxManage',  # Will be auto-detected based on platform
        'default_graphics': 'vmsvga',
        'default_vram': 128
    },
    'qemu': {
        'qemu_system_exe': 'qemu-system-x86_64',
        'qemu_img_exe': 'qemu-img',
        'default_machine': 'pc',
        'default_accel': 'kvm',
        'default_drive_format': 'qcow2',
        'default_network': 'user',
        'monitor_socket': True,           # Use QMP socket for control
        'guest_agent': True,              # Require QEMU Guest Agent
        'guest_agent_socket': True,       # Use Unix socket for guest agent
        'use_libguestfs': True            # Use libguestfs for file ops when stopped
    }
}

