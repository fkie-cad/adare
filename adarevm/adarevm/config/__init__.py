import platform
from pathlib import Path
from adarelib.config import SHARE_POINT_VM

NAME = 'adarevm'
VERSION = '0.0.1'

# timestamp format
TIMESTAMP_FORMAT = '%Y-%m-%dT%H:%M:%S.%f%z'

if platform.system() == 'Windows':
    VARIABLES_FILE = Path("C:/Users/vagrant/AppData/Local/Temp/LINUXAUTO_VARS")
    SHARED_BASE_DIR = SHARE_POINT_VM['windows']
elif platform.system() == 'Linux':
    VARIABLES_FILE = Path("/tmp/LINUXAUTO_VARS")
    SHARED_BASE_DIR = SHARE_POINT_VM['linux']

# set log format
CONSOLEHANDLER = '%(levelprefix)s %(name)s - %(message)s'
FILEHANDLER = '[%(asctime)s]: %(name)s: %(levelname)s - %(message)s'

