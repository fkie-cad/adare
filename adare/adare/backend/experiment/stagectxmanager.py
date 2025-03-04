# external imports
import contextlib
import threading

# internal imports
from adarelib.types.stage import Stage as StageType
from adare.backend.experiment.database import update_stage_in_run
from adarelib.config import StatusEnum

# configure logging
import logging
log = logging.getLogger(__name__)


class StageCtxManager(contextlib.AbstractContextManager):
    stage_id: int = None

    def __init__(self, stage: StageType, experimentrun_ulid: str = '', event: threading.Event = None):
        self.stage = stage
        self.experimentrun_ulid = experimentrun_ulid
        self.event = event
        self.stage_id = -1

    def __enter__(self):
        self.stage.start()
        if self.experimentrun_ulid:
            self.stage_id = update_stage_in_run(self.stage, self.experimentrun_ulid, self.stage_id)
        return self

    def set_status(self, status: int):
        self.stage.status = status

    def __exit__(self, exc_type, exc_value, traceback):
        if self.event and self.event.is_set():
            self.stage.status = StatusEnum.INTERRUPTED
        self.stage.end()
        if self.experimentrun_ulid:
            self.stage_id = update_stage_in_run(self.stage, self.experimentrun_ulid, self.stage_id)
