"""
Resource Resolution System.

This module provides functionality to resolve references to global resources
(VMs and environments) from project databases to actual resource data from
global registries. This bridges the gap between the project-specific database
and the global shared resources.
"""

import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
import json

from adare.database.api.global_registry.vm_registry import VmRegistryApi
from adare.database.api.global_registry.environment_registry import EnvironmentRegistryApi
from adare.database.api.project_database import ProjectDatabaseApi
from adare.database.models.global_registry import GlobalVm, GlobalEnvironment
from adare.database.models.project_database import GlobalResourceReference, ExperimentEnvironmentReference
from adare.database.exceptions import EntityNotFoundError, ValidationError

log = logging.getLogger(__name__)


class ResourceResolver:
    """
    Resolves global resource references to actual resource data.

    This class provides methods to resolve VM and environment references
    from project databases to the actual resources stored in global registries.
    It handles caching, error handling, and provides unified access to resources.
    """

    def __init__(self, project_path: Path):
        """
        Initialize resource resolver for a specific project.

        Args:
            project_path: Absolute path to project directory
        """
        self.project_path = Path(project_path)
        self.project_db = ProjectDatabaseApi(project_path)
        self.vm_registry = VmRegistryApi()
        self.environment_registry = EnvironmentRegistryApi()

        # Cache for resolved resources (reduces registry lookups)
        self._vm_cache = {}
        self._environment_cache = {}
        self._cache_timestamp = datetime.utcnow()
        self._cache_ttl_seconds = 300  # 5 minutes

    def _is_cache_valid(self) -> bool:
        """Check if cache is still valid based on TTL."""
        elapsed = (datetime.utcnow() - self._cache_timestamp).total_seconds()
        return elapsed < self._cache_ttl_seconds

    def _clear_cache(self):
        """Clear resource cache."""
        self._vm_cache.clear()
        self._environment_cache.clear()
        self._cache_timestamp = datetime.utcnow()

    def resolve_vm_reference(self, vm_reference: Union[str, GlobalResourceReference],
                            include_usage_info: bool = False) -> Optional[Dict[str, Any]]:
        """
        Resolve a VM reference to actual VM data.

        Args:
            vm_reference: Either VM ID string or GlobalResourceReference instance
            include_usage_info: If True, include project usage information

        Returns:
            Dict with resolved VM data and metadata, or None if not found

        Raises:
            ValidationError: If reference is invalid
        """
        try:
            # Extract VM ID and reference metadata
            if isinstance(vm_reference, str):
                vm_id = vm_reference
                reference_data = None
            elif isinstance(vm_reference, GlobalResourceReference):
                if vm_reference.resource_type != 'vm':
                    raise ValidationError(f"Expected VM reference, got {vm_reference.resource_type}")
                vm_id = vm_reference.global_resource_id
                reference_data = vm_reference
            else:
                raise ValidationError(f"Invalid VM reference type: {type(vm_reference)}")

            # Check cache first
            if self._is_cache_valid() and vm_id in self._vm_cache:
                log.debug(f"Using cached VM data for {vm_id}")
                cached_result = self._vm_cache[vm_id].copy()
                if reference_data:
                    cached_result['project_reference'] = self._serialize_reference(reference_data)
                return cached_result

            # Resolve from global registry
            with self.vm_registry:
                vm = self.vm_registry.get_vm_by_id(vm_id)
                if not vm:
                    log.warning(f"VM {vm_id} not found in global registry")
                    return None

                # Build resolved data
                resolved_data = {
                    'id': vm.id,
                    'name': vm.name,
                    'description': vm.description,
                    'file_path': str(vm.full_file_path),
                    'hash': vm.hash,
                    'os_info': {
                        'platform': vm.os_platform,
                        'type': vm.os_type,
                        'distribution': vm.os_distribution,
                        'version': vm.os_version,
                        'language': vm.os_language,
                        'architecture': vm.os_architecture,
                        'display_name': vm.os_display_name
                    },
                    'technical_details': {
                        'vbox_uuid': vm.vbox_uuid,
                        'base_snapshot_name': vm.base_snapshot_name,
                        'import_status': vm.import_status,
                        'use_snapshots': vm.use_snapshots,
                        'last_verified': vm.last_verified.isoformat() if vm.last_verified else None
                    },
                    'metadata': {
                        'created_at': vm.created_at.isoformat(),
                        'updated_at': vm.updated_at.isoformat() if vm.updated_at else None,
                        'created_by': vm.created_by,
                        'file_size_bytes': vm.file_size_bytes,
                        'usage_count': vm.usage_count,
                        'last_used': vm.last_used.isoformat() if vm.last_used else None
                    }
                }

                # Add project-specific reference data
                if reference_data:
                    resolved_data['project_reference'] = self._serialize_reference(reference_data)

                # Add usage information if requested
                if include_usage_info:
                    usage_records = self.vm_registry.get_vm_usage(vm_id)
                    resolved_data['usage_info'] = [
                        {
                            'project_path': usage.project_path,
                            'project_name': usage.project_name,
                            'alias_name': usage.alias_name,
                            'usage_count': usage.usage_count,
                            'first_used': usage.first_used.isoformat(),
                            'last_used': usage.last_used.isoformat()
                        }
                        for usage in usage_records
                    ]

                # Cache the result
                self._vm_cache[vm_id] = resolved_data.copy()

                log.debug(f"Resolved VM {vm_id}: {vm.name}")
                return resolved_data

        except Exception as e:
            log.error(f"Failed to resolve VM reference {vm_reference}: {e}")
            raise

    def resolve_environment_reference(self, env_reference: Union[str, GlobalResourceReference, ExperimentEnvironmentReference],
                                     include_vm_info: bool = True,
                                     include_usage_info: bool = False) -> Optional[Dict[str, Any]]:
        """
        Resolve an environment reference to actual environment data.

        Args:
            env_reference: Environment ID string, GlobalResourceReference, or ExperimentEnvironmentReference
            include_vm_info: If True, include resolved VM information
            include_usage_info: If True, include project usage information

        Returns:
            Dict with resolved environment data and metadata, or None if not found

        Raises:
            ValidationError: If reference is invalid
        """
        try:
            # Extract environment ID and reference metadata
            env_id = None
            reference_data = None

            if isinstance(env_reference, str):
                env_id = env_reference
            elif isinstance(env_reference, GlobalResourceReference):
                if env_reference.resource_type != 'environment':
                    raise ValidationError(f"Expected environment reference, got {env_reference.resource_type}")
                env_id = env_reference.global_resource_id
                reference_data = env_reference
            elif isinstance(env_reference, ExperimentEnvironmentReference):
                env_id = env_reference.global_environment_id
                reference_data = env_reference
            else:
                raise ValidationError(f"Invalid environment reference type: {type(env_reference)}")

            # Check cache first
            cache_key = f"{env_id}_{include_vm_info}_{include_usage_info}"
            if self._is_cache_valid() and cache_key in self._environment_cache:
                log.debug(f"Using cached environment data for {env_id}")
                cached_result = self._environment_cache[cache_key].copy()
                if reference_data:
                    cached_result['project_reference'] = self._serialize_reference(reference_data)
                return cached_result

            # Resolve from global registry
            with self.environment_registry:
                environment = self.environment_registry.get_environment_by_id(env_id)
                if not environment:
                    log.warning(f"Environment {env_id} not found in global registry")
                    return None

                # Build resolved data
                resolved_data = {
                    'id': environment.id,
                    'name': environment.name,
                    'description': environment.description,
                    'file_path': str(environment.full_file_path),
                    'sha256hash': environment.sha256hash,
                    'version': environment.version,
                    'vm_id': environment.vm_id,
                    'configuration': {
                        'installations': json.loads(environment.installations or '[]'),
                        'tags': environment.tag_list
                    },
                    'metadata': {
                        'created_at': environment.created_at.isoformat(),
                        'updated_at': environment.updated_at.isoformat() if environment.updated_at else None,
                        'created_by': environment.created_by,
                        'file_size_bytes': environment.file_size_bytes,
                        'usage_count': environment.usage_count,
                        'last_used': environment.last_used.isoformat() if environment.last_used else None
                    },
                    'versioning': {
                        'version': environment.version,
                        'parent_environment_id': environment.parent_environment_id
                    }
                }

                # Add project-specific reference data
                if reference_data:
                    resolved_data['project_reference'] = self._serialize_reference(reference_data)

                # Include VM information if requested
                if include_vm_info and environment.vm_id:
                    vm_data = self.resolve_vm_reference(environment.vm_id)
                    if vm_data:
                        resolved_data['vm_info'] = vm_data

                # Add usage information if requested
                if include_usage_info:
                    usage_records = self.environment_registry.get_environment_usage(env_id)
                    resolved_data['usage_info'] = [
                        {
                            'project_path': usage.project_path,
                            'project_name': usage.project_name,
                            'alias_name': usage.alias_name,
                            'usage_count': usage.usage_count,
                            'first_used': usage.first_used.isoformat(),
                            'last_used': usage.last_used.isoformat()
                        }
                        for usage in usage_records
                    ]

                # Cache the result
                self._environment_cache[cache_key] = resolved_data.copy()

                log.debug(f"Resolved environment {env_id}: {environment.name}")
                return resolved_data

        except Exception as e:
            log.error(f"Failed to resolve environment reference {env_reference}: {e}")
            raise

    def _serialize_reference(self, reference: Union[GlobalResourceReference, ExperimentEnvironmentReference]) -> Dict[str, Any]:
        """Serialize reference data for inclusion in resolved results."""
        if isinstance(reference, GlobalResourceReference):
            return {
                'type': 'global_resource_reference',
                'project_alias': reference.project_alias,
                'usage_notes': reference.usage_notes,
                'configuration_overrides': json.loads(reference.configuration_overrides or '{}'),
                'is_active': reference.is_active,
                'pinned_version': reference.pinned_version,
                'first_used': reference.first_used.isoformat(),
                'last_used': reference.last_used.isoformat(),
                'usage_count': reference.usage_count
            }
        elif isinstance(reference, ExperimentEnvironmentReference):
            return {
                'type': 'experiment_environment_reference',
                'experiment_id': reference.experiment_id,
                'environment_alias': reference.environment_alias,
                'configuration_overrides': json.loads(reference.configuration_overrides or '{}'),
                'execution_order': reference.execution_order,
                'is_primary': reference.is_primary,
                'last_used': reference.last_used.isoformat() if reference.last_used else None
            }
        else:
            return {}

    def resolve_experiment_environments(self, experiment_name: str) -> List[Dict[str, Any]]:
        """
        Resolve all environment references for a specific experiment.

        Args:
            experiment_name: Name of experiment

        Returns:
            List of resolved environment data for the experiment

        Raises:
            EntityNotFoundError: If experiment not found
        """
        try:
            with self.project_db:
                experiment = self.project_db.get_experiment_by_name(experiment_name)
                if not experiment:
                    raise EntityNotFoundError(f"Experiment '{experiment_name}' not found")

                resolved_environments = []

                for env_ref in experiment.environment_refs:
                    resolved_env = self.resolve_environment_reference(
                        env_ref,
                        include_vm_info=True,
                        include_usage_info=False
                    )

                    if resolved_env:
                        resolved_environments.append(resolved_env)
                    else:
                        log.warning(f"Failed to resolve environment {env_ref.global_environment_id} for experiment {experiment_name}")

                # Sort by execution order if specified
                resolved_environments.sort(key=lambda x: x.get('project_reference', {}).get('execution_order', 999))

                log.info(f"Resolved {len(resolved_environments)} environments for experiment {experiment_name}")
                return resolved_environments

        except Exception as e:
            log.error(f"Failed to resolve environments for experiment {experiment_name}: {e}")
            raise

    def get_project_resource_summary(self) -> Dict[str, Any]:
        """
        Get a summary of all resources used by this project.

        Returns:
            Dict with resource summary information
        """
        try:
            with self.project_db:
                # Get all resource references
                vm_refs = self.project_db.get_global_resource_references('vm')
                env_refs = self.project_db.get_global_resource_references('environment')

                summary = {
                    'project_path': str(self.project_path),
                    'vm_resources': {
                        'count': len(vm_refs),
                        'vms': []
                    },
                    'environment_resources': {
                        'count': len(env_refs),
                        'environments': []
                    },
                    'resolution_errors': []
                }

                # Resolve VM references
                for vm_ref in vm_refs:
                    try:
                        resolved_vm = self.resolve_vm_reference(vm_ref, include_usage_info=False)
                        if resolved_vm:
                            summary['vm_resources']['vms'].append({
                                'id': resolved_vm['id'],
                                'name': resolved_vm['name'],
                                'alias': vm_ref.project_alias or resolved_vm['name'],
                                'os_display_name': resolved_vm['os_info']['display_name'],
                                'usage_count': resolved_vm['metadata']['usage_count'],
                                'file_size_gb': round((resolved_vm['metadata']['file_size_bytes'] or 0) / (1024**3), 2)
                            })
                        else:
                            summary['resolution_errors'].append(f"VM {vm_ref.global_resource_id} not found")
                    except Exception as e:
                        summary['resolution_errors'].append(f"VM {vm_ref.global_resource_id}: {e}")

                # Resolve environment references
                for env_ref in env_refs:
                    try:
                        resolved_env = self.resolve_environment_reference(env_ref, include_vm_info=False, include_usage_info=False)
                        if resolved_env:
                            summary['environment_resources']['environments'].append({
                                'id': resolved_env['id'],
                                'name': resolved_env['name'],
                                'alias': env_ref.project_alias or resolved_env['name'],
                                'version': resolved_env['version'],
                                'vm_id': resolved_env['vm_id'],
                                'usage_count': resolved_env['metadata']['usage_count'],
                                'file_size_mb': round((resolved_env['metadata']['file_size_bytes'] or 0) / (1024**2), 2)
                            })
                        else:
                            summary['resolution_errors'].append(f"Environment {env_ref.global_resource_id} not found")
                    except Exception as e:
                        summary['resolution_errors'].append(f"Environment {env_ref.global_resource_id}: {e}")

                return summary

        except Exception as e:
            log.error(f"Failed to get project resource summary: {e}")
            raise

    def validate_project_references(self) -> Dict[str, Any]:
        """
        Validate that all project resource references are resolvable.

        Returns:
            Dict with validation results
        """
        validation_results = {
            'valid_vm_references': 0,
            'invalid_vm_references': 0,
            'valid_environment_references': 0,
            'invalid_environment_references': 0,
            'errors': [],
            'missing_resources': []
        }

        try:
            with self.project_db:
                # Validate VM references
                vm_refs = self.project_db.get_global_resource_references('vm')
                for vm_ref in vm_refs:
                    try:
                        resolved_vm = self.resolve_vm_reference(vm_ref.global_resource_id)
                        if resolved_vm:
                            validation_results['valid_vm_references'] += 1
                        else:
                            validation_results['invalid_vm_references'] += 1
                            validation_results['missing_resources'].append(f"VM {vm_ref.global_resource_id}")
                    except Exception as e:
                        validation_results['invalid_vm_references'] += 1
                        validation_results['errors'].append(f"VM {vm_ref.global_resource_id}: {e}")

                # Validate environment references
                env_refs = self.project_db.get_global_resource_references('environment')
                for env_ref in env_refs:
                    try:
                        resolved_env = self.resolve_environment_reference(env_ref.global_resource_id)
                        if resolved_env:
                            validation_results['valid_environment_references'] += 1
                        else:
                            validation_results['invalid_environment_references'] += 1
                            validation_results['missing_resources'].append(f"Environment {env_ref.global_resource_id}")
                    except Exception as e:
                        validation_results['invalid_environment_references'] += 1
                        validation_results['errors'].append(f"Environment {env_ref.global_resource_id}: {e}")

        except Exception as e:
            validation_results['errors'].append(f"Validation error: {e}")

        return validation_results

    def refresh_cache(self):
        """Force refresh of resource cache."""
        self._clear_cache()
        log.info("Resource cache refreshed")


# Convenience functions for common operations

def resolve_vm_for_project(project_path: Path, vm_id: str) -> Optional[Dict[str, Any]]:
    """
    Convenience function to resolve a VM for a specific project.

    Args:
        project_path: Path to project
        vm_id: VM ID to resolve

    Returns:
        Resolved VM data or None if not found
    """
    resolver = ResourceResolver(project_path)
    return resolver.resolve_vm_reference(vm_id)


def resolve_environment_for_project(project_path: Path, env_id: str) -> Optional[Dict[str, Any]]:
    """
    Convenience function to resolve an environment for a specific project.

    Args:
        project_path: Path to project
        env_id: Environment ID to resolve

    Returns:
        Resolved environment data or None if not found
    """
    resolver = ResourceResolver(project_path)
    return resolver.resolve_environment_reference(env_id)


def get_project_resources(project_path: Path) -> Dict[str, Any]:
    """
    Convenience function to get all resources for a project.

    Args:
        project_path: Path to project

    Returns:
        Project resource summary
    """
    resolver = ResourceResolver(project_path)
    return resolver.get_project_resource_summary()