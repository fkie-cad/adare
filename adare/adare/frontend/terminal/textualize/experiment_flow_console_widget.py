from __future__ import annotations

from rich.spinner import SPINNERS
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.reactive import reactive
from textual.widgets import Static

from adare.backend.experiment.console_state import ConsoleState
from adarelib.constants import StatusEnum


class ExperimentRunFlowConsoleWidget(VerticalScroll):
    """
    A Textual widget that displays log messages with an animated spinner.
    Uses ConsoleState for thread-safe message storage.
    """
    state: ConsoleState

    # A reactive tick counter (used to cycle spinner frames)
    tick: reactive[int] = reactive(0)
    ticks_per_second: int = 12
    _widgets_map: dict[str, Static]

    def __init__(self):
        super().__init__()
        self.state = ConsoleState()
        self.tick = 0
        self._widgets_map = {}

    def on_mount(self) -> None:
        # Set an interval to update the tick, which triggers re-rendering.
        self.set_interval(1 / self.ticks_per_second, self._update_tick)
        # Initial update
        self._update_console_ui()

    def _update_tick(self) -> None:
        self.tick += 1
        self._update_console_ui()

    def _update_console_ui(self) -> None:
        """
        Efficiently update the console UI by modifying existing widgets
        or adding new ones, avoiding full recomposition.
        """
        snapshot = self.state.get_snapshot()
        should_scroll = False

        # We need to handle identifiers that might have been removed (unlikely in this append-only log, but good practice)
        # For now, we assume append-only or simple updates.

        for identifier, message_object in snapshot.items():
            text_content = self._generate_message(identifier, message_object, self.tick)
            rich_text = Text.from_markup(text_content)

            if identifier in self._widgets_map:
                # Update existing widget
                self._widgets_map[identifier].update(rich_text)
            else:
                # Create new widget
                new_widget = Static(rich_text)
                self.mount(new_widget)
                self._widgets_map[identifier] = new_widget
                should_scroll = True

        if should_scroll:
            # Schedule scroll_end after the refresh so layout is updated and virtual size is correct
            self.call_after_refresh(self.scroll_end, animate=False)

    def _generate_message(self, identifier: str, message_object: dict, spinner_position: int = 0) -> str:
        # NOTE: message_object comes from snapshot
        message = message_object['message']

        # Start with an icon based on status.
        icon = StatusEnum.get_icon(message_object.get("status"), color=True)
        message = f"{icon} {message}"

        # If a spinner is defined, get the appropriate frame.
        spinner_key = message_object.get("spinner")
        if spinner_key:
            frames = SPINNERS[spinner_key]["frames"]
            spinner_position %= len(frames)
            if message_object.get("spinner_style"):
                style = message_object["spinner_style"]
                message = f"[{style}]{frames[spinner_position]}[/{style}] {message}"
            else:
                message = f"{frames[spinner_position]} {message}"

        # Add indentation based on level.
        level = message_object.get("level", 0)
        if level > 0:
            message = ("  " * level) + message

        # Append result-status icon if available.
        if message_object.get("result_status"):
            message = f"{message} {StatusEnum.get_icon(message_object['result_status'], color=True)}"

        # We could also add duration here if we want parity with Rich console
        if message_object.get('duration'):
             message = f"{message} ({message_object['duration']:.2f}s)"

        return message

    def compose(self) -> ComposeResult:
        # We don't yield anything initially; _update_console_ui will handle mounting.
        yield from []

    @property
    def n_lines(self):
        # We can't easily get length without lock or snapshot, but since we are in UI thread (mostly)
        # accessing underlying dict length is technically racy but might be ok for just a count?
        # Safe way:
        with self.state._lock:
            return len(self.state.messages)

    # --- Logging methods ---
    # These delegate to ConsoleState which handles the locking.
    # We then trigger a refresh so the UI updates immediately for non-spinner events too.
    # Note: refresh() might need to be scheduled on main thread if called from background.
    # Textual's call_from_thread should be used if this is called from thread.
    # However, existing code called refresh() directly which implies it assumed main thread
    # or Textual handles it (Textual methods are generally not thread safe).
    # Since existing code had `self.refresh()` we'll keep it, but we should be careful.
    # Ideally: self.app.call_from_thread(self.refresh, recompose=True) if we possess 'app'.

    def _trigger_refresh(self):
        # Safely trigger UI update from any thread
        try:
            # self.app raises NoActiveAppError/LookupError if not mounted or no active app
            app = self.app
        except (Exception, LookupError):
            app = None

        if app:
            try:
                app.call_from_thread(self._update_console_ui)
            except RuntimeError:
                # If called from the same thread (e.g. in tests or main loop), call directly
                self._update_console_ui()
        else:
            # Fallback for tests or no-app context
            self._update_console_ui()

    def log_success(self, identifier: str, message: str, level: int = 0) -> None:
        self.state.log_success(identifier, message, level)
        self._trigger_refresh()

    def log_warning(self, identifier: str, message: str, level: int = 0) -> None:
        self.state.log_warning(identifier, message, level)
        self._trigger_refresh()

    def log_error(self, identifier: str, message: str, level: int = 0) -> None:
        self.state.log_error(identifier, message, level)
        self._trigger_refresh()

    def log_interrupted(self, identifier: str, message: str, level: int = 0) -> None:
        self.state.log_interrupted(identifier, message, level)
        self._trigger_refresh()

    def log_failed(self, identifier: str, message: str, level: int = 0) -> None:
        self.state.log_failed(identifier, message, level)
        self._trigger_refresh()

    def log_finished(self, identifier: str, message: str, level: int = 0) -> None:
        self.state.log_finished(identifier, message, level)
        self._trigger_refresh()

    def change_log_message(self, identifier: str, message: str) -> None:
        self.state.change_log_message(identifier, message)
        self._trigger_refresh()

    def log_spinner(
            self,
            identifier: str,
            message: str,
            level: int = 0,
            spinner: str = "dots",
            spinner_style: str = "bold blue",
    ) -> None:
        self.state.log_spinner(identifier, message, level, spinner, spinner_style)
        self._trigger_refresh()

    def log_spinner_done(
            self,
            identifier: str,
            status: int,
            message: str = None,
            result_status: int = None,
            duration: float = None
    ) -> None:
        self.state.log_spinner_done(identifier, status, message, result_status, duration)
        self._trigger_refresh()

    def exists(self, identifier: str) -> bool:
        return self.state.exists(identifier)

    # --- Methods for compatibility with ExperimentFlowConsole interface ---
    def start(self):
        """Start the console (no-op for widget as it's driven by Textual app)."""
        pass

    def stop(self):
        """Stop the console (no-op for widget)."""
        pass


class FlowWidgetManager:
    def __init__(self):
        self.handlers = {}  # Dictionary to store experiment_id to handler mappings

    def add_handler(self, experimentrun_ulid: str, handler: ExperimentRunFlowConsoleWidget):
        self.handlers[experimentrun_ulid] = handler
        # Also register with the backend flowconsolemanager so run.py can find it
        from adare.backend.experiment.print import flowconsolemanager
        flowconsolemanager.add_handler(experimentrun_ulid, handler)

    def get_handler(self, experimentrun_ulid: str) -> ExperimentRunFlowConsoleWidget:
        return self.handlers[experimentrun_ulid]

    def remove_handler(self, experimentrun_ulid: str):
        if experimentrun_ulid in self.handlers:
            del self.handlers[experimentrun_ulid]
            # Also remove from backend manager
            from adare.backend.experiment.print import flowconsolemanager
            flowconsolemanager.remove_handler(experimentrun_ulid)


flowwidgetmanager = FlowWidgetManager()
