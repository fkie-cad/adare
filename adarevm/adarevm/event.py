from datetime import datetime
from pathlib import Path
import attrs

from adarevm.config import TIMESTAMP_FORMAT
from adarelib.helperfunctions.yaml import dict_to_yaml
from adarevm.testset.teststatus import TestStatus

import logging
log = logging.getLogger(__name__)


@attrs.define
class Event:
    # action or test
    category: str
    timestamp: str


@attrs.define
class ActionEvent(Event):
    name: str
    description: str
    category: str = 'action'
    timestamp: str = attrs.field(default=attrs.Factory(lambda: datetime.now().strftime(TIMESTAMP_FORMAT)))


@attrs.define
class CommandStart(Event):
    command_name: str
    category: str = 'command'
    timestamp: str = attrs.field(default=attrs.Factory(lambda: datetime.now().strftime(TIMESTAMP_FORMAT)))


@attrs.define
class CommandEnd(Event):
    command_name: str
    category: str = 'command'
    timestamp: str = attrs.field(default=attrs.Factory(lambda: datetime.now().strftime(TIMESTAMP_FORMAT)))



@attrs.define
class TestStart(Event):
    test_name: str
    category: str = 'test'
    timestamp: str = attrs.field(default=attrs.Factory(lambda: datetime.now().strftime(TIMESTAMP_FORMAT)))


@attrs.define
class TestEnd(Event):
    test_name: str
    status: TestStatus
    details: list = attrs.field(default=attrs.Factory(list))
    category: str = 'test'
    timestamp: str = attrs.field(default=attrs.Factory(lambda: datetime.now().strftime(TIMESTAMP_FORMAT)))


@attrs.define
class EventSystemData:
    version: str
    experiment: str
    start_time: str
    end_time: str
    events: list = attrs.field(default=attrs.Factory(list))


class EventSystem:
    path: Path
    data: EventSystemData

    def __init__(self, path: Path, experiment_name: str):
        self.path = path
        self.data = EventSystemData(
            version='0.1',
            experiment=experiment_name,
            start_time=datetime.now().strftime(TIMESTAMP_FORMAT),
            end_time='',
            events=[]
        )

    def log(self, event: Event):
        self.data.events.append(event)

    def save(self):
        self.data.end_time = datetime.now().strftime(TIMESTAMP_FORMAT)
        data = attrs.asdict(self.data)
        dict_to_yaml(self.path, data)
