# set program details
NAME = "AutoArtParser"
VERSION = "0.0.1"
PACKAGE = 'reproldfauto'

# timestamp format
TIMESTAMP_FORMAT = '%Y-%m-%dT%H:%M:%S.%f%z'

# LOGGING DEFAULTS
CONSOLEHANDLER = '%(levelprefix)s %(name)s - %(message)s'
CONSOLEHANDLER_SHORT = '%(levelprefix)s %(message)s'
FILEHANDLER = '[%(asctime)s]: %(name)s: %(levelname)s - %(message)s'
DEFAULTLOGFILE = "D:/main.log"
ABBREV_DEBUG = ['DEBUG', 'debug', 'Debug', 'd', 'D']
ABBREV_INFO = ['INFO', 'info', 'Info', 'i', 'I']
ABBREV_WARNING = ['WARNING', 'warning', 'Warning', 'w', 'W']
ABBREV_ERROR = ['ERROR', 'error', 'Error', 'e', 'E']
ABBREV_CRITICAL = ['CRITICAL', 'critical', 'Critical', 'c', 'C']

# set default variables
BASEDIR = "."
LOGDIR_RELPROJ = "logs"
PROGRAMS_RELPROJ = "programs"
SETUPDIR_RELPROJ = "setup"
ENVDIR_RELPROJ = "environments"
INPUTDIR_RELPROJ = "input"

ENVCONFIGURATIONFILENAME = ".envconf.yml"
PROJECTINFOFILENAME = '.projconf.yml'

INPUT_RELENV = "input"
PROGRAMS_RELENV = "scripts"
LOGDIR_RELENV = "logs"
RESULT_RELENV = "result"
NETWORKDRIVE_RELENV = "networkdrives"
EXTERNALPROGRAMS_RELENV = "externalprograms"

PARSEANDTESTPROG = 'ParseAndTest'
GUIAUTOMATIONPROG = 'GUIAutomation'

SCENARIOBASEDIR_IN_GUIAUTOMATION = 'src/guiautomation/Scenario/'

# default values for data located in package
PCK_TEMPLATES = 'data/templates/'
PCK_EXAMPLES = 'data/examples/'
PCK_EXAMPLES_SETUPFILES = PCK_EXAMPLES+'EnvironmentSetupFiles'
PCK_EXAMPLES_GUISCENARIOS = PCK_EXAMPLES+'GUIScenarios'
PCK_EXAMPLES_INPUTFILES = PCK_EXAMPLES+'ScenarioInputs'
PCK_PROGRAMS = 'data/programs/'
PCK_PROGRAMS_GUIAUTOMATION = PCK_PROGRAMS+GUIAUTOMATIONPROG
PCK_PROGRAMS_PARSEANDTEST = PCK_PROGRAMS+PARSEANDTESTPROG

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

SCRIPTS_SUFFIX = {
    'linux': '.sh',
    'windows': '.ps1'
}
