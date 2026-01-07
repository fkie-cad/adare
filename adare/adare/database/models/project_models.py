"""
Project database models for project-specific resources.

This module defines SQLAlchemy ORM classes for project-specific resources
such as experiments, runs, and abstract tests. These models are stored in
individual project databases and reference global resources by ID.
"""

from sqlalchemy import Column, Integer, String, ForeignKey, Table, DateTime, CHAR, Boolean, func, Enum as SAEnum, Text, JSON, Index
from sqlalchemy.orm import relationship, backref
import ulid
from sqlalchemy_serializer import SerializerMixin
from sqlalchemy.ext.hybrid import hybrid_property
from adarelib.constants import StatusEnum
from sqlalchemy.orm import declarative_base

# Create separate base for project models
ProjectBase = declarative_base()


class Tag(SerializerMixin, ProjectBase):
    """
    Tag for categorizing experiments in project database.
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

StatusEnumType = SAEnum(StatusEnum, name="statusenum")

# Project mapping tables
mapping_experiment_abstracttest = Table(
    "mapping_experiment_abstracttest",
    ProjectBase.metadata,
    Column("experiment_id", ForeignKey("experiment.id")),
    Column("abstracttest_id", ForeignKey("abstract_test.id")),
)

mapping_experiment_tag = Table(
    "mapping_experiment_tag",
    ProjectBase.metadata,
    Column("experiment_id", ForeignKey("experiment.id")),
    Column("tag_id", ForeignKey("tag.id"))
)

mapping_experiment_environment = Table(
    "mapping_experiment_environment",
    ProjectBase.metadata,
    Column("experiment_id", ForeignKey("experiment.id")),
    Column("environment_id", String)  # Reference to global environment ID, not FK
)

mapping_abstracttest_testparameterentry = Table(
    "mapping_abstracttest_testparameterentry",
    ProjectBase.metadata,
    Column("abstracttest_id", ForeignKey("abstract_test.id")),
    Column("testparameterentry_id", ForeignKey("test_parameter_entry.id")),
)

mapping_usbdrive_experiment = Table(
    "mapping_usbdrive_experiment",
    ProjectBase.metadata,
    Column("usbdrive_id", ForeignKey("usb_drive.id")),
    Column("experiment_id", ForeignKey("experiment.id")),
)

mapping_abstracttest_tool = Table(
    "mapping_abstracttest_tool",
    ProjectBase.metadata,
    Column("abstract_test_id", ForeignKey("abstract_test.id")),
    Column("tool_id", ForeignKey("tool.id")),
)


class Status(SerializerMixin, ProjectBase):
    """
    Status for test results or events (project-specific).
    """
    __tablename__ = 'status'
    RELATIONSHIPS_TO_DICT = True

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    name = Column(String, nullable=False, unique=True, index=True)

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return f"<Status(name='{self.name}')>"


class Result(SerializerMixin, ProjectBase):
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


class TestParameterEntry(SerializerMixin, ProjectBase):
    """
    Parameter entry for abstract tests - project-specific values.
    """
    __tablename__ = 'test_parameter_entry'
    RELATIONSHIPS_TO_DICT = True

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    parameter_id = Column(String, nullable=False)  # Global test parameter ID
    value = Column(String, nullable=False)

    @property
    def parameter(self):
        """Get the global test parameter object for this entry."""
        from adare.database.reference_manager import reference_manager
        return reference_manager.get_testparameter_object(self.parameter_id)

    def __str__(self):
        param = self.parameter
        name = param.name if param else self.parameter_id
        return f"{name}={self.value}"

    def __repr__(self):
        param = self.parameter
        name = param.name if param else self.parameter_id
        return f"<TestParameterEntry(parameter='{name}',value='{self.value}')>"


class Tool(SerializerMixin, ProjectBase):
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


class AbstractTest(SerializerMixin, ProjectBase):
    """
    Abstract test definition within experiments.
    """
    __tablename__ = 'abstract_test'
    RELATIONSHIPS_TO_DICT = True

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    repetitions = Column(Integer, default=1)

    # Reference to global test function by ID (not FK)
    testfunction_id = Column(String, nullable=False)  # Global test function ID

    parameters = relationship(TestParameterEntry, secondary=mapping_abstracttest_testparameterentry)
    tools = relationship(Tool, secondary=mapping_abstracttest_tool)

    @property
    def testfunction(self):
        """Get the global test function object for this abstract test."""
        from adare.database.reference_manager import reference_manager
        return reference_manager.get_testfunction_object(self.testfunction_id)

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return f"<AbstractTest(name='{self.name}',testfunction_id='{self.testfunction_id}',repetitions={self.repetitions})>"


class LogFile(SerializerMixin, ProjectBase):
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


class USBDrive(SerializerMixin, ProjectBase):
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

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return f"<USBDrive(name='{self.name}',vendor_id='{self.vendor_id}',product_id='{self.product_id}')>"


class Experiment(SerializerMixin, ProjectBase):
    """
    Experiment definition within a project.
    """
    __tablename__ = 'experiment'
    RELATIONSHIPS_TO_DICT = True

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    name = Column(String, nullable=False, unique=True, index=True)
    description = Column(String, nullable=True)
    sha256 = Column(String, nullable=False)
    sha256_playbook = Column(String, nullable=True)
    sha256_metadata = Column(String, nullable=True)

    # Note: project_id removed as experiments are now stored per-project

    abstract_tests = relationship(AbstractTest, secondary=mapping_experiment_abstracttest)
    usb_drives = relationship(USBDrive, secondary=mapping_usbdrive_experiment)
    playbook = relationship("Playbook", back_populates="experiment", uselist=False, cascade="all, delete-orphan")
    tags = relationship(Tag, secondary=mapping_experiment_tag)

    # References to global resources (stored as string IDs, not FKs)
    environment_ids = Column(JSON, nullable=True)  # List of global environment IDs

    created_at = Column(DateTime, nullable=True, default=func.now())

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return f"<Experiment(name='{self.name}',description='{self.description}',id='{self.id}')>"

    @property
    def environments(self):
        """Get the global environment objects for this experiment."""
        if not self.environment_ids:
            return []
        from adare.database.reference_manager import reference_manager
        return [reference_manager.get_environment_object(env_id) for env_id in self.environment_ids if env_id]

    @property
    def environments_names(self):
        """Get environment names for this experiment."""
        envs = self.environments
        return [env.name for env in envs if env]

    @property
    def tags_names(self):
        """Get tag names for this experiment."""
        return [tag.name for tag in self.tags]


class Event(SerializerMixin, ProjectBase):
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
    error = Column(String)
    parent_event_id = Column(CHAR(26), ForeignKey('event.id', ondelete='SET NULL'), nullable=True)  # Parent event ID for nested events
    parent_event = relationship("Event", remote_side=[id], backref=backref("child_events", cascade="all, delete-orphan"))

    # Success/failure tracking for all events
    success = Column(Boolean, nullable=True)

    # Universal event grouping ID to group start/complete event pairs
    event_group_id = Column(String, nullable=True)     # Groups related events (start/complete pairs)

    # Specific event type (e.g., 'TEST_START', 'TEST_COMPLETE', 'CLICK_START', etc.)
    event_type_specific = Column(String, nullable=True)
    execution_time = Column(Integer, nullable=True)     # Duration in milliseconds

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

    def __str__(self):
        return str(self.error)

    def __repr__(self):
        return f"<ErrorEvent(error='{self.error}')>"

    @hybrid_property
    def stage_submessage(self):
        return f'{self.error}' if self.error else 'Unknown error'

    @hybrid_property
    def stage_result(self):
        return StatusEnum.ERROR


class ActionEvent(Event):
    """
    Event representing any action during experiment execution (click, keyboard, test, etc.).
    This is a flexible event type that can store various action types and their data.
    """
    __tablename__ = 'action_events'
    __mapper_args__ = {
        'polymorphic_identity': 'action_event',
    }
    id = Column(CHAR(26), ForeignKey('event.id'), primary_key=True)

    # Action type and event type fields
    action_type = Column(String)  # e.g., 'click', 'keyboard', 'test', etc.
    action_id = Column(String)    # Unique action identifier for pairing start/complete events

    # Generic action data as JSON-like text field
    # This allows us to store any action-specific data flexibly
    action_data = Column(String, nullable=True)  # JSON serialized action data

    @hybrid_property
    def display_level(self):
        """
        Compute display level based on parent relationship hierarchy.
        Root level actions have display_level = 0, each nested level adds 1.
        """
        if not self.parent_event_id:
            return 0  # Root level

        # Find parent event and recursively compute depth
        parent = self.__class__.query.filter_by(id=self.parent_event_id).first()
        if parent and hasattr(parent, 'display_level'):
            return parent.display_level + 1
        else:
            # If parent not found or doesn't have display_level, assume next level
            return 1

    @hybrid_property
    def stage_submessage(self):
        return f'{self.action_type} action'

    @hybrid_property
    def stage_result(self):
        if self.success is None:
            return StatusEnum.PENDING
        return StatusEnum.SUCCESS if self.success else StatusEnum.FAILED


class EventFactory:
    """
    Factory for creating event instances based on category.
    """
    @staticmethod
    def create_event(category, **kwargs):
        # add category to kwargs
        kwargs['category'] = category

        # Handle error_message -> error field mapping for backward compatibility
        if 'error_message' in kwargs and kwargs['error_message']:
            kwargs['error'] = kwargs.pop('error_message')

        if category == 'action' or category == 'command':
            return ActionEvent(**kwargs)
        elif category == 'test':
            return TestEvent(**kwargs)
        elif category == 'error':
            return ErrorEvent(**kwargs)
        else:
            raise ValueError(f'Invalid category: {category}')


class ExperimentRunFiles(SerializerMixin, ProjectBase):
    """
    Files associated with experiment runs.
    """
    __tablename__ = 'experiment_run_files'
    RELATIONSHIPS_TO_DICT = True

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))
    zip_file_path = Column(String, nullable=True)
    results_file_path = Column(String, nullable=True)
    actions_file_path = Column(String, nullable=True)
    system_info_file_path = Column(String, nullable=True)

    log_adare_id = Column(CHAR(26), ForeignKey('log_file.id', ondelete='SET NULL'), nullable=True)
    log_adare = relationship(LogFile, foreign_keys=[log_adare_id])

    log_adarevm_id = Column(CHAR(26), ForeignKey('log_file.id', ondelete='SET NULL'), nullable=True)
    log_adarevm = relationship(LogFile, foreign_keys=[log_adarevm_id])

    def __str__(self):
        return f"ExperimentRunFiles({self.id})"

    def __repr__(self):
        return f"<ExperimentRunFiles(id='{self.id}')>"


class Stage(SerializerMixin, ProjectBase):
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

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return f"<Stage(name='{self.name}',msg='{self.msg}')>"


class StageInRun(SerializerMixin, ProjectBase):
    """
    Stage execution within an experiment run.
    """
    __tablename__ = 'stage_in_run'
    RELATIONSHIPS_TO_DICT = True

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))

    stage_id = Column(CHAR(26), ForeignKey('stage.id', ondelete='CASCADE'), nullable=False)
    stage = relationship(Stage, backref=backref("stage_in_runs", cascade="all, delete-orphan"))

    status_id = Column(CHAR(26), ForeignKey('status.id', ondelete='RESTRICT'), nullable=False)
    status = relationship(Status, backref=backref("stage_in_runs"))

    run_id = Column(CHAR(26), ForeignKey('experiment_run.id', ondelete='CASCADE'))

    # start_time and end_time as DateTime for SQL compatibility
    start_time = Column(DateTime, nullable=True)
    end_time = Column(DateTime, nullable=True)

    def __str__(self):
        return f"StageInRun({self.stage.name if self.stage else 'Unknown'}, {self.status.name if self.status else 'Unknown'})"

    def __repr__(self):
        return f"<StageInRun(stage='{self.stage.name if self.stage else 'Unknown'}',status='{self.status.name if self.status else 'Unknown'}')>"


class ExperimentRun(SerializerMixin, ProjectBase):
    """
    Individual experiment run within a project.
    """
    __tablename__ = 'experiment_run'
    RELATIONSHIPS_TO_DICT = True

    id = Column(CHAR(26), primary_key=True, default=lambda: str(ulid.ULID()))

    experiment_id = Column(CHAR(26), ForeignKey('experiment.id', ondelete='CASCADE'), nullable=True)
    experiment = relationship(Experiment, backref=backref("runs", cascade="all, delete-orphan"))

    # Reference to global environment (stored as string ID, not FK)
    environment_id = Column(String, nullable=True)  # Global environment ID

    # Reference to global VM instance (stored as string ID, not FK)
    vm_instance_id = Column(String, nullable=True)  # Global VM instance ID

    path = Column(String, nullable=True)

    start_time = Column(DateTime, nullable=True)
    end_time = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=True, default=func.now())

    status = Column(StatusEnumType, default=StatusEnum.PENDING)
    fake = Column(Boolean, default=False)
    published = Column(Boolean, default=False)

    # Files associated with this run
    files_id = Column(CHAR(26), ForeignKey('experiment_run_files.id', ondelete='SET NULL'), nullable=True)
    files = relationship(ExperimentRunFiles, backref=backref("experiment_run", uselist=False))

    # Stages in this run
    stages_in_run = relationship(StageInRun, backref="experiment_run", cascade="all, delete-orphan")

    # Composite indexes for common query patterns
    __table_args__ = (
        Index('idx_run_experiment_status', 'experiment_id', 'status'),
        Index('idx_run_environment', 'environment_id', 'status'),
        Index('idx_run_vm_instance', 'vm_instance_id', 'status'),
    )

    def __str__(self):
        return f"ExperimentRun({self.experiment.name if self.experiment else 'Unknown'}, {self.id})"

    def __repr__(self):
        return f"<ExperimentRun(experiment='{self.experiment.name if self.experiment else 'Unknown'}',id='{self.id}',status='{self.status}')>"

    @property
    def environment(self):
        """Get the global environment object for this run."""
        if not self.environment_id:
            return None
        from adare.database.reference_manager import reference_manager
        return reference_manager.get_environment_object(self.environment_id)

    @property
    def environment_name(self):
        """Get the environment name for this run."""
        env = self.environment
        return env.name if env else None

    @property
    def vm_instance(self):
        """Get the global VM instance object for this run."""
        if not self.vm_instance_id:
            return None
        from adare.database.reference_manager import reference_manager
        return reference_manager.get_vm_instance_object(self.vm_instance_id)

    @hybrid_property
    def is_valid(self):
        return bool(self.experiment_id and self.environment_id and self.files_id)

    @hybrid_property
    def experiment_name(self) -> str:
        return self.experiment.name if self.experiment else ''

    @hybrid_property
    def experiment_dotnotation(self) -> str:
        # Handle cases where environment or experiment might be None
        if not self.environment or not self.experiment:
            return 'unknown.unknown.unknown'

        # Handle case where environment.project might be None - get from reference manager
        from adare.database.reference_manager import reference_manager
        env_obj = reference_manager.get_environment_object(self.environment_id)
        # Since environments are global and don't have project relationships,
        # we'll use 'unknown' for project name as environments are shared across projects
        project_name = 'unknown'

        return f'{project_name}.{env_obj.name if env_obj else "unknown"}.{self.experiment.name}'

    @hybrid_property
    def duration(self):
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None

    @hybrid_property
    def tests(self):
        return [
            event for event in self.events
            if isinstance(event, TestEvent)
        ]

    @hybrid_property
    def result_status(self):
        # Handle case where experiment is None
        if not self.experiment:
            return StatusEnum.ERROR

        # First check for test execution failures and result failures
        # This takes priority over missing tests since failed tests cause early termination
        for t in self.tests:
            # Check if test execution failed (success=False in Event base class)
            if hasattr(t, 'success') and t.success is False:
                return StatusEnum.FAILED

            # Check if test result indicates failure
            if t.result and int(t.result.status_id) != StatusEnum.SUCCESS:
                return StatusEnum.FAILED

        # Only check for missing tests if no tests failed
        # (missing tests are expected when earlier tests failed and stopped execution)
        for test in self.experiment.abstract_tests:
            found = False
            for t in self.tests:
                if t.abstract_test_id == test.id:
                    found = True
                    break
            if not found:
                return StatusEnum.TEST_MISSING

        return StatusEnum.SUCCESS

    @hybrid_property
    def ulid(self):
        """Provide ulid property that maps to the id field for consistency."""
        return self.id

    @ulid.setter
    def ulid(self, value):
        """Allow setting ulid which maps to the id field."""
        self.id = value
    

class Playbook(SerializerMixin, ProjectBase):
    """Main playbook container linked to experiment."""
    __tablename__ = 'playbook'
    RELATIONSHIPS_TO_DICT = True

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



class PlaybookItem(SerializerMixin, ProjectBase):
    """Unified model for actions and blocks with hierarchical support."""
    __tablename__ = 'playbook_item'
    RELATIONSHIPS_TO_DICT = True

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



class ActionExecution(SerializerMixin, ProjectBase):
    """Execution tracking per action step."""
    __tablename__ = 'action_execution'
    RELATIONSHIPS_TO_DICT = True

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

