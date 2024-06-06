import time
import threading

from adarelib.types.stage import Stage
from adare.backend.experiment.database import update_stage_in_run

# configure logging
import logging
log = logging.getLogger(__name__)


class ExperimentEventManager:
    events: dict

    def __init__(self):
        self.events = {}

    def add_threading_event(self, experimentrun_uuid: str, event: threading.Event, event_name: str):
        if experimentrun_uuid not in self.events:
            self.events[experimentrun_uuid] = {}
        self.events[experimentrun_uuid][event_name] = event

    def get_threading_event(self, experimentrun_uuid: str, event_name: str):
        return self.events[experimentrun_uuid][event_name]


experiment_event_manager = ExperimentEventManager()
