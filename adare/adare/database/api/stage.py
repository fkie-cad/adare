# external imports
# configure logging
import logging
from pathlib import Path

import sqlalchemy

from adare.database.api.base import ProjectDatabaseApi

# internal imports
from adare.database.models.project_models import Stage as StageModel
from adare.database.models.project_models import StageInRun as StageInRunModel
from adare.types.stages import Stage

log = logging.getLogger(__name__)


class StageDbApi(ProjectDatabaseApi):
    def __init__(self, project_path: Path):
        super().__init__(project_path)

    def update_stage_in_run(self, stage: Stage, run_id: str, stage_id: str) -> int:
        if not (stage_db := self._session.query(StageModel).filter(StageModel.name == stage.name).first()):
            raise sqlalchemy.orm.exc.NoResultFound(f"Stage '{stage.name}' not found in database")

        stage_in_run = self._session.query(StageInRunModel).filter(StageInRunModel.stage_id == stage_db.id).filter(StageInRunModel.run_id == run_id).filter(StageInRunModel.id == stage_id).first()

        if stage_in_run:
            if stage.start_time:
                stage_in_run.start_time = stage.start_time
            if stage.end_time:
                stage_in_run.end_time = stage.end_time
            if stage.status:
                # Get or create Status object for the status enum value
                from adare.database.models.project_models import Status
                from adarelib.constants import StatusEnum
                # Convert integer to StatusEnum object to get the name
                status_enum = StatusEnum(stage.status)
                status_obj = self._session.query(Status).filter_by(name=status_enum.name).first()
                if not status_obj:
                    status_obj = Status(name=status_enum.name)
                    self._session.add(status_obj)
                    self._session.flush()  # Get the ID
                stage_in_run.status_id = status_obj.id
        else:
            # Get or create Status object for the status enum value
            status_obj = None
            if stage.status:
                from adare.database.models.project_models import Status
                from adarelib.constants import StatusEnum
                # Convert integer to StatusEnum object to get the name
                status_enum = StatusEnum(stage.status)
                status_obj = self._session.query(Status).filter_by(name=status_enum.name).first()
                if not status_obj:
                    status_obj = Status(name=status_enum.name)
                    self._session.add(status_obj)
                    self._session.flush()  # Get the ID

            stage_in_run = StageInRunModel(
                id=stage_id,
                stage_id=stage_db.id,
                run_id=run_id,
                start_time=stage.start_time,
                end_time=stage.end_time,
                status_id=status_obj.id if status_obj else None,
            )
            self._session.add(stage_in_run)

        self._session.commit()
        return stage_in_run.id

    def get_stages(self) -> list[StageModel]:
        stages = self._session.query(StageModel).all()
        self._expunge_multiple(stages)
        return stages

