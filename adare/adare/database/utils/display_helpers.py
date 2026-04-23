"""
Shared utility functions for data display logic.

These functions help reduce code duplication across database API classes.
"""
# configure logging
import logging
from functools import lru_cache

log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_current_project_name() -> str | None:
    """
    Get current project name with caching to avoid repeated filesystem access.

    Returns:
        Project name if found, None otherwise
    """
    try:
        from adare.backend.basics import determine_projectdirectory
        project_path = determine_projectdirectory(None, silent=True)
        return project_path.name if project_path else None
    except Exception as e:
        log.debug(f"Could not determine current project: {e}")
        return None


def get_smart_display_name(obj, obj_type: str, current_project_name: str = None) -> str:
    """
    Get context-aware display name for objects (environments, experiments, testfunctions).

    Args:
        obj: The database object
        obj_type: Type of object ('environment', 'experiment', 'testfunction')
        current_project_name: Current project context (detected if None)

    Returns:
        str: Display name - either just the name part or full dotnotation
    """
    if current_project_name is None:
        current_project_name = get_current_project_name()

    # Get the full dotnotation (create it for experiments if needed)
    if obj_type == 'experiment':
        # For experiments, create dotnotation using current project context
        # (experiments are stored per-project, environments are global with no project relationship)
        full_dotnotation = f'{current_project_name}.{obj.name}' if current_project_name else obj.name
    else:
        full_dotnotation = obj.dotnotation

    if obj_type == 'environment':
        # Environments are global and don't have project relationships
        # Return just the environment name (simpler for global resources)
        return obj.name

    if obj_type == 'experiment':
        # For experiments in the current project context, return just the name
        # Otherwise return the full dotnotation
        if current_project_name:
            return obj.name  # Return just the experiment name
        return full_dotnotation  # Return full project.name format

    if obj_type == 'testfunction':
        # For testfunctions, check if from current project context
        if current_project_name and '.' in full_dotnotation:
            tf_project = full_dotnotation.split('.', 1)[0]
            if tf_project == current_project_name:
                return full_dotnotation.split('.', 1)[1] if '.' in full_dotnotation else obj.name
            return full_dotnotation
        return obj.name

    # Default fallback
    return obj.name


def safe_get_sync_status(obj) -> tuple[bool, bool]:
    """
    Safely get sync status from an object.

    Args:
        obj: Database object that may have sync_metadata

    Returns:
        Tuple of (published, in_request) booleans
    """
    try:
        if hasattr(obj, 'sync_metadata') and obj.sync_metadata:
            published = bool(obj.sync_metadata.is_synced)
            in_request = bool(obj.sync_metadata.needs_sync)
            return published, in_request
    except Exception as e:
        log.debug(f"Could not get sync status: {e}")

    return False, False


def safe_get_os_info(vm) -> tuple[str, str, str, str, str]:
    """
    Safely extract OS information from VM object.

    Args:
        vm: VM object that may have osinfo

    Returns:
        Tuple of (os_info_str, os, distribution, version, language)
    """
    if not vm:
        return "No VM", "", "", "", ""

    try:
        osinfo = vm.osinfo if hasattr(vm, 'osinfo') else None
        if osinfo:
            return (
                str(osinfo),
                osinfo.os or "",
                osinfo.distribution or "",
                osinfo.version or "",
                osinfo.language or ""
            )
    except Exception as e:
        log.debug(f"Could not get OS info: {e}")

    return "Unknown", "", "", "", ""


def safe_get_vm_info(env) -> tuple[str, str]:
    """
    Safely extract VM information from environment.

    Args:
        env: Environment object that may have VM

    Returns:
        Tuple of (vm_name, vm_id)
    """
    try:
        vm = env.vm if hasattr(env, 'vm') else None
        if vm:
            return vm.name, vm.id
    except Exception as e:
        log.debug(f"Could not get VM info: {e}")

    return "No VM", ""


def safe_get_tags(obj) -> list:
    """
    Safely extract tags from an object.

    Args:
        obj: Database object that may have tags

    Returns:
        List of tag names
    """
    try:
        if hasattr(obj, 'tags') and obj.tags:
            return [tag.name for tag in obj.tags]
    except Exception as e:
        log.debug(f"Could not get tags: {e}")

    return []
