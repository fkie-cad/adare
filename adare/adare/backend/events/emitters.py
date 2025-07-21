from adare.backend.events.pubsub import publish
from adare.types.stages import Stage

import logging
log = logging.getLogger(__name__)

def emit_stage(ulid: str, stage: Stage, stage_id: str) -> None:
    publish(ulid, {
        "data": stage.to_dict(),
        "stage_id": stage_id,
    })
    log.debug(f"Emitted stage event for {ulid}: {stage.name} with ID {stage_id}")
