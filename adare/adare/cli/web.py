# configure logging
import logging

log = logging.getLogger(__name__)

from adare.web.login import login, logout


def exec_web_login(arguments):
    login()


def exec_web_logout(arguments):
    logout()
