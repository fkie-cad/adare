import platform
NAME = 'GUIAutomation'
VERSION = '0.0.1'

# timestamp format
TIMESTAMP_FORMAT = '%Y-%m-%dT%H:%M:%S.%f%z'

if platform.system() == 'Windows':
    VARIABLES_FILE = "C:/Users/vagrant/AppData/Local/Temp/LINUXAUTO_VARS"
else:
    VARIABLES_FILE = "/tmp/LINUXAUTO_VARS"

# set log format
CONSOLEHANDLER = '%(levelprefix)s %(name)s - %(message)s'
FILEHANDLER = '[%(asctime)s]: %(name)s: %(levelname)s - %(message)s'
DEFAULTLOGFILE = "~/main.log"
