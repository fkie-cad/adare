"""
Development mode session database models.

This module defines the DevSession model for tracking persistent dev mode sessions
across CLI invocations. Sessions are stored globally in the database.
"""

import ulid
from sqlalchemy import CHAR, Column, DateTime, String, func
from sqlalchemy_serializer import SerializerMixin

# Use GlobalBase for global models (shared across projects)
from adare.database.models.global_models import GlobalBase


class DevSession(SerializerMixin, GlobalBase):
    """
    Persistent dev mode session metadata.

    Tracks active development sessions to support:
    - Session persistence across CLI restarts
    - Multi-session management
    - Stale session cleanup
    - Status tracking

    Attributes:
        session_id: Unique ULID identifier for the session
        project_path: Path to the ADARE project
        experiment_name: Name of the experiment being developed
        environment_name: Name of the VM environment
        vm_name: Name of the VM instance (for cleanup verification)
        overlay_disk_path: Path to the experiment overlay disk (prevents base disk deletion)
        run_directory_path: Path to the experiment run directory (prevents "None" directories)
        status: Session status (running, stopped, crashed)
        created_at: Timestamp when session was created
        updated_at: Timestamp of last status update
    """
    __tablename__ = 'dev_sessions'
    RELATIONSHIPS_TO_DICT = True

    session_id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    project_path = Column(String(512), nullable=False, index=True)
    experiment_name = Column(String(255), nullable=False)
    environment_name = Column(String(255), nullable=False)
    vm_name = Column(String(255), nullable=False)
    overlay_disk_path = Column(String(1024), nullable=True)  # Path to experiment overlay disk
    run_directory_path = Column(String(1024), nullable=True)  # Path to the experiment run directory
    status = Column(String(20), default='running', nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())
    cached_start_command = Column(String(1024), nullable=True)  # Cached adarevm start command

    def __str__(self):
        return f"DevSession({self.session_id})"

    def __repr__(self):
        return (
            f"<DevSession(id='{self.session_id}', "
            f"experiment='{self.experiment_name}', "
            f"environment='{self.environment_name}', "
            f"status='{self.status}')>"
        )
