import threading
from typing import Dict, Optional, Any
from datetime import datetime, timezone
from adarelib.constants import StatusEnum
import logging

log = logging.getLogger(__name__)

class ConsoleState:
    """
    Shared state for experiment console logging.
    Handles message storage, thread safety, and status updates.
    Decouples logic from the specific view (Rich Console or Textual Widget).
    """

    def __init__(self):
        self._lock = threading.Lock()
        self.messages: Dict[str, Dict[str, Any]] = {}
        self.experiment_start_time: Optional[datetime] = None

    def _get_default_message_structure(
        self,
        message: str,
        level: int = 0,
        status: int = StatusEnum.NONE,
        spinner: Optional[str] = None,
        spinner_style: Optional[str] = None,
        duration: Optional[float] = None,
        start_time: Optional[datetime] = None,
        result_status: Optional[int] = None,
        is_experiment_timer: bool = False
    ) -> Dict[str, Any]:
        return {
            "message": message,
            "level": level,
            "status": status,
            "spinner": spinner,
            "spinner_style": spinner_style,
            "duration": duration,
            "start_time": start_time,
            "result_status": result_status,
            "is_experiment_timer": is_experiment_timer
        }

    def log_message(self, identifier: str, message: str, level: int = 0, status: int = StatusEnum.NONE, duration: Optional[float] = None) -> None:
        """Generic log method."""
        with self._lock:
            self.messages[identifier] = self._get_default_message_structure(
                message=message, level=level, status=status, duration=duration
            )

    def log_success(self, identifier: str, message: str, level: int = 0, duration: float = None) -> None:
        self.log_message(identifier, message, level, StatusEnum.SUCCESS, duration)

    def log_warning(self, identifier: str, message: str, level: int = 0, duration: float = None) -> None:
        self.log_message(identifier, message, level, StatusEnum.WARNING, duration)

    def log_error(self, identifier: str, message: str, level: int = 0, duration: float = None) -> None:
        self.log_message(identifier, message, level, StatusEnum.ERROR, duration)

    def log_interrupted(self, identifier: str, message: str, level: int = 0, duration: float = None) -> None:
        self.log_message(identifier, message, level, StatusEnum.INTERRUPTED, duration)

    def log_failed(self, identifier: str, message: str, level: int = 0, duration: float = None) -> None:
        self.log_message(identifier, message, level, StatusEnum.FAILED, duration)

    def log_finished(self, identifier: str, message: str, level: int = 0, duration: float = None) -> None:
        self.log_message(identifier, message, level, StatusEnum.FINISHED, duration)

    def log_interactive_pause(self, identifier: str, message: str, level: int = 0, duration: float = None) -> None:
        self.log_message(identifier, message, level, StatusEnum.PAUSE, duration)

    def log_ulid(self, ulid: str, level: int = 0):
        with self._lock:
            self.messages['ULID'] = self._get_default_message_structure(
                message=f'ULID: {ulid}', level=level, status=StatusEnum.NONE
            )

    def log_spinner(self, identifier: str, message: str, level: int = 0, spinner: str = 'dots', spinner_style: str = 'bold blue', start_time: datetime = None) -> None:
        with self._lock:
            self.messages[identifier] = self._get_default_message_structure(
                message=message,
                level=level,
                status=StatusEnum.NONE,
                spinner=spinner,
                spinner_style=spinner_style,
                start_time=start_time
            )

    def log_spinner_done(self, identifier: str, status: int, message: str = None, result_status: int = None, duration: float = None) -> None:
        with self._lock:
            if identifier not in self.messages:
                log.warning(f"Attempted to update non-existent spinner message: {identifier}")
                return
            
            updated_msg = self.messages[identifier]
            updated_msg['spinner'] = None
            updated_msg['spinner_style'] = None
            updated_msg['status'] = status
            if result_status is not None:
                updated_msg['result_status'] = result_status
            if message:
                updated_msg['message'] = message
            if duration is not None:
                updated_msg['duration'] = duration
            
            self.messages[identifier] = updated_msg

    def change_log_message(self, identifier: str, message: str) -> None:
        with self._lock:
            if identifier in self.messages:
                self.messages[identifier]['message'] = message

    def exists(self, identifier: str) -> bool:
        with self._lock:
            return identifier in self.messages

    def start_experiment_timer(self):
        with self._lock:
            self.experiment_start_time = datetime.now(timezone.utc)
            self.messages['EXPERIMENT_TIMER'] = self._get_default_message_structure(
                message="",
                level=0,
                status=StatusEnum.NONE,
                start_time=self.experiment_start_time,
                is_experiment_timer=True
            )

    def finish_experiment_timer(self, success: bool = True):
        with self._lock:
            if 'EXPERIMENT_TIMER' in self.messages:
                timer_msg = self.messages['EXPERIMENT_TIMER']
                if timer_msg.get('start_time'):
                    end_time = datetime.now(timezone.utc)
                    timer_msg['duration'] = (end_time - timer_msg['start_time']).total_seconds()
                timer_msg['status'] = StatusEnum.SUCCESS if success else StatusEnum.FAILED
                timer_msg['start_time'] = None

    def log_multi_experiment_summary(self, content: str):
         with self._lock:
            self.messages['MULTI_EXPERIMENT_SUMMARY'] = self._get_default_message_structure(
                message=content,
                level=0,
                status=StatusEnum.NONE
            )

    def get_snapshot(self) -> Dict[str, Dict[str, Any]]:
        """
        Returns a thread-safe snapshot of the current messages.
        Use this for rendering to avoid holding the lock during render.
        """
        with self._lock:
            # Deep copy might be too expensive if messages are large, 
            # but usually they are just strings and small dicts.
            # Shallow copy of the dict of dicts should be safe enough if we don't mutate inner dicts in place elsewhere without lock.
            # Since we replace inner dicts or mutate them under lock, a shallow copy of the outer dict
            # protects against iteration size changes. 
            # However, if render thread reads an inner dict while writer thread mutates it, that's a race.
            # So we should probably return a deep copy or copy the inner dicts too.
            return {k: v.copy() for k, v in self.messages.items()}

    def clear(self):
        with self._lock:
            self.messages.clear()
