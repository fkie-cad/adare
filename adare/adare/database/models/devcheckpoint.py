"""
Development mode checkpoint database model.

This module defines the DevCheckpoint model for tracking external libvirt snapshots
in dev mode. Each checkpoint represents a complete VM state snapshot stored as
external files (memory + disk overlay) with metadata in the database.
"""

from datetime import datetime

import ulid
from sqlalchemy import CHAR, JSON, Column, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import backref, relationship
from sqlalchemy_serializer import SerializerMixin

# Use GlobalBase for global models (shared across projects)
from adare.database.models.global_models import GlobalBase


class DevCheckpoint(SerializerMixin, GlobalBase):
    """
    External libvirt snapshot metadata for dev mode checkpoints.

    Tracks checkpoint state including:
    - External snapshot file locations (memory + disk)
    - Libvirt snapshot metadata name
    - Playbook variable state at checkpoint time
    - Creation timestamp

    Attributes:
        checkpoint_id: Unique ULID identifier for the checkpoint
        session_id: Foreign key to parent DevSession
        name: User-friendly checkpoint name
        description: Optional checkpoint description
        memory_file_path: Path to external memory save file (.save)
        disk_file_path: Path to external disk overlay file (.qcow2)
        snapshot_name: Libvirt snapshot name (for virsh operations)
        variable_state: JSON-serialized playbook variables at checkpoint time
        created_at: Timestamp when checkpoint was created
    """
    __tablename__ = 'dev_checkpoints'
    RELATIONSHIPS_TO_DICT = True

    # Primary key
    checkpoint_id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))

    # Foreign key to session
    session_id = Column(CHAR(26), ForeignKey('dev_sessions.session_id', ondelete='CASCADE'), nullable=False, index=True)
    session = relationship("DevSession", backref=backref("checkpoints", cascade="all, delete-orphan"))

    # Checkpoint metadata
    name = Column(String(255), nullable=False)  # User-friendly name
    description = Column(String, nullable=True)

    # External snapshot file paths
    memory_file_path = Column(String(1024), nullable=False)  # RAM save file
    disk_file_path = Column(String(1024), nullable=False)    # Disk overlay file
    snapshot_name = Column(String(512), nullable=False)      # libvirt snapshot name

    # Variable state (JSON serialized)
    variable_state = Column(JSON, nullable=True)  # Dict[str, Any] from playbook

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Indexes for efficient querying
    __table_args__ = (
        Index('idx_checkpoint_session', 'session_id', 'created_at'),
        Index('idx_checkpoint_name', 'session_id', 'name'),
    )

    def __str__(self):
        return f"DevCheckpoint({self.name})"

    def __repr__(self):
        return (
            f"<DevCheckpoint(id='{self.checkpoint_id}', "
            f"session='{self.session_id}', "
            f"name='{self.name}')>"
        )
