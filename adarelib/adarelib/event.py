from datetime import datetime
from pathlib import Path
import attrs
import contextlib

from adarevm.config import TIMESTAMP_FORMAT
from adarelib.helperfunctions.yaml import dict_to_yaml
from adarelib.types.event import Event, EventSystemData
from adarelib.customyaml.customloader import YAML_STATUS_DUMPER

import logging
log = logging.getLogger(__name__)


class EventSystem:
    path: Path
    data: EventSystemData
    group_id: int

    def __init__(self, path: Path, experiment_name: str):
        self.path = path
        self.data = EventSystemData(
            version='0.1',
            experiment=experiment_name,
            start_time=datetime.now().strftime(TIMESTAMP_FORMAT),
            end_time='',
            events=[]
        )
        self.group_id = 0

    def log(self, event: Event, group_id: int = None) -> (str, int):
        if not group_id:
            self.group_id += 1
            event.group_id = self.group_id
        else:
            event.group_id = group_id
        self.data.events.append(event)
        self.save()
        return event.uuid, event.group_id

    def save(self):
        self.data.end_time = datetime.now().strftime(TIMESTAMP_FORMAT)
        data = attrs.asdict(self.data)
        dict_to_yaml(self.path, data, dumper=YAML_STATUS_DUMPER)


class EventCtxManager(contextlib.AbstractContextManager):
    event: Event
    event_system: EventSystem
    group_id: int

    def __init__(self, event: Event, event_system: EventSystem):
        self.event_system = event_system
        self.event = event
        self.group_id = -1

    def __enter__(self):
        _, self.group_id = self.event_system.log(self.event)
        return self

    def update(self, event: Event):
        self.event = event

    def __exit__(self, exc_type, exc_value, traceback):
        self.event_system.log(self.event, self.group_id)
        pass
