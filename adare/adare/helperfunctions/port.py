# external imports
# configure logging
import logging
import socket

log = logging.getLogger(__name__)


def is_localhost_port_free(port: int) -> bool:
    port_free = False

    host = '127.0.0.1'

    s = socket.socket()
    try:
        s.bind((host, port))
        s.close()
        port_free = True
    except OSError:
        pass

    return port_free
