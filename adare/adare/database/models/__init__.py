from sqlalchemy.orm import declarative_base

# Legacy base for backward compatibility
Base = declarative_base()

# Import all models to ensure they're registered

# Import new model structures
from .global_models import GlobalBase
from .project_models import ProjectBase

# Import all global models
from .global_models import (
    SyncMetadata, Tag, PostSetupInstallation, TestParameter, TestFunctionFile,
    TestFunction, OsInfo, Project, Vm, VmSnapshot, Environment
)

# Import dev mode models
from .devsession import DevSession
from .devcheckpoint import DevCheckpoint

# Import all project models
from .project_models import (
    Tag as ProjectTag, Status, Result, TestParameterEntry, Tool, AbstractTest, LogFile, USBDrive,
    Experiment, Event, ExperimentRunFiles, Stage, StageInRun, ExperimentRun,
    Playbook, PlaybookItem, ActionExecution
)
