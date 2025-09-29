"""
Global database models for shared resources.

This module defines SQLAlchemy ORM classes for globally shared resources
such as VMs, environments, test functions, and project metadata.
These models are stored in the global database and shared across all projects.
"""

from sqlalchemy import Column, Integer, String, ForeignKey, Table, DateTime, CHAR, Boolean, func, Enum as SAEnum
from sqlalchemy.orm import relationship, backref
import ulid
from pathlib import Path
from sqlalchemy_serializer import SerializerMixin
from sqlalchemy.ext.hybrid import hybrid_property
from adarelib.constants import StatusEnum, VMStatus
from sqlalchemy.orm import declarative_base

# Create separate base for global models
GlobalBase = declarative_base()

StatusEnumType = SAEnum(StatusEnum, name="statusenum")
VMStatusEnumType = SAEnum(VMStatus, name="vmstatusenum")
SyncStatusEnum = SAEnum('pending', 'synced', 'failed', 'local_only', name="syncstatusenum")
SyncDirectionEnum = SAEnum('push', 'pull', 'bidirectional', name="syncdirectionenum")

# Global mapping tables
mapping_environment_tag = Table(
    "mapping_environment_tag",
    GlobalBase.metadata,
    Column("environment_id", ForeignKey("environment.id")),
    Column("tag_id", ForeignKey("tag.id")),
)

mapping_testfunction_testparameter = Table(
    "mapping_testfunction_testparameter",
    GlobalBase.metadata,
    Column("test_function_id", ForeignKey("test_function.id")),
    Column("test_parameter_id", ForeignKey("test_parameter.id")),
)

mapping_postsetupinstallation_environment = Table(
    "mapping_postsetupinstallation_environment",
    GlobalBase.metadata,
    Column("postsetupinstallation_id", ForeignKey("post_setup_installation.id")),
    Column("environment_id", ForeignKey("environment.id")),
)


class SyncMetadata(SerializerMixin, GlobalBase):
    """
    Metadata for tracking synchronization state of entities with remote instances.
    """
    __tablename__ = 'sync_metadata'
    RELATIONSHIPS_TO_DICT = True

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))

    # Sync timing
    last_sync_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=func.now())

    # Sync state
    sync_status = Column(SyncStatusEnum, default='pending')
    sync_direction = Column(SyncDirectionEnum, default='push')
    failure_reason = Column(String, nullable=True)

    # Remote tracking
    remote_id = Column(String, nullable=True)
    remote_url = Column(String, nullable=True)

    def __str__(self):
        return f"SyncMetadata({self.id})"

    def __repr__(self):
        return f"<SyncMetadata(id='{self.id}', status='{self.sync_status}')>"

    @hybrid_property
    def is_synced(self):
        return self.sync_status == 'synced'

    @hybrid_property
    def needs_sync(self):
        return self.sync_status in ['pending', 'failed']


class Tag(SerializerMixin, GlobalBase):
    """
    Tag for categorizing environments and other global entities.
    """
    __tablename__ = 'tag'
    RELATIONSHIPS_TO_DICT = True
    serialize_rules = ('-id',)

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    name = Column(String, nullable=False, unique=True, index=True)

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return f"<Tag(name='{self.name}')>"


class PostSetupInstallation(SerializerMixin, GlobalBase):
    """
    Post-setup installation command for environments.
    """
    __tablename__ = 'post_setup_installation'
    RELATIONSHIPS_TO_DICT = True

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    command = Column(String, nullable=False)
    shell = Column(Boolean, default=False)
    cwd = Column(String, nullable=True, default=None)

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return f"<PostSetupInstallation(name='{self.name}',description='{self.description}',command='{self.command}')>"


class TestParameter(SerializerMixin, GlobalBase):
    """
    Defines a parameter for test functions, including type and description.
    """
    __tablename__ = 'test_parameter'
    RELATIONSHIPS_TO_DICT = True

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    name = Column(String, nullable=False, unique=True, index=True)
    dtype = Column(String, nullable=False)
    description = Column(String, nullable=True)
    optional = Column(Boolean, default=False)

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return f"<TestParameter(name='{self.name}',dtype='{self.dtype}')>"


class TestFunctionFile(SerializerMixin, GlobalBase):
    """
    Represents a file containing one or more test functions, with metadata and hash.
    """
    __tablename__ = 'test_function_file'
    RELATIONSHIPS_TO_DICT = True

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    name = Column(String, nullable=False, unique=True, index=True)
    path = Column(String, unique=True, nullable=False)
    requirements_path = Column(String, nullable=True)
    sha256hash = Column(String, nullable=False)
    description = Column(String, nullable=True, default=None)

    sync_metadata_id = Column(CHAR(26), ForeignKey('sync_metadata.id', ondelete='CASCADE'), nullable=True)
    sync_metadata = relationship("SyncMetadata", backref="test_function_file")

    @hybrid_property
    def num_functions(self):
        return len(self.test_functions)

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return f"<TestFunctionFile(name='{self.name}',description='{self.description}')>"


class TestFunction(SerializerMixin, GlobalBase):
    """
    Represents a test function definition, including its parameters and file association.
    """
    __tablename__ = 'test_function'
    RELATIONSHIPS_TO_DICT = True
    serialize_rules = ('-id',)

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    type = Column(String, nullable=False)
    name = Column(String, nullable=False, index=True)
    description = Column(String, nullable=True)
    sha256hash = Column(String, nullable=False)

    file_id = Column(CHAR(26), ForeignKey('test_function_file.id'), nullable=False)
    file = relationship(TestFunctionFile, backref=backref("test_functions", cascade="all, delete-orphan"))

    parameters = relationship(TestParameter, secondary=mapping_testfunction_testparameter, backref='test_functions')

    @hybrid_property
    def dotnotation(self):
        return f"{Path(self.file.name).stem}.{self.name}"

    @hybrid_property
    def num_parameters(self):
        return len(self.parameters)

    def __str__(self):
        return self.dotnotation

    def __repr__(self):
        return f"<TestFunction(name='{self.dotnotation}',description='{self.description}')>"


class OsInfo(SerializerMixin, GlobalBase):
    """
    Operating system information for VMs and environments.
    """
    __tablename__ = 'os_info'
    RELATIONSHIPS_TO_DICT = True

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    platform = Column(String, nullable=False)
    os = Column(String, nullable=True)
    distribution = Column(String, nullable=True)
    version = Column(String, nullable=True)
    language = Column(String, nullable=True)
    architecture = Column(String, nullable=True, default='x86_64')
    details = Column(String, nullable=True)

    def __str__(self):
        return f"{self.platform} {self.distribution} {self.version}".strip()

    def __repr__(self):
        return f"<OsInfo(platform='{self.platform}', distribution='{self.distribution}', version='{self.version}')>"


class Project(SerializerMixin, GlobalBase):
    """
    Project metadata stored in global database.
    """
    __tablename__ = 'project'
    RELATIONSHIPS_TO_DICT = True

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    name = Column(String, unique=True)
    description = Column(String)
    path = Column(String, unique=True)

    def __repr__(self):
        return f"<Project(name='{self.name}',description='{self.description}',path='{self.path}')>"


class Vm(SerializerMixin, GlobalBase):
    """
    Virtual machine definition stored globally.
    """
    __tablename__ = 'vm'
    RELATIONSHIPS_TO_DICT = True

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    name = Column(String, nullable=False, unique=True, index=True)
    file = Column(String, nullable=False, unique=True)
    hash = Column(String, nullable=False)
    description = Column(String, nullable=True)

    # VirtualBox integration fields
    vbox_uuid = Column(String, nullable=True, unique=True, index=True)
    base_snapshot_name = Column(String, nullable=True)
    import_status = Column(VMStatusEnumType, default=VMStatus.IMPORTED)
    last_verified = Column(DateTime, nullable=True)
    use_snapshots = Column(Boolean, default=True)

    # OS information
    osinfo_id = Column(CHAR(26), ForeignKey('os_info.id', ondelete='RESTRICT'), nullable=True)
    osinfo = relationship(OsInfo, backref=backref("vms"))

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return f"<Vm(name='{self.name}',file='{self.file}',hash='{self.hash}')>"


class VmSnapshot(SerializerMixin, GlobalBase):
    """
    VM snapshot information.
    """
    __tablename__ = 'vm_snapshot'
    RELATIONSHIPS_TO_DICT = True

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    vbox_uuid = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=True, default=func.now())

    vm_id = Column(CHAR(26), ForeignKey('vm.id', ondelete='CASCADE'), nullable=True)
    vm = relationship(Vm, backref=backref("snapshots", cascade="all, delete-orphan"))

    # Optional reference to VM instance for instance-specific snapshots
    vm_instance_id = Column(CHAR(26), ForeignKey('vm_instance.id', ondelete='CASCADE'), nullable=True)
    vm_instance = relationship("VmInstance", backref=backref("snapshots", cascade="all, delete-orphan"))

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return f"<VmSnapshot(name='{self.name}', vm='{self.vm.name if self.vm else None}')>"


class VmInstance(SerializerMixin, GlobalBase):
    """
    VM instance tracking for concurrent experiment support.

    Tracks individual VirtualBox VM instances created from base VMs,
    enabling multiple experiments to run concurrently with the same environment.
    """
    __tablename__ = 'vm_instance'
    RELATIONSHIPS_TO_DICT = True

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))

    # Reference to base VM this instance was created from
    vm_id = Column(CHAR(26), ForeignKey('vm.id', ondelete='CASCADE'), nullable=False)
    vm = relationship(Vm, backref=backref("instances", cascade="all, delete-orphan"))

    # VirtualBox specific identifiers
    vbox_uuid = Column(String, nullable=True, unique=True, index=True)
    instance_name = Column(String, nullable=False, unique=True, index=True)

    # Experiment tracking
    current_experiment_run_id = Column(String, nullable=True, index=True)
    websocket_port = Column(Integer, nullable=True, index=True)

    # Instance lifecycle
    status = Column(String, nullable=False, default='active', index=True)  # active/available/cleanup_pending
    created_at = Column(DateTime, nullable=False, default=func.now())
    last_used_at = Column(DateTime, nullable=False, default=func.now())

    # Snapshot configuration for this instance
    base_snapshot_name = Column(String, nullable=True)
    use_snapshots = Column(Boolean, default=True)

    def __str__(self):
        return str(self.instance_name)

    def __repr__(self):
        return f"<VmInstance(name='{self.instance_name}', vm='{self.vm.name if self.vm else None}', status='{self.status}')>"

    @hybrid_property
    def is_available(self):
        return self.status == 'available'

    @hybrid_property
    def is_active(self):
        return self.status == 'active'

    def mark_available(self):
        """Mark instance as available for reuse."""
        self.status = 'available'
        self.current_experiment_run_id = None
        self.last_used_at = func.now()

    def mark_active(self, experiment_run_id: str):
        """Mark instance as active for an experiment."""
        self.status = 'active'
        self.current_experiment_run_id = experiment_run_id
        self.last_used_at = func.now()

    def mark_cleanup_pending(self):
        """Mark instance for cleanup."""
        self.status = 'cleanup_pending'


class Environment(SerializerMixin, GlobalBase):
    """
    Environment definition stored globally.
    """
    __tablename__ = 'environment'
    RELATIONSHIPS_TO_DICT = True

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    name = Column(String, nullable=False, unique=True, index=True)
    description = Column(String, nullable=True)

    # VM relationship
    vm_id = Column(CHAR(26), ForeignKey('vm.id', ondelete='RESTRICT'), nullable=True)
    vm = relationship(Vm, backref=backref("environments"))

    installations = relationship(PostSetupInstallation, secondary=mapping_postsetupinstallation_environment)

    file = Column(String, nullable=True)
    sha256hash = Column(String, nullable=True)

    created_at = Column(DateTime, nullable=True, default=func.now())

    tags = relationship(Tag, secondary=mapping_environment_tag)

    sync_metadata_id = Column(CHAR(26), ForeignKey('sync_metadata.id', ondelete='CASCADE'), nullable=True)
    sync_metadata = relationship("SyncMetadata", backref="environment")

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return f"<Environment(name='{self.name}',description='{self.description}')>"