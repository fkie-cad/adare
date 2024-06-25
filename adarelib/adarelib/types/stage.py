import attrs
from datetime import datetime
import cattrs
import typing
import threading

from adarelib.config import StatusEnum


@attrs.define
class Stage:
    description: typing.ClassVar[str] = 'stage description'
    name: typing.ClassVar[str] = 'stage'
    msg: typing.ClassVar[str] = 'todo ...'
    parent: typing.ClassVar["Stage"] = None
    optional: typing.ClassVar[bool] = False
    # set default to now
    start_time: datetime = None
    end_time: datetime = None
    status: int = attrs.field(default=StatusEnum.NONE)
    sub_msg: str = ''
    result_status: int = attrs.field(default=StatusEnum.NONE)

    def __str__(self):
        return f'{self.name}: {self.msg}'

    def start(self):
        self.start_time = datetime.utcnow()

    def set_status(self, status: int):
        self.status = status

    def end(self, status: int = StatusEnum.FINISHED):
        self.end_time = datetime.utcnow()
        if self.status == StatusEnum.NONE:
            self.status = status

    @classmethod
    def get_subclass(cls, name: str):
        return next(
            (subclass for subclass in cls.get_subclasses() if subclass.name == name),
            None
        )

    @classmethod
    def get_subclasses(cls):
        return cls.__subclasses__()


@attrs.define
class BoxRunStage(Stage):
    name: typing.ClassVar[str] = 'box_run'
    msg: typing.ClassVar[str] = 'run vagrant box'
    description: typing.ClassVar[str] = 'todo ...'
    optional: typing.ClassVar[bool] = False
    parent: typing.ClassVar["Stage"] = None


@attrs.define
class BoxDestroyStage(Stage):
    name: typing.ClassVar[str] = 'box_destroy'
    msg: typing.ClassVar[str] = 'destroy vagrant box'
    description: typing.ClassVar[str] = 'todo ...'
    optional: typing.ClassVar[bool] = False
    parent: typing.ClassVar["Stage"] = None


@attrs.define
class CleanupStage(Stage):
    name: typing.ClassVar[str] = 'cleanup'
    msg: typing.ClassVar[str] = 'cleanup'
    description: typing.ClassVar[str] = 'todo ...'
    optional: typing.ClassVar[bool] = False
    parent: typing.ClassVar["Stage"] = None


@attrs.define
class ExperimentIntegrityCheckStage(Stage):
    name: typing.ClassVar[str] = 'integrity_check_experiment'
    msg: typing.ClassVar[str] = 'integrity check experiment'
    description: typing.ClassVar[str] = 'todo ...'
    optional: typing.ClassVar[bool] = False
    parent: typing.ClassVar["Stage"] = None


@attrs.define
class ProjectIntegrityCheckStage(Stage):
    name: typing.ClassVar[str] = 'integrity_check_project'
    msg: typing.ClassVar[str] = 'integrity check project'
    description: typing.ClassVar[str] = 'todo ...'
    optional: typing.ClassVar[bool] = False
    parent: typing.ClassVar["Stage"] = None


@attrs.define
class InstallationsStage(Stage):
    name: typing.ClassVar[str] = 'box.installations'
    msg: typing.ClassVar[str] = 'install additional software'
    description: typing.ClassVar[str] = 'todo ...'
    optional: typing.ClassVar[bool] = False
    parent: typing.ClassVar["Stage"] = BoxRunStage


@attrs.define
class ExperimentSetupStage(Stage):
    name: typing.ClassVar[str] = 'box.experiment_setup'
    msg: typing.ClassVar[str] = 'install adarevm and setup experiment'
    description: typing.ClassVar[str] = 'todo ...'
    optional: typing.ClassVar[bool] = False
    parent: typing.ClassVar["Stage"] = BoxRunStage


@attrs.define
class ExperimentRunStage(Stage):
    name: typing.ClassVar[str] = 'box.experiment_run'
    msg: typing.ClassVar[str] = 'run the experiment'
    description: typing.ClassVar[str] = 'todo ...'
    optional: typing.ClassVar[bool] = False
    parent: typing.ClassVar["Stage"] = BoxRunStage


@attrs.define
class ExperimentTestStage(Stage):
    name: typing.ClassVar[str] = 'box.experiment_run.test'
    msg: typing.ClassVar[str] = 'test'
    description: typing.ClassVar[str] = 'todo ...'
    optional: typing.ClassVar[bool] = False
    parent: typing.ClassVar["Stage"] = ExperimentRunStage


@attrs.define
class ExperimentGuiClickStage(Stage):
    name: typing.ClassVar[str] = 'box.experiment_run.gui:click'
    msg: typing.ClassVar[str] = 'gui.click'
    description: typing.ClassVar[str] = 'todo ...'
    optional: typing.ClassVar[bool] = False
    parent: typing.ClassVar["Stage"] = ExperimentRunStage


@attrs.define
class ExperimentGuiIdleStage(Stage):
    name: typing.ClassVar[str] = 'box.experiment_run.gui:idle'
    msg: typing.ClassVar[str] = 'gui.idle'
    description: typing.ClassVar[str] = 'todo ...'
    optional: typing.ClassVar[bool] = False
    parent: typing.ClassVar["Stage"] = ExperimentRunStage


@attrs.define
class ExperimentGuiFindStage(Stage):
    name: typing.ClassVar[str] = 'box.experiment_run.gui:find'
    msg: typing.ClassVar[str] = 'gui.find'
    description: typing.ClassVar[str] = 'todo ...'
    optional: typing.ClassVar[bool] = False
    parent: typing.ClassVar["Stage"] = ExperimentRunStage


@attrs.define
class ExperimentGuiKeypressStage(Stage):
    name: typing.ClassVar[str] = 'box.experiment_run.gui:keypress'
    msg: typing.ClassVar[str] = 'gui.keypress'
    description: typing.ClassVar[str] = 'todo ...'
    optional: typing.ClassVar[bool] = False
    parent: typing.ClassVar["Stage"] = ExperimentRunStage


@attrs.define
class ExperimentCommandStage(Stage):
    name: typing.ClassVar[str] = 'box.experiment_run.command'
    msg: typing.ClassVar[str] = 'command'
    description: typing.ClassVar[str] = 'todo ...'
    optional: typing.ClassVar[bool] = False
    parent: typing.ClassVar["Stage"] = ExperimentRunStage


@attrs.define
class VagrantBoxExistCheckStage(Stage):
    name: typing.ClassVar[str] = 'box_exist_check'
    msg: typing.ClassVar[str] = 'check if vagrant box exists'
    description: typing.ClassVar[str] = 'todo ...'
    optional: typing.ClassVar[bool] = False
    parent: typing.ClassVar["Stage"] = None


@attrs.define
class RunDirectoryCreationStage(Stage):
    name: typing.ClassVar[str] = 'run_dir_creation'
    msg: typing.ClassVar[str] = 'create run directory'
    description: typing.ClassVar[str] = 'todo ...'
    optional: typing.ClassVar[bool] = False
    parent: typing.ClassVar["Stage"] = None

