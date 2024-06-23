from sqlalchemy import Column, Integer, String, ForeignKey, Table, DateTime, CHAR, Boolean
from sqlalchemy.orm import relationship, backref
from sqlalchemy.ext.declarative import declarative_base
import ulid
from pathlib import Path
from datetime import datetime
from sqlalchemy_serializer import SerializerMixin
from sqlalchemy.ext.hybrid import hybrid_property
from adarelib.config import StatusEnum

Base = declarative_base()
# mapping_experimentrun_test = Table(
#     "mapping_experimentrun_test",
#     Base.metadata,
#     Column("experimentrun_ulid", ForeignKey("experimentrun.ulid")),
#     Column("test_ulid", ForeignKey("test.ulid")),
# )

mapping_experiment_abstracttest = Table(
    "mapping_experiment_abstracttest",
    Base.metadata,
    Column("experiment_ulid", ForeignKey("experiment.ulid")),
    Column("abstracttest_ulid", ForeignKey("abstracttest.ulid")),
)

mapping_experiment_tag = Table(
    "mapping_experiment_tag",
    Base.metadata,
    Column("experiment_ulid", ForeignKey("experiment.ulid")),
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
    Column("abstracttest_ulid", ForeignKey("abstracttest.ulid")),
    Column("testparameterentry_id", ForeignKey("testparameterentry.id")),
)
mapping_postsetupinstallation_environment = Table(
    "mapping_postsetupinstallation_environment",
    Base.metadata,
    Column("postsetupinstallation_id", ForeignKey("postsetupinstallation.id")),
    Column("environment_id", ForeignKey("environment.ulid")),
)
mapping_usbdrive_experiment = Table(
    "mapping_usbdrive_experiment",
    Base.metadata,
    Column("usbdrive_id", ForeignKey("usbdrive.id")),
    Column("experiment_ulid", ForeignKey("experiment.ulid")),
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
    Column("experiment_ulid", ForeignKey("experiment.ulid")),
    Column("environment_id", ForeignKey("environment.ulid")),
)
mapping_abstracttest_tool = Table(
    "mapping_abstracttest_tool",
    Base.metadata,
    Column("abstracttest_ulid", ForeignKey("abstracttest.ulid")),
    Column("tool_id", ForeignKey("tool.id")),
)
mapping_project_testfunctionfile = Table(
    "mapping_project_testfunctionfile",
    Base.metadata,
    Column("project_id", ForeignKey("project.id")),
    Column("testfunctionfile_id", ForeignKey("testfunctionfile.id")),
)


class Status(SerializerMixin, Base):
    __tablename__ = 'status'
    RELATIONSHIPS_TO_DICT = True

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String)

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return f"<Status(name='{self.name}')>"


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


class Result(SerializerMixin, Base):
    """
        Result of a test.
    """
    __tablename__ = 'result'
    RELATIONSHIPS_TO_DICT = True
    serialize_rules = ('-id', '-status_id')

    id = Column(Integer, primary_key=True, autoincrement=True)
    status = Column(Integer)
    details = Column(String, nullable=True)


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
    sha256hash = Column(String)
    description = Column(String, nullable=True, default=None)

    @hybrid_property
    def num_functions(self):
        return len(self.testfunctions)

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

    @hybrid_property
    def dotnotation(self):
        return f"{Path(self.file.name).stem}.{self.name}"

    @hybrid_property
    def num_parameters(self):
        return len(self.possible_parameters)

    def __str__(self):
        return self.dotnotation

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

    ulid = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
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

    ulid = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    name = Column(String)
    path = Column(String, unique=True)

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

    testfunction_files = relationship(TestFunctionFile, secondary=mapping_project_testfunctionfile, backref='projects')

    def __repr__(self):
        return f"<Project(name='{self.name}',description='{self.description}',path='{self.path}')>"


class Environment(SerializerMixin, Base):
    __tablename__ = 'environment'
    RELATIONSHIPS_TO_DICT = True

    ulid = Column(String, primary_key=True, default=lambda: str(ulid.ULID()))
    name = Column(String)
    vagrantbox = Column(String)
    description = Column(String)

    osinfo_id = Column(Integer, ForeignKey('osinfo.id'))
    osinfo = relationship(OsInfo, backref=backref("environments", cascade="all, delete-orphan"))

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

    ulid = Column(String, primary_key=True, default=lambda: str(ulid.ULID()))
    name = Column(String)
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
    sha256 = Column(String, nullable=True)

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
        return f"<Experiment(name='{self.name}')>"


class Event(SerializerMixin, Base):
    __tablename__ = 'event'
    RELATIONSHIPS_TO_DICT = True

    ulid = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    event_type = Column(String)
    category = Column(String)
    experiment_run_id = Column(String, ForeignKey('experimentrun.ulid'))
    experiment_run = relationship("ExperimentRun", backref=backref("events", cascade="all, delete-orphan"))
    status = Column(Integer, default=StatusEnum.PENDING)
    error = Column(String)
    stage = Column(Boolean, default=False)
    group_id = Column(Integer)
    stage_in_run_id = Column(Integer, ForeignKey('stageinrun.id'), nullable=True, default=None)
    stage_in_run = relationship("StageInRun", backref=backref("events", cascade="all, delete-orphan"))

    timestamp = Column(DateTime)

    @hybrid_property
    def stage_submessage(self):
        return None

    @hybrid_property
    def stage_result(self):
        return None

    __mapper_args__ = {
        'polymorphic_identity': 'event',
        'polymorphic_on': event_type
    }


# class ActionEvent(Event):
#     __tablename__ = 'action_event'
#     __mapper_args__ = {
#         'polymorphic_identity': 'action_event',
#     }
#     id = Column(CHAR(26), ForeignKey('event.ulid'), primary_key=True)
#     name = Column(String)
#     description = Column(String)
#
#     @hybrid_property
#     def stage_submessage(self):
#         return f'{self.name}'


class CommandEvent(Event):
    __tablename__ = 'command_event'
    __mapper_args__ = {
        'polymorphic_identity': 'command_event',
    }
    id = Column(CHAR(26), ForeignKey('event.ulid'), primary_key=True)
    name = Column(String)
    command = Column(String)
    returncode = Column(Integer)
    stdout = Column(String)

    @hybrid_property
    def stage_submessage(self):
        return f'{self.command}'

    @hybrid_property
    def stage_result(self):
        return None


class TestEvent(Event):
    __tablename__ = 'test_event'
    __mapper_args__ = {
        'polymorphic_identity': 'test_event',
    }
    id = Column(CHAR(26), ForeignKey('event.ulid'), primary_key=True)
    abstract_test_id = Column(CHAR(26), ForeignKey('abstracttest.ulid'), nullable=True)
    abstract_test = relationship(AbstractTest, backref=backref("test_events", cascade="all, delete-orphan"))
    result_id = Column(Integer, ForeignKey('result.id'), nullable=True)
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
    __tablename__ = 'error_event'
    __mapper_args__ = {
        'polymorphic_identity': 'error_event',
    }
    id = Column(CHAR(26), ForeignKey('event.ulid'), primary_key=True)
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
    __tablename__ = 'gui_find_event'
    __mapper_args__ = {
        'polymorphic_identity': 'gui_find_event',
    }
    id = Column(CHAR(26), ForeignKey('event.ulid'), primary_key=True)
    text = Column(Boolean)
    objective = Column(String)
    success = Column(Integer)

    @hybrid_property
    def stage_submessage(self):
        msg = '(text)' if self.text else '(img)'
        msg += f' {self.objective}'
        return msg

    @hybrid_property
    def stage_result(self):
        return None


class GuiClickEvent(Event):
    __tablename__ = 'gui_click_event'
    __mapper_args__ = {
        'polymorphic_identity': 'gui_click_event',
    }
    id = Column(CHAR(26), ForeignKey('event.ulid'), primary_key=True)
    clicktype = Column(String)
    modifiers = Column(String)
    target = Column(String)

    @hybrid_property
    def stage_submessage(self):
        msg = f'{self.clicktype} {self.target}'
        if self.modifiers:
            msg += f' (mod: {self.modifiers})'
        return msg

    @hybrid_property
    def stage_result(self):
        return None


class GuiKeypressEvent(Event):
    __tablename__ = 'gui_keypress_event'
    __mapper_args__ = {
        'polymorphic_identity': 'gui_keypress_event',
    }
    id = Column(CHAR(26), ForeignKey('event.ulid'), primary_key=True)
    keys = Column(String)

    @hybrid_property
    def stage_submessage(self):
        return f'{self.keys}'

    @hybrid_property
    def stage_result(self):
        return None


class GuiIdleEvent(Event):
    __tablename__ = 'gui_idle_event'
    __mapper_args__ = {
        'polymorphic_identity': 'gui_idle_event',
    }
    id = Column(CHAR(26), ForeignKey('event.ulid'), primary_key=True)
    seconds = Column(Integer)

    @hybrid_property
    def stage_submessage(self):
        return f'{self.seconds} seconds'

    @hybrid_property
    def stage_result(self):
        return None


class EventFactory:
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
    __tablename__ = 'experimentrunfiles'
    RELATIONSHIPS_TO_DICT = True

    id = Column(Integer, primary_key=True, autoincrement=True)

    log_vagrant_id = Column(Integer, ForeignKey('logfile.ulid'), nullable=True)
    log_vagrant = relationship(LogFile, foreign_keys=[log_vagrant_id])

    package_dump_id = Column(Integer, ForeignKey('logfile.ulid'), nullable=True)
    package_dump = relationship(LogFile, foreign_keys=[package_dump_id])

    log_installations_id = Column(Integer, ForeignKey('logfile.ulid'), nullable=True)
    log_installations = relationship(LogFile, foreign_keys=[log_installations_id])

    log_run_id = Column(Integer, ForeignKey('logfile.ulid'), nullable=True)
    log_run = relationship(LogFile, foreign_keys=[log_run_id])


class Stage(SerializerMixin, Base):
    __tablename__ = 'stage'
    RELATIONSHIPS_TO_DICT = True

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True)
    msg = Column(String, nullable=True)
    description = Column(String, nullable=True)
    optional = Column(Boolean)

    parent_id = Column(Integer, ForeignKey('stage.id'), nullable=True)
    parent = relationship("Stage", remote_side=[id], backref=backref("children", cascade="all, delete-orphan"))

    @hybrid_property
    def level(self):
        return self.parent.level + 1 if self.parent else 0


class StageInRun(SerializerMixin, Base):
    __tablename__ = 'stageinrun'
    RELATIONSHIPS_TO_DICT = True

    id = Column(Integer, primary_key=True, autoincrement=True)
    stage_id = Column(Integer, ForeignKey('stage.id'))
    stage = relationship(Stage)

    start_time = Column(DateTime, nullable=True)
    end_time = Column(DateTime, nullable=True)
    status = Column(Integer, default=StatusEnum.PENDING)
    sub_msg = Column(String, nullable=True)
    result_status = Column(Integer, nullable=True)

    run_id = Column(String, ForeignKey('experimentrun.ulid'))
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
    __tablename__ = 'experimentrun'
    RELATIONSHIPS_TO_DICT = True

    ulid = Column(String, primary_key=True, default=lambda: str(ulid.ULID()))
    experiment_id = Column(String, ForeignKey('experiment.ulid'), nullable=True)
    experiment = relationship(Experiment, backref=backref("runs", cascade="all, delete-orphan"))
    environment_id = Column(Integer, ForeignKey('environment.ulid'), nullable=True)
    environment = relationship(Environment, backref=backref("runs", cascade="all, delete-orphan"))

    path = Column(String, nullable=True)

    timestamp_start = Column(DateTime, nullable=True)
    timestamp_end = Column(DateTime, nullable=True)

    status = Column(Integer, default=StatusEnum.PENDING)

    published = Column(Boolean, default=False)

    files_id = Column(Integer, ForeignKey('experimentrunfiles.id'), nullable=True)
    files = relationship(ExperimentRunFiles, backref=backref("experimentrun", uselist=False))

    # currently not used
    sha256_validation_hash = Column(String, nullable=True)

    @hybrid_property
    def is_valid(self):
        return bool(self.experiment_id and self.environment_id and self.files_id)

    @hybrid_property
    def experiment_name(self) -> str:
        return self.experiment.name if self.experiment else ''

    @hybrid_property
    def experiment_dotnotation(self) -> str:
        return f'{self.experiment.project.name}.{self.environment.name}.{self.experiment.name}'

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
        return next(
            (
                StatusEnum.ERROR
                for test in self.tests
                if test.status == StatusEnum.ERROR
            ),
            StatusEnum.SUCCESS,
        )

    def __str__(self):
        return str(self.ulid)

    def __repr__(self):
        return f"<ExperimentRun(ulid='{self.ulid}',experiment={self.experiment_id})>"
