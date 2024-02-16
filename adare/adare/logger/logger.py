# external imports
import logging
import sys
from pathlib import Path

# internal imports
import adare.config as config


APP_LOGGER_NAME = config.NAME


class FileHandlerFormatter(logging.Formatter):
    """
        custom formatter that is used for logging to a file
    """
    def __init__(self):
        logging.Formatter.__init__(self, config.FILEHANDLER, None)

    def format(self, record):
        if record.levelno == logging.DEBUG:
            record.levelprefix = "[*]"
        elif record.levelno == logging.INFO:
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


class ConsoleHandlerFormatter(logging.Formatter):
    """
        custom formatter that is used for logging to console
    """
    def __init__(self):
        logging.Formatter.__init__(self, config.CONSOLEHANDLER, None)

    def format(self, record):
        if record.levelno == logging.DEBUG:
            record.levelprefix = "[*]"
        elif record.levelno == logging.INFO:
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


class ConsoleShortHandlerFormatter(logging.Formatter):
    """
        custom formatter that is used for logging to console
    """
    def __init__(self):
        logging.Formatter.__init__(self, config.CONSOLEHANDLER_SHORT, None)

    def format(self, record):
        if record.levelno == logging.DEBUG:
            record.levelprefix = "[*]"
        elif record.levelno == logging.INFO:
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


def setup_logger(loglevel_console=None, loglevel_file=None, logfile=None, console=True, console_details=False):
    """
        setup up logging for a project

        :param loglevel_console: contains the loglevel such that no log messages with lower loglevel are shown in the console
        :param loglevel_file: contains the loglevel such that no log messages with lower loglevel are shown in the logfile
        :param logfile: path of the logfile that should be used (None if no logfile should be created)
        :param console: True if log should be printed to console and False if not
    """

    if not loglevel_console:
        loglevel_console = logging.DEBUG
    if not loglevel_file:
        loglevel_file = logging.DEBUG
    if not console:
        loglevel_console = logging.CRITICAL


    handler = logging.StreamHandler(sys.stdout)
    if console_details:
        handler.setFormatter(ConsoleHandlerFormatter())
    else:
        handler.setFormatter(ConsoleShortHandlerFormatter())
    handler.setLevel(loglevel_console)
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(loglevel_console)

    if logfile:
        if not Path(logfile).parent.is_dir():
            print(f'logging in file {str(logfile)} couldn\'t be initialized')
        else:
            handler = logging.FileHandler(logfile, encoding='utf-8')
            handler.setFormatter(FileHandlerFormatter())
            logging.getLogger().addHandler(handler)
            # check if loglevel_file is higher than loglevel_console and adjust logger level if necessary
            if loglevel_file < loglevel_console:
                logging.getLogger().setLevel(loglevel_file)

