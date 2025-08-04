from adare.backend.events.pubsub import subscribe_cli, subscribe_db
from adare.backend.experiment.print import flowconsolemanager
from adarelib.constants import StatusEnum
from adare.types.stages import Stage, _stage_registry

import logging
log = logging.getLogger(__name__)

def event_listener_cli(ulid):
    console = flowconsolemanager.get_handler(ulid)
    if not console:
        log.error(f"[EventListener CLI] No console found for ULID: {ulid}")
        return
    for event in subscribe_cli(ulid):
        try:
            log.info(f"[EventListener CLI] Processing event for {ulid}: {event}")
            stage = event.get("data", {})
            stage_id = event.get("stage_id")
            if not stage:
                log.warning(f"[EventListener CLI] No stage data found in event: {event}")
                continue
            stage = Stage.from_dict(stage)
            
            # Debug logging for duplicate stage investigation
            log.info(f"[EventListener CLI] Stage: {stage.name}, ID: {stage_id}, Start: {stage.start_time}, End: {stage.end_time}, Status: {stage.status}")

            # Check stage status first
            finished = stage.start_time and stage.end_time
            in_progress = stage.start_time and not stage.end_time
            
            # Calculate display level based on parent hierarchy
            level = 0
            parent = stage.parent
            while parent:
                parent_stage_class = _stage_registry.get(parent)
                if not parent_stage_class:
                    log.warning(f"[EventListener CLI] Parent stage {parent} not found in registry")
                    break
                level += 1
                parent = parent_stage_class().parent
                if level > 10:
                    log.warning(f"[EventListener CLI] Level too high, breaking loop due to expected endless loop: {level}")
                    break
            
            if stage.sub_msg:
                message = f"{stage.name}: {stage.sub_msg}"
            else:
                message = stage.msg

            if finished:
                if console.exists(stage_id):
                    # Add interrupt indication for spinner updates
                    if stage.status == StatusEnum.INTERRUPTED:
                        message = f"{message} (interrupted by user)"
                    if stage.result_status:
                        console.log_spinner_done(identifier=stage_id, status=stage.status, message=message, result_status=stage.result_status)
                    else:
                        console.log_spinner_done(identifier=stage_id,  status=stage.status, message=message)
                    log.info(f"[EventListener CLI] Processed stage event for {ulid}: {stage.name if stage else 'None'}")
                    continue
                else:
                    if stage.status == StatusEnum.SUCCESS:
                        console.log_success(identifier=stage_id, message=message, level=level)
                    elif stage.status == StatusEnum.WARNING:
                        console.log_warning(identifier=stage_id, message=message, level=level)
                    elif stage.status == StatusEnum.ERROR:
                        console.log_error(identifier=stage_id, message=message, level=level)
                    elif stage.status == StatusEnum.INTERRUPTED:
                        interrupted_message = f"{message} (interrupted by user)"
                        console.log_interrupted(identifier=stage_id, message=interrupted_message, level=level)
                    elif stage.status == StatusEnum.FAILED:
                        console.log_failed(identifier=stage_id, message=message, level=level)
                    elif stage.status == StatusEnum.FINISHED:
                        console.log_finished(identifier=stage_id, message=message, level=level)
            elif in_progress:
                # Only add the stage if it doesn't already exist
                if not console.exists(stage_id):
                    log.info(f"[EventListener CLI] Creating new console spinner for stage: {stage.name}, ID: {stage_id}, Level: {level}")
                    console.log_spinner(identifier=stage_id, message=message, level=level)
                else:
                    log.info(f"[EventListener CLI] Stage already exists in console: {stage.name}, ID: {stage_id}")

        except Exception as e:
            # Log or handle malformed events
            log.error(f"[EventListener CLI] Error processing event: {e}")

        log.info(f"[EventListener CLI] Processed stage event for {ulid}: {stage.name if stage else 'None'}")


def event_listener_db(ulid):
    for event in subscribe_db(ulid):
        from adare.backend.experiment.database import update_stage_in_run
        stage = event.get("data", {})
        stage_id = event.get("stage_id")
        stage = Stage.from_dict(stage) if stage else None
        if not stage:
            log.error(f"[EventListener DB] No stage data found in event: {event}")
            return
        update_stage_in_run(stage=stage, experimentrun_ulid=ulid, stage_id=stage_id)
        log.debug(f"[EventListener DB] Processed stage event for {ulid}: {stage.name if stage else 'None'}")