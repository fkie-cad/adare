"""Database models for playbook structure."""

from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text, ForeignKey, JSON, CHAR
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import ulid

from . import Base


class Playbook(Base):
    """Main playbook container linked to experiment."""
    __tablename__ = 'playbook'
    
    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    experiment_id = Column(CHAR(26), ForeignKey('experiment.id', ondelete='CASCADE'), nullable=False)
    
    name = Column(String(255), nullable=False)
    description = Column(Text)
    settings = Column(JSON)  # idle times, timeouts, etc.
    original_yaml_content = Column(Text)  # Full original YAML content for perfect recovery
    version = Column(Integer, default=1)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    experiment = relationship("Experiment", back_populates="playbook")
    items = relationship("PlaybookItem", back_populates="playbook", cascade="all, delete-orphan")


class PlaybookItem(Base):
    """Unified model for actions and blocks with hierarchical support."""
    __tablename__ = 'playbook_item'
    
    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    playbook_id = Column(CHAR(26), ForeignKey('playbook.id', ondelete='CASCADE'), nullable=False)
    parent_id = Column(CHAR(26), ForeignKey('playbook_item.id', ondelete='CASCADE'), nullable=True)
    
    item_type = Column(String(50), nullable=False)  # 'action', 'group_block', 'if_block', etc.
    sequence_order = Column(Integer, nullable=False)
    
    # For actions only
    action_type = Column(String(50))  # 'click', 'keyboard', 'scroll', etc.
    target = Column(JSON)  # action targeting information
    
    # For all items (actions and blocks)
    parameters = Column(JSON, nullable=False)  # type-specific configuration
    conditions = Column(JSON)  # execution conditions
    
    name = Column(String(255))
    description = Column(Text)
    is_enabled = Column(Boolean, default=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    playbook = relationship("Playbook", back_populates="items")
    parent = relationship("PlaybookItem", remote_side=[id], back_populates="children")
    children = relationship("PlaybookItem", back_populates="parent", cascade="all, delete-orphan")
    executions = relationship("ActionExecution", back_populates="playbook_item", cascade="all, delete-orphan")


class ActionExecution(Base):
    """Execution tracking per action step."""
    __tablename__ = 'action_execution'
    
    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    playbook_item_id = Column(CHAR(26), ForeignKey('playbook_item.id'), nullable=False)
    experiment_run_id = Column(CHAR(26), nullable=True)
    
    status = Column(String(20), nullable=False)  # 'pending', 'running', 'success', 'failed', 'skipped'
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    
    result_data = Column(JSON)  # screenshots, coordinates, error details, timing
    error_message = Column(Text)
    attempt_number = Column(Integer, default=1)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    playbook_item = relationship("PlaybookItem", back_populates="executions")