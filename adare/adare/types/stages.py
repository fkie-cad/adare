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

@register_stage
@attrs.define
class VMStopStage(Stage):
    name: ClassVar[str] = 'vm_stop'
    msg: ClassVar[str] = 'Stopping Virtual Machine'

@register_stage
@attrs.define
class VMDestroyStage(Stage):
    name: ClassVar[str] = 'vm_destroy'
    msg: ClassVar[str] = 'Destroying Virtual Machine'

@register_stage
@attrs.define
class VMWaitTillReadyStage(Stage):
    name: ClassVar[str] = 'vm_wait_till_ready'
    msg: ClassVar[str] = 'Waiting until VM is ready'

@register_stage
@attrs.define
class VMCreateStage(Stage):
    name: ClassVar[str] = 'vm_create'
    msg: ClassVar[str] = 'Creating Virtual Machine'

@register_stage
@attrs.define
class VMMountSharedDirectoriesStage(Stage):
    name: ClassVar[str] = 'vm_mount_shared_directories'
    msg: ClassVar[str] = 'Mounting shared directories in VM'

@register_stage
@attrs.define
class CleanupStage(Stage):
    name: ClassVar[str] = 'cleanup'
    msg: ClassVar[str] = 'Performing cleanup tasks'

@register_stage
@attrs.define
class ExperimentIntegrityCheckStage(Stage):
    name: ClassVar[str] = 'integrity_check_experiment'
    msg: ClassVar[str] = 'Performing integrity check on experiment'

@register_stage
@attrs.define
class ProjectIntegrityCheckStage(Stage):
    name: ClassVar[str] = 'integrity_check_project'
    msg: ClassVar[str] = 'Performing integrity check on project'

@register_stage
@attrs.define
class InstallAdareVMStage(Stage):
    name: ClassVar[str] = 'vm.install_adare_vm'
    msg: ClassVar[str] = 'Waiting until adarevm is installed in the VM'
    parent: ClassVar[str] = 'vm_start'

@register_stage
@attrs.define
class ConnectToVMStage(Stage):
    name: ClassVar[str] = 'vm.connect_to_vm'
    msg: ClassVar[str] = 'Connecting to the VM via Websocket'
    parent: ClassVar[str] = 'vm_start'

@register_stage
@attrs.define
class InstallationsStage(Stage):
    name: ClassVar[str] = 'vm.installations'
    msg: ClassVar[str] = 'Installing additional software'
    parent: ClassVar[str] = 'vm_start'

@register_stage
@attrs.define
class ExperimentRunStage(Stage):
    name: ClassVar[str] = 'vm.experiment_run'
    msg: ClassVar[str] = 'Running the experiment'
    parent: ClassVar[str] = 'vm_start'

@register_stage
@attrs.define
class ExperimentTestStage(Stage):
    name: ClassVar[str] = 'vm.experiment_run.test'
    msg: ClassVar[str] = 'test'
    parent: ClassVar[str] = 'vm.experiment_run'

@register_stage
@attrs.define
class ExperimentGuiClickStage(Stage):
    name: ClassVar[str] = 'vm.experiment_run.gui:click'
    msg: ClassVar[str] = 'gui.click'
    parent: ClassVar[str] = 'vm.experiment_run'

@register_stage
@attrs.define
class ExperimentGuiIdleStage(Stage):
    name: ClassVar[str] = 'vm.experiment_run.gui:idle'
    msg: ClassVar[str] = 'gui.idle'
    parent: ClassVar[str] = 'vm.experiment_run'

@register_stage
@attrs.define
class ExperimentGuiFindStage(Stage):
    name: ClassVar[str] = 'vm.experiment_run.gui:find'
    msg: ClassVar[str] = 'gui.find'
    parent: ClassVar[str] = 'vm.experiment_run'

@register_stage
@attrs.define
class ExperimentGuiKeypressStage(Stage):
    name: ClassVar[str] = 'vm.experiment_run.gui:keypress'
    msg: ClassVar[str] = 'gui.keypress'
    parent: ClassVar[str] = 'vm.experiment_run'

@register_stage
@attrs.define
class ExperimentCommandStage(Stage):
    name: ClassVar[str] = 'vm.experiment_run.command'
    msg: ClassVar[str] = 'command'
    parent: ClassVar[str] = 'vm.experiment_run'

@register_stage
@attrs.define
class VagrantBoxExistCheckStage(Stage):
    name: ClassVar[str] = 'vm_exist_check'
    msg: ClassVar[str] = 'Checking if Vagrant box exists'

@register_stage
@attrs.define
class RunDirectoryCreationStage(Stage):
    name: ClassVar[str] = 'run_dir_creation'
    msg: ClassVar[str] = 'Creating run directory'