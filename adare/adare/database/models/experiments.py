from sqlalchemy import Column, Integer, String, ForeignKey, Table, DateTime, CHAR, UniqueConstraint, Boolean
from sqlalchemy.orm import relationship, backref
from sqlalchemy.ext.declarative import declarative_base
import uuid
from datetime import datetime
from adarelib.helperfunctions.hash import hash_file_sha256, combine_hashes
from sqlalchemy import event
from sqlalchemy_serializer import SerializerMixin

Base = declarative_base()
mapping_experimentrun_test = Table(
    "mapping_experimentrun_test",
    Base.metadata,
    Column("experimentrun_uuid", ForeignKey("experimentrun.uuid")),
    Column("test_uuid", ForeignKey("test.uuid")),
)

mapping_experiment_abstracttest = Table(
    "mapping_experiment_abstracttest",
    Base.metadata,
    Column("experiment_uuid", ForeignKey("experiment.uuid")),
    Column("abstracttest_uuid", ForeignKey("abstracttest.uuid")),
)

mapping_experiment_tag = Table(
    "mapping_experiment_tag",
    Base.metadata,
    Column("experiment_uuid", ForeignKey("experiment.uuid")),
    Column("tag_id", ForeignKey("tag.id")),
)

mapping_testfunction_testparameter = Table(
    "mapping_testfunction_testparameter",
    Base.metadata,
    Column("testfunction_id", ForeignKey("testfunction.id")),
    Column("testparameter_id", ForeignKey("testparameter.id")),
)

mapping_abstracttest_testparameterentry = Table(
    "mapping_abstracttest_testparameterentry",
    Base.metadata,
    Column("abstracttest_uuid", ForeignKey("abstracttest.uuid")),
    Column("testparameterentry_id", ForeignKey("testparameterentry.id")),
)
mapping_postsetupinstallation_environment = Table(
    "mapping_postsetupinstallation_environment",
    Base.metadata,
    Column("postsetupinstallation_id", ForeignKey("postsetupinstallation.id")),
    Column("environment_id", ForeignKey("environment.uuid")),
)
mapping_usbdrive_experiment = Table(
    "mapping_usbdrive_experiment",
    Base.metadata,
    Column("usbdrive_id", ForeignKey("usbdrive.id")),
    Column("experiment_uuid", ForeignKey("experiment.uuid")),
)
mapping_smbdrive_smbshare = Table(
    "mapping_smbdrive_smbshare",
    Base.metadata,
    Column("smbdrive_id", ForeignKey("smbdrive.id")),
    Column("smbshare_id", ForeignKey("smbshare.id")),
)
mapping_smbdrive_user = Table(
    "mapping_smbdrive_user",
    Base.metadata,
    Column("smbdrive_id", ForeignKey("smbdrive.id")),
    Column("user_id", ForeignKey("networkdriveuser.id")),
)
mapping_nfsdrive_nfsshare = Table(
    "mapping_nfsdrive_nfsshare",
    Base.metadata,
    Column("nfsdrive_id", ForeignKey("nfsdrive.id")),
    Column("nfsshare_id", ForeignKey("nfshare.id")),
)
mapping_experiment_environment = Table(
    "mapping_experiment_environment",
    Base.metadata,
    Column("experiment_uuid", ForeignKey("experiment.uuid")),
    Column("environment_id", ForeignKey("environment.uuid")),
)
mapping_abstracttest_tool = Table(
    "mapping_abstracttest_tool",
    Base.metadata,
    Column("abstracttest_uuid", ForeignKey("abstracttest.uuid")),
    Column("tool_id", ForeignKey("tool.id")),
)


class Tag(SerializerMixin, Base):
    __tablename__ = 'tag'
    RELATIONSHIPS_TO_DICT = True
    serialize_rules = ('-id',)

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String)

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return f"<Tag(name='{self.name}')>"


class PostSetupInstallation(SerializerMixin, Base):
    __tablename__ = 'postsetupinstallation'
    RELATIONSHIPS_TO_DICT = True

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String)
    description = Column(String, nullable=True)
    command = Column(String)

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return f"<PostSetupInstallation(name='{self.name}',description='{self.description}',command='{self.command}')>"


class Status(SerializerMixin, Base):
    """
        Collection of possible status.
    """
    __tablename__ = 'status'
    RELATIONSHIPS_TO_DICT = True
    serialize_rules = ('-id',)

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return f"<Status(name='{self.name}')>"


class Result(SerializerMixin, Base):
    """
        Result of a test.
    """
    __tablename__ = 'result'
    RELATIONSHIPS_TO_DICT = True
    serialize_rules = ('-id', '-status_id')

    id = Column(Integer, primary_key=True, autoincrement=True)
    status_id = Column(Integer, ForeignKey('status.id'), nullable=False)
    details = Column(String, nullable=True)

    status = relationship(Status)

    def __str__(self):
        return str(self.status)

    def __repr__(self):
        return f"<Result(status='{self.status}',details='{self.details}')>"


class TestParameter(SerializerMixin, Base):
    __tablename__ = 'testparameter'
    RELATIONSHIPS_TO_DICT = True

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String)
    dtype = Column(String)

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return f"<TestParameter(name='{self.name}',dtype='{self.dtype}')>"


class TestParameterEntry(SerializerMixin, Base):
    __tablename__ = 'testparameterentry'
    RELATIONSHIPS_TO_DICT = True
    serialize_rules = ('-id', '-parameter_id')

    id = Column(Integer, primary_key=True, autoincrement=True)
    parameter_id = Column(Integer, ForeignKey('testparameter.id', ondelete='CASCADE'), nullable=False)
    value = Column(String)

    parameter = relationship(TestParameter)

    def __str__(self):
        return str(self.parameter)

    def __repr__(self):
        return f"<TestParameterEntries(parameter='{self.parameter}',dtype='{self.value}')>"


class TestFunctionFile(SerializerMixin, Base):
    __tablename__ = 'testfunctionfile'
    RELATIONSHIPS_TO_DICT = True

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String)
    path = Column(String, unique=True)
    sha256hash = Column(String, unique=True)
    description = Column(String, nullable=True, default=None)

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return f"<TestFunctionContainer(name='{self.name}',description='{self.description}')>"


class TestFunction(SerializerMixin, Base):
    __tablename__ = 'testfunction'
    RELATIONSHIPS_TO_DICT = True
    serialize_rules = ('-id',)

    id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(String)
    name = Column(String)
    description = Column(String)
    sha256hash = Column(String, unique=True)

    file_id = Column(Integer, ForeignKey('testfunctionfile.id'))
    file = relationship(TestFunctionFile, backref=backref("testfunctions", cascade="all, delete-orphan"))

    possible_parameters = relationship(TestParameter, secondary=mapping_testfunction_testparameter)

    @property
    def fullname(self):
        return f"{self.file.name}.{self.name}"

    def __str__(self):
        return self.fullname

    def __repr__(self):
        return f"<TestFunction(name='{self.fullname}',description='{self.description}')>"


class Command(SerializerMixin, Base):
    __tablename__ = 'tool'
    RELATIONSHIPS_TO_DICT = True
    serialize_rules = ('-id',)

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String)
    command = Column(String)

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return f"<Command(name='{self.name}',command='{self.command}')>"


class AbstractTest(SerializerMixin, Base):
    __tablename__ = 'abstracttest'
    RELATIONSHIPS_TO_DICT = True

    uuid = Column(CHAR(32), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String)
    description = Column(String)

    testfunction = relationship(TestFunction, backref=backref("abstracttests", cascade="all, delete-orphan"))
    testfunction_id = Column(Integer, ForeignKey('testfunction.id'))

    parameters = relationship(TestParameterEntry, secondary=mapping_abstracttest_testparameterentry)

    depends_on_tool = relationship(Command, secondary=mapping_abstracttest_tool)

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return f"<AbstractTest(name='{self.name}',testfunction='{self.testfunction}')>"


class Test(SerializerMixin, Base):
    __tablename__ = 'test'
    RELATIONSHIPS_TO_DICT = True

    uuid = Column(CHAR(32), primary_key=True, default=lambda: str(uuid.uuid4()))

    result_id = Column(Integer, ForeignKey('result.id'))
    abstracttest_id = Column(CHAR(32), ForeignKey('abstracttest.uuid'))

    result = relationship(Result)
    abstracttest = relationship(AbstractTest, backref=backref("tests", cascade="all, delete-orphan"))

    def __str__(self):
        return str(self.uuid)

    def __repr__(self):
        return f"<Test(uuid='{self.uuid}',abstracttest='{self.abstracttest}')>"


class OsInfo(SerializerMixin, Base):
    __tablename__ = 'osinfo'
    RELATIONSHIPS_TO_DICT = True
    serialize_rules = ('-id', '-platform')

    id = Column(Integer, primary_key=True, autoincrement=True)

    platform = Column(String, nullable=False)
    os = Column(String)
    distribution = Column(String)
    version = Column(String)
    language = Column(String)
    architecture = Column(String)
    details = Column(String)

    def __str__(self):
        return f'{self.os} - {self.distribution} {self.version} ({self.language, self.architecture})'

    def __repr__(self):
        return f"<OsInfo(os='{self.os}',distribution='{self.distribution}',version='{self.version}',language='{self.language}',architecture='{self.architecture}')>"


class LogFile(SerializerMixin, Base):
    __tablename__ = 'logfile'
    RELATIONSHIPS_TO_DICT = True

    uuid = Column(CHAR(32), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String)
    path = Column(String)

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return f"<LogFile(name='{self.name}',path='{self.path}')>"


class NetworkDriveUser(SerializerMixin, Base):
    __tablename__ = 'networkdriveuser'
    RELATIONSHIPS_TO_DICT = True

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String)
    password = Column(String)

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return f"<NetworkDriveUser(username='{self.username}',password='{self.password}')>"


class SMBShare(SerializerMixin, Base):
    __tablename__ = 'smbshare'
    RELATIONSHIPS_TO_DICT = True

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String)
    local_path = Column(String)
    remote_path = Column(String)
    user_id = Column(Integer, ForeignKey('networkdriveuser.id'))
    user = relationship("NetworkDriveUser", backref=backref("smbdrives", cascade="all, delete-orphan"))

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return f"<SMBShare(name='{self.name}',local_path='{self.local_path}',remote_path='{self.remote_path}',user='{self.user}')>"


class NFSShare(SerializerMixin, Base):
    __tablename__ = 'nfshare'
    RELATIONSHIPS_TO_DICT = True

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String)
    local_path = Column(String)
    remote_path = Column(String)
    allowed_hosts = Column(String)

    # options = Column(String)

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return f"<NFSShare(name='{self.name}',local_path='{self.local_path}',remote_path='{self.remote_path}',allowed_hosts='{self.allowed_hosts}')>"


class SMBDrive(SerializerMixin, Base):
    __tablename__ = 'smbdrive'
    RELATIONSHIPS_TO_DICT = True

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True)
    shares = relationship(SMBShare, secondary=mapping_smbdrive_smbshare)
    users = relationship(NetworkDriveUser, secondary=mapping_smbdrive_user)
    workgroup = Column(String)

    def __str__(self):
        return str(self.name)


class NFSDrive(SerializerMixin, Base):
    __tablename__ = 'nfsdrive'
    RELATIONSHIPS_TO_DICT = True

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True)
    shares = relationship(NFSShare, secondary=mapping_nfsdrive_nfsshare)

    def __str__(self):
        return str(self.name)


class USBDrive(SerializerMixin, Base):
    __tablename__ = 'usbdrive'
    RELATIONSHIPS_TO_DICT = True

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String)
    vendor_id = Column(String)
    product_id = Column(String)
    manufacturer = Column(String)
    product = Column(String)
    serial_number = Column(String)


class Project(SerializerMixin, Base):
    __tablename__ = 'project'
    RELATIONSHIPS_TO_DICT = True

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True)
    description = Column(String)
    path = Column(String, unique=True)

    def __repr__(self):
        return f"<Project(name='{self.name}',description='{self.description}',path='{self.path}')>"


class Environment(SerializerMixin, Base):
    __tablename__ = 'environment'
    RELATIONSHIPS_TO_DICT = True

    uuid = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String)
    vagrantbox = Column(String)
    description = Column(String)

    osinfo_id = Column(Integer, ForeignKey('osinfo.id'))
    osinfo = relationship(OsInfo)

    project_id = Column(Integer, ForeignKey('project.id'))
    project = relationship(Project, backref=backref("environments", cascade="all, delete-orphan"))

    installations = relationship(PostSetupInstallation, secondary=mapping_postsetupinstallation_environment)

    file = Column(String)
    sha256hash = Column(String, unique=True)

    in_request = Column(Boolean, default=False)
    published = Column(Boolean, default=False)

    created_at = Column(DateTime, nullable=True, default=datetime.now)

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return f"<Environment(name='{self.name}',osinfo='{self.osinfo}',vagrantbox='{self.vagrantbox}')>"


class Experiment(SerializerMixin, Base):
    __tablename__ = 'experiment'
    RELATIONSHIPS_TO_DICT = True

    uuid = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, unique=True)
    description = Column(String)

    tags = relationship(Tag, secondary=mapping_experiment_tag)
    abstract_tests = relationship(AbstractTest, secondary=mapping_experiment_abstracttest)

    action_file = Column(String)
    testset_file = Column(String)
    metadata_file = Column(String)
    bibtex_file = Column(String, nullable=True, default=None)
    markdown_file = Column(String, nullable=True, default=None)

    sha256_action = Column(String)
    sha256_testset = Column(String)
    sha256_metadata = Column(String)
    sha256_bibtex = Column(String, nullable=True)
    sha256_markdown = Column(String, nullable=True)
    sha256_hash = Column(String, nullable=True)

    in_request = Column(Boolean, default=False)
    published = Column(Boolean, default=False)

    smbdrive_id = Column(Integer, ForeignKey('smbdrive.id'), nullable=True)
    smbdrive = relationship(SMBDrive)
    nfsdrive_id = Column(Integer, ForeignKey('nfsdrive.id'), nullable=True)
    nfsdrive = relationship(NFSDrive)
    usbdrives = relationship(USBDrive, secondary=mapping_usbdrive_experiment)

    environments = relationship(Environment, secondary=mapping_experiment_environment, backref='experiments')
    project_id = Column(Integer, ForeignKey('project.id'))
    project = relationship(Project, backref=backref("experiments", cascade="all, delete-orphan"))

    created_at = Column(DateTime, nullable=True, default=datetime.now)

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return f"<Experiment(name='{self.name}',publish_status='{self.publish_status}')>"


class Event(SerializerMixin, Base):
    __tablename__ = 'event'
    RELATIONSHIPS_TO_DICT = True

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String)
    event_log_id = Column(Integer, ForeignKey('eventlog.id'))
    event_log = relationship("EventLog", backref=backref("events", cascade="all, delete-orphan"))

    timestamp = Column(DateTime)

    __mapper_args__ = {
        'polymorphic_identity': 'event',
        'polymorphic_on': event_type
    }


class ActionEvent(Event):
    __tablename__ = 'action_event'
    __mapper_args__ = {
        'polymorphic_identity': 'action_event',
    }
    id = Column(Integer, ForeignKey('event.id'), primary_key=True)
    name = Column(String)
    description = Column(String)


class CommandStartEvent(Event):
    __tablename__ = 'command_start_event'
    __mapper_args__ = {
        'polymorphic_identity': 'command_start_event',
    }
    id = Column(Integer, ForeignKey('event.id'), primary_key=True)
    command_name = Column(String)


class CommandEndEvent(Event):
    __tablename__ = 'command_end_event'
    __mapper_args__ = {
        'polymorphic_identity': 'command_end_event',
    }
    id = Column(Integer, ForeignKey('event.id'), primary_key=True)
    command_name = Column(String)


class TestStartEvent(Event):
    __tablename__ = 'test_start_event'
    __mapper_args__ = {
        'polymorphic_identity': 'test_start_event',
    }
    id = Column(Integer, ForeignKey('event.id'), primary_key=True)
    test_name = Column(String)


class TestEndEvent(Event):
    __tablename__ = 'test_end_event'
    __mapper_args__ = {
        'polymorphic_identity': 'test_end_event',
    }
    id = Column(Integer, ForeignKey('event.id'), primary_key=True)
    test_name = Column(String)
    result_id = Column(Integer, ForeignKey('result.id'))
    result = relationship(Result)

    def __str__(self):
        return str(self.test_name)

    def __repr__(self):
        return f"<TestEndEvent(test_name='{self.test_name}',result='{self.result}')>"


class EventLog(SerializerMixin, Base):
    __tablename__ = 'eventlog'
    RELATIONSHIPS_TO_DICT = True

    id = Column(Integer, primary_key=True, autoincrement=True)
    path = Column(String)
    start_time = Column(DateTime)
    end_time = Column(DateTime)


class ExperimentRunEvents(SerializerMixin, Base):
    __tablename__ = 'events'
    RELATIONSHIPS_TO_DICT = True

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String)
    event_log_id = Column(Integer, ForeignKey('eventlog.id'))
    event_log = relationship("EventLog", backref=backref("events", cascade="all, delete-orphan"))

    timestamp = Column(DateTime)

    __mapper_args__ = {
        'polymorphic_identity': 'event',
        'polymorphic_on': event_type
    }


class ExperimentRun(SerializerMixin, Base):
    __tablename__ = 'experimentrun'
    RELATIONSHIPS_TO_DICT = True

    uuid = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    experiment_id = Column(String, ForeignKey('experiment.uuid'))
    experiment = relationship(Experiment, backref=backref("runs", cascade="all, delete-orphan"))
    environment_id = Column(Integer, ForeignKey('environment.uuid'))
    environment = relationship(Environment, backref=backref("runs", cascade="all, delete-orphan"))
    path = Column(String, nullable=True)

    event_log_id = Column(Integer, ForeignKey('eventlog.id'))
    event_log = relationship("EventLog", backref=backref("experimentruns", cascade="all, delete-orphan"))

    timestamp_start = Column(DateTime, nullable=True)
    timestamp_end = Column(DateTime, nullable=True)
    tests = relationship(Test, secondary=mapping_experimentrun_test)

    published = Column(Boolean, default=False)

    status_id = Column(Integer, ForeignKey('status.id'))
    status_adarevm_id = Column(Integer, ForeignKey('status.id'))
    status_vagrant_id = Column(Integer, ForeignKey('status.id'))

    logfile_vagrant_id = Column(Integer, ForeignKey('logfile.uuid'), nullable=True)
    logfile_adarevm_id = Column(Integer, ForeignKey('logfile.uuid'), nullable=True)
    logfile_installed_packages_id = Column(Integer, ForeignKey('logfile.uuid'), nullable=True)
    logfile_installations_id = Column(Integer, ForeignKey('logfile.uuid'), nullable=True)
    logfile_run_experiment_id = Column(Integer, ForeignKey('logfile.uuid'), nullable=True)

    status = relationship(Status, foreign_keys=[status_id])
    status_adarevm = relationship(Status, foreign_keys=[status_adarevm_id])
    status_vagrant = relationship(Status, foreign_keys=[status_vagrant_id])

    logfile_vagrant = relationship(LogFile, foreign_keys=[logfile_vagrant_id])
    logfile_adarevm = relationship(LogFile, foreign_keys=[logfile_adarevm_id])
    logfile_installed_packages = relationship(LogFile, foreign_keys=[logfile_installed_packages_id])
    logfile_postsetup_installations = relationship(LogFile, foreign_keys=[logfile_installations_id])
    logfile_run_experiment = relationship(LogFile, foreign_keys=[logfile_run_experiment_id])

    # currently not used
    sha256_validation_hash = Column(String, nullable=True)

    def __str__(self):
        return str(self.uuid)

    def __repr__(self):
        return f"<ExperimentRun(uuid='{self.uuid}',experiment={self.experiment_id})>"
