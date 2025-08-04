import attrs
from datetime import datetime, timezone
import typing
from typing import ClassVar
import cattrs

from adarelib.constants import StatusEnum

# -------------------------------
# Stage Registry Infrastructure
# -------------------------------

_stage_registry: dict[str, typing.Type["Stage"]] = {}

def register_stage(cls: typing.Type["Stage"]) -> typing.Type["Stage"]:
    instance = cls()
    if not hasattr(instance, "name"):
        raise ValueError(f"Cannot register stage without 'name': {cls}")
    _stage_registry[instance.name] = cls
    return cls
def get_stage_class(name: str) -> typing.Optional[typing.Type["Stage"]]:
    return _stage_registry.get(name)

# -------------------------------
# cattrs Converter Setup
# -------------------------------

converter = cattrs.Converter()

# Handle datetime → str and back
converter.register_unstructure_hook(datetime, lambda dt: dt.isoformat() if dt else None)
converter.register_structure_hook(datetime, lambda s, _: datetime.fromisoformat(s) if s else None)

# Handle StatusEnum → int and back
converter.register_unstructure_hook(StatusEnum, lambda e: int(e))
converter.register_structure_hook(StatusEnum, lambda i, _: StatusEnum(i))

# -------------------------------
# Stage Base Class
# -------------------------------

@attrs.define
class Stage:
    # Class-level metadata
    name: ClassVar[str] = 'stage'
    msg: ClassVar[str] = 'todo ...'
    description: ClassVar[str] = 'stage description'
    parent: ClassVar[typing.Optional[str]] = None
    optional: ClassVar[bool] = False

    # Runtime state (instance fields)
    start_time: typing.Optional[datetime] = None
    end_time: typing.Optional[datetime] = None
    status: int = attrs.field(default=StatusEnum.NONE)
    sub_msg: str = ''
    result_status: int = attrs.field(default=StatusEnum.NONE)

    def __str__(self):
        return f'{self.name}: {self.msg}'

    def start(self):
        self.start_time = datetime.now(timezone.utc)

    def end(self, status: int = StatusEnum.FINISHED):
        self.end_time = datetime.now(timezone.utc)
        if self.status == StatusEnum.NONE:
            self.status = status

    def set_status(self, status: int):
        self.status = status

    def to_dict(self) -> dict:
        data = converter.unstructure(self)
        # Inject class-level metadata into the dict
        data.update({
            'name': self.name,
            'msg': self.msg,
            'description': self.description,
            'parent': self.parent,
            'optional': self.optional,
        })
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Stage":
        stage_cls = get_stage_class(data["name"])
        if not stage_cls:
            raise ValueError(f"Unknown stage: {data['name']}")
        return converter.structure(data, stage_cls)

    @classmethod
    def get_subclasses(cls) -> list[type]:
        """Recursively get all subclasses of this Stage class."""
        subclasses = set()
        def recurse(sub):
            for sc in sub.__subclasses__():
                subclasses.add(sc)
                recurse(sc)
        recurse(cls)
        return list(subclasses)

# ----------------------------------
# Concrete Stages
# ----------------------------------

@register_stage
@attrs.define
class VMRunStage(Stage):
    name: ClassVar[str] = 'vm_start'
    msg: ClassVar[str] = 'Starting Virtual Machine'
    parent: ClassVar[str] = 'vm_setup'

@register_stage
@attrs.define
class VMStopStage(Stage):
    name: ClassVar[str] = 'vm_stop'
    msg: ClassVar[str] = 'Stopping Virtual Machine'
    parent: ClassVar[str] = 'cleanup_shutdown'

@register_stage
@attrs.define
class VMDestroyStage(Stage):
    name: ClassVar[str] = 'vm_destroy'
    msg: ClassVar[str] = 'Destroying Virtual Machine'
    parent: ClassVar[str] = 'cleanup_shutdown'

@register_stage
@attrs.define
class VMWaitTillReadyStage(Stage):
    name: ClassVar[str] = 'vm_wait_till_ready'
    msg: ClassVar[str] = 'Waiting until VM is ready'
    parent: ClassVar[str] = 'vm_setup'

@register_stage
@attrs.define
class VMCreateStage(Stage):
    name: ClassVar[str] = 'vm_create'
    msg: ClassVar[str] = 'Creating Virtual Machine'
    parent: ClassVar[str] = 'vm_setup'

@register_stage
@attrs.define
class VMMountSharedDirectoriesStage(Stage):
    name: ClassVar[str] = 'vm_mount_shared_directories'
    msg: ClassVar[str] = 'Mounting shared directories in VM'
    parent: ClassVar[str] = 'vm_setup'

@register_stage
@attrs.define
class ExperimentIntegrityCheckStage(Stage):
    name: ClassVar[str] = 'integrity_check_experiment'
    msg: ClassVar[str] = 'Checking experiment integrity'
    parent: ClassVar[str] = 'experiment_preparation'

@register_stage
@attrs.define
class ProjectIntegrityCheckStage(Stage):
    name: ClassVar[str] = 'integrity_check_project'
    msg: ClassVar[str] = 'Checking project integrity'
    parent: ClassVar[str] = 'experiment_preparation'

@register_stage
@attrs.define
class InstallAdareVMStage(Stage):
    name: ClassVar[str] = 'install_adare_vm'
    msg: ClassVar[str] = 'Installing AdareVM'
    parent: ClassVar[str] = 'software_installation'

@register_stage
@attrs.define
class ConnectToVMStage(Stage):
    name: ClassVar[str] = 'connect_to_vm'
    msg: ClassVar[str] = 'Connecting to VM via WebSocket'
    parent: ClassVar[str] = 'software_installation'

@register_stage
@attrs.define
class InstallationsStage(Stage):
    name: ClassVar[str] = 'environment_installations'
    msg: ClassVar[str] = 'Installing environment software'
    parent: ClassVar[str] = 'software_installation'

@register_stage
@attrs.define
class ExperimentRunStage(Stage):
    name: ClassVar[str] = 'experiment_run'
    msg: ClassVar[str] = 'Running the experiment'
    parent: ClassVar[str] = 'experiment_execution'

@register_stage
@attrs.define
class ExperimentTestStage(Stage):
    name: ClassVar[str] = 'experiment_test'
    msg: ClassVar[str] = 'Running test'
    parent: ClassVar[str] = 'experiment_run'

@register_stage
@attrs.define
class ExperimentGuiClickStage(Stage):
    name: ClassVar[str] = 'gui_click'
    msg: ClassVar[str] = 'GUI click action'
    parent: ClassVar[str] = 'experiment_run'

@register_stage
@attrs.define
class ExperimentGuiIdleStage(Stage):
    name: ClassVar[str] = 'gui_idle'
    msg: ClassVar[str] = 'GUI idle wait'
    parent: ClassVar[str] = 'experiment_run'

@register_stage
@attrs.define
class ExperimentGuiFindStage(Stage):
    name: ClassVar[str] = 'gui_find'
    msg: ClassVar[str] = 'GUI find element'
    parent: ClassVar[str] = 'experiment_run'

@register_stage
@attrs.define
class ExperimentGuiKeypressStage(Stage):
    name: ClassVar[str] = 'gui_keypress'
    msg: ClassVar[str] = 'GUI keypress action'
    parent: ClassVar[str] = 'experiment_run'

@register_stage
@attrs.define
class ExperimentCommandStage(Stage):
    name: ClassVar[str] = 'experiment_command'
    msg: ClassVar[str] = 'Executing command'
    parent: ClassVar[str] = 'experiment_run'

@register_stage
@attrs.define
class VagrantBoxExistCheckStage(Stage):
    name: ClassVar[str] = 'vm_exist_check'
    msg: ClassVar[str] = 'Checking if Vagrant box exists'

# ----------------------------------
# Top-Level Parent Stages (Main Progress Phases)
# ----------------------------------

@register_stage
@attrs.define
class ExperimentPreparationStage(Stage):
    name: ClassVar[str] = 'experiment_preparation'
    msg: ClassVar[str] = 'Preparing experiment'
    description: ClassVar[str] = 'Setting up directories, validating configuration, and performing integrity checks'

@register_stage
@attrs.define
class VirtualMachineSetupStage(Stage):
    name: ClassVar[str] = 'vm_setup'
    msg: ClassVar[str] = 'Setting up Virtual Machine'
    description: ClassVar[str] = 'Creating, starting, and configuring the virtual machine'

@register_stage
@attrs.define
class SoftwareInstallationStage(Stage):
    name: ClassVar[str] = 'software_installation'
    msg: ClassVar[str] = 'Installing software and services'
    description: ClassVar[str] = 'Installing AdareVM, connecting services, and setting up environment'

@register_stage
@attrs.define
class ExperimentExecutionStage(Stage):
    name: ClassVar[str] = 'experiment_execution'
    msg: ClassVar[str] = 'Executing experiment'
    description: ClassVar[str] = 'Running the experiment playbook and tests'

@register_stage
@attrs.define
class CleanupShutdownStage(Stage):
    name: ClassVar[str] = 'cleanup_shutdown'
    msg: ClassVar[str] = 'Cleanup and shutdown'
    description: ClassVar[str] = 'Finalizing results and cleaning up resources'

# ----------------------------------
# Sub-Stages for Experiment Preparation
# ----------------------------------

@register_stage
@attrs.define
class SetupDirectoriesStage(Stage):
    name: ClassVar[str] = 'setup_directories'
    msg: ClassVar[str] = 'Setting up directories'
    parent: ClassVar[str] = 'experiment_preparation'

@register_stage
@attrs.define
class ValidatePlaybookStage(Stage):
    name: ClassVar[str] = 'validate_playbook'
    msg: ClassVar[str] = 'Validating playbook'
    parent: ClassVar[str] = 'experiment_preparation'

@register_stage
@attrs.define
class ResolveEnvironmentStage(Stage):
    name: ClassVar[str] = 'resolve_environment'
    msg: ClassVar[str] = 'Resolving environment'
    parent: ClassVar[str] = 'experiment_preparation'

@register_stage
@attrs.define
class CheckAppdataStage(Stage):
    name: ClassVar[str] = 'check_appdata'
    msg: ClassVar[str] = 'Checking application data'
    parent: ClassVar[str] = 'experiment_preparation'

@register_stage
@attrs.define
class RunDirectoryCreationStage(Stage):
    name: ClassVar[str] = 'run_dir_creation'
    msg: ClassVar[str] = 'Creating run directory'
    parent: ClassVar[str] = 'experiment_preparation'

@register_stage
@attrs.define
class StartMCPServerStage(Stage):
    name: ClassVar[str] = 'start_mcp_server'
    msg: ClassVar[str] = 'Starting MCP server'
    parent: ClassVar[str] = 'experiment_preparation'

# ----------------------------------
# Sub-Stages for Cleanup & Shutdown
# ----------------------------------

@register_stage
@attrs.define
class FinalizeStage(Stage):
    name: ClassVar[str] = 'finalize'
    msg: ClassVar[str] = 'Finalizing results'
    parent: ClassVar[str] = 'cleanup_shutdown'

@register_stage
@attrs.define
class ShutdownMCPServerStage(Stage):
    name: ClassVar[str] = 'shutdown_mcp_server'
    msg: ClassVar[str] = 'Stopping MCP server'
    parent: ClassVar[str] = 'cleanup_shutdown'

@register_stage
@attrs.define
class ShutdownWebSocketStage(Stage):
    name: ClassVar[str] = 'shutdown_websocket'
    msg: ClassVar[str] = 'Disconnecting WebSocket'
    parent: ClassVar[str] = 'cleanup_shutdown'