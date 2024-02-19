NAME = 'adarelib'
# timestamp format
TIMESTAMP_FORMAT = '%Y-%m-%dT%H:%M:%S.%f%z'

# LOGGING DEFAULTS
CONSOLEHANDLER = '%(levelprefix)s %(name)s - %(message)s'
CONSOLEHANDLER_SHORT = '%(levelprefix)s %(message)s'
FILEHANDLER = '[%(asctime)s]: %(name)s: %(levelname)s - %(message)s'
ABBREV_DEBUG = ['DEBUG', 'debug', 'Debug', 'd', 'D']
ABBREV_INFO = ['INFO', 'info', 'Info', 'i', 'I']
ABBREV_WARNING = ['WARNING', 'warning', 'Warning', 'w', 'W']
ABBREV_ERROR = ['ERROR', 'error', 'Error', 'e', 'E']
ABBREV_CRITICAL = ['CRITICAL', 'critical', 'Critical', 'c', 'C']