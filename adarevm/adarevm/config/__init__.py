import platform
from pathlib import Path

NAME = 'adarevm'
VERSION = '0.0.1'

# timestamp format
TIMESTAMP_FORMAT = '%Y-%m-%dT%H:%M:%S.%f%z'

if platform.system() == 'Windows':
    VARIABLES_FILE = Path("C:/Users/vagrant/AppData/Local/Temp/LINUXAUTO_VARS")
elif platform.system() == 'Linux':
    VARIABLES_FILE = Path("/tmp/LINUXAUTO_VARS")

# set log format
CONSOLEHANDLER = '%(levelprefix)s %(name)s - %(message)s'
FILEHANDLER = '[%(asctime)s]: %(name)s: %(levelname)s - %(message)s'

