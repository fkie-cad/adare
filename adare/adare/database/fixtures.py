import sqlalchemy
from adarelib.types.stage import Stage as StageType
from adare.database.models.experiment import Stage, Status
from adarelib.config import StatusEnum

# configure logging
import logging
log = logging.getLogger(__name__)


def fixture_stages(session: sqlalchemy.orm.Session):
    updated = False
    for stage in StageType.get_subclasses():
        if session.query(Stage).filter(Stage.name == stage.name).first():
            continue
        kwargs = {
            'name': stage.name,
            'msg': stage.msg,
            'description': stage.description,
            'optional': stage.optional,
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
        session.commit()
        updated = True
    if updated:
        log.info("updated fixtures for stages")


def fixture_status(session: sqlalchemy.orm.Session):
    updated = False
    for status in StatusEnum:
        if session.query(Status).filter(Status.name == status.name).first():
            continue
        status_db = Status(name=status.name, id=status.value)
        session.add(status_db)
        session.commit()
        updated = True
    if updated:
        log.info("updated fixtures for status")