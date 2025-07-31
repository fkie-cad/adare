"""
Database models for the experiment management system.

This module defines SQLAlchemy ORM classes representing the core entities
of the application, such as experiments, environments, test functions, results,
network drives, and related mapping tables. These models are used to map
Python objects to database tables and manage relationships between entities.
"""

from sqlalchemy import Column, Integer, String, ForeignKey, Table, DateTime, CHAR, Boolean, func, Enum as SAEnum
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

mapping_experiment_abstracttest = Table(
    "mapping_experiment_abstracttest",
    Base.metadata,
    Column("experiment_id", ForeignKey("experiment.id")),
    Column("abstracttest_id", ForeignKey("abstract_test.id")),
)

mapping_experiment_tag = Table(
    "mapping_experiment_tag",
    Base.metadata,
    Column("experiment_id", ForeignKey("experiment.id")),
    Column("tag_id", ForeignKey("tag.id")),
)
mapping_environment_tag = Table(
    "mapping_environment_tag",
    Base.metadata,
    Column("environment_id", ForeignKey("environment.id")),
    Column("tag_id", ForeignKey("tag.id")),
)

mapping_testfunction_testparameter = Table(
    "mapping_testfunction_testparameter",
    Base.metadata,
    Column("test_function_id", ForeignKey("test_function.id")),
    Column("test_parameter_id", ForeignKey("test_parameter.id")),
)

mapping_abstracttest_testparameterentry = Table(
    "mapping_abstracttest_testparameterentry",
    Base.metadata,
    Column("abstracttest_id", ForeignKey("abstract_test.id")),
    Column("testparameterentry_id", ForeignKey("test_parameter_entry.id")),
)
mapping_postsetupinstallation_environment = Table(
    "mapping_postsetupinstallation_environment",
    Base.metadata,
    Column("postsetupinstallation_id", ForeignKey("post_setup_installation.id")),
    Column("environment_id", ForeignKey("environment.id")),
)
mapping_usbdrive_experiment = Table(
    "mapping_usbdrive_experiment",
    Base.metadata,
    Column("usbdrive_id", ForeignKey("usb_drive.id")),
    Column("experiment_id", ForeignKey("experiment.id")),
)
mapping_smbdrive_smbshare = Table(
    "mapping_smbdrive_smbshare",
    Base.metadata,
    Column("smbdrive_id", ForeignKey("smb_drive.id")),
    Column("smbshare_id", ForeignKey("smb_share.id")),
)
mapping_smbdrive_user = Table(
    "mapping_smbdrive_user",
    Base.metadata,
    Column("smbdrive_id", ForeignKey("smb_drive.id")),
    Column("user_id", ForeignKey("network_drive_user.id")),
)
mapping_nfsdrive_nfsshare = Table(
    "mapping_nfsdrive_nfsshare",
    Base.metadata,
    Column("nfsdrive_id", ForeignKey("nfs_drive.id")),
    Column("nfsshare_id", ForeignKey("nfs_share.id")),
)
mapping_experiment_environment = Table(
    "mapping_experiment_environment",
    Base.metadata,
    Column("experiment_id", ForeignKey("experiment.id")),
    Column("environment_id", ForeignKey("environment.id")),
)
mapping_abstracttest_tool = Table(
    "mapping_abstracttest_tool",
    Base.metadata,
    Column("abstract_test_id", ForeignKey("abstract_test.id")),
    Column("tool_id", ForeignKey("tool.id")),
)
mapping_project_testfunctionfile = Table(
    "mapping_project_testfunctionfile",
    Base.metadata,
    Column("project_id", ForeignKey("project.id")),
    Column("test_function_file_id", ForeignKey("test_function_file.id")),
)


class SyncMetadata(SerializerMixin, Base):
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
    
    # Remote tracking (replaces old remote_id, remote_url, in_request, published)
    remote_id = Column(String, nullable=True)
    remote_url = Column(String, nullable=True)

    def __str__(self):
        return f"SyncMetadata({self.id})"

    def __repr__(self):
        return f"<SyncMetadata(id='{self.id}', status='{self.sync_status}', published={self.published})>"

    @hybrid_property
    def is_synced(self):
        return self.sync_status == 'synced'

    @hybrid_property
    def needs_sync(self):
        return self.sync_status in ['pending', 'failed']


class Status(SerializerMixin, Base):
    """
    Represents a status for test results or events (e.g., success, failure, pending).
    """
    __tablename__ = 'status'
    RELATIONSHIPS_TO_DICT = True

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    name = Column(String, nullable=False, unique=True, index=True)

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return f"<Status(name='{self.name}')>"


class Tag(SerializerMixin, Base):
    """
    Tag for categorizing experiments, environments, and other entities.
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


class PostSetupInstallation(SerializerMixin, Base):
    """
    Post-setup installation command for environments, specifying commands to run after environment setup.
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


class Result(SerializerMixin, Base):
    """
    Stores the result of a test, including status and optional details.
    """
    __tablename__ = 'result'
    RELATIONSHIPS_TO_DICT = True
    serialize_rules = ('-id', '-status_id')

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    status_id = Column(CHAR(26), ForeignKey('status.id', ondelete='CASCADE'), nullable=False, index=True)
    details = Column(String, nullable=True)

    def __init__(self, *args, status=None, **kwargs):
        if status is not None:
            kwargs['status_id'] = status
        super().__init__(*args, **kwargs)

    @property
    def status(self):
        # Return the status_id for compatibility
        return self.status_id

    @status.setter
    def status(self, value):
        self.status_id = value

    def __str__(self):
        return str(self.status)

    def __repr__(self):
        return f"<Result(status='{self.status}',details='{self.details}')>"


class TestParameter(SerializerMixin, Base):
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

    entries = relationship("TestParameterEntry", back_populates="parameter")


class TestParameterEntry(SerializerMixin, Base):
    """
    Stores a value entry for a test parameter, used in test execution.
    """
    __tablename__ = 'test_parameter_entry'
    RELATIONSHIPS_TO_DICT = True
    serialize_rules = ('-id', '-parameter_id')

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    parameter_id = Column(CHAR(26), ForeignKey('test_parameter.id', ondelete='CASCADE'), nullable=False)
    value = Column(String, nullable=False)

    parameter = relationship("TestParameter", back_populates="entries")

    def __str__(self):
        return str(self.parameter)

    def __repr__(self):
        return f"<TestParameterEntry(parameter='{self.parameter}',value='{self.value}')>"


class TestFunctionFile(SerializerMixin, Base):
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
    sync_metadata = relationship("SyncMetadata", backref="testfunction_file")

    @hybrid_property
    def num_functions(self):
        return len(self.test_functions)

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return f"<TestFunctionFile(name='{self.name}',description='{self.description}')>"


class TestFunction(SerializerMixin, Base):
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


class Tool(SerializerMixin, Base):
    """
    Represents an external tool or command that can be used in tests or setups.
    """
    __tablename__ = 'tool'
    RELATIONSHIPS_TO_DICT = True
    serialize_rules = ('-id',)

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    name = Column(String)
    command = Column(String)

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return f"<Tool(name='{self.name}',command='{self.command}')>"


class AbstractTest(SerializerMixin, Base):
    """
    Represents an abstract test, linking to a test function, parameters, and required tools.
    """
    __tablename__ = 'abstract_test'
    RELATIONSHIPS_TO_DICT = True

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    name = Column(String)
    description = Column(String)

    testfunction = relationship(TestFunction, backref=backref("abstract_tests", cascade="all, delete-orphan"))
    testfunction_id = Column(CHAR(26), ForeignKey('test_function.id', ondelete='SET NULL'), nullable=True)

    parameters = relationship(TestParameterEntry, secondary=mapping_abstracttest_testparameterentry)

    depends_on_tool = relationship(Tool, secondary=mapping_abstracttest_tool)

    remote_id = Column(String, nullable=True, default=None)

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return f"<AbstractTest(name='{self.name}',test_function='{self.test_function}')>"


class OsInfo(SerializerMixin, Base):
    """
    Stores information about an operating system, such as platform, version, and architecture.
    """
    __tablename__ = 'os_info'
    RELATIONSHIPS_TO_DICT = True
    serialize_rules = ('-id', '-platform')

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))

    platform = Column(String, nullable=False)
    os = Column(String)
    distribution = Column(String)
    version = Column(String)
    language = Column(String)
    architecture = Column(String)
    details = Column(String)

    def __str__(self):
        lang = self.language if self.language else '-'
        arch = self.architecture if self.architecture else '-'
        if lang != '-' or arch != '-':
            return f'{self.os} - {self.distribution} {self.version} ({lang},{arch})'
        return f'{self.os} - {self.distribution} {self.version}'

    def __repr__(self):
        return f"<OsInfo(os='{self.os}',distribution='{self.distribution}',version='{self.version}',language='{self.language}',architecture='{self.architecture}')>"


class LogFile(SerializerMixin, Base):
    """
    Represents a log file generated during experiment runs or environment setup.
    """
    __tablename__ = 'log_file'
    RELATIONSHIPS_TO_DICT = True

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    name = Column(String)
    path = Column(String, unique=True)

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return f"<LogFile(name='{self.name}',path='{self.path}')>"


class NetworkDriveUser(SerializerMixin, Base):
    """
    Represents a user for network drive authentication (credentials should be hashed).
    """
    __tablename__ = 'network_drive_user'
    RELATIONSHIPS_TO_DICT = True

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    username = Column(String, nullable=False, unique=True, index=True)
    password = Column(String, nullable=False)  # TODO: Store hashed passwords only!

    def __str__(self):
        return str(self.username)

    def __repr__(self):
        return f"<NetworkDriveUser(username='{self.username}',password='{self.password}')>"


class SMBShare(SerializerMixin, Base):
    """
    Represents an SMB share, including local and remote paths and associated user.
    """
    __tablename__ = 'smb_share'
    RELATIONSHIPS_TO_DICT = True

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    name = Column(String)
    local_path = Column(String)
    remote_path = Column(String)
    user_id = Column(CHAR(26), ForeignKey('network_drive_user.id', ondelete='SET NULL'))
    user = relationship("NetworkDriveUser", backref=backref("smbdrives", cascade="all, delete-orphan"))

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return f"<SMBShare(name='{self.name}',local_path='{self.local_path}',remote_path='{self.remote_path}',user='{self.user}')>"


class NFSShare(SerializerMixin, Base):
    """
    Represents an NFS share, including allowed hosts and paths.
    """
    __tablename__ = 'nfs_share'
    RELATIONSHIPS_TO_DICT = True

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    name = Column(String)
    local_path = Column(String)
    remote_path = Column(String)
    allowed_hosts = Column(String)

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return f"<NFSShare(name='{self.name}',local_path='{self.local_path}',remote_path='{self.remote_path}',allowed_hosts='{self.allowed_hosts}')>"


class SMBDrive(SerializerMixin, Base):
    """
    Represents an SMB drive, which can have multiple shares and users.
    """
    __tablename__ = 'smb_drive'
    RELATIONSHIPS_TO_DICT = True

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    name = Column(String, unique=True)
    shares = relationship(SMBShare, secondary=mapping_smbdrive_smbshare)
    users = relationship(NetworkDriveUser, secondary=mapping_smbdrive_user)
    workgroup = Column(String)

    def __str__(self):
        return str(self.name)


class NFSDrive(SerializerMixin, Base):
    """
    Represents an NFS drive, which can have multiple shares.
    """
    __tablename__ = 'nfs_drive'
    RELATIONSHIPS_TO_DICT = True

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    name = Column(String, unique=True)
    shares = relationship(NFSShare, secondary=mapping_nfsdrive_nfsshare)

    def __str__(self):
        return str(self.name)


class USBDrive(SerializerMixin, Base):
    """
    Represents a USB drive, including hardware identifiers and manufacturer info.
    """
    __tablename__ = 'usb_drive'
    RELATIONSHIPS_TO_DICT = True

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    name = Column(String)
    vendor_id = Column(String)
    product_id = Column(String)
    manufacturer = Column(String)
    product = Column(String)
    serial_number = Column(String)


class Project(SerializerMixin, Base):
    """
    Represents a project, grouping test function files and environments.
    """
    __tablename__ = 'project'
    RELATIONSHIPS_TO_DICT = True

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    name = Column(String, unique=True)
    description = Column(String)
    path = Column(String, unique=True)

    test_function_files = relationship(TestFunctionFile, secondary=mapping_project_testfunctionfile, backref='projects')

    @hybrid_property
    def environments_names(self):
        return [env.name for env in self.environments]

    def __repr__(self):
        return f"<Project(name='{self.name}',description='{self.description}',path='{self.path}')>"


class Vm(SerializerMixin, Base):
    """
    Represents a virtual machine, including its file path, OS info, and project association.
    """
    __tablename__ = 'vm'
    RELATIONSHIPS_TO_DICT = True

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    name = Column(String, nullable=False, unique=True, index=True)
    file = Column(String, nullable=False, unique=True)
    hash = Column(String, nullable=False)
    description = Column(String, nullable=True)

    osinfo_id = Column(CHAR(26), ForeignKey('os_info.id', ondelete='RESTRICT'), nullable=False)
    osinfo = relationship(OsInfo, backref=backref("environments", cascade="all, delete-orphan"))


class Environment(SerializerMixin, Base):
    """
    Represents a test environment, including OS info, project, and setup details.
    """
    __tablename__ = 'environment'
    RELATIONSHIPS_TO_DICT = True

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    name = Column(String, nullable=False, unique=True, index=True)
    description = Column(String, nullable=True)

    # VM relationship
    vm_id = Column(CHAR(26), ForeignKey('vm.id', ondelete='RESTRICT'), nullable=False)
    vm = relationship(Vm, backref=backref("environments", cascade="all, delete-orphan"))

    project_id = Column(CHAR(26), ForeignKey('project.id', ondelete='CASCADE'), nullable=False)
    project = relationship(Project, backref=backref("environments", cascade="all, delete-orphan"))

    installations = relationship(PostSetupInstallation, secondary=mapping_postsetupinstallation_environment)

    file = Column(String, nullable=True)
    sha256hash = Column(String, nullable=True)

    created_at = Column(DateTime, nullable=True, default=func.now())

    tags = relationship(Tag, secondary=mapping_environment_tag)

    sync_metadata_id = Column(CHAR(26), ForeignKey('sync_metadata.id', ondelete='CASCADE'), nullable=True)
    sync_metadata = relationship("SyncMetadata", backref="environment")

    @hybrid_property
    def ulid(self):
        """Provide ulid property that maps to the id field for consistency."""
        return self.id

    @ulid.setter
    def ulid(self, value):
        """Allow setting ulid which maps to the id field."""
        self.id = value

    @hybrid_property
    def dotnotation(self):
        return f'{self.project.name}.{self.name}'

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        vm_name = self.vm.name if self.vm else 'None'
        return f"<Environment(name='{self.name}',osinfo='{self.osinfo}',vm='{vm_name}')>"


class Experiment(SerializerMixin, Base):
    """
    Represents an experiment, including metadata, tags, environments, and test sets.
    """
    __tablename__ = 'experiment'
    RELATIONSHIPS_TO_DICT = True

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    name = Column(String, nullable=False, unique=True, index=True)

    description = Column(String, nullable=True)

    tags = relationship(Tag, secondary=mapping_experiment_tag)
    abstract_tests = relationship(AbstractTest, secondary=mapping_experiment_abstracttest, backref='experiments')
    playbook = relationship("Playbook", back_populates="experiment", uselist=False, cascade="all, delete-orphan")

    playbook_file = Column(String, nullable=True)
    testset_file = Column(String, nullable=True)
    metadata_file = Column(String, nullable=True)
    bibtex_file = Column(String, nullable=True, default=None)
    markdown_file = Column(String, nullable=True, default=None)

    sha256_playbook = Column(String, nullable=True)
    sha256_testset = Column(String, nullable=True)
    sha256_metadata = Column(String, nullable=True)
    sha256_bibtex = Column(String, nullable=True)
    sha256_markdown = Column(String, nullable=True)
    sha256 = Column(String, nullable=True)

    smbdrive_id = Column(CHAR(26), ForeignKey('smb_drive.id', ondelete='SET NULL'), nullable=True)
    smbdrive = relationship(SMBDrive)
    nfsdrive_id = Column(CHAR(26), ForeignKey('nfs_drive.id', ondelete='SET NULL'), nullable=True)
    nfsdrive = relationship(NFSDrive)
    usbdrives = relationship(USBDrive, secondary=mapping_usbdrive_experiment)

    environments = relationship(Environment, secondary=mapping_experiment_environment, backref='experiments')

    created_at = Column(DateTime, nullable=True, default=func.now())

    sync_metadata_id = Column(CHAR(26), ForeignKey('sync_metadata.id', ondelete='CASCADE'), nullable=True)
    sync_metadata = relationship("SyncMetadata", backref="experiment")

    @hybrid_property
    def environments_names(self):
        return [env.name for env in self.environments]

    @hybrid_property
    def ulid(self):
        """Provide ulid property that maps to the id field for consistency."""
        return self.id

    @ulid.setter
    def ulid(self, value):
        """Allow setting ulid which maps to the id field."""
        self.id = value

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return f"<Experiment(name='{self.name}')>"


class Event(SerializerMixin, Base):
    """
    Base class for events occurring during experiment runs (polymorphic).
    """
    __tablename__ = 'event'
    RELATIONSHIPS_TO_DICT = True

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    event_type = Column(String)
    category = Column(String)
    experiment_run_id = Column(String, ForeignKey('experiment_run.id', ondelete='CASCADE'))
    experiment_run = relationship("ExperimentRun", backref=backref("events", cascade="all, delete-orphan"))
    status = Column(StatusEnumType, default=StatusEnum.PENDING)
    error = Column(String)
    stage = Column(Boolean, default=False)
    group_key = Column(String)
    stage_in_run_id = Column(CHAR(26), ForeignKey('stage_in_run.id', ondelete='SET NULL'), nullable=True, default=None)
    stage_in_run = relationship("StageInRun", backref=backref("events", cascade="all, delete-orphan"))

    timestamp = Column(DateTime)

    @hybrid_property
    def stage_submessage(self):
        return None

    @hybrid_property
    def stage_result(self):
        return None

    @hybrid_property
    def ulid(self):
        """Provide ulid property that maps to the id field for consistency."""
        return self.id

    @ulid.setter
    def ulid(self, value):
        """Allow setting ulid which maps to the id field."""
        self.id = value

    __mapper_args__ = {
        'polymorphic_identity': 'event',
        'polymorphic_on': event_type
    }


class CommandEvent(Event):
    """
    Event representing the execution of a command during an experiment run.
    """
    __tablename__ = 'command_events'
    __mapper_args__ = {
        'polymorphic_identity': 'command_event',
    }
    id = Column(CHAR(26), ForeignKey('event.id'), primary_key=True)
    name = Column(String)
    command = Column(String)
    returncode = Column(Integer)
    stdout = Column(String)

    @hybrid_property
    def stage_submessage(self):
        name, args = self.command.split(' ', 1)
        return f'Running {self.name} with arguments {args}'

    @hybrid_property
    def stage_result(self):
        return None


class TestEvent(Event):
    """
    Event representing the execution of a test during an experiment run.
    """
    __tablename__ = 'test_events'
    __mapper_args__ = {
        'polymorphic_identity': 'test_event',
    }
    id = Column(CHAR(26), ForeignKey('event.id'), primary_key=True)
    abstract_test_id = Column(CHAR(26), ForeignKey('abstract_test.id'), nullable=True)
    result_id = Column(CHAR(26), ForeignKey('result.id'), nullable=True)
    abstract_test = relationship(AbstractTest, backref=backref("test_events", cascade="all, delete-orphan"))
    result = relationship(Result)

    def __str__(self):
        return str(self.abstract_test.name)

    def __repr__(self):
        return f"<TestEvent(test_name='{self.abstract_test.name}',result='{self.result}')>"

    @hybrid_property
    def stage_submessage(self):
        return f'{self.abstract_test.name}' if self.abstract_test else ''

    @hybrid_property
    def stage_result(self):
        return self.result.status if self.result else StatusEnum.PENDING


class ErrorEvent(Event):
    """
    Event representing an error that occurred during an experiment run.
    """
    __tablename__ = 'error_events'
    __mapper_args__ = {
        'polymorphic_identity': 'error_event',
    }
    id = Column(CHAR(26), ForeignKey('event.id'), primary_key=True)
    error_name = Column(String)
    error_msg = Column(String)

    def __str__(self):
        return str(self.error)

    def __repr__(self):
        return f"<ErrorEvent(error='{self.error_msg}')>"

    @hybrid_property
    def stage_submessage(self):
        return f'{self.error_msg}'

    @hybrid_property
    def stage_result(self):
        return StatusEnum.ERROR


class GuiFindEvent(Event):
    """
    Event representing a GUI find operation (text or image) during an experiment run.
    """
    __tablename__ = 'gui_find_events'
    __mapper_args__ = {
        'polymorphic_identity': 'gui_find_event',
    }
    id = Column(CHAR(26), ForeignKey('event.id'), primary_key=True)
    text = Column(Boolean)
    objective = Column(String)
    success = Column(Integer)
    positions = Column(String)

    @hybrid_property
    def stage_submessage(self):
        if self.text:
            return f'Find text "{self.objective}" on screen'
        else:
            return f'Find image "{self.objective}" on screen'

    @hybrid_property
    def stage_result(self):
        if self.success <= 0:
            return StatusEnum.ERROR
        return StatusEnum.SUCCESS


class GuiClickEvent(Event):
    """
    Event representing a GUI click operation during an experiment run.
    """
    __tablename__ = 'gui_click_events'
    __mapper_args__ = {
        'polymorphic_identity': 'gui_click_event',
    }
    id = Column(CHAR(26), ForeignKey('event.id'), primary_key=True)
    clicktype = Column(String)
    modifiers = Column(String)
    target = Column(String)

    @hybrid_property
    def stage_submessage(self):
        if self.clicktype == 'left':
            msg = f'Clicking left at coordinates {self.target}'
        elif self.clicktype == 'right':
            msg = f'Clicking right at coordinates {self.target}'
        elif self.clicktype == 'double':
            msg = f'Double clicking at coordinates {self.target}'
        elif self.clicktype == 'double_right':
            msg = f'Double right clicking at coordinates {self.target}'
        else:
            msg = f'Clicking at coordinates {self.target}'
        if self.modifiers:
            msg += f' (mod: {self.modifiers})'
        return msg

    @hybrid_property
    def stage_result(self):
        return None


class GuiKeypressEvent(Event):
    """
    Event representing a GUI keypress operation during an experiment run.
    """
    __tablename__ = 'gui_keypress_events'
    __mapper_args__ = {
        'polymorphic_identity': 'gui_keypress_event',
    }
    id = Column(CHAR(26), ForeignKey('event.id'), primary_key=True)
    keys = Column(String)

    @hybrid_property
    def stage_submessage(self):
        return f'Pressing keys {self.keys}'

    @hybrid_property
    def stage_result(self):
        return None


class GuiIdleEvent(Event):
    """
    Event representing an idle/wait period during an experiment run.
    """
    __tablename__ = 'gui_idle_events'
    __mapper_args__ = {
        'polymorphic_identity': 'gui_idle_event',
    }
    id = Column(CHAR(26), ForeignKey('event.id'), primary_key=True)
    seconds = Column(Integer)

    @hybrid_property
    def stage_submessage(self):
        return f'Wait idle for {self.seconds} seconds'

    @hybrid_property
    def stage_result(self):
        return None


class EventFactory:
    """
    Factory for creating event instances based on category.
    """
    @staticmethod
    def create_event(category, **kwargs):
        # add category to kwargs
        kwargs['category'] = category
        # if category == 'action':
        #     return ActionEvent(**kwargs)
        if category == 'command':
            return CommandEvent(**kwargs)
        elif category == 'test':
            return TestEvent(**kwargs)
        elif category == 'gui:find':
            return GuiFindEvent(**kwargs)
        elif category == 'gui:click':
            return GuiClickEvent(**kwargs)
        elif category == 'gui:keypress':
            return GuiKeypressEvent(**kwargs)
        elif category == 'gui:idle':
            return GuiIdleEvent(**kwargs)
        elif category == 'error':
            return ErrorEvent(**kwargs)
        else:
            raise ValueError(f'Invalid category: {category}')


class ExperimentRunFiles(SerializerMixin, Base):
    """
    Stores references to log files generated during an experiment run.
    """
    __tablename__ = 'experiment_run_file'
    RELATIONSHIPS_TO_DICT = True

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))

    log_vagrant_id = Column(CHAR(26), ForeignKey('log_file.id', ondelete='SET NULL'), nullable=True)
    log_vagrant = relationship(LogFile, foreign_keys=[log_vagrant_id])

    log_adarevm_id = Column(CHAR(26), ForeignKey('log_file.id', ondelete='SET NULL'), nullable=True)
    log_adarevm = relationship(LogFile, foreign_keys=[log_adarevm_id])


class Stage(SerializerMixin, Base):
    """
    Represents a stage in an experiment or test run, possibly hierarchical.
    """
    __tablename__ = 'stage'
    RELATIONSHIPS_TO_DICT = True

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    name = Column(String, unique=True)
    msg = Column(String, nullable=True)
    description = Column(String, nullable=True)
    optional = Column(Boolean)

    parent_id = Column(CHAR(26), ForeignKey('stage.id'), nullable=True)
    parent = relationship("Stage", remote_side=[id], backref=backref("children", cascade="all, delete-orphan"))

    @hybrid_property
    def level(self):
        return self.parent.level + 1 if self.parent else 0


class StageInRun(SerializerMixin, Base):
    """
    Represents a stage instance within a specific experiment run, tracking timing and status.
    """
    __tablename__ = 'stage_in_run'
    RELATIONSHIPS_TO_DICT = True

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    stage_id = Column(CHAR(26), ForeignKey('stage.id'))
    stage = relationship(Stage)

    start_time = Column(DateTime, nullable=True)
    end_time = Column(DateTime, nullable=True)
    status = Column(StatusEnumType, default=StatusEnum.PENDING)
    sub_msg = Column(String, nullable=True)
    result_status = Column(Integer, nullable=True)

    run_id = Column(CHAR(26), ForeignKey('experiment_run.id', ondelete='CASCADE'))
    run = relationship("ExperimentRun", backref=backref("stages", cascade="all, delete-orphan"))

    @hybrid_property
    def duration(self):
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None

    @hybrid_property
    def pending(self):
        return not self.start_time

    @hybrid_property
    def in_progress(self):
        return self.start_time and not self.end_time

    @hybrid_property
    def finished(self):
        return self.start_time and self.end_time


class ExperimentRun(SerializerMixin, Base):
    """
    Represents a single run of an experiment, including environment, timing, and results.
    """
    __tablename__ = 'experiment_run'
    RELATIONSHIPS_TO_DICT = True

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    experiment_id = Column(CHAR(26), ForeignKey('experiment.id', ondelete='CASCADE'), nullable=True)
    experiment = relationship(Experiment, backref=backref("runs", cascade="all, delete-orphan"))
    environment_id = Column(CHAR(26), ForeignKey('environment.id', ondelete='CASCADE'), nullable=True)
    environment = relationship(Environment, backref=backref("runs", cascade="all, delete-orphan"))

    path = Column(String, nullable=True)

    timestamp_start = Column(DateTime, nullable=True)
    timestamp_end = Column(DateTime, nullable=True)

    status = Column(StatusEnumType, default=StatusEnum.PENDING)

    published = Column(Boolean, default=False)

    files_id = Column(CHAR(26), ForeignKey('experiment_run_file.id', ondelete='SET NULL'), nullable=True)
    files = relationship(ExperimentRunFiles, backref=backref("experimentrun", uselist=False))

    # currently not used
    sha256_validation_hash = Column(String, nullable=True)
    # used for test runs
    fake = Column(Boolean, default=False)

    @hybrid_property
    def is_valid(self):
        return bool(self.experiment_id and self.environment_id and self.files_id)

    @hybrid_property
    def experiment_name(self) -> str:
        return self.experiment.name if self.experiment else ''

    @hybrid_property
    def experiment_dotnotation(self) -> str:
        return f'{self.environment.project.name}.{self.environment.name}.{self.experiment.name}'

    @hybrid_property
    def duration(self):
        if self.timestamp_start and self.timestamp_end:
            return self.timestamp_end - self.timestamp_start
        return None

    @hybrid_property
    def tests(self):
        return [
            event for event in self.events
            if isinstance(event, TestEvent)
        ]

    @hybrid_property
    def result_status(self):
        for test in self.experiment.abstract_tests:
            found = False
            for t in self.tests:
                if t.abstract_test_id == test.id:
                    if t.result:
                        found = True
                        break
            if not found:
                return StatusEnum.TEST_MISSING
        for t in self.tests:
            if not t.result:
                continue
            if t.result.status != StatusEnum.SUCCESS:
                return StatusEnum.FAILED
        return StatusEnum.SUCCESS

    @hybrid_property
    def ulid(self):
        """Provide ulid property that maps to the id field for consistency."""
        return self.id

    @ulid.setter
    def ulid(self, value):
        """Allow setting ulid which maps to the id field."""
        self.id = value

    def __str__(self):
        return str(self.id)

    def __repr__(self):
        return f"<ExperimentRun(id='{self.id}',experiment={self.experiment_id})>"

