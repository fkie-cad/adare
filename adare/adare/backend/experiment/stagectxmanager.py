# external imports
import contextlib
import threading
from ulid import ULID

# internal imports
from adare.backend.events.emitters import emit_stage
from adare.types.stages import Stage
from adarelib.constants import StatusEnum

# configure logging
import logging
log = logging.getLogger(__name__)

# Thread-local storage to track active parent stages
import contextvars
_active_parent_stage = contextvars.ContextVar('active_parent_stage', default=None)


class StageCtxManager(contextlib.AbstractContextManager):
    stage: Stage = None
    experimentrun_ulid: str = ''
    event: threading.Event = None
    stage_id: str = None

    def __init__(self, stage: Stage, experimentrun_ulid: str = '', event: threading.Event = None):
        self.stage = stage
        self.experimentrun_ulid = experimentrun_ulid
        self.event = event

    def __enter__(self):
        # Validate parent-child relationship for child stages
        if hasattr(self.stage, 'parent') and self.stage.parent:
            current_parent = _active_parent_stage.get()
            if current_parent is None:
                raise ValueError(f"Child stage '{self.stage.name}' requires parent '{self.stage.parent}' but no parent stage is active")
            if current_parent != self.stage.parent:
                raise ValueError(f"Child stage '{self.stage.name}' expects parent '{self.stage.parent}' but active parent is '{current_parent}'")

        # Set this stage as active parent if it's a parent stage (has no parent itself)
        is_parent_stage = not (hasattr(self.stage, 'parent') and self.stage.parent)
        if is_parent_stage:
            self._parent_token = _active_parent_stage.set(self.stage.name)

        self.stage.start()
        if not self.stage_id:
            self.stage_id = str(ULID())
        if self.experimentrun_ulid:
            emit_stage(self.experimentrun_ulid, stage=self.stage, stage_id=self.stage_id)
        return self

    def set_status(self, status: int):
        self.stage.status = status
        emit_stage(self.experimentrun_ulid, stage=self.stage, stage_id=self.stage_id)

    def __exit__(self, exc_type, exc_value, traceback):
        # Handle different exit conditions based on priority:
        # 1. If user interrupted (event set), mark as interrupted (takes priority over exceptions)
        # 2. If an exception occurred, mark as failed/error
        # 3. Otherwise, let the stage complete with its current status

        if self.event and self.event.is_set() and self.stage.status != StatusEnum.SUCCESS:
            # User interrupted and stage hasn't already completed successfully
            # This takes priority over exceptions since interrupts can cause CancelledError
            self.stage.status = StatusEnum.INTERRUPTED
        elif exc_type is not None:
            # An exception occurred during stage execution (only if not interrupted)
            from adare.exceptions import LoggedErrorException
            if issubclass(exc_type, LoggedErrorException):
                # This is an expected experiment error (guest OS issues, etc.)
                self.stage.status = StatusEnum.FAILED
                log.debug(f"Stage '{self.stage.name}' failed due to LoggedErrorException: {exc_value}")
            else:
                # This is an unexpected error (programming errors, etc.)
                self.stage.status = StatusEnum.ERROR
                log.debug(f"Stage '{self.stage.name}' errored due to unexpected exception: {exc_value}")

        self.stage.end()
        if self.experimentrun_ulid:
            # For parent stages, wait for the event processing queue to drain
            is_parent_stage = not (hasattr(self.stage, 'parent') and self.stage.parent)
            if is_parent_stage:
                self._wait_for_event_queue_drain()

            emit_stage(self.experimentrun_ulid, stage=self.stage, stage_id=self.stage_id)

    def _wait_for_event_queue_drain(self):
        """Wait for the event processing queue to drain before completing parent stage."""
        try:
            from adare.backend.events.coordinator import get_stage_coordinator
            coordinator = get_stage_coordinator()
            if coordinator:
                # Use the proper public method to wait for queue drain
                drained = coordinator.wait_for_queue_drain(timeout=0.1)
                if not drained:
                    log.debug(f"Event queue did not drain within timeout for parent stage: {self.stage.name}")
        except Exception as e:
            # If we can't check the queue, just continue
            log.debug(f"Could not wait for event queue drain: {e}")
            pass

        # Reset parent context if this was a parent stage
        if hasattr(self, '_parent_token'):
            _active_parent_stage.reset(self._parent_token)
