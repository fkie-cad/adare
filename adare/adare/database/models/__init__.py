from sqlalchemy.orm import declarative_base

# Legacy base for backward compatibility
Base = declarative_base()

# Import all models to ensure they're registered

# Import new model structures
from .devcheckpoint import DevCheckpoint

# Import dev mode models
from .devsession import DevSession

# Import all global models
from .global_models import (
    Environment,
    GlobalBase,
    OsInfo,
    PostSetupInstallation,
    Project,
    SyncMetadata,
    Tag,
    TestFunction,
    TestFunctionFile,
    TestParameter,
    Vm,
    VmSnapshot,
)
from .project_models import (
    AbstractTest,
    ActionExecution,
    Event,
    Experiment,
    ExperimentRun,
    ExperimentRunFiles,
    LogFile,
    Playbook,
    PlaybookItem,
    ProjectBase,
    Result,
    Stage,
    StageInRun,
    Status,
    TestParameterEntry,
    Tool,
    USBDrive,
)

# Import all project models
from .project_models import Tag as ProjectTag
