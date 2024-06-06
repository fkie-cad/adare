from adare.database.models.experiment import StageInRun, Stage
from adare.backend.experiment.print import flowconsolemanager, ExperimentFlowConsole

from sqlalchemy import event
from sqlalchemy.orm import Session

# configure logging
import logging
log = logging.getLogger(__name__)


def print_to_console(session: Session, console: ExperimentFlowConsole, target: StageInRun):

    # determine level
    level = 0

    stage = session.query(Stage).filter(Stage.id == target.stage_id).first()
    if not target.start_time:
        log.info(f'no start time for stage {stage.name}')
        return
    parent = stage.parent
    while parent:
        level += 1
        parent = parent.parent
        if level > 10:
            log.error('Parent level exceeds 10')
            return

    identifier = str(target.id)
    if target.sub_msg:
        message = f'{stage.msg} - {target.sub_msg}'
    else:
        message = stage.msg
    if target.finished:
        if console.exists(identifier):
            console.log_spinner_done(identifier=identifier, status=target.status, message=message)
            return
        if target.status == 'success':
            console.log_success(identifier=identifier, message=message, level=level)
        elif target.status == 'warning':
            console.log_warning(identifier=identifier, message=message, level=level)
        elif target.status == 'error':
            console.log_error(identifier=identifier, message=message, level=level)
        elif target.status == 'interrupted':
            console.log_interrupted(identifier=identifier, message=message, level=level)
    if target.in_progress:
        console.log_spinner(identifier=identifier, message=message, level=level)


@event.listens_for(StageInRun, 'after_insert')
def receive_after_insert(mapper, connection, target):
    session = Session(bind=connection)
    console = flowconsolemanager.get_handler(target.run_id)
    print_to_console(session, console, target)


@event.listens_for(StageInRun, 'after_update')
def receive_after_update(mapper, connection, target):
    session = Session(bind=connection)
    console = flowconsolemanager.get_handler(target.run_id)
    print_to_console(session, console, target)


