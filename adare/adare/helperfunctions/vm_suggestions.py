"""
VM detection and suggestion utilities.

This module provides functions for finding similar VMs, suggesting alternatives,
and providing context-aware VM recommendations.
"""

import difflib

# configure logging
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class VMSuggestion:
    """Represents a VM suggestion with metadata."""
    name: str
    score: float
    scope: str
    os_type: str | None = None
    architecture: str | None = None
    description: str | None = None
    reason: str | None = None


def suggest_similar_vm_names(
    target_name: str,
    available_names: list[str],
    max_suggestions: int = 3,
    cutoff: float = 0.4
) -> list[VMSuggestion]:
    """
    Find VM names similar to the target using fuzzy matching.

    Args:
        target_name: The VM name that wasn't found
        available_names: List of available VM names
        max_suggestions: Maximum number of suggestions to return
        cutoff: Minimum similarity score (0.0 to 1.0)

    Returns:
        List of VMSuggestion objects sorted by similarity score
    """
    if not available_names:
        return []

    # Use difflib for fuzzy matching
    matches = difflib.get_close_matches(
        target_name,
        available_names,
        n=max_suggestions,
        cutoff=cutoff
    )

    suggestions = []
    for match in matches:
        # Calculate similarity score
        similarity = difflib.SequenceMatcher(None, target_name.lower(), match.lower()).ratio()
        suggestions.append(VMSuggestion(
            name=match,
            score=similarity,
            scope='unknown',  # Will be filled by caller with actual VM data
            reason=f"Similar to '{target_name}' (similarity: {similarity:.2f})"
        ))

    return suggestions


def suggest_vms_by_os_requirements(
    available_vms: list[dict[str, Any]],
    required_os: str | None = None,
    required_platform: str | None = None,
    max_suggestions: int = 5
) -> list[VMSuggestion]:
    """
    Suggest VMs based on OS requirements.

    Args:
        available_vms: List of VM dictionaries with metadata
        required_os: Required OS type (e.g., 'Windows 10', 'Ubuntu')
        required_platform: Required platform (e.g., 'windows', 'linux')
        max_suggestions: Maximum number of suggestions

    Returns:
        List of VMSuggestion objects ranked by compatibility
    """
    if not available_vms:
        return []

    suggestions = []
    for vm in available_vms:
        score = 0.0
        reasons = []

        vm_os = vm.get('os_type', '').lower()
        vm_platform = vm.get('architecture', '').lower()

        # Exact OS match
        if required_os and vm_os == required_os.lower():
            score += 1.0
            reasons.append(f"Exact OS match: {vm_os}")
        # Partial OS match
        elif required_os and required_os.lower() in vm_os:
            score += 0.7
            reasons.append(f"Partial OS match: {vm_os}")

        # Platform match
        if required_platform and vm_platform == required_platform.lower():
            score += 0.5
            reasons.append(f"Platform match: {vm_platform}")

        # Basic compatibility if any match
        if score > 0:
            suggestions.append(VMSuggestion(
                name=vm.get('name', 'Unknown'),
                score=score,
                scope=vm.get('scope', 'unknown'),
                os_type=vm.get('os_type'),
                architecture=vm.get('architecture'),
                description=vm.get('description'),
                reason='; '.join(reasons) if reasons else 'Available VM'
            ))

    # Sort by score (descending) and limit results
    suggestions.sort(key=lambda x: x.score, reverse=True)
    return suggestions[:max_suggestions]


def generate_vm_not_found_message(
    vm_name: str,
    suggestions: list[VMSuggestion],
    project_context: str | None = None
) -> tuple[str, list[str]]:
    """
    Generate enhanced error message with VM suggestions.

    Args:
        vm_name: The VM name that wasn't found
        suggestions: List of VM suggestions
        project_context: Optional project context for scoped suggestions

    Returns:
        Tuple of (error_message, list_of_solutions)
    """
    context = f" in project '{project_context}'" if project_context else ""

    if not suggestions:
        message = f"VM '{vm_name}' not found{context}. No similar VMs available."
        solutions = [
            "Check VM name spelling and try again",
            "Run 'adare vm list' to see all available VMs",
            "Load a new VM with 'adare vm load <file.ova>'",
            "Initialize VM storage with 'adare vm init' if not done yet"
        ]
    else:
        similar_vms = [f"'{s.name}' ({s.scope})" for s in suggestions[:3]]
        message = f"VM '{vm_name}' not found{context}. Similar VMs available: {', '.join(similar_vms)}"

        solutions = [
            f"Try one of these similar VMs: {', '.join([s.name for s in suggestions[:3]])}",
            "Check VM name spelling and try again",
            "Run 'adare vm list' to see all available VMs"
        ]

        # Add project-specific solutions
        if project_context:
            solutions.extend([
                f"Load a VM for this project with 'adare vm load <file.ova> --project {project_context}'",
                "Use a global VM with 'adare vm list --scope global'"
            ])
        else:
            solutions.append("Load a new VM with 'adare vm load <file.ova>'")

    return message, solutions


def suggest_vms_for_environment(
    environment_metadata: dict[str, Any],
    available_vms: list[dict[str, Any]],
    project_id: str | None = None
) -> list[VMSuggestion]:
    """
    Suggest VMs specifically for environment requirements.

    Args:
        environment_metadata: Environment configuration metadata
        available_vms: Available VMs to choose from
        project_id: Optional project context

    Returns:
        List of VMSuggestion objects tailored for the environment
    """
    # Extract OS requirements from environment
    os_info = environment_metadata.get('os', {})
    required_os = os_info.get('os')
    required_platform = os_info.get('platform')

    # Get suggestions based on OS requirements
    suggestions = suggest_vms_by_os_requirements(
        available_vms=available_vms,
        required_os=required_os,
        required_platform=required_platform
    )

    # Boost score for project-scoped VMs when in project context
    if project_id:
        for suggestion in suggestions:
            if suggestion.scope == 'project':
                suggestion.score += 0.2
                if suggestion.reason:
                    suggestion.reason += "; Project VM (preferred)"
                else:
                    suggestion.reason = "Project VM (preferred)"

    return suggestions


def check_vm_files_in_directory(directory: Path, extensions: list[str] = None) -> list[Path]:
    """
    Scan directory for potential VM files.

    Args:
        directory: Directory to scan
        extensions: File extensions to look for (default: ['.ova'])

    Returns:
        List of potential VM file paths
    """
    if extensions is None:
        extensions = ['.ova']

    vm_files = []
    if not directory.exists():
        return vm_files

    try:
        for ext in extensions:
            vm_files.extend(directory.glob(f"**/*{ext}"))

        log.debug(f"Found {len(vm_files)} potential VM files in {directory}")
        return vm_files

    except Exception as e:
        log.debug(f"Error scanning directory {directory} for VM files: {e}")
        return []


def format_vm_suggestions_for_cli(suggestions: list[VMSuggestion]) -> str:
    """
    Format VM suggestions for CLI output.

    Args:
        suggestions: List of VM suggestions

    Returns:
        Formatted string for display
    """
    if not suggestions:
        return "No VM suggestions available."

    lines = ["Available VMs:"]
    for i, suggestion in enumerate(suggestions[:5], 1):
        scope_info = f" ({suggestion.scope})" if suggestion.scope != 'unknown' else ""
        os_info = f" - {suggestion.os_type}" if suggestion.os_type else ""
        lines.append(f"  {i}. {suggestion.name}{scope_info}{os_info}")
        if suggestion.reason:
            lines.append(f"     → {suggestion.reason}")

    return '\n'.join(lines)
