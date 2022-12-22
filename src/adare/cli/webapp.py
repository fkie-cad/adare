# external imports
import pkg_resources
import platform

# internal imports
from adare.config import PORT_WEBAPP
from adare.helperFunctions.subprocess.run_command import run_cmd
from adare.helperFunctions.port.port import is_localhost_port_free
from adare.django_settings.setup import django_setup

# configure logging
import logging
log = logging.getLogger(__name__)


def webapp(arguments):
    port = PORT_WEBAPP
    if arguments.port:
        port = int(arguments.port)
        if port < 0 or port > 49152:
            port = PORT_WEBAPP

    while not is_localhost_port_free(port) and port <= 49152:
        log.warning(f'port {port} is in use and can therefore not be used for the webapp')
        port += 1

    log.debug(f'webapp port: {port}')

    system = platform.system()
    cmd = []
    if system == 'Windows':
        cmd.append('py')
    elif system == "Linux" or system == "Darwin":
        cmd.append('python3')
    else:
        log.fatal(f'the os {system} is not supported by the tool')
    cmd += ['django_manage.py', 'runserver', f'localhost:{port}']

    # django_setup()

    print(f'webapp is running on http://127.0.0.1:{port}')

    run_cmd(cmd, cwd=pkg_resources.resource_filename('adare', ''), quiet=True)

    print(f'webapp closed')

