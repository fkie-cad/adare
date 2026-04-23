# internal imports
# configure logging
import logging

from adare.config import VERSION

log = logging.getLogger(__name__)


def exec_show_version(arguments, parser):
    """
        cli function to show the program version
    """
    if arguments.version:
        print(f'Version {VERSION}')
    else:
        parser.print_help()
