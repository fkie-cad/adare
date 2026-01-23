from adare.backend.events.coordinator import get_stage_coordinator
from adare.types.stages import Stage
from adare.types.actions import ActionEvent

import logging
log = logging.getLogger(__name__)

def emit_stage(ulid: str, stage: Stage, stage_id: str) -> None:
    """Emit a stage event through the thread-safe coordinator."""
    coordinator = get_stage_coordinator()
    # Only emit if coordinator is actually started
    if coordinator._started:
        coordinator.emit_stage_event(ulid, stage, stage_id)
        log.debug(f"Emitted stage event for {ulid}: {stage.name} with ID {stage_id}")
    else:
        # Coordinator not started - expected for lightweight operations like dev stop
        log.debug(f"Coordinator not started, skipping event for stage: {stage.name}")


def emit_action(ulid: str, action_event: ActionEvent, action_id: str) -> None:
    """Emit an action event through the thread-safe coordinator."""
    coordinator = get_stage_coordinator()
    # Only emit if coordinator is actually started
    if coordinator._started:
        coordinator.emit_action_event(ulid, action_event, action_id)
        log.debug(f"Emitted action event for {ulid}: {action_event.action_type} with ID {action_id}")
    else:
        # Coordinator not started - expected for lightweight operations
        log.debug(f"Coordinator not started, skipping action event: {action_event.action_type}")
