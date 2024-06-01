import sqlalchemy
from adarelib.types.experiment import Stage

# configure logging
import logging
log = logging.getLogger(__name__)


def fixture_stages(session: sqlalchemy.orm.Session):
    for stage in Stage.__subclasses__():
        if session.query(Stage).filter(Stage.name == stage.name).first():
            return None
        kwargs = {
            'name': stage.name,
            'description': stage.description,
            'optional': stage.optional
        }
        parent = session.query(Stage).filter(Stage.name == stage.parent.name).first()
        if parent:
            kwargs['parent_id'] = parent.id
        stage_db = Stage(**kwargs)
        session.add(stage_db)
    log.info("updated fixtures for stages")





