"""
Database models for project-specific databases.

This module defines SQLAlchemy ORM classes for project-specific data storage.
Each project gets its own database containing only:
- Experiments and their configurations
- Test functions and results
- References to global resources (VMs, environments)
- Project-specific settings and logs

Global resources (VMs, environments) are stored in separate global registries.
"""

from sqlalchemy import Column, Integer, String, ForeignKey, Table, DateTime, CHAR, Boolean, func, Enum as SAEnum, Text, UniqueConstraint
from sqlalchemy.orm import relationship, backref
import ulid
from pathlib import Path
from sqlalchemy_serializer import SerializerMixin
from sqlalchemy.ext.hybrid import hybrid_property
from adarelib.constants import StatusEnum

from . import Base

StatusEnumType = SAEnum(StatusEnum, name="statusenum")
SyncStatusEnum = SAEnum('pending', 'synced', 'failed', 'local_only', name="syncstatusenum")
SyncDirectionEnum = SAEnum('push', 'pull', 'bidirectional', name="syncdirectionenum")
ResourceTypeEnum = SAEnum('vm', 'environment', 'template', name="resourcetypeenum")

# Mapping tables for many-to-many relationships
mapping_experiment_abstracttest = Table(
    "mapping_experiment_abstracttest",
    Base.metadata,
    Column("experiment_id", ForeignKey("project_experiment.id")),
    Column("abstracttest_id", ForeignKey("project_abstract_test.id")),
)

mapping_experiment_tag = Table(
    "mapping_experiment_tag",
    Base.metadata,
    Column("experiment_id", ForeignKey("project_experiment.id")),
    Column("tag_id", ForeignKey("project_tag.id")),
)

mapping_testfunction_testparameter = Table(
    "mapping_testfunction_testparameter",
    Base.metadata,
    Column("test_function_id", ForeignKey("project_test_function.id")),
    Column("test_parameter_id", ForeignKey("project_test_parameter.id")),
)

mapping_abstracttest_testparameterentry = Table(
    "mapping_abstracttest_testparameterentry",
    Base.metadata,
    Column("abstracttest_id", ForeignKey("project_abstract_test.id")),
    Column("testparameterentry_id", ForeignKey("project_test_parameter_entry.id")),
)

mapping_abstracttest_tool = Table(
    "mapping_abstracttest_tool",
    Base.metadata,
    Column("abstract_test_id", ForeignKey("project_abstract_test.id")),
    Column("tool_id", ForeignKey("project_tool.id")),
)

mapping_project_testfunctionfile = Table(
    "mapping_project_testfunctionfile",
    Base.metadata,
    Column("project_metadata_id", ForeignKey("project_metadata.id")),
    Column("testfunctionfile_id", ForeignKey("project_test_function_file.id")),
)

mapping_usbdrive_experiment = Table(
    "mapping_usbdrive_experiment",
    Base.metadata,
    Column("usbdrive_id", ForeignKey("project_usb_drive.id")),
    Column("experiment_id", ForeignKey("project_experiment.id")),
)


class ProjectMetadata(SerializerMixin, Base):
    """
    Stores metadata about the project itself.

    This replaces the global Project table, containing only project-specific
    information stored within the project's own database.
    """
    __tablename__ = 'project_metadata'
    RELATIONSHIPS_TO_DICT = True

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    name = Column(String, nullable=False, index=True)
    description = Column(String, nullable=True)
    path = Column(String, nullable=False)  # Absolute path to project directory

    # Project configuration
    created_at = Column(DateTime, default=func.now())
    created_by = Column(String, nullable=True)
    version = Column(String, nullable=True, default="1.0.0")

    # Project settings
    auto_cleanup = Column(Boolean, default=True)
    default_vm_ref = Column(String, nullable=True)  # Default global VM reference
    default_env_ref = Column(String, nullable=True)  # Default global environment reference

    # Database schema version for migration support
    schema_version = Column(String, nullable=False, default="1.0.0")

    test_function_files = relationship("ProjectTestFunctionFile", secondary=mapping_project_testfunctionfile, backref='project_metadata')

    def __repr__(self):
        return f"<ProjectMetadata(name='{self.name}',path='{self.path}',version='{self.version}')>"


class GlobalResourceReference(SerializerMixin, Base):
    """
    References to global resources (VMs, environments) used by this project.

    Instead of storing the actual resource data, projects store references
    to resources in the global registries. This enables sharing while
    maintaining project boundaries.
    """
    __tablename__ = 'global_resource_reference'
    RELATIONSHIPS_TO_DICT = True

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))

    # Resource identification
    resource_type = Column(ResourceTypeEnum, nullable=False)  # 'vm' or 'environment'
    global_resource_id = Column(CHAR(26), nullable=False, index=True)  # ID in global registry

    # Project-specific details
    project_alias = Column(String, nullable=True)  # Project-specific name for the resource
    usage_notes = Column(Text, nullable=True)  # Project-specific notes
    configuration_overrides = Column(Text, nullable=True)  # JSON string with project-specific config

    # Usage tracking
    first_used = Column(DateTime, default=func.now())
    last_used = Column(DateTime, default=func.now())
    usage_count = Column(Integer, default=1)

    # Status
    is_active = Column(Boolean, default=True)  # Whether this resource is actively used
    pinned_version = Column(String, nullable=True)  # Pin to specific version if needed

    @hybrid_property
    def display_name(self):
        """Get the display name (alias or resource ID)."""
        return self.project_alias or self.global_resource_id

    def __str__(self):
        return f"{self.resource_type}:{self.display_name}"

    def __repr__(self):
        return f"<GlobalResourceReference(type='{self.resource_type}',id='{self.global_resource_id}',alias='{self.project_alias}')>"


class ProjectExperiment(SerializerMixin, Base):
    """
    Represents an experiment within this project.

    Experiments are project-specific and reference global resources
    rather than containing them directly.
    """
    __tablename__ = 'project_experiment'
    RELATIONSHIPS_TO_DICT = True

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    name = Column(String, nullable=False, unique=True, index=True)
    description = Column(String, nullable=True)

    # File references (within project)
    playbook_file = Column(String, nullable=True)
    metadata_file = Column(String, nullable=True)
    bibtex_file = Column(String, nullable=True)
    markdown_file = Column(String, nullable=True)

    # File hashes for integrity checking
    sha256_playbook = Column(String, nullable=True)
    sha256_metadata = Column(String, nullable=True)
    sha256_bibtex = Column(String, nullable=True)
    sha256_markdown = Column(String, nullable=True)
    sha256 = Column(String, nullable=True)  # Combined hash

    # Timing
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    last_run = Column(DateTime, nullable=True)

    # Status
    status = Column(StatusEnumType, default=StatusEnum.NOT_REACHED)

    # Relationships within project
    tags = relationship("ProjectTag", secondary=mapping_experiment_tag)
    abstract_tests = relationship("ProjectAbstractTest", secondary=mapping_experiment_abstracttest, backref='experiments')
    playbook = relationship("ProjectPlaybook", back_populates="experiment", uselist=False, cascade="all, delete-orphan")

    # Resource references (many-to-many via environment references)
    environment_refs = relationship("ExperimentEnvironmentReference", back_populates="experiment", cascade="all, delete-orphan")
    usb_drives = relationship("ProjectUSBDrive", secondary=mapping_usbdrive_experiment)

    # Sync metadata for remote synchronization
    sync_metadata_id = Column(CHAR(26), ForeignKey('project_sync_metadata.id', ondelete='CASCADE'), nullable=True)
    sync_metadata = relationship("ProjectSyncMetadata", backref="experiment")

    @hybrid_property
    def environment_names(self):
        """Get names of environments used by this experiment."""
        return [ref.environment_alias or ref.global_environment_id for ref in self.environment_refs]

    def __str__(self):
        return self.name

    def __repr__(self):
        return f"<ProjectExperiment(name='{self.name}',status='{self.status}',envs={len(self.environment_refs)})>"


class ExperimentEnvironmentReference(SerializerMixin, Base):
    """
    Links experiments to global environments with project-specific configuration.

    This replaces the direct experiment-environment relationship with a reference
    system that allows project-specific environment configuration.
    """
    __tablename__ = 'experiment_environment_reference'
    RELATIONSHIPS_TO_DICT = True

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))

    # Relationships
    experiment_id = Column(CHAR(26), ForeignKey('project_experiment.id', ondelete='CASCADE'), nullable=False)
    experiment = relationship("ProjectExperiment", back_populates="environment_refs")

    # Global resource reference
    global_environment_id = Column(CHAR(26), nullable=False, index=True)  # ID in global environment registry

    # Project-specific configuration
    environment_alias = Column(String, nullable=True)  # Project-specific name
    configuration_overrides = Column(Text, nullable=True)  # JSON string with overrides
    execution_order = Column(Integer, nullable=True)  # Order for multi-environment experiments

    # Status tracking
    last_used = Column(DateTime, nullable=True)
    is_primary = Column(Boolean, default=False)  # Primary environment for this experiment

    def __str__(self):
        return f"{self.experiment.name}:{self.environment_alias or self.global_environment_id}"

    def __repr__(self):
        return f"<ExperimentEnvironmentReference(exp='{self.experiment.name}',env='{self.global_environment_id}',alias='{self.environment_alias}')>"


class ProjectTestFunctionFile(SerializerMixin, Base):
    """
    Represents a test function file within this project.
    """
    __tablename__ = 'project_test_function_file'
    RELATIONSHIPS_TO_DICT = True

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    name = Column(String, nullable=False, unique=True, index=True)
    path = Column(String, unique=True, nullable=False)  # Relative to project directory
    requirements_path = Column(String, nullable=True)
    sha256hash = Column(String, nullable=False)
    description = Column(String, nullable=True)

    # Sync metadata
    sync_metadata_id = Column(CHAR(26), ForeignKey('project_sync_metadata.id', ondelete='CASCADE'), nullable=True)
    sync_metadata = relationship("ProjectSyncMetadata", backref="testfunction_file")

    @hybrid_property
    def num_functions(self):
        return len(self.test_functions)

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return f"<ProjectTestFunctionFile(name='{self.name}',functions={self.num_functions})>"


class ProjectTestFunction(SerializerMixin, Base):
    """
    Represents a test function within this project.
    """
    __tablename__ = 'project_test_function'
    RELATIONSHIPS_TO_DICT = True
    serialize_rules = ('-id',)

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    type = Column(String, nullable=False)
    name = Column(String, nullable=False, index=True)
    description = Column(String, nullable=True)
    sha256hash = Column(String, nullable=False)

    file_id = Column(CHAR(26), ForeignKey('project_test_function_file.id'), nullable=False)
    file = relationship(ProjectTestFunctionFile, backref=backref("test_functions", cascade="all, delete-orphan"))

    parameters = relationship("ProjectTestParameter", secondary=mapping_testfunction_testparameter, backref='test_functions')

    @hybrid_property
    def dotnotation(self):
        return f"{Path(self.file.name).stem}.{self.name}"

    @hybrid_property
    def num_parameters(self):
        return len(self.parameters)

    def __str__(self):
        return self.dotnotation

    def __repr__(self):
        return f"<ProjectTestFunction(name='{self.dotnotation}',params={self.num_parameters})>"


class ProjectTestParameter(SerializerMixin, Base):
    """
    Represents a test parameter within this project.
    """
    __tablename__ = 'project_test_parameter'
    RELATIONSHIPS_TO_DICT = True

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    name = Column(String, nullable=False, index=True)
    dtype = Column(String, nullable=False)
    description = Column(String, nullable=True)

    def __str__(self):
        return f"{self.name}({self.dtype})"

    def __repr__(self):
        return f"<ProjectTestParameter(name='{self.name}',dtype='{self.dtype}')>"

    entries = relationship("ProjectTestParameterEntry", back_populates="parameter")


class ProjectTestParameterEntry(SerializerMixin, Base):
    """
    Stores a value entry for a test parameter within this project.
    """
    __tablename__ = 'project_test_parameter_entry'
    RELATIONSHIPS_TO_DICT = True
    serialize_rules = ('-id', '-parameter_id')

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    parameter_id = Column(CHAR(26), ForeignKey('project_test_parameter.id', ondelete='CASCADE'), nullable=False)
    value = Column(String, nullable=False)

    parameter = relationship("ProjectTestParameter", back_populates="entries")

    def __str__(self):
        return str(self.parameter)

    def __repr__(self):
        return f"<ProjectTestParameterEntry(parameter='{self.parameter}',value='{self.value}')>"


class ProjectAbstractTest(SerializerMixin, Base):
    """
    Represents an abstract test within this project.
    """
    __tablename__ = 'project_abstract_test'
    RELATIONSHIPS_TO_DICT = True

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    test_function_id = Column(CHAR(26), ForeignKey('project_test_function.id', ondelete='CASCADE'), nullable=False)
    test_function = relationship(ProjectTestFunction, backref=backref("abstract_tests", cascade="all, delete-orphan"))

    parameter_entries = relationship("ProjectTestParameterEntry", secondary=mapping_abstracttest_testparameterentry)
    tools = relationship("ProjectTool", secondary=mapping_abstracttest_tool)

    def __str__(self):
        return f"{self.test_function.dotnotation}({len(self.parameter_entries)} params)"

    def __repr__(self):
        return f"<ProjectAbstractTest(function='{self.test_function.dotnotation}',params={len(self.parameter_entries)})>"


class ProjectTool(SerializerMixin, Base):
    """
    Represents an external tool used in this project.
    """
    __tablename__ = 'project_tool'
    RELATIONSHIPS_TO_DICT = True
    serialize_rules = ('-id',)

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    name = Column(String, nullable=False)
    command = Column(String, nullable=False)
    description = Column(String, nullable=True)

    def __str__(self):
        return self.name

    def __repr__(self):
        return f"<ProjectTool(name='{self.name}',command='{self.command}')>"


class ProjectTag(SerializerMixin, Base):
    """
    Represents a tag within this project.
    """
    __tablename__ = 'project_tag'
    RELATIONSHIPS_TO_DICT = True
    serialize_rules = ('-id',)

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    name = Column(String, nullable=False, unique=True, index=True)
    description = Column(String, nullable=True)

    def __str__(self):
        return self.name

    def __repr__(self):
        return f"<ProjectTag(name='{self.name}')>"


class ProjectPlaybook(SerializerMixin, Base):
    """
    Represents a playbook within this project.
    """
    __tablename__ = 'project_playbook'
    RELATIONSHIPS_TO_DICT = True
    serialize_rules = ('-experiment',)

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    experiment_id = Column(CHAR(26), ForeignKey('project_experiment.id', ondelete='CASCADE'), nullable=False)
    experiment = relationship("ProjectExperiment", back_populates="playbook")

    # Playbook content (stored as JSON string)
    actions = Column(Text, nullable=True)  # JSON string of playbook actions
    metadata = Column(Text, nullable=True)  # JSON string of playbook metadata

    def __str__(self):
        return f"Playbook for {self.experiment.name}"

    def __repr__(self):
        return f"<ProjectPlaybook(experiment='{self.experiment.name}')>"


class ProjectUSBDrive(SerializerMixin, Base):
    """
    Represents a USB drive configuration within this project.
    """
    __tablename__ = 'project_usb_drive'
    RELATIONSHIPS_TO_DICT = True

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    name = Column(String, nullable=False)
    vendor_id = Column(String, nullable=True)
    product_id = Column(String, nullable=True)
    manufacturer = Column(String, nullable=True)
    product = Column(String, nullable=True)
    serial_number = Column(String, nullable=True)

    def __str__(self):
        return self.name

    def __repr__(self):
        return f"<ProjectUSBDrive(name='{self.name}',vendor='{self.vendor_id}')>"


class ProjectSyncMetadata(SerializerMixin, Base):
    """
    Synchronization metadata for this project.
    """
    __tablename__ = 'project_sync_metadata'
    RELATIONSHIPS_TO_DICT = True

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))

    # Remote sync information
    remote_url = Column(String, nullable=True)
    remote_id = Column(String, nullable=True)
    sync_direction = Column(SyncDirectionEnum, nullable=True)

    # Sync status
    last_sync = Column(DateTime, nullable=True)
    sync_status = Column(SyncStatusEnum, default=SyncStatusEnum.local_only)
    is_published = Column(Boolean, default=False)

    # Conflict resolution
    local_hash = Column(String, nullable=True)
    remote_hash = Column(String, nullable=True)
    conflict_resolution = Column(String, nullable=True)

    def __str__(self):
        return f"Sync to {self.remote_url or 'local'}"

    def __repr__(self):
        return f"<ProjectSyncMetadata(status='{self.sync_status}',url='{self.remote_url}')>"


class ProjectExperimentRun(SerializerMixin, Base):
    """
    Represents a single run of an experiment within this project.
    """
    __tablename__ = 'project_experiment_run'
    RELATIONSHIPS_TO_DICT = True

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))

    # Experiment reference
    experiment_id = Column(CHAR(26), ForeignKey('project_experiment.id', ondelete='CASCADE'), nullable=False)
    experiment = relationship("ProjectExperiment", backref=backref("runs", cascade="all, delete-orphan"))

    # Environment reference used for this run
    environment_ref_id = Column(CHAR(26), ForeignKey('experiment_environment_reference.id'), nullable=False)
    environment_ref = relationship("ExperimentEnvironmentReference")

    # Run details
    started_at = Column(DateTime, default=func.now())
    completed_at = Column(DateTime, nullable=True)
    status = Column(StatusEnumType, default=StatusEnum.IN_PROGRESS)

    # Results and logs
    results_path = Column(String, nullable=True)  # Path to results directory (relative to project)
    log_path = Column(String, nullable=True)  # Path to log file (relative to project)

    # Execution context
    executed_by = Column(String, nullable=True)  # User who executed the run
    execution_notes = Column(Text, nullable=True)  # Notes about this specific run

    # Error handling
    error_message = Column(Text, nullable=True)
    error_details = Column(Text, nullable=True)  # JSON string with detailed error info

    @hybrid_property
    def duration_seconds(self):
        """Calculate run duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    def __str__(self):
        return f"{self.experiment.name} run {self.id[:8]}"

    def __repr__(self):
        return f"<ProjectExperimentRun(experiment='{self.experiment.name}',status='{self.status}',duration={self.duration_seconds})>"