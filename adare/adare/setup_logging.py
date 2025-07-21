"""Logging setup and configuration for ADARE.

This module provides a clean interface for setting up application-wide logging
based on command line arguments and configuration.
"""

import logging
from typing import List, Optional, Any

import adare.config as config
from adare.logger import logger
from adare.logger.logger import ConsoleHandlerFormatter


def setup_logging(arguments: Any, commandline: List[str]) -> None:
    """Configure logging for the ADARE application.
    
    Sets up both console and file logging based on command line arguments.
    Console logging level is determined by verbosity flags, while file logging
    level is set via the --log-level argument.
    
    Args:
        arguments: Parsed command line arguments containing:
            - verbose: Enable INFO level console logging
            - very_verbose: Enable DEBUG level console logging  
            - log_level: File logging level (debug/info/warning/error/critical)
            - logfile: Optional path to log file
        commandline: List of command line arguments for logging
    """
    console_level = _determine_console_log_level(arguments)
    file_level = _determine_file_log_level(arguments)
    
    # Setup primary logging through our custom logger
    _setup_application_logger(console_level, file_level, arguments.logfile)
    
    # Configure root logger to ensure consistent formatting across all modules
    _configure_root_logger(console_level)
    
    # Log the command that initiated this session
    logging.info(f'COMMAND: {" ".join(commandline)}')


def _determine_console_log_level(arguments: Any) -> int:
    """Determine console logging level from verbosity flags.
    
    Args:
        arguments: Command line arguments
        
    Returns:
        Logging level constant (DEBUG, INFO, WARNING)
    """
    if arguments.very_verbose:
        return logging.DEBUG
    elif arguments.verbose:
        return logging.INFO
    else:
        return logging.WARNING


def _determine_file_log_level(arguments: Any) -> Optional[int]:
    """Determine file logging level from --log-level argument.
    
    Args:
        arguments: Command line arguments
        
    Returns:
        Logging level constant or None if not specified
    """
    if not arguments.log_level:
        return None
        
    log_level = arguments.log_level.strip().lower()
    
    level_mapping = {
        **{level: logging.DEBUG for level in config.ABBREV_DEBUG},
        **{level: logging.INFO for level in config.ABBREV_INFO},
        **{level: logging.WARNING for level in config.ABBREV_WARNING},
        **{level: logging.ERROR for level in config.ABBREV_ERROR},
        **{level: logging.CRITICAL for level in config.ABBREV_CRITICAL},
    }
    
    return level_mapping.get(log_level)


def _setup_application_logger(console_level: int, file_level: Optional[int], 
                             logfile: Optional[str]) -> None:
    """Setup the main application logger using our custom implementation.
    
    Args:
        console_level: Console logging level
        file_level: File logging level (None if no file logging)
        logfile: Path to log file (None if no file logging)
    """
    logger.setup_logger(
        loglevel_console=console_level,
        loglevel_file=file_level,
        logfile=logfile,
        console=True
    )


def _configure_root_logger(console_level: int) -> None:
    """Configure the root logger to ensure consistent formatting.
    
    This ensures that all modules using logging.getLogger() get consistent
    formatting and proper level filtering.
    
    Args:
        console_level: Console logging level to apply
    """
    root_logger = logging.getLogger()
    
    # Clear any existing handlers
    _clear_existing_handlers(root_logger)
    
    # Set level and add our console handler
    root_logger.setLevel(console_level)
    
    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_handler.setFormatter(ConsoleHandlerFormatter())
    root_logger.addHandler(console_handler)


def _clear_existing_handlers(logger_instance: logging.Logger) -> None:
    """Remove all existing handlers from a logger.
    
    Args:
        logger_instance: Logger to clear handlers from
    """
    while logger_instance.handlers:
        logger_instance.handlers.pop()
