import attrs
from datetime import datetime
import cattrs


@attrs.define
class Stage:
    name: str
    description: str
    parent: "Stage" = None
    optional: bool = False
    start_time: datetime = None
    end_time: datetime = None

    def __str__(self):
        return f'{self.name}: {self.description}'

    @classmethod
    def from_data(cls, data: dict):
        subclasses = cls.__subclasses__()
        for subclass in subclasses:
            if subclass.name == data['name']:
                return cattrs.structure(data, subclass)
        return None


@attrs.define
class SetupStage(Stage):
    name = 'setup'
    description = 'todo ...'
    optional = False


@attrs.define
class BootStage(Stage):
    name = 'boot'
    description = 'todo ...'
    optional = False


@attrs.define
class InstallStage(Stage):
    name = 'install'
    description = 'todo ...'
    optional = False


@attrs.define
class MountStage(Stage):
    name = 'mount'
    description = 'todo ...'
    optional = True


@attrs.define
class ExperimentStage(Stage):
    name = 'experiment'
    description = 'todo ...'
    optional = False


@attrs.define
class DumpStage(Stage):
    name = 'dump'
    description = 'todo ...'
    optional = True


@attrs.define
class TeardownStage(Stage):
    name = 'teardown'
    description = 'todo ...'
    optional = False


@attrs.define
class CleanupStage(Stage):
    name = 'cleanup'
    description = 'todo ...'
    optional = False


