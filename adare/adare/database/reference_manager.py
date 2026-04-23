"""
Reference management system for cross-database relationships.

This module handles validation and resolution of references between
project databases and global resources (VMs, environments, test functions).
"""

import logging
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from adare.database.api.base import GlobalDatabaseApi, ProjectDatabaseApi
from adare.database.exceptions import DatabaseError
from adare.database.models.global_models import Environment, Project, TestFunction, Vm
from adare.database.models.project_models import Experiment, ExperimentRun

log = logging.getLogger(__name__)


class GlobalResourceNotFoundError(DatabaseError):
    """Raised when a referenced global resource cannot be found."""
    pass


class InvalidReferenceError(DatabaseError):
    """Raised when a reference is invalid or malformed."""
    pass


class ReferenceManager:
    """
    Manages references between project databases and global resources.

    This class provides validation, resolution, and tracking of references
    from project-specific data to globally shared resources.

    Features:
    - LRU cache with TTL (time-to-live) for performance
    - Thread-safe cache operations
    - Automatic cache eviction when size limit exceeded
    """

    def __init__(self, cache_ttl_seconds: int = 300, max_cache_size: int = 1000):
        """
        Initialize reference manager with caching.

        Args:
            cache_ttl_seconds: Cache time-to-live in seconds (default: 300 = 5 minutes)
            max_cache_size: Maximum number of cached items (default: 1000)
        """
        self._global_api = None
        self._cache = {}
        self._cache_timestamps = {}
        self._cache_lock = threading.Lock()
        self._cache_ttl = timedelta(seconds=cache_ttl_seconds)
        self._max_cache_size = max_cache_size

    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cached value is still valid (not expired)."""
        if cache_key not in self._cache_timestamps:
            return False

        age = datetime.now(UTC) - self._cache_timestamps[cache_key]
        return age < self._cache_ttl

    def _cache_get(self, cache_key: str):
        """Get from cache if valid, else None."""
        with self._cache_lock:
            if cache_key in self._cache and self._is_cache_valid(cache_key):
                return self._cache[cache_key]
            # Remove expired entry
            if cache_key in self._cache:
                del self._cache[cache_key]
                del self._cache_timestamps[cache_key]
            return None

    def _cache_set(self, cache_key: str, value):
        """Set cache with timestamp and evict old entries if needed."""
        with self._cache_lock:
            self._cache[cache_key] = value
            self._cache_timestamps[cache_key] = datetime.now(UTC)

            # Evict oldest 20% of entries if cache too large
            if len(self._cache) > self._max_cache_size:
                num_to_evict = int(self._max_cache_size * 0.2)
                sorted_keys = sorted(
                    self._cache_timestamps.keys(),
                    key=lambda k: self._cache_timestamps[k]
                )
                for key in sorted_keys[:num_to_evict]:
                    del self._cache[key]
                    del self._cache_timestamps[key]
                log.debug(f"Evicted {num_to_evict} old cache entries")

    def invalidate_cache(self, pattern: str = None):
        """
        Invalidate cache entries.

        Args:
            pattern: Optional pattern to match. If None, clears all cache.
        """
        with self._cache_lock:
            if pattern is None:
                # Clear all
                self._cache.clear()
                self._cache_timestamps.clear()
                log.debug("Cleared all cache entries")
            else:
                # Clear matching pattern
                keys_to_remove = [k for k in self._cache.keys() if pattern in k]
                for key in keys_to_remove:
                    del self._cache[key]
                    del self._cache_timestamps[key]
                log.debug(f"Cleared {len(keys_to_remove)} cache entries matching '{pattern}'")

    def _get_global_api(self) -> GlobalDatabaseApi:
        """Get or create global database API connection."""
        if self._global_api is None:
            self._global_api = GlobalDatabaseApi()
        return self._global_api

    def validate_environment_exists(self, environment_id: str) -> bool:
        """
        Validate that a global environment exists.

        Args:
            environment_id: Global environment ID

        Returns:
            True if environment exists, False otherwise
        """
        try:
            with self._get_global_api() as api:
                environment = api.get_by_ulid(Environment, environment_id)
                return environment is not None
        except Exception as e:
            log.error(f"Error validating environment {environment_id}: {e}")
            return False

    def validate_vm_exists(self, vm_id: str) -> bool:
        """
        Validate that a global VM exists.

        Args:
            vm_id: Global VM ID

        Returns:
            True if VM exists, False otherwise
        """
        try:
            with self._get_global_api() as api:
                vm = api.get_by_ulid(Vm, vm_id)
                return vm is not None
        except Exception as e:
            log.error(f"Error validating VM {vm_id}: {e}")
            return False

    def validate_testfunction_exists(self, testfunction_id: str) -> bool:
        """
        Validate that a global test function exists.

        Args:
            testfunction_id: Global test function ID

        Returns:
            True if test function exists, False otherwise
        """
        try:
            with self._get_global_api() as api:
                testfunction = api.get_by_ulid(TestFunction, testfunction_id)
                return testfunction is not None
        except Exception as e:
            log.error(f"Error validating test function {testfunction_id}: {e}")
            return False

    def get_environment_info(self, environment_id: str) -> dict[str, Any] | None:
        """
        Get environment information from global database.

        Args:
            environment_id: Global environment ID

        Returns:
            Dictionary with environment info or None if not found
        """
        try:
            with self._get_global_api() as api:
                environment = api.get_by_ulid(Environment, environment_id)
                if environment:
                    api.expunge(environment)
                    return {
                        'id': environment.id,
                        'name': environment.name,
                        'description': environment.description,
                        'vm_id': environment.vm_id,
                        'file': environment.file
                    }
                return None
        except Exception as e:
            log.error(f"Error getting environment info {environment_id}: {e}")
            return None

    def get_vm_info(self, vm_id: str) -> dict[str, Any] | None:
        """
        Get VM information from global database.

        Args:
            vm_id: Global VM ID

        Returns:
            Dictionary with VM info or None if not found
        """
        try:
            with self._get_global_api() as api:
                vm = api.get_by_ulid(Vm, vm_id)
                if vm:
                    api.expunge(vm)
                    return {
                        'id': vm.id,
                        'name': vm.name,
                        'description': vm.description,
                        'file': vm.file,
                        'hash': vm.hash
                    }
                return None
        except Exception as e:
            log.error(f"Error getting VM info {vm_id}: {e}")
            return None

    def get_testfunction_info(self, testfunction_id: str) -> dict[str, Any] | None:
        """
        Get test function information from global database.

        Args:
            testfunction_id: Global test function ID

        Returns:
            Dictionary with test function info or None if not found
        """
        try:
            with self._get_global_api() as api:
                testfunction = api.get_by_ulid(TestFunction, testfunction_id)
                if testfunction:
                    api.expunge(testfunction)
                    return {
                        'id': testfunction.id,
                        'name': testfunction.name,
                        'description': testfunction.description,
                        'dotnotation': testfunction.dotnotation
                    }
                return None
        except Exception as e:
            log.error(f"Error getting test function info {testfunction_id}: {e}")
            return None

    def get_environment_object(self, environment_id: str):
        """
        Get environment object from global database.

        Args:
            environment_id: Global environment ID

        Returns:
            Environment object or None if not found
        """
        cache_key = f"env_obj_{environment_id}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        try:
            with self._get_global_api() as api:
                environment = api.get_by_ulid(Environment, environment_id)
                if environment:
                    api.expunge(environment)  # Detach from session
                    self._cache_set(cache_key, environment)
                    return environment
                return None
        except Exception as e:
            log.error(f"Error getting environment object {environment_id}: {e}")
            return None

    def get_testfunction_object(self, testfunction_id: str):
        """
        Get test function object from global database.

        Args:
            testfunction_id: Global test function ID

        Returns:
            TestFunction object or None if not found
        """
        cache_key = f"tf_obj_{testfunction_id}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        try:
            with self._get_global_api() as api:
                from sqlalchemy.orm import joinedload
                testfunction = api._session.query(TestFunction).options(
                    joinedload(TestFunction.file)
                ).filter(TestFunction.id == testfunction_id).first()

                if testfunction:
                    # Access the file relationship to ensure it's loaded
                    _ = testfunction.file
                    api.expunge(testfunction)  # Detach from session
                    self._cache_set(cache_key, testfunction)
                    return testfunction
                return None
        except Exception as e:
            log.error(f"Error getting test function object {testfunction_id}: {e}")
            return None

    def get_testparameter_object(self, parameter_id: str):
        """
        Get test parameter object from global database.

        Args:
            parameter_id: Global test parameter ID

        Returns:
            TestParameter object or None if not found
        """
        cache_key = f"tp_obj_{parameter_id}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        try:
            with self._get_global_api() as api:
                from adare.database.models.global_models import TestParameter
                parameter = api.get_by_ulid(TestParameter, parameter_id)
                if parameter:
                    api.expunge(parameter)  # Detach from session
                    self._cache_set(cache_key, parameter)
                    return parameter
                return None
        except Exception as e:
            log.error(f"Error getting test parameter object {parameter_id}: {e}")
            return None

    def get_vm_object(self, vm_id: str):
        """
        Get VM object from global database.

        Args:
            vm_id: Global VM ID

        Returns:
            VM object or None if not found
        """
        cache_key = f"vm_obj_{vm_id}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        try:
            with self._get_global_api() as api:
                vm = api.get_by_ulid(Vm, vm_id)
                if vm:
                    api.expunge(vm)  # Detach from session
                    self._cache_set(cache_key, vm)
                    return vm
                return None
        except Exception as e:
            log.error(f"Error getting VM object {vm_id}: {e}")
            return None

    def get_projects_using_environment(self, environment_id: str) -> list[str]:
        """
        Get list of project paths that use a specific environment.

        Args:
            environment_id: Global environment ID

        Returns:
            List of project paths using this environment
        """
        projects = []
        try:
            with self._get_global_api() as api:
                all_projects = api._session.query(Project).all()

                for project in all_projects:
                    try:
                        project_path = Path(project.path)
                        with ProjectDatabaseApi(project_path) as project_api:
                            # Check if any experiment runs reference this environment
                            runs = project_api._session.query(ExperimentRun).filter(
                                ExperimentRun.environment_id == environment_id
                            ).all()
                            if runs:
                                projects.append(project.path)
                    except Exception as e:
                        log.warning(f"Error checking project {project.path}: {e}")

        except Exception as e:
            log.error(f"Error finding projects using environment {environment_id}: {e}")

        return projects

    def get_projects_using_vm(self, vm_id: str) -> list[str]:
        """
        Get list of project paths that use a specific VM (via environments).

        Args:
            vm_id: Global VM ID

        Returns:
            List of project paths using this VM
        """
        projects = []
        try:
            with self._get_global_api() as api:
                # Find environments that use this VM
                environments = api._session.query(Environment).filter(
                    Environment.vm_id == vm_id
                ).all()

                # For each environment, find projects that use it
                for env in environments:
                    env_projects = self.get_projects_using_environment(env.id)
                    projects.extend(env_projects)

                # Remove duplicates
                projects = list(set(projects))

        except Exception as e:
            log.error(f"Error finding projects using VM {vm_id}: {e}")

        return projects

    def get_projects_using_testfunction(self, testfunction_id: str) -> list[str]:
        """
        Get list of project paths that use a specific test function.

        Args:
            testfunction_id: Global test function ID

        Returns:
            List of project paths using this test function
        """
        projects = []
        try:
            with self._get_global_api() as api:
                all_projects = api._session.query(Project).all()

                for project in all_projects:
                    try:
                        project_path = Path(project.path)
                        with ProjectDatabaseApi(project_path) as project_api:
                            # Check if any abstract tests reference this test function
                            from adare.database.models.project_models import AbstractTest
                            tests = project_api._session.query(AbstractTest).filter(
                                AbstractTest.testfunction_id == testfunction_id
                            ).all()
                            if tests:
                                projects.append(project.path)
                    except Exception as e:
                        log.warning(f"Error checking project {project.path}: {e}")

        except Exception as e:
            log.error(f"Error finding projects using test function {testfunction_id}: {e}")

        return projects

    def validate_experiment_references(self, project_path: Path, experiment_id: str) -> dict[str, Any]:
        """
        Validate all global references in an experiment.

        Args:
            project_path: Path to the project
            experiment_id: Experiment ID

        Returns:
            Dictionary with validation results
        """
        results = {
            'valid': True,
            'missing_environments': [],
            'missing_testfunctions': [],
            'errors': []
        }

        try:
            with ProjectDatabaseApi(project_path) as project_api:
                experiment = project_api.get_by_ulid(Experiment, experiment_id)
                if not experiment:
                    results['valid'] = False
                    results['errors'].append(f"Experiment {experiment_id} not found")
                    return results

                # Validate environment references
                if hasattr(experiment, 'environment_ids') and experiment.environment_ids:
                    for env_id in experiment.environment_ids:
                        if not self.validate_environment_exists(env_id):
                            results['valid'] = False
                            results['missing_environments'].append(env_id)

                # Validate test function references in abstract tests
                for abstract_test in experiment.abstract_tests:
                    if not self.validate_testfunction_exists(abstract_test.testfunction_id):
                        results['valid'] = False
                        results['missing_testfunctions'].append(abstract_test.testfunction_id)

        except Exception as e:
            results['valid'] = False
            results['errors'].append(f"Error validating experiment: {e}")
            log.error(f"Error validating experiment {experiment_id}: {e}")

        return results

    def validate_project_references(self, project_path: Path) -> dict[str, Any]:
        """
        Validate all global references in a project.

        Args:
            project_path: Path to the project

        Returns:
            Dictionary with validation results
        """
        results = {
            'valid': True,
            'missing_environments': set(),
            'missing_testfunctions': set(),
            'invalid_experiments': [],
            'errors': []
        }

        try:
            with ProjectDatabaseApi(project_path) as project_api:
                experiments = project_api._session.query(Experiment).all()

                for experiment in experiments:
                    exp_results = self.validate_experiment_references(project_path, experiment.id)
                    if not exp_results['valid']:
                        results['valid'] = False
                        results['invalid_experiments'].append(experiment.name)
                        results['missing_environments'].update(exp_results['missing_environments'])
                        results['missing_testfunctions'].update(exp_results['missing_testfunctions'])
                        results['errors'].extend(exp_results['errors'])

                # Convert sets back to lists for JSON serialization
                results['missing_environments'] = list(results['missing_environments'])
                results['missing_testfunctions'] = list(results['missing_testfunctions'])

        except Exception as e:
            results['valid'] = False
            results['errors'].append(f"Error validating project: {e}")
            log.error(f"Error validating project {project_path}: {e}")

        return results

    def get_vm_instance_object(self, vm_instance_id: str):
        """
        Get VM instance object from global database.

        Args:
            vm_instance_id: Global VM instance ID

        Returns:
            VmInstance object or None if not found
        """
        cache_key = f"vmi_obj_{vm_instance_id}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        try:
            from adare.database.models.global_models import VmInstance
            with self._get_global_api() as api:
                vm_instance = api._session.query(VmInstance).filter(
                    VmInstance.id == vm_instance_id
                ).first()

                if vm_instance:
                    api.expunge(vm_instance)  # Detach from session
                    self._cache_set(cache_key, vm_instance)
                    return vm_instance
                return None
        except Exception as e:
            log.error(f"Error getting VM instance object {vm_instance_id}: {e}")
            return None


# Global instance for easy access
reference_manager = ReferenceManager()
