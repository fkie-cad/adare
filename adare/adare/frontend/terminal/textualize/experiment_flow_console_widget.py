from __future__ import annotations
from typing import Any, Dict

from rich.text import Text
from rich.spinner import SPINNERS
from textual.app import App, ComposeResult, RenderResult
from textual.widget import Widget
from textual.containers import VerticalGroup
from textual.widgets import Static
from textual.reactive import reactive
from adarelib.constants import StatusEnum


class ExperimentRunFlowConsoleWidget(VerticalGroup):
    """
    A Textual widget that displays log messages with an animated spinner.
    """
    # Dictionary to store messages keyed by identifier.
    messages: Dict[str, dict] = {}
    # A reactive tick counter (used to cycle spinner frames)
    tick: reactive[int] = reactive(0)
    ticks_per_second: int = 12
    lines: list

    def __init__(self):
        super().__init__()
        self.tick = 0
        self.lines = []

    def on_mount(self) -> None:
        # Set an interval to update the tick, which triggers re-rendering.
        self.set_interval(1 / self.ticks_per_second, self._update_tick)

    def _update_tick(self) -> None:
        self.tick += 1
        self.refresh(recompose=True)

    def _generate_message(self, identifier: str, spinner_position: int = 0) -> str:
        msg_obj = self.messages[identifier]
        # Start with an icon based on status.
        icon = StatusEnum.get_icon(msg_obj.get("status"), color=True)
        message = f"{icon} {msg_obj.get('message', '')}"
        # If a spinner is defined, get the appropriate frame.
        spinner_key = msg_obj.get("spinner")
        if spinner_key:
            frames = SPINNERS[spinner_key]["frames"]
            spinner_position %= len(frames)
            if msg_obj.get("spinner_style"):
                style = msg_obj["spinner_style"]
                message = f"[{style}]{frames[spinner_position]}[/{style}] {message}"
            else:
                message = f"{frames[spinner_position]} {message}"
        # Add indentation based on level.
        level = msg_obj.get("level", 0)
        if level > 0:
            message = ("  " * level) + message
        # Append result-status icon if available.
        if msg_obj.get("result_status"):
            message = f"{message} {StatusEnum.get_icon(msg_obj['result_status'], color=True)}"
        return message

    def compose(self) -> ComposeResult:
        self.lines = [self._generate_message(identifier, self.tick) for identifier in self.messages]
        for line in self.lines:
            yield Static(Text.from_markup(line))

    @property
    def n_lines(self):
        return len(self.messages)

    # --- Logging methods ---

    def log_success(self, identifier: str, message: str, level: int = 0) -> None:
        self.messages[identifier] = {
            "message": message,
            "spinner": None,
            "spinner_style": None,
            "level": level,
            "status": StatusEnum.SUCCESS,
            "result_status": None,
        }
        self.refresh(layout=True, recompose=True)

    def log_warning(self, identifier: str, message: str, level: int = 0) -> None:
        self.messages[identifier] = {
            "message": message,
            "spinner": None,
            "spinner_style": None,
            "level": level,
            "status": StatusEnum.WARNING,
            "result_status": None,
        }
        self.refresh(layout=True, recompose=True)

    def log_error(self, identifier: str, message: str, level: int = 0) -> None:
        self.messages[identifier] = {
            "message": message,
            "spinner": None,
            "spinner_style": None,
            "level": level,
            "status": StatusEnum.ERROR,
            "result_status": None,
        }
        self.refresh(layout=True, recompose=True)

    def log_interrupted(self, identifier: str, message: str, level: int = 0) -> None:
        self.messages[identifier] = {
            "message": message,
            "spinner": None,
            "spinner_style": None,
            "level": level,
            "status": StatusEnum.INTERRUPTED,
            "result_status": None,
        }
        self.refresh(layout=True, recompose=True)

    def log_failed(self, identifier: str, message: str, level: int = 0) -> None:
        self.messages[identifier] = {
            "message": message,
            "spinner": None,
            "spinner_style": None,
            "level": level,
            "status": StatusEnum.FAILED,
            "result_status": None,
        }
        self.refresh(layout=True, recompose=True)

    def log_finished(self, identifier: str, message: str, level: int = 0) -> None:
        self.messages[identifier] = {
            "message": message,
            "spinner": None,
            "spinner_style": None,
            "level": level,
            "status": StatusEnum.FINISHED,
            "result_status": None,
        }
        self.refresh(layout=True, recompose=True)

    def change_log_message(self, identifier: str, message: str) -> None:
        if identifier in self.messages:
            self.messages[identifier]["message"] = message
            self.refresh(layout=True, recompose=True)

    def log_spinner(
            self,
            identifier: str,
            message: str,
            level: int = 0,
            spinner: str = "dots",
            spinner_style: str = "bold blue",
    ) -> None:
        self.messages[identifier] = {
            "message": message,
            "spinner": spinner,
            "spinner_style": spinner_style,
            "level": level,
            "status": StatusEnum.NONE,
            "result_status": None,
        }
        self.refresh(layout=True, recompose=True)

    def log_spinner_done(
            self,
            identifier: str,
            status: int,
            message: str = None,
            result_status: int = None,
            duration: float = None
    ) -> None:
        if identifier in self.messages:
            updated = self.messages[identifier]
            updated["spinner"] = None
            updated["spinner_style"] = None
            updated["status"] = status
            updated["result_status"] = result_status
            if message:
                updated["message"] = message
            if duration is not None:
                updated["duration"] = duration
            self.messages[identifier] = updated
            self.refresh(layout=True, recompose=True)

    def exists(self, identifier: str) -> bool:
        return identifier in self.messages


class FlowWidgetManager:
    def __init__(self):
        self.handlers = {}  # Dictionary to store experiment_id to handler mappings

    def add_handler(self, experimentrun_ulid: str, handler: ExperimentRunFlowConsoleWidget):
        self.handlers[experimentrun_ulid] = handler

    def get_handler(self, experimentrun_ulid: str) -> ExperimentRunFlowConsoleWidget:
        return self.handlers[experimentrun_ulid]

    def remove_handler(self, experimentrun_ulid: str):
        del self.handlers[experimentrun_ulid]


flowwidgetmanager = FlowWidgetManager()
