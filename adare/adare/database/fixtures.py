import sqlalchemy
from adarelib.types.experiment import Stage as StageType
from adare.database.models.experiment import Stage

# configure logging
import logging
log = logging.getLogger(__name__)


def fixture_stages(session: sqlalchemy.orm.Session):
    for stage in StageType.get_subclasses():
        if session.query(Stage).filter(Stage.name == stage.name).first():
            continue
        kwargs = {
            'name': stage.name,
            'description': stage.description,
            'optional': stage.optional
        }
        if stage.parent:
            if (
                parent := session.query(Stage)
                .filter(Stage.name == stage.parent.name)
                .first()
            ):
                kwargs['parent_id'] = parent.id
        stage_db = Stage(**kwargs)
        session.add(stage_db)
    log.info("updated fixtures for stages")
