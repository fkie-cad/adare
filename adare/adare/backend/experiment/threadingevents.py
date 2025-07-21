import time
import threading

from adare.types.stage import Stage
from adare.backend.experiment.database import update_stage_in_run

# configure logging
import logging
log = logging.getLogger(__name__)


class ExperimentEventManager:
    events: dict

    def __init__(self):
        self.events = {}

    def add_threading_event(self, experimentrun_ulid: str, event: threading.Event, event_name: str):
        if experimentrun_ulid not in self.events:
            self.events[experimentrun_ulid] = {}
        self.events[experimentrun_ulid][event_name] = event

    def get_threading_event(self, experimentrun_ulid: str, event_name: str):
        return self.events[experimentrun_ulid][event_name]


experiment_event_manager = ExperimentEventManager()
