# external imports
import contextlib

# internal imports
from adarelib.types.stage import Stage as StageType
from adare.backend.experiment.database import update_stage_in_run

# configure logging
import logging
log = logging.getLogger(__name__)


class StageCtxManager(contextlib.AbstractContextManager):
    def __init__(self, stage: StageType, experimentrun_ulid: str = ''):
        self.stage = stage
        self.experimentrun_ulid = experimentrun_ulid

    def __enter__(self):
        self.stage.start()
        if self.experimentrun_ulid:
            update_stage_in_run(self.stage, self.experimentrun_ulid)
        return self

    def set_status(self, status: int):
        self.stage.status = status

    def __exit__(self, exc_type, exc_value, traceback):
        self.stage.end()
        if self.experimentrun_ulid:
            update_stage_in_run(self.stage, self.experimentrun_ulid)
