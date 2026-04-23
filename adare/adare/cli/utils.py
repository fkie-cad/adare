"""Shared CLI utilities to eliminate duplication across CLI modules."""

import logging

from adare.backend.basics import determine_projectdirectory
from adare.console import print_error_message
from adare.exceptions import NoProjectFoundError

log = logging.getLogger(__name__)


def handle_api_error(result) -> None:
    """Handle an API error result by printing formatted error message and exiting."""
    error = result.error
    print_error_message(
        title=f'{error.code}: {error.message}',
        next_steps=error.solutions
    )
    exit(1)


def get_project_path(arguments):
    """Get project path from arguments or current directory."""
    project = getattr(arguments, 'project', None)
    project_directory = determine_projectdirectory(project)
    if not project_directory:
        raise NoProjectFoundError(log, specified_project=project)
    return project_directory
