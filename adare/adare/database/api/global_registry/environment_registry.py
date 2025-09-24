"""
Global Environment Registry API.

This module provides database operations for the global environment registry,
which stores environments that can be shared across multiple projects.
"""

import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
import json

from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func

from adare.config.configdirectory import APPDATA_DIR
from adare.database.api.base import EnhancedDatabaseApi
from adare.database.models.global_registry import (
    GlobalEnvironment,
    GlobalVm,
    ResourceUsage,
    GlobalResourceMetadata
)
from adare.database.exceptions import (
    DatabaseError,
    EntityNotFoundError,
    ValidationError
)

log = logging.getLogger(__name__)


class EnvironmentRegistryApi(EnhancedDatabaseApi):
    """
    Database API for global environment registry operations.

    Manages environments that are stored globally and can be referenced by multiple projects.
    Provides usage tracking, version management, and resource cleanup.
    """

    def __init__(self):
        """Initialize environment registry API with global environment registry database."""
        environment_registry_path = APPDATA_DIR / 'environment_registry.db'
        super().__init__(db_path=environment_registry_path)
        self._ensure_environment_storage_directory()
        self._ensure_registry_metadata()

    def _ensure_environment_storage_directory(self):
        """Ensure the global environment storage directory exists."""
        try:
            environments_dir = APPDATA_DIR / 'environments'
            environments_dir.mkdir(parents=True, exist_ok=True)
            log.debug(f"Environment storage directory ensured at: {environments_dir}")
        except OSError as e:
            log.error(f"Failed to create environment storage directory: {e}")
            raise DatabaseError(f"Cannot create environment storage directory: {e}")

    def _ensure_registry_metadata(self):
        """Ensure registry metadata exists and is up to date."""
        with self:
            metadata = self._session.query(GlobalResourceMetadata).first()
            if not metadata:
                metadata = GlobalResourceMetadata(
                    registry_version="1.0.0",
                    auto_cleanup_enabled=True,
                    cleanup_threshold_days=30,
                    max_environment_size_mb=100
                )
                self._session.add(metadata)
                self._session.commit()
                log.info("Created global environment registry metadata")

    def create_environment(self, name: str, vm_id: str, file_path: Path,
                          sha256hash: str, description: str = '',
                          installations: List[Dict] = None, tags: List[str] = None,
                          version: str = "1.0.0", created_by: str = None,
                          parent_environment_id: str = None) -> GlobalEnvironment:
        """
        Create a new environment in the global registry.

        Args:
            name: Unique environment name
            vm_id: ID of global VM this environment uses
            file_path: Path to environment file (will be moved to global storage)
            sha256hash: SHA256 hash of environment file
            description: Environment description
            installations: List of post-setup installations
            tags: List of tags for categorization
            version: Semantic version (default: "1.0.0")
            created_by: User who created the environment
            parent_environment_id: ID of parent environment (for versioning)

        Returns:
            Created GlobalEnvironment instance

        Raises:
            ValidationError: If environment name or hash already exists
            EntityNotFoundError: If VM not found
            DatabaseError: If database operation fails
        """
        with self:
            # Verify VM exists (we'll check in VM registry)
            from .vm_registry import VmRegistryApi
            vm_registry = VmRegistryApi()
            with vm_registry:
                vm = vm_registry.get_vm_by_id(vm_id)
                if not vm:
                    raise EntityNotFoundError(f"VM with ID '{vm_id}' not found in registry")

            # Check for existing environment with same name or hash
            existing_env = self._session.query(GlobalEnvironment).filter(
                (GlobalEnvironment.name == name) | (GlobalEnvironment.sha256hash == sha256hash)
            ).first()

            if existing_env:
                if existing_env.name == name:
                    raise ValidationError(f"Environment with name '{name}' already exists")
                else:
                    raise ValidationError(f"Environment with hash '{sha256hash}' already exists")

            # Move environment file to global storage if not already there
            global_env_path = self._move_environment_to_global_storage(file_path, name)

            # Get file size
            try:
                file_size = global_env_path.stat().st_size
            except OSError:
                file_size = None
                log.warning(f"Could not get file size for environment {name}")

            # Process installations as JSON string
            installations_json = None
            if installations:
                try:
                    installations_json = json.dumps(installations)
                except (TypeError, ValueError) as e:
                    log.warning(f"Failed to serialize installations for {name}: {e}")

            # Process tags as comma-separated string
            tags_str = None
            if tags:
                tags_str = ", ".join(tags)

            # Create environment record
            environment = GlobalEnvironment(
                name=name,
                description=description,
                file=str(global_env_path.relative_to(APPDATA_DIR / 'environments')),
                sha256hash=sha256hash,
                file_size_bytes=file_size,
                vm_id=vm_id,
                installations=installations_json,
                tags=tags_str,
                version=version,
                created_by=created_by,
                parent_environment_id=parent_environment_id
            )

            self._session.add(environment)
            self._session.flush()  # Get ID

            log.info(f"Created global environment: {name} v{version} ({sha256hash[:8]})")
            return environment

    def _move_environment_to_global_storage(self, source_path: Path, env_name: str) -> Path:
        """
        Move environment file to global storage location.

        Args:
            source_path: Current path of environment file
            env_name: Name of environment (used for file naming)

        Returns:
            Path to environment file in global storage

        Raises:
            DatabaseError: If file operation fails
        """
        source_path = Path(source_path)
        environments_dir = APPDATA_DIR / 'environments'

        # Generate target filename
        target_filename = f"{env_name}{source_path.suffix}"
        target_path = environments_dir / target_filename

        # Check if source is already in global storage
        try:
            if source_path.resolve().is_relative_to(environments_dir.resolve()):
                log.debug(f"Environment file already in global storage: {source_path}")
                return source_path
        except ValueError:
            pass  # Not in global storage, need to move

        # Move file to global storage
        try:
            if source_path.exists():
                # Ensure target directory exists
                target_path.parent.mkdir(parents=True, exist_ok=True)

                # Move file
                source_path.rename(target_path)
                log.info(f"Moved environment file from {source_path} to {target_path}")
            else:
                log.warning(f"Source environment file not found: {source_path}")
                # Create empty file as placeholder
                target_path.touch()

            return target_path

        except OSError as e:
            log.error(f"Failed to move environment file to global storage: {e}")
            raise DatabaseError(f"Cannot move environment file to global storage: {e}")

    def get_environment_by_id(self, env_id: str) -> Optional[GlobalEnvironment]:
        """Get environment by ID."""
        with self:
            return self.get_by_ulid(GlobalEnvironment, env_id)

    def get_environment_by_name(self, name: str) -> Optional[GlobalEnvironment]:
        """Get environment by name."""
        with self:
            return self._session.query(GlobalEnvironment).filter(
                GlobalEnvironment.name == name
            ).first()

    def get_environment_by_hash(self, sha256hash: str) -> Optional[GlobalEnvironment]:
        """Get environment by file hash."""
        with self:
            return self._session.query(GlobalEnvironment).filter(
                GlobalEnvironment.sha256hash == sha256hash
            ).first()

    def get_all_environments(self, include_vm_info: bool = False,
                           include_usage_stats: bool = False) -> List[GlobalEnvironment]:
        """
        Get all environments in the registry.

        Args:
            include_vm_info: If True, eagerly load VM information
            include_usage_stats: If True, eagerly load usage statistics

        Returns:
            List of GlobalEnvironment instances
        """
        with self:
            query = self._session.query(GlobalEnvironment)

            if include_vm_info:
                query = query.options(joinedload(GlobalEnvironment.vm))

            return query.order_by(GlobalEnvironment.name).all()

    def get_environments_by_vm(self, vm_id: str) -> List[GlobalEnvironment]:
        """
        Get all environments that use a specific VM.

        Args:
            vm_id: VM ID

        Returns:
            List of GlobalEnvironment instances
        """
        with self:
            return self._session.query(GlobalEnvironment).filter(
                GlobalEnvironment.vm_id == vm_id
            ).order_by(GlobalEnvironment.name).all()

    def get_environments_by_tag(self, tag: str) -> List[GlobalEnvironment]:
        """
        Get all environments that have a specific tag.

        Args:
            tag: Tag to search for

        Returns:
            List of GlobalEnvironment instances
        """
        with self:
            return self._session.query(GlobalEnvironment).filter(
                GlobalEnvironment.tags.contains(tag)
            ).order_by(GlobalEnvironment.name).all()

    def search_environments(self, query: str) -> List[GlobalEnvironment]:
        """
        Search environments by name, description, or tags.

        Args:
            query: Search query

        Returns:
            List of matching GlobalEnvironment instances
        """
        with self:
            search_filter = (
                GlobalEnvironment.name.contains(query) |
                GlobalEnvironment.description.contains(query) |
                GlobalEnvironment.tags.contains(query)
            )

            return self._session.query(GlobalEnvironment).filter(
                search_filter
            ).order_by(GlobalEnvironment.name).all()

    def update_environment(self, env_id: str, **kwargs) -> GlobalEnvironment:
        """
        Update environment metadata.

        Args:
            env_id: Environment ID
            **kwargs: Fields to update

        Returns:
            Updated GlobalEnvironment instance

        Raises:
            EntityNotFoundError: If environment not found
        """
        with self:
            environment = self.get_by_ulid_or_404(GlobalEnvironment, env_id)

            # Update allowed fields
            allowed_fields = {
                'description', 'installations', 'tags', 'version'
            }

            for key, value in kwargs.items():
                if key in allowed_fields:
                    if key == 'installations' and isinstance(value, list):
                        # Convert list to JSON string
                        try:
                            value = json.dumps(value)
                        except (TypeError, ValueError) as e:
                            log.warning(f"Failed to serialize installations: {e}")
                            continue
                    elif key == 'tags' and isinstance(value, list):
                        # Convert list to comma-separated string
                        value = ", ".join(value)

                    setattr(environment, key, value)
                else:
                    log.warning(f"Ignoring update to non-updateable field: {key}")

            environment.updated_at = datetime.utcnow()
            self._session.commit()

            log.info(f"Updated environment {environment.name} (ID: {env_id})")
            return environment

    def create_environment_version(self, parent_env_id: str, new_version: str,
                                  **kwargs) -> GlobalEnvironment:
        """
        Create a new version of an existing environment.

        Args:
            parent_env_id: ID of parent environment
            new_version: Version string for new environment
            **kwargs: Additional fields for new environment

        Returns:
            New GlobalEnvironment instance

        Raises:
            EntityNotFoundError: If parent environment not found
        """
        with self:
            parent_env = self.get_by_ulid_or_404(GlobalEnvironment, parent_env_id)

            # Generate new name with version
            new_name = f"{parent_env.name}_v{new_version}"

            # Create new environment based on parent
            new_env_data = {
                'name': new_name,
                'description': kwargs.get('description', parent_env.description),
                'vm_id': kwargs.get('vm_id', parent_env.vm_id),
                'file_path': kwargs.get('file_path'),  # Must be provided
                'sha256hash': kwargs.get('sha256hash'),  # Must be provided
                'installations': kwargs.get('installations',
                                           json.loads(parent_env.installations or '[]')),
                'tags': parent_env.tag_list,
                'version': new_version,
                'created_by': kwargs.get('created_by'),
                'parent_environment_id': parent_env_id
            }

            return self.create_environment(**new_env_data)

    def delete_environment(self, env_id: str, force: bool = False) -> bool:
        """
        Delete environment from registry and storage.

        Args:
            env_id: Environment ID
            force: If True, delete even if environment is in use

        Returns:
            True if deleted successfully

        Raises:
            EntityNotFoundError: If environment not found
            ValidationError: If environment is in use and force=False
        """
        with self:
            environment = self.get_by_ulid_or_404(GlobalEnvironment, env_id)

            # Check usage if not forcing
            if not force:
                usage_count = self._session.query(ResourceUsage).filter(
                    ResourceUsage.resource_type == 'environment',
                    ResourceUsage.resource_id == env_id
                ).count()

                if usage_count > 0:
                    raise ValidationError(
                        f"Environment '{environment.name}' is used by {usage_count} project(s). "
                        f"Use force=True to delete anyway."
                    )

            # Check for child versions
            child_versions = self._session.query(GlobalEnvironment).filter(
                GlobalEnvironment.parent_environment_id == env_id
            ).count()

            if child_versions > 0 and not force:
                raise ValidationError(
                    f"Environment '{environment.name}' has {child_versions} child version(s). "
                    f"Use force=True to delete anyway."
                )

            # Delete physical file
            try:
                env_file_path = environment.full_file_path
                if env_file_path.exists():
                    env_file_path.unlink()
                    log.info(f"Deleted environment file: {env_file_path}")
            except OSError as e:
                log.warning(f"Failed to delete environment file {environment.file}: {e}")

            # Delete usage records
            self._session.query(ResourceUsage).filter(
                ResourceUsage.resource_type == 'environment',
                ResourceUsage.resource_id == env_id
            ).delete()

            # Delete child versions if forcing
            if force:
                self._session.query(GlobalEnvironment).filter(
                    GlobalEnvironment.parent_environment_id == env_id
                ).update({'parent_environment_id': None})

            # Delete environment record
            self._session.delete(environment)
            self._session.commit()

            log.info(f"Deleted environment {environment.name} (ID: {env_id})")
            return True

    def track_environment_usage(self, env_id: str, project_path: str, project_name: str = None,
                               alias_name: str = None, usage_notes: str = None) -> ResourceUsage:
        """
        Track usage of an environment by a project.

        Args:
            env_id: Environment ID
            project_path: Absolute path to project
            project_name: Project name (for convenience)
            alias_name: Project-specific alias for the environment
            usage_notes: Project-specific notes

        Returns:
            ResourceUsage instance

        Raises:
            EntityNotFoundError: If environment not found
        """
        with self:
            # Verify environment exists
            environment = self.get_by_ulid_or_404(GlobalEnvironment, env_id)

            # Get or create usage record
            usage, created = self.get_or_create(
                ResourceUsage,
                defaults={
                    'project_name': project_name,
                    'alias_name': alias_name,
                    'usage_notes': usage_notes,
                    'usage_count': 1
                },
                resource_type='environment',
                resource_id=env_id,
                project_path=project_path
            )

            if not created:
                # Update existing usage
                usage.last_used = datetime.utcnow()
                usage.usage_count += 1
                if alias_name:
                    usage.alias_name = alias_name
                if usage_notes:
                    usage.usage_notes = usage_notes

            # Update environment usage stats
            environment.usage_count = self._session.query(ResourceUsage).filter(
                ResourceUsage.resource_type == 'environment',
                ResourceUsage.resource_id == env_id
            ).count()
            environment.last_used = datetime.utcnow()

            self._session.commit()

            action = "Created" if created else "Updated"
            log.info(f"{action} environment usage tracking: {environment.name} -> {project_name or project_path}")

            return usage

    def stop_environment_usage(self, env_id: str, project_path: str) -> bool:
        """
        Stop tracking environment usage by a project.

        Args:
            env_id: Environment ID
            project_path: Project path

        Returns:
            True if usage was removed
        """
        with self:
            usage = self._session.query(ResourceUsage).filter(
                ResourceUsage.resource_type == 'environment',
                ResourceUsage.resource_id == env_id,
                ResourceUsage.project_path == project_path
            ).first()

            if usage:
                self._session.delete(usage)

                # Update environment usage count
                environment = self.get_by_ulid(GlobalEnvironment, env_id)
                if environment:
                    environment.usage_count = self._session.query(ResourceUsage).filter(
                        ResourceUsage.resource_type == 'environment',
                        ResourceUsage.resource_id == env_id
                    ).count()

                self._session.commit()
                log.info(f"Stopped environment usage tracking: {env_id} -> {project_path}")
                return True

            return False

    def get_environment_usage(self, env_id: str) -> List[ResourceUsage]:
        """
        Get all usage records for an environment.

        Args:
            env_id: Environment ID

        Returns:
            List of ResourceUsage instances
        """
        with self:
            return self._session.query(ResourceUsage).filter(
                ResourceUsage.resource_type == 'environment',
                ResourceUsage.resource_id == env_id
            ).order_by(ResourceUsage.last_used.desc()).all()

    def get_project_environments(self, project_path: str) -> List[Dict[str, Any]]:
        """
        Get all environments used by a specific project.

        Args:
            project_path: Project path

        Returns:
            List of dicts with environment and usage information
        """
        with self:
            # Query environments with their usage info for this project
            results = self._session.query(GlobalEnvironment, ResourceUsage).join(
                ResourceUsage,
                (ResourceUsage.resource_type == 'environment') &
                (ResourceUsage.resource_id == GlobalEnvironment.id)
            ).filter(
                ResourceUsage.project_path == project_path
            ).options(
                joinedload(GlobalEnvironment.vm)
            ).all()

            return [
                {
                    'environment': env,
                    'usage': usage,
                    'alias': usage.alias_name or env.name,
                    'last_used': usage.last_used,
                    'usage_count': usage.usage_count,
                    'vm_name': env.vm.name if env.vm else None
                }
                for env, usage in results
            ]

    def cleanup_unused_environments(self, threshold_days: int = 30, dry_run: bool = True) -> Dict[str, Any]:
        """
        Clean up environments that haven't been used recently.

        Args:
            threshold_days: Remove environments unused for this many days
            dry_run: If True, don't actually delete anything

        Returns:
            Dict with cleanup results
        """
        from datetime import timedelta

        cutoff_date = datetime.utcnow() - timedelta(days=threshold_days)

        with self:
            # Find environments that are either never used or haven't been used recently
            unused_environments = self._session.query(GlobalEnvironment).filter(
                (GlobalEnvironment.last_used.is_(None)) |
                (GlobalEnvironment.last_used < cutoff_date)
            ).filter(
                GlobalEnvironment.usage_count == 0
            ).all()

            results = {
                'found_unused': len(unused_environments),
                'deleted': 0,
                'failed': 0,
                'dry_run': dry_run,
                'environment_list': [env.name for env in unused_environments]
            }

            if not dry_run:
                for env in unused_environments:
                    try:
                        self.delete_environment(env.id, force=True)
                        results['deleted'] += 1
                    except Exception as e:
                        log.error(f"Failed to delete unused environment {env.name}: {e}")
                        results['failed'] += 1

            log.info(f"Environment cleanup: found {results['found_unused']} unused environments")
            return results

    def get_registry_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the environment registry.

        Returns:
            Dict with registry statistics
        """
        with self:
            total_environments = self._session.query(GlobalEnvironment).count()
            total_usage = self._session.query(ResourceUsage).filter(
                ResourceUsage.resource_type == 'environment'
            ).count()

            # Calculate total storage used
            total_size = self._session.query(func.sum(GlobalEnvironment.file_size_bytes)).scalar() or 0

            # Get top used environments
            top_environments = self._session.query(GlobalEnvironment).order_by(
                GlobalEnvironment.usage_count.desc()
            ).limit(5).all()

            # Get environments by VM
            vm_distribution = self._session.query(
                GlobalEnvironment.vm_id,
                func.count(GlobalEnvironment.id).label('count')
            ).group_by(GlobalEnvironment.vm_id).all()

            return {
                'total_environments': total_environments,
                'total_projects_using': total_usage,
                'total_storage_bytes': total_size,
                'total_storage_mb': round(total_size / (1024**2), 2),
                'top_used_environments': [
                    {'name': env.name, 'usage_count': env.usage_count}
                    for env in top_environments
                ],
                'environments_per_vm': [
                    {'vm_id': vm_id, 'environment_count': count}
                    for vm_id, count in vm_distribution
                ]
            }