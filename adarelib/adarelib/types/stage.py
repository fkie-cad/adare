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
        self.start_time = datetime.now()

    def set_status(self, status: int):
        if StatusEnum.is_valid(status):
            self.status = status
        else:
            raise ValueError(f'Invalid status: {status}')

    def end(self, status: int = StatusEnum.SUCCESS):
        self.end_time = datetime.now()
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
class ExperimentStage(Stage):
    name: typing.ClassVar[str] = 'box.experiment'
    msg: typing.ClassVar[str] = 'perform experiment'
    description: typing.ClassVar[str] = 'todo ...'
    optional: typing.ClassVar[bool] = False
    parent: typing.ClassVar["Stage"] = BoxRunStage


@attrs.define
class ExperimentTestStage(Stage):
    name: typing.ClassVar[str] = 'box.experiment.test'
    msg: typing.ClassVar[str] = 'test experiment'
    description: typing.ClassVar[str] = 'todo ...'
    optional: typing.ClassVar[bool] = False
    parent: typing.ClassVar["Stage"] = ExperimentStage


@attrs.define
class ExperimentGuiClickStage(Stage):
    name: typing.ClassVar[str] = 'box.experiment.gui:click'
    msg: typing.ClassVar[str] = 'click gui element'
    description: typing.ClassVar[str] = 'todo ...'
    optional: typing.ClassVar[bool] = False
    parent: typing.ClassVar["Stage"] = ExperimentStage
