# external imports
import sqlalchemy
from pathlib import Path

# internal imports
import adare.config.database as config_database
from adare.database.models.experiment import Stage as StageModel, StageInRun as StageInRunModel, Base as ExperimentBase
from adare.database.api.database import DatabaseApi
from adare.types.stages import Stage

# configure logging
import logging
log = logging.getLogger(__name__)


class StageDbApi(DatabaseApi):
    def __init__(self, db_path: Path = config_database.get_database_location()):
        super().__init__(db_path)
        ExperimentBase.metadata.create_all(self.engine)

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
                stage_in_run.status = stage.status
        else:
            stage_in_run = StageInRunModel(
                id=stage_id,
                stage_id=stage_db.id,
                run_id=run_id,
                start_time=stage.start_time,
                end_time=stage.end_time,
                status=stage.status,
            )
            self._session.add(stage_in_run)

        self._session.commit()
        return stage_in_run.id

    def get_stages(self) -> list[StageModel]:
        stages = self._session.query(StageModel).all()
        self._expunge_multiple(stages)
        return stages

