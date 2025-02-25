from typing import Callable, Awaitable
import contextlib
import uuid

from adarelib.types.event import Event
from adarelib.types.ws import EVENT

import logging
log = logging.getLogger(__name__)

class EventCtxManager(contextlib.AbstractContextManager):
    event: Event
    group_key: uuid.UUID or None
    log_func: Callable[[str], Awaitable[None]]

    def __init__(self, event: Event, log_func: Callable[[str], Awaitable[None]]):
        self.log_func = log_func
        self.event = event
        self.group_key = None

    def _log(self):
        self.event.group_key = str(self.group_key)
        event_ws_msg = EVENT(self.event)
        self.log_func(event_ws_msg.encode())

    def __enter__(self):
        self.group_key = uuid.uuid4()
        self._log()
        return self

    def update(self, event: Event):
        self.event = event
        self._log()

    def __exit__(self, exc_type, exc_value, traceback):
        pass