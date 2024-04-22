# external imports
import sqlalchemy
from pathlib import Path
from datetime import datetime
import json

# internal imports
from adare.database.api.experiment import ExperimentApi
from adarelib.event import EventSystemData

# configure logging
import logging
log = logging.getLogger(__name__)


class EventDbApi(ExperimentApi):

    def update_events(self, experiment_run_uuid: str, events: EventSystemData):
        pass