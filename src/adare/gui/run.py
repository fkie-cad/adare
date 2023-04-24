# internal imports
from adare.helperFunctions.subprocess.run_command import run_python

# configure logging
import logging
log = logging.getLogger(__name__)


def runserver(port: int, quiet: bool = True):
    # todo: save output to log file
    cmd = ['gui/main.py', str(port)]
    run_python(cmd, quiet=quiet)