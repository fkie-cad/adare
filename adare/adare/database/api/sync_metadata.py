"""
Database API for SyncMetadata management.

This module provides specialized operations for managing synchronization metadata,
including tracking sync state, handling remote entities, and managing sync workflows.
"""

import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from pathlib import Path

from adare.database.api.base import EnhancedDatabaseApi
from adare.database.models.experiment import SyncMetadata, Base
from adare.database.exceptions import SyncError, EntityNotFoundError, ValidationError

log = logging.getLogger(__name__)


class SyncMetadataApi(EnhancedDatabaseApi):
    """
    API for managing synchronization metadata.
    
    Provides operations for:
    - Creating and updating sync metadata
    - Tracking sync state and timing
    - Managing remote entity relationships
    - Handling sync failures and retries
    """
    
    def __init__(self, db_path: Optional[Path] = None):
        super().__init__(db_path)
        Base.metadata.create_all(self.engine)
    
    def create_sync_metadata(self, 
                           sync_direction: str = 'push',
                           remote_id: Optional[str] = None,
                           remote_url: Optional[str] = None) -> SyncMetadata:
        """
        Create new sync metadata entry.
        
        Args:
            sync_direction: Direction of sync ('push', 'pull', 'bidirectional')
            remote_id: Remote entity identifier
            remote_url: Remote instance URL
            
        Returns:
            Created SyncMetadata instance
            
        Raises:
            ValidationError: If sync_direction is invalid
            DatabaseError: If database operation fails
        """
        valid_directions = ['push', 'pull', 'bidirectional']
        if sync_direction not in valid_directions:
            raise ValidationError(f"Invalid sync_direction. Must be one of: {valid_directions}")
        
        return self.create_entity(
            SyncMetadata,
            sync_direction=sync_direction,
            sync_status='pending',
            remote_id=remote_id,
            remote_url=remote_url,
            created_at=datetime.now(timezone.utc)
        )
    
    def update_sync_status(self, 
                          sync_metadata_id: str,
                          status: str,
                          failure_reason: Optional[str] = None) -> SyncMetadata:
        """
        Update sync status for metadata entry.
        
        Args:
            sync_metadata_id: ULID of sync metadata
            status: New sync status ('pending', 'synced', 'failed', 'local_only')
            failure_reason: Reason for failure (if status is 'failed')
            
        Returns:
            Updated SyncMetadata instance
            
        Raises:
            EntityNotFoundError: If sync metadata not found
            ValidationError: If status is invalid
            DatabaseError: If database operation fails
        """
        valid_statuses = ['pending', 'synced', 'failed', 'local_only']
        if status not in valid_statuses:
            raise ValidationError(f"Invalid status. Must be one of: {valid_statuses}")
        
        sync_metadata = self.get_by_ulid_or_404(SyncMetadata, sync_metadata_id)
        
        update_data = {
            'sync_status': status,
            'failure_reason': failure_reason
        }
        
        # Update last_sync_at for successful syncs
        if status == 'synced':
            update_data['last_sync_at'] = datetime.now(timezone.utc)
            update_data['failure_reason'] = None  # Clear any previous failure reason
        
        return self.update_entity(sync_metadata, **update_data)
    
    def mark_synced(self, sync_metadata_id: str) -> SyncMetadata:
        """
        Mark sync metadata as successfully synced.
        
        Args:
            sync_metadata_id: ULID of sync metadata
            
        Returns:
            Updated SyncMetadata instance
        """
        return self.update_sync_status(sync_metadata_id, 'synced')
    
    def mark_failed(self, sync_metadata_id: str, failure_reason: str) -> SyncMetadata:
        """
        Mark sync metadata as failed with reason.
        
        Args:
            sync_metadata_id: ULID of sync metadata
            failure_reason: Reason for sync failure
            
        Returns:
            Updated SyncMetadata instance
        """
        return self.update_sync_status(sync_metadata_id, 'failed', failure_reason)
    
    def get_pending_syncs(self, 
                         sync_direction: Optional[str] = None,
                         limit: Optional[int] = None) -> List[SyncMetadata]:
        """
        Get all pending sync metadata entries.
        
        Args:
            sync_direction: Filter by sync direction
            limit: Maximum number of results
            
        Returns:
            List of pending SyncMetadata instances
        """
        filters = {'sync_status': 'pending'}
        if sync_direction:
            filters['sync_direction'] = sync_direction
        
        return self.list_entities(
            SyncMetadata,
            filters=filters,
            order_by='created_at',
            limit=limit
        )
    
    def get_failed_syncs(self, 
                        since_hours: Optional[int] = 24,
                        limit: Optional[int] = None) -> List[SyncMetadata]:
        """
        Get failed sync metadata entries.
        
        Args:
            since_hours: Only include failures within this many hours
            limit: Maximum number of results
            
        Returns:
            List of failed SyncMetadata instances
        """
        query = self._session.query(SyncMetadata).filter(
            SyncMetadata.sync_status == 'failed'
        )
        
        if since_hours:
            cutoff_time = datetime.now(timezone.utc) - timezone.utc.localize(
                datetime.fromtimestamp(since_hours * 3600)
            ).utctimetuple()
            query = query.filter(SyncMetadata.created_at >= cutoff_time)
        
        if limit:
            query = query.limit(limit)
        
        return query.order_by(SyncMetadata.created_at.desc()).all()
    
    def get_sync_stats(self) -> Dict[str, Any]:
        """
        Get synchronization statistics.
        
        Returns:
            Dictionary with sync statistics
        """
        stats = {}
        
        # Count by status
        for status in ['pending', 'synced', 'failed', 'local_only']:
            stats[f'{status}_count'] = self.count_entities(
                SyncMetadata, 
                {'sync_status': status}
            )
        
        # Count by direction
        for direction in ['push', 'pull', 'bidirectional']:
            stats[f'{direction}_count'] = self.count_entities(
                SyncMetadata,
                {'sync_direction': direction}
            )
        
        # Recent activity
        recent_syncs = self._session.query(SyncMetadata).filter(
            SyncMetadata.last_sync_at.isnot(None)
        ).order_by(SyncMetadata.last_sync_at.desc()).limit(5).all()
        
        stats['recent_syncs'] = [
            {
                'id': sync.id,
                'status': sync.sync_status,
                'direction': sync.sync_direction,
                'last_sync_at': sync.last_sync_at,
                'remote_id': sync.remote_id
            }
            for sync in recent_syncs
        ]
        
        return stats
    
    def cleanup_old_syncs(self, 
                         older_than_days: int = 30,
                         keep_failed: bool = True) -> int:
        """
        Clean up old sync metadata entries.
        
        Args:
            older_than_days: Remove syncs older than this many days
            keep_failed: Whether to preserve failed syncs
            
        Returns:
            Number of records deleted
        """
        cutoff_time = datetime.now(timezone.utc) - timezone.utc.localize(
            datetime.fromtimestamp(older_than_days * 24 * 3600)
        ).utctimetuple()
        
        query = self._session.query(SyncMetadata).filter(
            SyncMetadata.created_at < cutoff_time
        )
        
        if keep_failed:
            query = query.filter(SyncMetadata.sync_status != 'failed')
        
        # Only delete successfully synced entries to preserve history
        query = query.filter(SyncMetadata.sync_status == 'synced')
        
        count = query.count()
        query.delete()
        
        log.info(f"Cleaned up {count} old sync metadata entries")
        return count
    
    def retry_failed_sync(self, sync_metadata_id: str) -> SyncMetadata:
        """
        Reset a failed sync to pending status for retry.
        
        Args:
            sync_metadata_id: ULID of sync metadata
            
        Returns:
            Updated SyncMetadata instance
        """
        sync_metadata = self.get_by_ulid_or_404(SyncMetadata, sync_metadata_id)
        
        if sync_metadata.sync_status != 'failed':
            raise ValidationError(f"Cannot retry sync with status: {sync_metadata.sync_status}")
        
        return self.update_entity(
            sync_metadata,
            sync_status='pending',
            failure_reason=None
        )
    
    def get_by_remote_id(self, remote_id: str) -> Optional[SyncMetadata]:
        """
        Get sync metadata by remote entity ID.
        
        Args:
            remote_id: Remote entity identifier
            
        Returns:
            SyncMetadata instance or None if not found
        """
        return self._session.query(SyncMetadata).filter(
            SyncMetadata.remote_id == remote_id
        ).first()
    
    def update_remote_info(self, 
                          sync_metadata_id: str,
                          remote_id: Optional[str] = None,
                          remote_url: Optional[str] = None) -> SyncMetadata:
        """
        Update remote entity information.
        
        Args:
            sync_metadata_id: ULID of sync metadata
            remote_id: New remote entity identifier
            remote_url: New remote instance URL
            
        Returns:
            Updated SyncMetadata instance
        """
        sync_metadata = self.get_by_ulid_or_404(SyncMetadata, sync_metadata_id)
        
        update_data = {}
        if remote_id is not None:
            update_data['remote_id'] = remote_id
        if remote_url is not None:
            update_data['remote_url'] = remote_url
        
        return self.update_entity(sync_metadata, **update_data)