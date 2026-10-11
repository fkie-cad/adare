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

# Login session models live in the global database
from .login import Token, UserSession
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

__all__ = [
    "DevCheckpoint",
    "DevSession",
    "Environment",
    "GlobalBase",
    "Token",
    "UserSession",
    "OsInfo",
    "PostSetupInstallation",
    "Project",
    "SyncMetadata",
    "Tag",
    "TestFunction",
    "TestFunctionFile",
    "TestParameter",
    "Vm",
    "VmSnapshot",
    "AbstractTest",
    "ActionExecution",
    "Event",
    "Experiment",
    "ExperimentRun",
    "ExperimentRunFiles",
    "LogFile",
    "Playbook",
    "PlaybookItem",
    "ProjectBase",
    "Result",
    "Stage",
    "StageInRun",
    "Status",
    "TestParameterEntry",
    "Tool",
    "USBDrive",
    "ProjectTag",
]
