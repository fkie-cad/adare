from sqlalchemy import Column, Integer, String, ForeignKey, Table, DateTime, CHAR
from sqlalchemy.orm import relationship, backref, DeclarativeBase
import uuid

from sqlalchemy_serializer import SerializerMixin

class Base(DeclarativeBase):
    pass

mapping_experiment_test = Table(
    "mapping_experiment_test",
    Base.metadata,
    Column("experiment_uuid", ForeignKey("experiment.uuid")),
    Column("test_uuid", ForeignKey("test.uuid")),
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

mapping_test_testparameterentry = Table(
    "mapping_test_testparameterentry",
    Base.metadata,
    Column("test_uuid", ForeignKey("test.uuid")),
    Column("testparameterentry_id", ForeignKey("testparameterentry.id")),
)

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
    name = Column(String)
    test_name = Column(String)
    test_description = Column(String)

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


class Test(SerializerMixin, Base):
    __tablename__ = 'test'
    RELATIONSHIPS_TO_DICT = True
    serialize_rules = ('-tool_id','-testfunction_id','-result_id')

    uuid = Column(CHAR(32), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String)
    description = Column(String)
    tool_id = Column(Integer, ForeignKey('tool.id'), nullable=True)
    testfunction_id = Column(Integer, ForeignKey('testfunction.id'))
    result_id = Column(Integer, ForeignKey('result.id'))

    tool = relationship(Tool)
    testfunction = relationship(TestFunction)
    result = relationship(Result)

    testparameterentry = relationship(TestParameterEntry, secondary=mapping_test_testparameterentry)


    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return f"<Test(name='{self.name}',description='{self.description}',tool='{self.tool}',testfunction='{self.testfunction}')>"


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
    serialize_rules = ('-logfile_run_experiment','-logfile_postsetup_installations', '-logfile_vagrant', '-logfile_parse_and_test', '-logfile_gui_automation', '-logfile_installed_packages',
                       '-logfile_run_experiment_id','-logfile_postsetup_installations_id', '-logfile_vagrant_id', '-logfile_parse_and_test_id', '-logfile_gui_automation_id', '-logfile_installed_packages_id',
                       '-status_gui_automation', '-status_parse_and_test', '-status_vagrant',
                       '-status_id','-status_gui_automation_id','-status_parse_and_test_id','-status_vagrant_id',
                       '-os_info_id',
                       '-tags')

    uuid = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String)
    timestamp_start = Column(DateTime)
    timestamp_end = Column(DateTime)
    os_info_id = Column(Integer, ForeignKey('osinfo.id'))
    description = Column(String)

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

    os_info = relationship(OsInfo)
    tags = relationship(Tag, secondary=mapping_experiment_tag)
    tests = relationship(Test, secondary=mapping_experiment_test)

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

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return f"<Experiment(name='{self.name}',uuid='{self.uuid}')>"

