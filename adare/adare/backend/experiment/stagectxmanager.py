# external imports
import contextlib
import threading
from ulid import ULID

# internal imports
from adare.backend.events.emitters import emit_stage
from adare.types.stages import Stage
from adarelib.constants import StatusEnum

# configure logging
import logging
log = logging.getLogger(__name__)


class StageCtxManager(contextlib.AbstractContextManager):
    stage: Stage = None
    experimentrun_ulid: str = ''
    event: threading.Event = None
    stage_id: str = None

    def __init__(self, stage: Stage, experimentrun_ulid: str = '', event: threading.Event = None):
        self.stage = stage
        self.experimentrun_ulid = experimentrun_ulid
        self.event = event

    def __enter__(self):
        self.stage.start()
        if not self.stage_id:
            self.stage_id = str(ULID())
        if self.experimentrun_ulid:
            emit_stage(self.experimentrun_ulid, stage=self.stage, stage_id=self.stage_id)
        return self

    def set_status(self, status: int):
        self.stage.status = status
        emit_stage(self.experimentrun_ulid, stage=self.stage, stage_id=self.stage_id)

    def __exit__(self, exc_type, exc_value, traceback):
        if self.event and self.event.is_set():
            self.stage.status = StatusEnum.INTERRUPTED
        self.stage.end()
        if self.experimentrun_ulid:
            emit_stage(self.experimentrun_ulid, stage=self.stage, stage_id=self.stage_id)
