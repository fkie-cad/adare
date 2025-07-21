"""
Database API for Tag management.

This module provides comprehensive tag operations including:
- Tag creation and management
- Tag association with experiments and environments
- Tag-based filtering and search
- Tag usage statistics
"""

import logging
from typing import Optional, List, Dict, Any, Union
from pathlib import Path

from adare.database.api.base import EnhancedDatabaseApi
from adare.database.models.experiment import Tag, Experiment, Environment, Base
from adare.database.exceptions import EntityNotFoundError, ValidationError

log = logging.getLogger(__name__)


class TagApi(EnhancedDatabaseApi):
    """
    API for managing tags and tag associations.
    
    Provides operations for:
    - Creating and managing tags
    - Associating tags with experiments and environments
    - Tag-based filtering and search
    - Tag usage analytics
    """
    
    def __init__(self, db_path: Optional[Path] = None):
        super().__init__(db_path)
        Base.metadata.create_all(self.engine)
    
    def create_tag(self, name: str, description: Optional[str] = None) -> Tag:
        """
        Create a new tag.
        
        Args:
            name: Tag name (must be unique)
            description: Optional tag description
            
        Returns:
            Created Tag instance
            
        Raises:
            ValidationError: If tag name is invalid or already exists
            DatabaseError: If database operation fails
        """
        # Validate tag name
        if not name or not name.strip():
            raise ValidationError("Tag name cannot be empty")
        
        name = name.strip().lower()  # Normalize tag names
        
        # Check if tag already exists
        existing_tag = self._session.query(Tag).filter(Tag.name == name).first()
        if existing_tag:
            raise ValidationError(f"Tag '{name}' already exists")
        
        return self.create_entity(Tag, name=name, description=description)
    
    def get_or_create_tag(self, name: str, description: Optional[str] = None) -> tuple[Tag, bool]:
        """
        Get existing tag or create new one.
        
        Args:
            name: Tag name
            description: Optional tag description (used only for creation)
            
        Returns:
            Tuple of (Tag instance, created_flag)
        """
        if not name or not name.strip():
            raise ValidationError("Tag name cannot be empty")
        
        name = name.strip().lower()
        
        return self.get_or_create(
            Tag,
            defaults={'description': description},
            name=name
        )
    
    def get_or_create_tags(self, tag_names: List[str]) -> List[Tag]:
        """
        Get or create multiple tags.
        
        Args:
            tag_names: List of tag names
            
        Returns:
            List of Tag instances
        """
        tags = []
        for name in tag_names:
            tag, _ = self.get_or_create_tag(name)
            tags.append(tag)
        return tags
    
    def get_tag_by_name(self, name: str) -> Optional[Tag]:
        """
        Get tag by name.
        
        Args:
            name: Tag name
            
        Returns:
            Tag instance or None if not found
        """
        if not name:
            return None
        
        return self._session.query(Tag).filter(Tag.name == name.strip().lower()).first()
    
    def list_tags(self, 
                  search: Optional[str] = None,
                  order_by: str = 'name',
                  limit: Optional[int] = None) -> List[Tag]:
        """
        List tags with optional search and ordering.
        
        Args:
            search: Search term for tag name or description
            order_by: Field to order by ('name', 'description')
            limit: Maximum number of results
            
        Returns:
            List of Tag instances
        """
        query = self._session.query(Tag)
        
        # Apply search filter
        if search:
            search_term = f"%{search.lower()}%"
            query = query.filter(
                Tag.name.like(search_term) | 
                Tag.description.like(search_term)
            )
        
        # Apply ordering
        if order_by == 'name':
            query = query.order_by(Tag.name)
        elif order_by == 'description':
            query = query.order_by(Tag.description)
        
        # Apply limit
        if limit:
            query = query.limit(limit)
        
        return query.all()
    
    def update_tag(self, tag_id: str, 
                   name: Optional[str] = None,
                   description: Optional[str] = None) -> Tag:
        """
        Update tag information.
        
        Args:
            tag_id: ULID of tag to update
            name: New tag name (optional)
            description: New tag description (optional)
            
        Returns:
            Updated Tag instance
            
        Raises:
            EntityNotFoundError: If tag not found
            ValidationError: If new name already exists
        """
        tag = self.get_by_ulid_or_404(Tag, tag_id)
        
        update_data = {}
        
        if name is not None:
            normalized_name = name.strip().lower()
            if normalized_name != tag.name:
                # Check if new name already exists
                existing = self._session.query(Tag).filter(Tag.name == normalized_name).first()
                if existing:
                    raise ValidationError(f"Tag '{normalized_name}' already exists")
                update_data['name'] = normalized_name
        
        if description is not None:
            update_data['description'] = description
        
        if update_data:
            return self.update_entity(tag, **update_data)
        
        return tag
    
    def delete_tag(self, tag_id: str, force: bool = False) -> None:
        """
        Delete a tag.
        
        Args:
            tag_id: ULID of tag to delete
            force: If True, delete even if tag is associated with entities
            
        Raises:
            EntityNotFoundError: If tag not found
            ValidationError: If tag is in use and force=False
        """
        tag = self.get_by_ulid_or_404(Tag, tag_id)
        
        if not force:
            # Check if tag is associated with any experiments or environments
            experiment_count = self._session.query(Experiment).filter(
                Experiment.tags.contains(tag)
            ).count()
            
            environment_count = self._session.query(Environment).filter(
                Environment.tags.contains(tag)
            ).count()
            
            total_usage = experiment_count + environment_count
            if total_usage > 0:
                raise ValidationError(
                    f"Tag '{tag.name}' is used by {total_usage} entities. "
                    f"Use force=True to delete anyway."
                )
        
        self.delete_entity(tag)
    
    def get_tag_usage_stats(self, tag_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get tag usage statistics.
        
        Args:
            tag_id: Optional specific tag ULID (if None, returns stats for all tags)
            
        Returns:
            Dictionary with usage statistics
        """
        if tag_id:
            tag = self.get_by_ulid_or_404(Tag, tag_id)
            tags = [tag]
        else:
            tags = self.list_tags()
        
        stats = {}
        
        for tag in tags:
            experiment_count = self._session.query(Experiment).filter(
                Experiment.tags.contains(tag)
            ).count()
            
            environment_count = self._session.query(Environment).filter(
                Environment.tags.contains(tag)
            ).count()
            
            tag_stats = {
                'name': tag.name,
                'description': tag.description,
                'experiment_count': experiment_count,
                'environment_count': environment_count,
                'total_usage': experiment_count + environment_count
            }
            
            if tag_id:
                return tag_stats
            else:
                stats[tag.id] = tag_stats
        
        return stats
    
    def get_most_used_tags(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get most frequently used tags.
        
        Args:
            limit: Maximum number of tags to return
            
        Returns:
            List of tag usage information, sorted by usage count
        """
        stats = self.get_tag_usage_stats()
        
        # Sort by total usage
        sorted_tags = sorted(
            stats.values(),
            key=lambda x: x['total_usage'],
            reverse=True
        )
        
        return sorted_tags[:limit]
    
    def get_unused_tags(self) -> List[Tag]:
        """
        Get tags that are not associated with any entities.
        
        Returns:
            List of unused Tag instances
        """
        # This is a bit complex with many-to-many relationships
        # We'll get all tags and filter out those with associations
        all_tags = self.list_tags()
        unused_tags = []
        
        for tag in all_tags:
            experiment_count = self._session.query(Experiment).filter(
                Experiment.tags.contains(tag)
            ).count()
            
            environment_count = self._session.query(Environment).filter(
                Environment.tags.contains(tag)
            ).count()
            
            if experiment_count == 0 and environment_count == 0:
                unused_tags.append(tag)
        
        return unused_tags
    
    def cleanup_unused_tags(self) -> int:
        """
        Delete all unused tags.
        
        Returns:
            Number of tags deleted
        """
        unused_tags = self.get_unused_tags()
        count = len(unused_tags)
        
        for tag in unused_tags:
            self.delete_entity(tag)
        
        log.info(f"Cleaned up {count} unused tags")
        return count
    
    def associate_tags_with_experiment(self, experiment_id: str, tag_names: List[str]) -> None:
        """
        Associate tags with an experiment.
        
        Args:
            experiment_id: ULID of experiment
            tag_names: List of tag names to associate
            
        Raises:
            EntityNotFoundError: If experiment not found
        """
        experiment = self.get_by_ulid_or_404(Experiment, experiment_id)
        tags = self.get_or_create_tags(tag_names)
        
        # Clear existing tags and set new ones
        experiment.tags = tags
        self._session.flush()
    
    def associate_tags_with_environment(self, environment_id: str, tag_names: List[str]) -> None:
        """
        Associate tags with an environment.
        
        Args:
            environment_id: ULID of environment
            tag_names: List of tag names to associate
            
        Raises:
            EntityNotFoundError: If environment not found
        """
        environment = self.get_by_ulid_or_404(Environment, environment_id)
        tags = self.get_or_create_tags(tag_names)
        
        # Clear existing tags and set new ones
        environment.tags = tags
        self._session.flush()
    
    def get_entities_by_tags(self, 
                           tag_names: List[str],
                           entity_type: str = 'both',
                           match_all: bool = True) -> Dict[str, List]:
        """
        Get entities associated with specific tags.
        
        Args:
            tag_names: List of tag names to search for
            entity_type: 'experiments', 'environments', or 'both'
            match_all: If True, entity must have ALL tags; if False, ANY tag
            
        Returns:
            Dictionary with 'experiments' and/or 'environments' lists
            
        Raises:
            ValidationError: If entity_type is invalid
        """
        if entity_type not in ['experiments', 'environments', 'both']:
            raise ValidationError("entity_type must be 'experiments', 'environments', or 'both'")
        
        # Get tag objects
        tags = []
        for name in tag_names:
            tag = self.get_tag_by_name(name)
            if tag:
                tags.append(tag)
        
        if not tags:
            return {'experiments': [], 'environments': []}
        
        result = {}
        
        if entity_type in ['experiments', 'both']:
            query = self._session.query(Experiment)
            
            if match_all:
                # Entity must have ALL tags
                for tag in tags:
                    query = query.filter(Experiment.tags.contains(tag))
            else:
                # Entity must have ANY tag
                query = query.filter(Experiment.tags.any(Tag.id.in_([tag.id for tag in tags])))
            
            result['experiments'] = query.all()
        
        if entity_type in ['environments', 'both']:
            query = self._session.query(Environment)
            
            if match_all:
                # Entity must have ALL tags
                for tag in tags:
                    query = query.filter(Environment.tags.contains(tag))
            else:
                # Entity must have ANY tag
                query = query.filter(Environment.tags.any(Tag.id.in_([tag.id for tag in tags])))
            
            result['environments'] = query.all()
        
        return result