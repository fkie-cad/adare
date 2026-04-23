"""
Utility functions for extracting fields from database models.

This module provides reusable utilities to extract specific fields from
database objects, reducing code duplication across the codebase.
"""
import logging
from typing import Any

log = logging.getLogger(__name__)


def extract_fields(obj: Any, fields: list[str] | None = None,
                  field_map: dict[str, str] | None = None) -> dict[str, Any]:
    """
    Extract specified fields from a database object.

    Args:
        obj: Database model instance
        fields: List of field names to extract. If None, returns full object.
        field_map: Optional mapping of field names to attribute names.
                  If not provided, field names are used directly as attribute names.

    Returns:
        Dictionary with extracted field values if fields is specified,
        otherwise returns the original object.

    Example:
        vm_data = extract_fields(vm, ['id', 'name', 'hash'])
        # Returns: {'id': '...', 'name': 'Ubuntu20', 'hash': 'abc123...'}

        # With field map
        vm_data = extract_fields(vm, ['id', 'name'], VM_FIELD_MAP)
    """
    # If no fields specified, return full object
    if fields is None:
        return obj

    # Default field mappings if not provided
    if field_map is None:
        field_map = {}

    result = {}
    for field in fields:
        # Use custom mapping if available, otherwise use field name directly
        attr_name = field_map.get(field, field)

        try:
            if hasattr(obj, attr_name):
                result[field] = getattr(obj, attr_name)
            else:
                log.warning(f"Object {type(obj).__name__} has no attribute '{attr_name}'")
                result[field] = None
        except AttributeError as e:
            log.warning(f"Error accessing field '{field}' on {type(obj).__name__}: {e}")
            result[field] = None

    return result


# Predefined field maps for common models
VM_FIELD_MAP = {
    'id': 'id',
    'name': 'name',
    'file': 'file',
    'hash': 'hash',
    'description': 'description',
    'osinfo': 'osinfo',
    'hypervisor': 'hypervisor',
    'use_snapshots': 'use_snapshots',
    'osinfo_id': 'osinfo_id',
}

EXPERIMENT_FIELD_MAP = {
    'id': 'id',
    'name': 'name',
    'description': 'description',
    'sha256': 'sha256',
    'sha256_playbook': 'sha256_playbook',
    'sha256_metadata': 'sha256_metadata',
    'ulid': 'id',  # Alias for id
    'environment_ids': 'environment_ids',
    'created_at': 'created_at',
}

ENVIRONMENT_FIELD_MAP = {
    'id': 'id',
    'name': 'name',
    'description': 'description',
    'vm_id': 'vm_id',
    'file': 'file',
    'sha256hash': 'sha256hash',
    'hypervisor': 'hypervisor',
    'created_at': 'created_at',
}

EXPERIMENT_RUN_FIELD_MAP = {
    'id': 'id',
    'experiment_id': 'experiment_id',
    'environment_id': 'environment_id',
    'vm_instance_id': 'vm_instance_id',
    'path': 'path',
    'start_time': 'start_time',
    'end_time': 'end_time',
    'status': 'status',
    'created_at': 'created_at',
}
