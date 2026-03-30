# external imports
from typing import Literal, Optional
import attrs
import cattrs
from datetime import datetime, timezone
import ulid
import traceback

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


@attrs.define
class TestResult:
    status: Literal[StatusEnum.SUCCESS, StatusEnum.FAILED, StatusEnum.ERROR]
    details: list = attrs.field(default=attrs.Factory(list))
    
    @classmethod
    def success(cls, details: list = None):
        """Create a successful test result."""
        return cls(status=StatusEnum.SUCCESS, details=details or [])
    
    @classmethod
    def failed(cls, details: list = None):
        """Create a failed test result (test ran but condition not met)."""
        return cls(status=StatusEnum.FAILED, details=details or [])
    
    @classmethod
    def error(cls, details: list = None):
        """Create an error test result (test could not execute)."""
        return cls(status=StatusEnum.ERROR, details=details or [])
    
    @classmethod
    def execution_error(cls, exception: Exception, context: str = None):
        """Create an error result from an exception."""
        if exception is None:
            # Handle cases where exception is None (some tests pass None)
            error_msg = context if context else "Unknown error"
            return cls(status=StatusEnum.ERROR, details=[error_msg])

        # Create basic error message
        error_msg = f"{type(exception).__name__}: {str(exception)}"
        if context:
            error_msg = f"{context} - {error_msg}"

        # Add full stack trace
        stack_trace = ''.join(traceback.format_exception(type(exception), exception, exception.__traceback__))

        return cls(status=StatusEnum.ERROR, details=[error_msg, f"Stack trace:\n{stack_trace}"])


@attrs.define
class TestEvent(Event):
    test_name: str
    result: Optional[TestResult] = None
    category: str = 'test'
    timestamp: str = attrs.field(default=attrs.Factory(lambda: datetime.now(timezone.utc).strftime(TIMESTAMP_FORMAT)))
    ulid: str = attrs.field(default=attrs.Factory(lambda: str(ulid.ULID())))
    status: int = StatusEnum.RUNNING
    error: str = ''


@attrs.define
class ErrorEvent(Event):
    error_name: str
    category: str = 'error'
    timestamp: str = attrs.field(default=attrs.Factory(lambda: datetime.now(timezone.utc).strftime(TIMESTAMP_FORMAT)))
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