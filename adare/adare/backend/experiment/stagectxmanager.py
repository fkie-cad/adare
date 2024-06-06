# external imports
import contextlib

# internal imports
from adarelib.types.stage import Stage as StageType
from adare.backend.experiment.database import update_stage_in_run

# configure logging
import logging
log = logging.getLogger(__name__)


class StageCtxManager(contextlib.AbstractContextManager):
    def __init__(self, stage: StageType, experimentrun_uuid: str):
        self.stage = stage
        self.experimentrun_uuid = experimentrun_uuid

    def __enter__(self):
        self.stage.start()
        update_stage_in_run(self.stage, self.experimentrun_uuid)
        return self

    def set_status(self, status: int):
        self.stage.status = status

    def __exit__(self, exc_type, exc_value, traceback):
        self.stage.end()
        update_stage_in_run(self.stage, self.experimentrun_uuid)
