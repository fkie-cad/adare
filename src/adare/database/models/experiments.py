from sqlalchemy import Column, Integer, String, ForeignKey, Table, DateTime, CHAR
from sqlalchemy.orm import relationship, backref, DeclarativeBase
import uuid

from sqlalchemy_serializer import SerializerMixin

class Base(DeclarativeBase):
    pass

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
mapping_scenario_experiment = Table(
    "mapping_scenario_experiment",
    Base.metadata,
    Column("scenario_uuid", ForeignKey("scenario.uuid")),
    Column("experiment_uuid", ForeignKey("experiment.uuid")),
)
mapping_scenario_tag = Table(
    "mapping_scenario_tag",
    Base.metadata,
    Column("scenario_uuid", ForeignKey("scenario.uuid")),
    Column("tag_id", ForeignKey("tag.id")),
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


class PublishStatus(SerializerMixin, Base):
    """
        Collection of possible status.
    """
    __tablename__ = 'publishstatus'
    RELATIONSHIPS_TO_DICT = True
    serialize_rules = ('-id',)

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return f"<PublishStatus(name='{self.name}')>"


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
    serialize_rules = ('-id',)

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


class TestFunction(SerializerMixin, Base):
    __tablename__ = 'testfunction'
    RELATIONSHIPS_TO_DICT = True
    serialize_rules = ('-id',)

    id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(String)
    name = Column(String)
    description = Column(String)

    possible_parameters = relationship(TestParameter, secondary=mapping_testfunction_testparameter)

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return f"<TestFunction(name='{self.name}',test_name='{self.test_name}',test_description='{self.test_description}')>"


class Tool(SerializerMixin, Base):
    __tablename__ = 'tool'
    RELATIONSHIPS_TO_DICT = True
    serialize_rules = ('-id',)

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String)
    command = Column(String)

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return f"<Tool(name='{self.name}',command='{self.command}')>"


class AbstractTest(SerializerMixin, Base):
    __tablename__ = 'abstracttest'
    RELATIONSHIPS_TO_DICT = True

    uuid = Column(CHAR(32), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String)
    description = Column(String)

    testfunction = relationship(TestFunction)
    parameters = relationship(TestParameterEntry, secondary=mapping_abstracttest_testparameterentry)
    tool = relationship(Tool)

    testfunction_id = Column(Integer, ForeignKey('testfunction.id'))
    tool_id = Column(Integer, ForeignKey('tool.id'), nullable=True)

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
    abstracttest = relationship(AbstractTest)

    def __str__(self):
        return str(self.uuid)

    def __repr__(self):
        return f"<Test(uuid='{self.uuid}',abstracttest='{self.abstracttest}')>"



class OsInfo(SerializerMixin, Base):
    __tablename__ = 'osinfo'
    RELATIONSHIPS_TO_DICT = True
    serialize_rules = ('-id',)

    id = Column(Integer, primary_key=True, autoincrement=True)
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


class Experiment(SerializerMixin, Base):
    __tablename__ = 'experiment'
    RELATIONSHIPS_TO_DICT = True

    uuid = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String)
    description = Column(String)
    publish_status_id = Column(Integer, ForeignKey('publishstatus.id'), nullable=False)

    action_file = Column(String)
    testset_file = Column(String)

    os_info_id = Column(Integer, ForeignKey('osinfo.id'))

    os_info = relationship(OsInfo)
    publish_status = relationship(PublishStatus)
    tags = relationship(Tag, secondary=mapping_experiment_tag)
    abstract_tests = relationship(AbstractTest, secondary=mapping_experiment_abstracttest)

    experiment_hash = Column(String, nullable=True)

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return f"<Experiment(name='{self.name}',publish_status='{self.publish_status}')>"



class ExperimentRun(SerializerMixin, Base):
    __tablename__ = 'experimentrun'
    RELATIONSHIPS_TO_DICT = True
    serialize_rules = ('-logfile_run_experiment','-logfile_postsetup_installations', '-logfile_vagrant', '-logfile_parse_and_test', '-logfile_gui_automation', '-logfile_installed_packages',
                       '-logfile_run_experiment_id','-logfile_postsetup_installations_id', '-logfile_vagrant_id', '-logfile_parse_and_test_id', '-logfile_gui_automation_id', '-logfile_installed_packages_id',
                       '-status_gui_automation', '-status_parse_and_test', '-status_vagrant',
                       '-status_id','-status_gui_automation_id','-status_parse_and_test_id','-status_vagrant_id')

    uuid = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    experiment_id = Column(String, ForeignKey('experiment.uuid'))
    experiment = relationship(Experiment)
    timestamp_start = Column(DateTime)
    timestamp_end = Column(DateTime)
    tests = relationship(Test, secondary=mapping_experimentrun_test)
    publish_status_id = Column(Integer, ForeignKey('publishstatus.id'), nullable=True)
    publish_status = relationship(PublishStatus)

    status_id = Column(Integer, ForeignKey('status.id'))
    status_gui_automation_id = Column(Integer, ForeignKey('status.id'))
    status_parse_and_test_id = Column(Integer, ForeignKey('status.id'))
    status_vagrant_id = Column(Integer, ForeignKey('status.id'))

    logfile_gui_automation_id = Column(Integer, ForeignKey('logfile.uuid'), nullable=True)
    logfile_parse_and_test_id = Column(Integer, ForeignKey('logfile.uuid'), nullable=True)
    logfile_vagrant_id = Column(Integer, ForeignKey('logfile.uuid'), nullable=True)
    logfile_installed_packages_id = Column(Integer, ForeignKey('logfile.uuid'), nullable=True)
    logfile_postsetup_installations_id = Column(Integer, ForeignKey('logfile.uuid'), nullable=True)
    logfile_run_experiment_id = Column(Integer, ForeignKey('logfile.uuid'), nullable=True)

    status = relationship(Status, foreign_keys=[status_id])
    status_gui_automation = relationship(Status, foreign_keys=[status_gui_automation_id])
    status_parse_and_test = relationship(Status, foreign_keys=[status_parse_and_test_id])
    status_vagrant = relationship(Status, foreign_keys=[status_vagrant_id])

    logfile_gui_automation = relationship(LogFile, foreign_keys=[logfile_gui_automation_id])
    logfile_parse_and_test = relationship(LogFile, foreign_keys=[logfile_parse_and_test_id])
    logfile_vagrant = relationship(LogFile, foreign_keys=[logfile_vagrant_id])
    logfile_installed_packages = relationship(LogFile, foreign_keys=[logfile_installed_packages_id])
    logfile_postsetup_installations = relationship(LogFile, foreign_keys=[logfile_postsetup_installations_id])
    logfile_run_experiment = relationship(LogFile, foreign_keys=[logfile_run_experiment_id])

    sha256_validation_hash = Column(String, nullable=True)

    def __str__(self):
        return str(self.uuid)

    def __repr__(self):
        return f"<ExperimentRun(uuid='{self.uuid}',experiment={self.experiment_id})>"


class Scenario(SerializerMixin, Base):
    __tablename__ = 'scenario'
    RELATIONSHIPS_TO_DICT = True

    uuid = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String)
    description = Column(String)
    publish_status_id = Column(Integer, ForeignKey('publishstatus.id'), nullable=True)
    experiments = relationship(Experiment, secondary=mapping_scenario_experiment, backref='experiments')

    publish_status = relationship(PublishStatus)
    tags = relationship(Tag, secondary=mapping_scenario_tag)


    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return f"<experiment(name='{self.name}',publish_status='{self.publish_status}')>"


class Request(SerializerMixin, Base):
    __tablename__ = 'request'
    RELATIONSHIPS_TO_DICT = True

    uuid = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String)
    description = Column(String)
    type = Column(String)

    experiment_id = Column(String, ForeignKey('experiment.uuid'), nullable=True)
    experiment = relationship(Experiment)

    scenario_id = Column(String, ForeignKey('scenario.uuid'), nullable=True)
    scenario = relationship(Scenario)

    status_id = Column(Integer, ForeignKey('publishstatus.id'))
    status = relationship(PublishStatus)

    def __str__(self):
        return str(self.uuid)

    def __repr__(self):
        return f"<ExperimentRequest(uuid='{self.uuid}',experiment={self.experiment_id},scenario={self.scenario_id},status={self.status_id})>"
