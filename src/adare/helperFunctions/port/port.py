# external imports
import socket

# configure logging
import logging
log = logging.getLogger(__name__)


def is_localhost_port_free(port: int) -> bool:
    port_free = False

    host = '127.0.0.1'

    s = socket.socket()
    try:
        s.bind((host, port))
        s.close()
        port_free = True
    except socket.error:
        pass

    return port_free
