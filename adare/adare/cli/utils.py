"""Shared CLI utilities to eliminate duplication across CLI modules."""

import logging
import sys

from adare.backend.basics import determine_projectdirectory
from adare.cli.errors import report_error
from adare.exceptions import NoProjectFoundError

log = logging.getLogger(__name__)


def handle_api_error(result) -> None:
    """Report an API error result once on stderr and exit.

    Exit code follows ``adare.cli.errors``: 3 for not-found codes, 2 for usage
    errors, 1 otherwise; json mode prints an ``{"error": {...}}`` document.
    """
    error = result.error
    sys.exit(report_error(error.code, error.message, error.solutions))


def get_project_path(arguments):
    """Get project path from arguments or current directory."""
    project = getattr(arguments, 'project', None)
    project_directory = determine_projectdirectory(project)
    if not project_directory:
        raise NoProjectFoundError(log, specified_project=project)
    return project_directory
