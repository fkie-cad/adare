# external imports
from typing import Literal, Optional
import attrs
import cattrs
from datetime import datetime
import ulid

from adarelib.constants import StatusEnum, TIMESTAMP_FORMAT

# configure logging
import logging
log = logging.getLogger(__name__)


@attrs.define
class Event:
    # action or test
    category: str
    timestamp: str
    status: int
    ulid: str
    error: str


# @attrs.define
# class ActionEvent(Event):
#     name: str
#     description: str
#     category: str = 'action'
#     timestamp: str = attrs.field(default=attrs.Factory(lambda: datetime.utcnow().strftime(TIMESTAMP_FORMAT)))
#     ulid: str = attrs.field(default=attrs.Factory(lambda: str(ulid.ULID())))
#     status: int = StatusEnum.RUNNING
#     error: str = ''




@attrs.define
class TestResult:
    status: Literal[StatusEnum.SUCCESS, StatusEnum.FAILED]
    details: list = attrs.field(default=attrs.Factory(list))


@attrs.define
class TestEvent(Event):
    test_name: str
    result: Optional[TestResult] = None
    category: str = 'test'
    timestamp: str = attrs.field(default=attrs.Factory(lambda: datetime.utcnow().strftime(TIMESTAMP_FORMAT)))
    ulid: str = attrs.field(default=attrs.Factory(lambda: str(ulid.ULID())))
    status: int = StatusEnum.RUNNING
    error: str = ''


@attrs.define
class ErrorEvent(Event):
    error_name: str
    category: str = 'error'
    timestamp: str = attrs.field(default=attrs.Factory(lambda: datetime.utcnow().strftime(TIMESTAMP_FORMAT)))
    ulid: str = attrs.field(default=attrs.Factory(lambda: str(ulid.ULID())))
    status: int = StatusEnum.NONE
    error: str = ''
    error_msg: str = ''




# EventSystemData removed - was unused dead code



def transform_data_to_event(data: dict) -> Event:
    """Legacy function - only supports basic event types for backward compatibility."""
    supported_events = {
        'test': TestEvent,
        'error': ErrorEvent
    }
    if data['category'] in supported_events:
        event_class = supported_events[data['category']]
        return cattrs.structure(data, event_class)
    else:
        log.warning(f'Legacy event category {data["category"]} not supported - use new ActionEvent system')
        raise ValueError(f'Legacy event category {data["category"]} not supported')