import logging
import logging.config
import sys

import guiautomation.config as config
from pathlib import Path

APP_LOGGER_NAME = config.NAME


class FileHandlerFormatter(logging.Formatter):
    def __init__(self):
        logging.Formatter.__init__(self, config.FILEHANDLER, None)

    def format(self, record):
        if record.levelno == logging.INFO:
            record.levelprefix = "[*]"
        elif record.levelno == logging.DEBUG:
            record.levelprefix = "[+]"
        elif record.levelno == logging.WARNING:
            record.levelprefix = "[!]"
        elif record.levelno == logging.ERROR:
            record.levelprefix = "[-]"
        elif record.levelno == logging.CRITICAL:
            record.levelprefix = "[--]"
        else:
            record.levelprefix = "[?]"

        return logging.Formatter.format(self, record)


class ConsoleHandlerFormatter(logging.Formatter):
    def __init__(self):
        logging.Formatter.__init__(self, config.CONSOLEHANDLER, None)

    def format(self, record):
        if record.levelno == logging.INFO:
            record.levelprefix = "[*]"
        elif record.levelno == logging.DEBUG:
            record.levelprefix = "[+]"
        elif record.levelno == logging.WARNING:
            record.levelprefix = "[!]"
        elif record.levelno == logging.ERROR:
            record.levelprefix = "[-]"
        elif record.levelno == logging.CRITICAL:
            record.levelprefix = "[X]"
        else:
            record.levelprefix = "[?]"

        return logging.Formatter.format(self, record)


def setup_logger(loglevel_console=logging.DEBUG, loglevel_file=logging.DEBUG, logfile: Path = None, console=True):
    if not loglevel_console:
        loglevel_console = logging.INFO
    if not loglevel_file:
        loglevel_file = logging.DEBUG
    if console:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(ConsoleHandlerFormatter())
        handler.setLevel(loglevel_console)
        logging.getLogger().addHandler(handler)

    if logfile:
        if not logfile.parent.is_dir():
            print(f"logging in file {logfile} couldn't be initialized")
        else:
            handler = logging.FileHandler(logfile.as_posix(), encoding='utf-8')
            handler.setFormatter(FileHandlerFormatter())
            logging.getLogger().addHandler(handler)
            logging.getLogger().setLevel(loglevel_file)
