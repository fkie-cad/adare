# internal imports
import adare.config as config

# configure logging
from adare.logger import logger
import logging as log


def setup_logging(arguments, commandline):
    """
    set up the logging for the application.

    :param arguments: namespace with command line arguments (needed are log_level_console, log_level_file, log_format_console, logfile)
    :param commandline: commandline string
    :return:
    """
    loglevel_console = None
    loglevel_file = None

    if arguments.very_verbose:
        loglevel_console = log.DEBUG
    elif arguments.verbose:
        loglevel_console = log.INFO

    if arguments.log_level:
        # remove whitespace from loglevel_console, loglevel_file and log_format_console
        arguments.log_level = arguments.log_level.strip()
        if arguments.log_level in config.ABBREV_DEBUG:
            loglevel_file = log.DEBUG
        elif arguments.log_level in config.ABBREV_INFO:
            loglevel_file = log.INFO
        elif arguments.log_level in config.ABBREV_WARNING:
            loglevel_file = log.WARNING
        elif arguments.log_level in config.ABBREV_ERROR:
            loglevel_file = log.ERROR
        elif arguments.log_level in config.ABBREV_CRITICAL:
            loglevel_file = log.CRITICAL

    console_logging = bool(loglevel_console)
    if arguments.logfile:
        logger.setup_logger(loglevel_console=loglevel_console, logfile=arguments.log, console=console_logging,  loglevel_file=loglevel_file)
    else:
        logger.setup_logger(loglevel_console=loglevel_console, logfile=None, console=console_logging, loglevel_file=loglevel_file)

    log.info(f'COMMAND: {" ".join(commandline)}')
