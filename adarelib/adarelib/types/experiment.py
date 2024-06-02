import attrs
from datetime import datetime
import cattrs
import typing


@attrs.define
class Stage:
    description: typing.ClassVar[str] = 'stage description'
    name: typing.ClassVar[str] = 'stage'
    parent: typing.ClassVar["Stage"] = None
    optional: typing.ClassVar[bool] = False
    start_time: datetime = None
    end_time: datetime = None

    def __str__(self):
        return f'{self.name}: {self.description}'

    @classmethod
    def from_data(cls, data: dict):
        subclasses = cls.__subclasses__()
        return next(
            (
                cattrs.structure(data, subclass)
                for subclass in subclasses
                if subclass.name == data['name']
            ),
            None,
        )

    @classmethod
    def get_subclasses(cls):
        return cls.__subclasses__()


@attrs.define
class SetupStage(Stage):
    name: typing.ClassVar[str] = 'setup'
    description: typing.ClassVar[str] = 'todo ...'
    optional: typing.ClassVar[bool] = False
    parent: typing.ClassVar["Stage"] = None


@attrs.define
class BootStage(Stage):
    name: typing.ClassVar[str] = 'boot'
    description: typing.ClassVar[str] = 'todo ...'
    optional: typing.ClassVar[bool] = False
    parent: typing.ClassVar["Stage"] = None


@attrs.define
class InstallStage(Stage):
    name: typing.ClassVar[str] = 'install'
    description: typing.ClassVar[str] = 'todo ...'
    optional: typing.ClassVar[bool] = False
    parent: typing.ClassVar["Stage"] = None


@attrs.define
class MountStage(Stage):
    name: typing.ClassVar[str] = 'mount'
    description: typing.ClassVar[str] = 'todo ...'
    optional: typing.ClassVar[bool] = True
    parent: typing.ClassVar["Stage"] = None


@attrs.define
class ExperimentStage(Stage):
    name: typing.ClassVar[str] = 'experiment'
    description: typing.ClassVar[str] = 'todo ...'
    optional: typing.ClassVar[bool] = False
    parent: typing.ClassVar["Stage"] = None


@attrs.define
class DumpStage(Stage):
    name: typing.ClassVar[str] = 'dump'
    description: typing.ClassVar[str] = 'todo ...'
    optional: typing.ClassVar[bool] = True
    parent: typing.ClassVar["Stage"] = None


@attrs.define
class TeardownStage(Stage):
    name: typing.ClassVar[str] = 'teardown'
    description: typing.ClassVar[str] = 'todo ...'
    optional: typing.ClassVar[bool] = False
    parent: typing.ClassVar["Stage"] = None


@attrs.define
class CleanupStage(Stage):
    name: typing.ClassVar[str] = 'cleanup'
    description: typing.ClassVar[str] = 'todo ...'
    optional: typing.ClassVar[bool] = False
    parent: typing.ClassVar["Stage"] = None


