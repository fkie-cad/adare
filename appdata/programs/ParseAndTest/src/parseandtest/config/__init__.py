import platform
from pathlib import Path

# set program details
NAME = "ParseAndTest"
VERSION = "0.0.1"

# timestamp format
TIMESTAMP_FORMAT = '%Y-%m-%dT%H:%M:%S.%f%z'

# set log format
CONSOLEHANDLER = '%(levelprefix)s %(name)s - %(message)s'
FILEHANDLER = '[%(asctime)s]: %(name)s: %(levelname)s - %(message)s'
DEFAULTLOGFILE = "~/main.log"

# set filepath for saved variables
VARIABLES_FILE = ''
if platform.system() == 'Windows':
    VARIABLES_FILE = Path("C:/Users/vagrant/AppData/Local/Temp/LINUXAUTO_VARS")
else:
    VARIABLES_FILE = Path("/tmp/LINUXAUTO_VARS")