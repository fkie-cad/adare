"""
Playbook Analysis Utilities

This module provides utilities for analyzing playbooks to extract information
about file references, dependencies, and other metadata.
"""

import logging
from typing import List, Set
from adare.types.playbook import Playbook, ActionType, PullAction, BlockAction

log = logging.getLogger(__name__)


def collect_pull_action_files(playbook: Playbook) -> List[str]:
    """
    Extract all file paths from pull actions in a playbook.

    This function recursively walks through all actions in the playbook,
    including nested actions within BlockActions, to find all PullAction
    instances and collect their source file paths.

    Args:
        playbook: Playbook instance to analyze

    Returns:
        List of unique file paths (src fields) from all pull actions
    """
    log.debug("Collecting pull action files from playbook")

    file_paths = set()

    if playbook.actions:
        file_paths.update(_extract_files_from_actions(playbook.actions))

    unique_files = list(file_paths)
    log.debug(f"Found {len(unique_files)} unique files in pull actions: {unique_files}")

    return unique_files


def _extract_files_from_actions(actions: List[ActionType]) -> Set[str]:
    """
    Recursively extract file paths from a list of actions.

    This function handles both direct PullActions and nested actions
    within BlockActions.

    Args:
        actions: List of action objects to analyze

    Returns:
        Set of file paths found in pull actions
    """
    file_paths = set()

    for action in actions:
        if isinstance(action, PullAction):
            if action.src:
                # src can be either a string or a list of strings
                if isinstance(action.src, list):
                    file_paths.update(action.src)
                    log.debug(f"Found pull action files: {action.src}")
                else:
                    file_paths.add(action.src)
                    log.debug(f"Found pull action file: {action.src}")
        elif isinstance(action, BlockAction):
            if action.actions:
                file_paths.update(_extract_files_from_actions(action.actions))

    return file_paths