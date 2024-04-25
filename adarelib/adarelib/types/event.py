# external imports
from typing import Literal, Optional
import attrs
import cattrs
from datetime import datetime
import uuid

import adarelib.config as config

# configure logging
import logging
log = logging.getLogger(__name__)


TEST_FAILED = 'failed'
TEST_SUCCESS = 'success'


@attrs.define
class Event:
    # action or test
    category: str
    timestamp: str
    status: str
    uuid: str
    error: str
    stage: str


@attrs.define
class ActionEvent(Event):
    name: str
    description: str
    category: str = 'action'
    timestamp: str = attrs.field(default=attrs.Factory(lambda: datetime.now().strftime(config.TIMESTAMP_FORMAT)))
    uuid: str = attrs.field(default=attrs.Factory(lambda: str(uuid.uuid4())))
    status = 'running'
    error: str = ''
    stage: str = ''


@attrs.define
class CommandEvent(Event):
    name: str
    command: str
    category: str = 'command'
    returncode: int = -1
    stdout: str = ''
    timestamp: str = attrs.field(default=attrs.Factory(lambda: datetime.now().strftime(config.TIMESTAMP_FORMAT)))
    uuid: str = attrs.field(default=attrs.Factory(lambda: str(uuid.uuid4())))
    status = 'running'
    error: str = ''
    stage: str = ''


@attrs.define
class TestResult:
    status: Literal['success', 'failure']
    details: list = attrs.field(default=attrs.Factory(list))


@attrs.define
class TestEvent(Event):
    test_name: str
    result: Optional[TestResult] = None
    category: str = 'test'
    timestamp: str = attrs.field(default=attrs.Factory(lambda: datetime.now().strftime(config.TIMESTAMP_FORMAT)))
    uuid: str = attrs.field(default=attrs.Factory(lambda: str(uuid.uuid4())))
    status = 'running'
    error: str = ''
    stage: str = ''


@attrs.define
class ErrorEvent(Event):
    error_name: str
    category: str = 'error'
    timestamp: str = attrs.field(default=attrs.Factory(lambda: datetime.now().strftime(config.TIMESTAMP_FORMAT)))
    uuid: str = attrs.field(default=attrs.Factory(lambda: str(uuid.uuid4())))
    status: str = ''
    stage: str = ''
    error: str = ''


@attrs.define
class GuiEvent(Event):
    pass


@attrs.define
class GuiFindEvent(GuiEvent):
    text: bool
    objective: str
    success: int = -1
    category: str = 'gui.find'
    timestamp: str = attrs.field(default=attrs.Factory(lambda: datetime.now().strftime(config.TIMESTAMP_FORMAT)))
    uuid: str = attrs.field(default=attrs.Factory(lambda: str(uuid.uuid4())))
    status = 'running'
    error: str = ''
    stage: str = ''


@attrs.define
class GuiClickEvent(GuiEvent):
    clicktype: str
    modifiers: list[str]
    target: str
    category: str = 'gui.click'
    timestamp: str = attrs.field(default=attrs.Factory(lambda: datetime.now().strftime(config.TIMESTAMP_FORMAT)))
    uuid: str = attrs.field(default=attrs.Factory(lambda: str(uuid.uuid4())))
    status = 'running'
    error: str = ''
    stage: str = ''


@attrs.define
class GuiKeypressEvent(GuiEvent):
    keys: list[str]
    category: str = 'gui.keypress'
    timestamp: str = attrs.field(default=attrs.Factory(lambda: datetime.now().strftime(config.TIMESTAMP_FORMAT)))
    uuid: str = attrs.field(default=attrs.Factory(lambda: str(uuid.uuid4())))
    status = 'running'
    error: str = ''
    stage: str = ''


@attrs.define
class GuiIdleEvent(GuiEvent):
    seconds: int
    category: str = 'gui.idle'
    timestamp: str = attrs.field(default=attrs.Factory(lambda: datetime.now().strftime(config.TIMESTAMP_FORMAT)))
    uuid: str = attrs.field(default=attrs.Factory(lambda: str(uuid.uuid4())))
    status = 'running'
    error: str = ''
    stage: str = ''


@attrs.define
class EventSystemData:
    version: str
    experiment: str
    start_time: str
    end_time: str
    events: list[Event] = attrs.field(default=attrs.Factory(list))

    @classmethod
    def from_dict(cls, data: dict):
        if not data:
            return None
        events = []
        for event in data['events']:
            supported_events = {
                'action': ActionEvent,
                'test': TestEvent,
                'gui.find': GuiFindEvent,
                'gui.click': GuiClickEvent,
                'gui.keypress': GuiKeypressEvent,
                'gui.idle': GuiIdleEvent,
                'command': CommandEvent,
            }
            if event['category'] in supported_events:
                event_class = supported_events[event['category']]
                events.append(cattrs.structure(event, event_class))
            else:
                log.warning(f'event category {event["category"]} is not supported')
        data['events'] = events
        return cls(**data)
