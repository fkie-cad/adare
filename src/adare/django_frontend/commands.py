# internal imports
from adare.helperFunctions.subprocess.run_command import run_python

# configure logging
import logging
log = logging.getLogger(__name__)


def runserver(port: int, quiet: bool = True):
    cmd = ['django_manage.py', 'runserver', f'localhost:{port}']
    run_python(cmd, quiet=quiet)


def makemigrations(app: str, quiet: bool = True):
    cmd = ['django_manage.py', 'makemigrations', app]
    run_python(cmd, quiet=quiet)


def migrate(quiet: bool = True):
    cmd = ['django_manage.py', 'migrate']
    run_python(cmd, quiet=quiet)
