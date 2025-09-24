"""
Database models for the global resource registry system.

This module defines SQLAlchemy ORM classes for managing shared resources
(VMs and environments) that can be used across multiple projects.
These models support the new architecture where:
- VMs are stored in a global registry (~/.adare/vm_registry.db)
- Environments are stored in a global registry (~/.adare/environment_registry.db)
- Projects reference these shared resources rather than owning them
"""

from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, CHAR, Boolean, func, Enum as SAEnum, Text, UniqueConstraint
from sqlalchemy.orm import relationship, backref
import ulid
from pathlib import Path
from sqlalchemy_serializer import SerializerMixin
from sqlalchemy.ext.hybrid import hybrid_property
from adarelib.constants import StatusEnum, VMStatus

from . import Base

StatusEnumType = SAEnum(StatusEnum, name="statusenum")
VMStatusEnumType = SAEnum(VMStatus, name="vmstatusenum")
SyncStatusEnum = SAEnum('pending', 'synced', 'failed', 'local_only', name="syncstatusenum")
ResourceTypeEnum = SAEnum('vm', 'environment', 'template', name="resourcetypeenum")
UsageTypeEnum = SAEnum('active', 'archived', 'deprecated', name="usagetypeenum")


class GlobalVm(SerializerMixin, Base):
    """
    Represents a virtual machine in the global registry.

    VMs are stored globally and can be referenced by multiple projects.
    This replaces the per-project VM storage with a shared resource model.
    """
    __tablename__ = 'global_vm'
    RELATIONSHIPS_TO_DICT = True

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    name = Column(String, nullable=False, unique=True, index=True)
    file = Column(String, nullable=False, unique=True)  # Path relative to ~/.adare/vms/
    hash = Column(String, nullable=False, unique=True, index=True)  # SHA256 hash of VM file
    description = Column(String, nullable=True)

    # VM Technical Details
    vbox_uuid = Column(String, nullable=True, unique=True, index=True)  # VirtualBox VM UUID
    base_snapshot_name = Column(String, nullable=True)  # Name of clean base snapshot
    import_status = Column(VMStatusEnumType, default=VMStatus.IMPORTED)  # VM status in VirtualBox
    last_verified = Column(DateTime, nullable=True)  # Last time VM was verified to exist
    use_snapshots = Column(Boolean, default=True)  # Use snapshot workflow vs import

    # OS Information (embedded instead of foreign key for global registry)
    os_platform = Column(String, nullable=True)  # windows, linux, macos
    os_type = Column(String, nullable=True)  # workstation, server, embedded
    os_distribution = Column(String, nullable=True)  # ubuntu, windows10, centos
    os_version = Column(String, nullable=True)  # 22.04, 10.0.19041, 8.4
    os_language = Column(String, nullable=True)  # en-US, de-DE, etc.
    os_architecture = Column(String, nullable=True)  # x86_64, arm64, i386
    os_details = Column(Text, nullable=True)  # Additional OS details

    # Resource Management
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    created_by = Column(String, nullable=True)  # User who created the VM
    file_size_bytes = Column(Integer, nullable=True)  # VM file size for resource tracking

    # Usage tracking
    usage_count = Column(Integer, default=0)  # How many projects currently use this VM
    last_used = Column(DateTime, nullable=True)  # Last time VM was used in an experiment

    @hybrid_property
    def full_file_path(self):
        """Get the full path to the VM file."""
        from adare.config.configdirectory import VMS_DIR
        return VMS_DIR / self.file

    @hybrid_property
    def os_display_name(self):
        """Get a human-readable OS description."""
        parts = []
        if self.os_distribution:
            parts.append(self.os_distribution)
        if self.os_version:
            parts.append(self.os_version)
        if self.os_language and self.os_language != 'en-US':
            parts.append(f"({self.os_language})")
        if self.os_architecture and self.os_architecture != 'x86_64':
            parts.append(f"[{self.os_architecture}]")
        return " ".join(parts) if parts else "Unknown OS"

    def __str__(self):
        return f"{self.name} ({self.os_display_name})"

    def __repr__(self):
        return f"<GlobalVm(name='{self.name}',os='{self.os_display_name}',hash='{self.hash[:8]}')>"


class GlobalEnvironment(SerializerMixin, Base):
    """
    Represents an environment configuration in the global registry.

    Environments are stored globally and can be referenced by multiple projects.
    This enables sharing of standardized environment setups across projects.
    """
    __tablename__ = 'global_environment'
    RELATIONSHIPS_TO_DICT = True

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    name = Column(String, nullable=False, unique=True, index=True)
    description = Column(String, nullable=True)

    # File Information
    file = Column(String, nullable=False, unique=True)  # Path relative to ~/.adare/environments/
    sha256hash = Column(String, nullable=False, unique=True, index=True)  # Hash of environment file
    file_size_bytes = Column(Integer, nullable=True)  # Environment file size

    # VM Reference
    vm_id = Column(CHAR(26), ForeignKey('global_vm.id', ondelete='RESTRICT'), nullable=False)
    vm = relationship(GlobalVm, backref=backref("environments", cascade="all, delete-orphan"))

    # Environment Configuration
    installations = Column(Text, nullable=True)  # JSON string of post-setup installations
    tags = Column(String, nullable=True)  # Comma-separated tags for searching/filtering

    # Resource Management
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    created_by = Column(String, nullable=True)  # User who created the environment

    # Usage tracking
    usage_count = Column(Integer, default=0)  # How many projects currently use this environment
    last_used = Column(DateTime, nullable=True)  # Last time environment was used

    # Versioning support
    version = Column(String, nullable=True)  # Semantic version (e.g., "1.0.0")
    parent_environment_id = Column(CHAR(26), ForeignKey('global_environment.id'), nullable=True)
    parent_environment = relationship("GlobalEnvironment", remote_side=[id], backref="child_versions")

    @hybrid_property
    def full_file_path(self):
        """Get the full path to the environment file."""
        from adare.config.configdirectory import APPDATA_DIR
        return APPDATA_DIR / 'environments' / self.file

    @hybrid_property
    def tag_list(self):
        """Get tags as a list."""
        return [tag.strip() for tag in (self.tags or "").split(",") if tag.strip()]

    @tag_list.setter
    def tag_list(self, value):
        """Set tags from a list."""
        self.tags = ", ".join(value) if value else None

    @hybrid_property
    def dotnotation(self):
        """Get environment in dot notation for compatibility."""
        return f"global.{self.name}"

    def __str__(self):
        return f"{self.name} (v{self.version or '1.0'})"

    def __repr__(self):
        return f"<GlobalEnvironment(name='{self.name}',vm='{self.vm.name if self.vm else None}',version='{self.version}')>"


class ResourceUsage(SerializerMixin, Base):
    """
    Tracks usage of global resources by projects.

    This table maintains relationships between projects and the global resources
    they use, enabling usage tracking, cleanup, and dependency management.
    """
    __tablename__ = 'resource_usage'
    RELATIONSHIPS_TO_DICT = True

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))

    # Resource identification
    resource_type = Column(ResourceTypeEnum, nullable=False)  # 'vm' or 'environment'
    resource_id = Column(CHAR(26), nullable=False)  # ID of the global resource

    # Project identification
    project_path = Column(String, nullable=False, index=True)  # Absolute path to project
    project_name = Column(String, nullable=True)  # Cached project name for convenience

    # Usage details
    usage_type = Column(UsageTypeEnum, default=UsageTypeEnum.active)  # active, archived, deprecated
    alias_name = Column(String, nullable=True)  # Project-specific alias for the resource
    usage_notes = Column(Text, nullable=True)  # Project-specific notes about resource usage

    # Tracking
    first_used = Column(DateTime, default=func.now())
    last_used = Column(DateTime, default=func.now())
    usage_count = Column(Integer, default=1)  # Number of times resource was used

    # Ensure uniqueness: one usage record per resource per project
    __table_args__ = (
        UniqueConstraint('resource_type', 'resource_id', 'project_path', name='unique_resource_project'),
    )

    @hybrid_property
    def project_directory(self):
        """Get the project directory as a Path object."""
        return Path(self.project_path)

    def __str__(self):
        return f"{self.project_name}:{self.resource_type}:{self.alias_name or self.resource_id}"

    def __repr__(self):
        return f"<ResourceUsage(project='{self.project_name}',resource='{self.resource_type}:{self.resource_id}',type='{self.usage_type}')>"


class ResourceSnapshot(SerializerMixin, Base):
    """
    Tracks snapshots of global VMs for efficient experiment setup.

    Snapshots are created and managed for global VMs to enable fast
    experiment initialization and rollback capabilities.
    """
    __tablename__ = 'resource_snapshot'
    RELATIONSHIPS_TO_DICT = True

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    vm_id = Column(CHAR(26), ForeignKey('global_vm.id', ondelete='CASCADE'), nullable=False)

    # Snapshot identification
    snapshot_name = Column(String, nullable=False)  # VirtualBox snapshot name
    snapshot_type = Column(String, nullable=False)  # base|experiment|backup
    snapshot_uuid = Column(String, nullable=True)  # VirtualBox snapshot UUID if available

    # Snapshot metadata
    description = Column(String, nullable=True)
    created_at = Column(DateTime, default=func.now())
    created_by = Column(String, nullable=True)  # User who created the snapshot

    # Experiment context (if applicable)
    experiment_context = Column(Text, nullable=True)  # JSON string with experiment details
    project_path = Column(String, nullable=True)  # Project that triggered snapshot creation

    # Storage information
    snapshot_size_bytes = Column(Integer, nullable=True)  # Snapshot disk usage

    # Relationships
    vm = relationship(GlobalVm, backref=backref("snapshots", cascade="all, delete-orphan"))

    def __str__(self):
        return f"{self.vm.name}:{self.snapshot_name}"

    def __repr__(self):
        return f"<ResourceSnapshot(vm='{self.vm.name}',name='{self.snapshot_name}',type='{self.snapshot_type}')>"


class GlobalResourceMetadata(SerializerMixin, Base):
    """
    Stores metadata and configuration for the global resource registry system.

    This table tracks system-wide settings, migration history, and registry status.
    """
    __tablename__ = 'global_resource_metadata'
    RELATIONSHIPS_TO_DICT = True

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))

    # Registry information
    registry_version = Column(String, nullable=False)  # Version of registry schema
    created_at = Column(DateTime, default=func.now())
    last_migration = Column(DateTime, nullable=True)  # Last time registry was migrated
    migration_source = Column(String, nullable=True)  # Source of last migration (e.g., "global_db_v1")

    # Configuration
    auto_cleanup_enabled = Column(Boolean, default=True)  # Automatically clean unused resources
    cleanup_threshold_days = Column(Integer, default=30)  # Days before unused resources are cleaned
    max_vm_size_gb = Column(Integer, default=50)  # Maximum allowed VM size
    max_environment_size_mb = Column(Integer, default=100)  # Maximum allowed environment size

    # Statistics (updated periodically)
    total_vms = Column(Integer, default=0)
    total_environments = Column(Integer, default=0)
    total_projects_using = Column(Integer, default=0)
    last_stats_update = Column(DateTime, nullable=True)

    def __str__(self):
        return f"Registry v{self.registry_version}"

    def __repr__(self):
        return f"<GlobalResourceMetadata(version='{self.registry_version}',vms={self.total_vms},envs={self.total_environments})>"