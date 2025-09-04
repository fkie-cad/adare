"""CLI commands for interactive experiment development."""

import logging
from pathlib import Path

from adare.backend.basics import determine_projectdirectory
from adare.exceptions import NoProjectFoundError

log = logging.getLogger(__name__)


def exec_experiment_dev(arguments):
    """Execute interactive development mode."""
    raise NotImplementedError(
        "Interactive development mode is not currently implemented. "
        "Use 'adare experiment develop' for testing experiments instead."
    )