# external imports
import sqlalchemy
from sqlalchemy.orm import sessionmaker
from pathlib import Path

# internal imports
import adare.config.database as config_database
from adare.database.models.experiment import Stage, StageInRun, Base as ExperimentBase
from adare.database.api.database import DatabaseApi
from adarelib.types.stage import Stage as StageType

# configure logging
import logging
log = logging.getLogger(__name__)


class StageDbApi(DatabaseApi):
    def __init__(self, db_path: Path = config_database.get_database_location()):
        super().__init__(db_path)
        ExperimentBase.metadata.create_all(self.engine)

    def update_stage_in_run(self, stage: StageType, run_id: str, stage_id: int = -1) -> int:
        if not (stage_db := self._session.query(Stage).filter(Stage.name == stage.name).first()):
            raise sqlalchemy.orm.exc.NoResultFound(f"Stage '{stage.name}' not found in database")

        if stage_id != -1:
            stage_in_run = self._session.query(StageInRun).filter(StageInRun.stage_id == stage_db.id).filter(StageInRun.run_id == run_id).filter(StageInRun.id == stage_id).first()
            if stage.start_time:
                stage_in_run.start_time = stage.start_time
            if stage.end_time:
                stage_in_run.end_time = stage.end_time
            if stage.status:
                stage_in_run.status = stage.status
        else:
            stage_in_run = StageInRun(
                stage_id=stage_db.id,
                run_id=run_id,
                start_time=stage.start_time,
                end_time=stage.end_time,
                status=stage.status,
            )
            self._session.add(stage_in_run)

        self._session.commit()
        return stage_in_run.id

    def get_stages(self) -> list[Stage]:
        stages = self._session.query(Stage).all()
        self._expunge_multiple(stages)
        return stages

