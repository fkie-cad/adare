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
    if arguments.log_level_console:
        if arguments.log_level_console in config.ABBREV_DEBUG:
            loglevel_console = log.DEBUG
        elif arguments.log_level_console in config.ABBREV_INFO:
            loglevel_console = log.INFO
        elif arguments.log_level_console in config.ABBREV_WARNING:
            loglevel_console = log.WARNING
        elif arguments.log_level_console in config.ABBREV_ERROR:
            loglevel_console = log.ERROR
        elif arguments.log_level_console in config.ABBREV_CRITICAL:
            loglevel_console = log.CRITICAL
    loglevel_file = None
    if arguments.log_level_file:
        if arguments.log_level_file in config.ABBREV_DEBUG:
            loglevel_file = log.DEBUG
        elif arguments.log_level_file in config.ABBREV_INFO:
            loglevel_file = log.INFO
        elif arguments.log_level_file in config.ABBREV_WARNING:
            loglevel_file = log.WARNING
        elif arguments.log_level_file in config.ABBREV_ERROR:
            loglevel_file = log.ERROR
        elif arguments.log_level_file in config.ABBREV_CRITICAL:
            loglevel_file = log.CRITICAL
    logformat = arguments.log_format_console
    if arguments.logfile:
        logger.setup_logger(loglevel_console=loglevel_console, logfile=arguments.logfile, loglevel_file=loglevel_file, console_details=logformat)
    else:
        logger.setup_logger(loglevel_console=loglevel_console, logfile=None, loglevel_file=loglevel_file, console_details=logformat)

    log.info(f'COMMAND: {" ".join(commandline)}')
