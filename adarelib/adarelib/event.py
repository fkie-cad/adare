from datetime import datetime
from pathlib import Path
import attrs

from adarevm.config import TIMESTAMP_FORMAT
from adarelib.helperfunctions.yaml import dict_to_yaml
from adarelib.types import Event, EventSystemData

import logging
log = logging.getLogger(__name__)


class EventSystem:
    path: Path
    data: EventSystemData
    stage: str

    def __init__(self, path: Path, experiment_name: str):
        self.path = path
        self.data = EventSystemData(
            version='0.1',
            experiment=experiment_name,
            start_time=datetime.now().strftime(TIMESTAMP_FORMAT),
            end_time='',
            events=[]
        )
        self.stage = 'init'

    def log(self, event: Event) -> str:
        event.stage = self.stage
        self.data.events.append(event)
        self.save()
        return event.uuid

    def save(self):
        self.data.end_time = datetime.now().strftime(TIMESTAMP_FORMAT)
        data = attrs.asdict(self.data)
        dict_to_yaml(self.path, data)
