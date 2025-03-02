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
    def __init__(self, stage: StageType, experimentrun_ulid: str = '', event: threading.Event = None):
        self.stage = stage
        self.experimentrun_ulid = experimentrun_ulid
        self.event = event

    def __enter__(self):
        self.stage.start()
        if self.experimentrun_ulid:
            update_stage_in_run(self.stage, self.experimentrun_ulid)
        return self

    def set_status(self, status: int):
        self.stage.status = status

    def __exit__(self, exc_type, exc_value, traceback):
        if self.event and self.event.is_set():
            self.stage.status = StatusEnum.INTERRUPTED
        self.stage.end()
        if self.experimentrun_ulid:
            update_stage_in_run(self.stage, self.experimentrun_ulid)
