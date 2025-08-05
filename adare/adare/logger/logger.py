"""Custom logging formatters and setup for ADARE.

Provides visual log level indicators and configurable logging handlers
for both console and file output with consistent formatting.
"""

import logging
import logging.config
import sys
from pathlib import Path
from typing import Optional

import adare.config as config

APP_LOGGER_NAME = config.NAME

# Log level to visual indicator mapping
LOG_LEVEL_PREFIXES = {
    logging.DEBUG: "[+]",
    logging.INFO: "[*]", 
    logging.WARNING: "[!]",
    logging.ERROR: "[-]",
    logging.CRITICAL: "[--]",  # File handler uses [--] for critical
}

CONSOLE_LEVEL_PREFIXES = {
    **LOG_LEVEL_PREFIXES,
    logging.CRITICAL: "[X]",  # Console handler uses [X] for critical
}


class BaseAdareFormatter(logging.Formatter):
    """Base formatter class for ADARE logging with visual indicators.
    
    Provides common functionality for adding level-specific prefixes
    to log messages for visual distinction.
    """
    
    def __init__(self, format_string: str, level_prefixes: dict[int, str]):
        """Initialize the formatter.
        
        Args:
            format_string: Python logging format string
            level_prefixes: Mapping from log levels to visual prefixes
        """
        super().__init__(format_string, None)
        self.level_prefixes = level_prefixes
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record with appropriate level prefix.
        
        Args:
            record: Log record to format
            
        Returns:
            Formatted log message string
        """
        # Add level prefix to record for use in format string
        record.levelprefix = self.level_prefixes.get(record.levelno, "[?]")
        return super().format(record)


class FileHandlerFormatter(BaseAdareFormatter):
    """File logging formatter with standard level indicators.
    
    Uses config.FILEHANDLER format string and file-appropriate
    level prefixes (including [--] for critical messages).
    """
    
    def __init__(self):
        super().__init__(config.FILEHANDLER, LOG_LEVEL_PREFIXES)


class ConsoleHandlerFormatter(BaseAdareFormatter):
    """Console logging formatter with visual level indicators.
    
    Uses config.CONSOLEHANDLER format string and console-appropriate
    level prefixes (including [X] for critical messages).
    """
    
    def __init__(self):
        super().__init__(config.CONSOLEHANDLER, CONSOLE_LEVEL_PREFIXES)


def setup_logger(loglevel_console: Optional[int] = logging.DEBUG, 
                loglevel_file: Optional[int] = logging.DEBUG, 
                logfile: Optional[str] = None, 
                console: bool = True) -> None:
    """Setup ADARE application logging with console and file handlers.
    
    Configures the root logger with appropriate handlers based on the
    provided parameters. Console output uses visual indicators while
    file output maintains detailed formatting.
    
    Args:
        loglevel_console: Console logging level (defaults to DEBUG)
        loglevel_file: File logging level (defaults to DEBUG) 
        logfile: Path to log file (None disables file logging)
        console: Whether to enable console logging (defaults to True)
    """
    # Normalize log levels
    console_level = loglevel_console or logging.INFO
    file_level = loglevel_file or logging.DEBUG
    
    root_logger = logging.getLogger()
    
    # Setup console logging if requested
    if console:
        _setup_console_handler(root_logger, console_level)
    
    # Setup file logging if logfile provided
    if logfile:
        _setup_file_handler(root_logger, file_level, logfile)


def _setup_console_handler(logger: logging.Logger, level: int) -> None:
    """Setup console logging handler.
    
    Args:
        logger: Logger to add handler to
        level: Logging level for console output
    """
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(ConsoleHandlerFormatter())
    console_handler.setLevel(level)
    logger.addHandler(console_handler)


def _setup_file_handler(logger: logging.Logger, level: int, logfile: str) -> None:
    """Setup file logging handler with validation.
    
    Args:
        logger: Logger to add handler to
        level: Logging level for file output
        logfile: Path to log file
    """
    logfile_path = Path(logfile)
    
    # Validate log directory exists
    if not logfile_path.parent.is_dir():
        print(f"Warning: Cannot initialize file logging - directory {logfile_path.parent} does not exist")
        return
    
    try:
        file_handler = logging.FileHandler(logfile, encoding='utf-8')
        file_handler.setFormatter(FileHandlerFormatter())
        file_handler.setLevel(level)
        logger.addHandler(file_handler)
        logger.setLevel(level)
    except (OSError, PermissionError) as e:
        print(f"Warning: Cannot initialize file logging - {e}")


def update_console_level(level: int) -> None:
    """Update console logging level for all console handlers.
    
    Args:
        level: New logging level for console handlers
    """
    root_logger = logging.getLogger()
    
    for handler in root_logger.handlers:
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
            handler.setLevel(level)