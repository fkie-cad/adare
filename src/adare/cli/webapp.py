# internal imports
from adare.config import PORT_WEBAPP
from adare.helperFunctions.port.port import is_localhost_port_free
from adare.gui.run import runserver as run_gui

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

    print(f'webapp is running on http://127.0.0.1:{port}')

    run_gui(port=port)

    print(f'webapp closed')

