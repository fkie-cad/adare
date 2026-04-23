# configure logging
import logging
import threading
import time
from datetime import UTC, datetime

from rich.console import Console
from rich.live import Live
from rich.spinner import SPINNERS
from rich.text import Text

from adare.backend.experiment.console_state import ConsoleState
from adarelib.constants import StatusEnum

log = logging.getLogger(__name__)


class ExperimentFlowConsole:
    console: Console
    stop_event: threading.Event
    thread: threading.Thread | None
    disable: bool
    external_stop_event: threading.Event | None

    state: ConsoleState
    ticks_per_second: int = 15  # 15 FPS for smoother animations
    _original_log_level: int | None  # Store original console log level

    indent_offset: int
    layout: Text

    def __init__(self, disable: bool = False, external_stop_event: threading.Event = None, indent_offset: int = 0):
        self.console = Console()
        self.stop_event = threading.Event()
        self.external_stop_event = external_stop_event
        self.state = ConsoleState()
        self.thread = None
        self.disable = disable
        self._original_log_level = None
        self.indent_offset = indent_offset

        # No need to re-initialize console with fixed height
        # Console will use full terminal and scroll naturally

        self.layout = Text('Loading...')

    def _start_live_in_thread(self):
        tick_count = 0
        with Live(self.layout, console=self.console, refresh_per_second=self.ticks_per_second,
                  auto_refresh=False, transient=False) as live:
            while not self.stop_event.is_set():
                try:
                    # Use snapshot to avoid holding lock during render
                    messages_snapshot = self.state.get_snapshot()
                    message_identifiers = list(messages_snapshot.keys())

                    # Ensure experiment timer appears first if it exists
                    if 'EXPERIMENT_TIMER' in message_identifiers:
                        message_identifiers.remove('EXPERIMENT_TIMER')
                        message_identifiers.insert(0, 'EXPERIMENT_TIMER')

                    # Generate ALL messages (preserve full history)
                    generated_messages = [
                        self._generate_message(identifier, messages_snapshot[identifier], tick_count)
                        for identifier in message_identifiers
                    ]
                    non_empty_messages = [msg for msg in generated_messages if msg.strip()]

                    # Apply sliding window: show only recent messages that fit terminal height
                    terminal_height = self.console.size.height
                    max_lines = terminal_height - 2  # Reserve 2 lines for Live display overhead

                    if len(non_empty_messages) > max_lines:
                        # Show most recent messages (tail behavior)
                        visible_messages = non_empty_messages[-max_lines:]
                    else:
                        # Show all messages if they fit
                        visible_messages = non_empty_messages

                    messages_as_str = '\n'.join(visible_messages)
                    live.update(messages_as_str)
                    live.refresh()  # Force manual refresh since auto_refresh=False
                    tick_count += 1

                except Exception as e:
                    # Don't let message generation errors break the refresh cycle
                    log.error(f"Error in flow console refresh cycle: {e}")
                    try:
                        live.update("Flow console error - please check logs")
                        live.refresh()
                    except (RuntimeError, ValueError):
                        pass

                time.sleep(0.067)  # ~67ms sleep for 15 FPS
        log.debug('rich live thread stopped')

    def start(self):
        if not self.disable:
            self._suppress_console_logging()
            self.thread = threading.Thread(target=self._start_live_in_thread)
            self.thread.start()

    def stop(self):
        if not self.disable:
            self.stop_event.set()
            if self.thread and self.thread.is_alive():
                self.thread.join()
            self._restore_console_logging()

    def print_final_output(self):
        """
        Print all accumulated messages to console after experiment completes.
        This ensures the full log is visible for review after stopping the live display.
        """
        if not self.disable:
            # Get final snapshot of all messages
            messages_snapshot = self.state.get_snapshot()
            message_identifiers = list(messages_snapshot.keys())

            # Ensure experiment timer appears first if it exists
            if 'EXPERIMENT_TIMER' in message_identifiers:
                message_identifiers.remove('EXPERIMENT_TIMER')
                message_identifiers.insert(0, 'EXPERIMENT_TIMER')

            # Generate and print all messages
            generated_messages = [
                self._generate_message(identifier, messages_snapshot[identifier], spinner_position=0)
                for identifier in message_identifiers
            ]
            non_empty_messages = [msg for msg in generated_messages if msg.strip()]

            if non_empty_messages:
                # Print to regular console (not Live), so it persists in terminal
                self.console.print('\n'.join(non_empty_messages))

    def _suppress_console_logging(self):
        """Suppress console logging when flow console is active."""
        from adare.setup_logging import set_console_log_level

        root_logger = logging.getLogger()
        for handler in root_logger.handlers:
            if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
                self._original_log_level = handler.level
                break

        set_console_log_level(logging.CRITICAL)

    def _restore_console_logging(self):
        """Restore original console logging level."""
        if self._original_log_level is not None:
            from adare.setup_logging import set_console_log_level
            set_console_log_level(self._original_log_level)

    def _generate_message(self, identifier: str, message_object: dict, spinner_position: int = 0):
        # NOTE: message_object comes from snapshot, so no lock needed here
        message = message_object['message']

        # Special handling for experiment timer
        if message_object.get('is_experiment_timer'):
            if not message and not message_object.get('duration') and not message_object.get('start_time'):
                return ""
        else:
            icon = StatusEnum.get_icon(message_object['status'], color=True)
            message = f'{icon} {message}'

        if message_object['spinner']:
            spinner = SPINNERS[message_object['spinner']]['frames']
            spinner_position %= len(spinner)
            if message_object['spinner_style']:
                style = message_object['spinner_style']
                message = f'[{style}]{spinner[spinner_position]}[/{style}] {message}'
            else:
                message = f'{spinner[spinner_position]} {message}'

        if message_object['level'] > 0:
            effective_level = max(0, message_object['level'] - self.indent_offset)
            message = ' ' * 2 * effective_level + message

        if message_object['result_status']:
            message = f'{message} {StatusEnum.get_icon(message_object["result_status"], color=True)}'

        # Duration display
        duration_text = None
        if message_object.get('duration'):
            if message_object.get('is_experiment_timer'):
                duration_text = self._format_experiment_timer_duration(
                    message_object['duration'], message_object['status']
                )
            else:
                duration_text = f"({message_object['duration']:.2f}s)"
        elif message_object.get('start_time'):
            elapsed_seconds = (datetime.now(UTC) - message_object['start_time']).total_seconds()
            if message_object.get('is_experiment_timer'):
                duration_text = self._format_experiment_timer_duration(
                    elapsed_seconds, message_object['status']
                )
            else:
                duration_text = f"({elapsed_seconds:.2f}s)"

        if duration_text:
            message = self._fit_line_to_terminal(message, duration_text)

        return message

    def _fit_line_to_terminal(self, message: str, duration_text: str) -> str:
        terminal_width = self.console.size.width
        from rich.text import Text

        complete_line = f"{message} {duration_text}"
        complete_obj = Text.from_markup(complete_line)
        complete_width = self.console.measure(complete_obj).maximum

        if complete_width > terminal_width:
            duration_obj = Text.from_markup(duration_text)
            duration_width = self.console.measure(duration_obj).maximum
            available_for_message = terminal_width - duration_width - 4

            if available_for_message > 10:
                message_obj = Text.from_markup(message)
                if len(message_obj) > available_for_message:
                    is_multiline = '\n' in message
                    if is_multiline:
                        first_line = message.split('\n')[0].strip()
                        import re
                        clean_first_line = re.sub(r'\[/?[^\]]*\]', '', first_line)
                        if len(clean_first_line) > available_for_message:
                            clean_first_line = clean_first_line[:available_for_message-3].strip()
                        message = f"{clean_first_line}..."
                    else:
                        import re
                        clean_message = re.sub(r'\[/?[^\]]*\]', '', message)
                        if len(clean_message) > available_for_message:
                            clean_message = clean_message[:available_for_message-3].strip()
                        message = f"{clean_message}..."

                current_width = self.console.measure(Text.from_markup(message)).maximum
                padding = terminal_width - current_width - duration_width
                if padding > 1:
                    message = f"{message}{' ' * (padding - 1)} {duration_text}"
                else:
                    message = f"{message} {duration_text}"
            else:
                message = f"{message[:terminal_width-10]}... {duration_text}"
        else:
            duration_obj = Text.from_markup(duration_text)
            duration_width = self.console.measure(duration_obj).maximum
            message_obj = Text.from_markup(message)
            message_width = self.console.measure(message_obj).maximum

            padding = terminal_width - message_width - duration_width
            message = f"{message}{' ' * (padding - 1)} {duration_text}" if padding > 1 else f"{message} {duration_text}"

        return message

    def log_success(self, identifier: str, message: str, level: int = 0, duration: float = None):
        self.state.log_success(identifier, message, level, duration)

    def log_ulid(self, ulid: str, level: int = 0):
        self.state.log_ulid(ulid, level)

    def log_multi_experiment_summary(self, experiment_name: str, environments: list, results: list, total_duration: float):
        # We perform the formatting here specifically for Rich console, then store the result string in state.
        # This keeps ConsoleState mostly UI-agnostic (it stores a string).

        # Categorize results
        successful_runs = [r for r in results if r['status'] == 'SUCCESS']
        failed_runs = [r for r in results if r['status'] == 'FAILED']
        interrupted_runs = [r for r in results if r['status'] == 'INTERRUPTED']
        skipped_runs = [r for r in results if r['status'] == 'SKIPPED']

        has_failures = len(failed_runs) > 0
        has_issues = len(interrupted_runs) > 0 or len(skipped_runs) > 0

        if has_failures:
            status_color = "red"
            status_icon = "❌"
        elif has_issues:
            status_color = "yellow"
            status_icon = "⚠️"
        else:
            status_color = "green"
            status_icon = "✅"

        summary_parts = []
        line_width = max(60, self.console.size.width - 10)
        separator = "[dim]" + "─" * line_width + "[/dim]"

        summary_parts.extend([
            "",
            separator,
            f"[bold {status_color}]EXPERIMENT SUMMARY: {experiment_name}[/bold {status_color}] {status_icon}"
        ])

        env_names = [env.name for env in environments]
        summary_parts.extend([
            f"  📊 Tested {len(environments)} environment(s): [dim]{', '.join(env_names)}[/dim]",
            f"  ⏱️  Total duration: [bold cyan]{self.state._format_experiment_timer_duration(total_duration, StatusEnum.NONE)}[/bold cyan]" # Reusing/Adapting formatting
            # Note: _format_duration_text was removed, using state's helper or local logic would be better.
            # Let's fix this properly below.
        ])

        # Formatting helper
        def format_dur(d):
            if not d: return "0s"
            if d >= 60:
                return f"{int(d//60)}m {d%60:.1f}s"
            return f"{d:.1f}s"

        # Correct previous line
        summary_parts[-1] = f"  ⏱️  Total duration: [bold cyan]{format_dur(total_duration)}[/bold cyan]"

        summary_parts.append("  📋 Results:")

        if successful_runs:
            summary_parts.append(f"     [bold green]✅ Successful: {len(successful_runs)}[/bold green]")
            for result in successful_runs:
                duration_str = f"({result['duration']:.1f}s)"
                summary_parts.append(f"        • [dim]{result['environment']}[/dim] [green]{duration_str}[/green]")

        if failed_runs:
            summary_parts.append(f"     [bold red]❌ Failed: {len(failed_runs)}[/bold red]")
            for result in failed_runs:
                duration_str = f"({result['duration']:.1f}s)"
                error_str = f" - {result['error']}" if result.get('error') else ""
                summary_parts.append(f"        • [dim]{result['environment']}[/dim] [red]{duration_str}[/red][dim]{error_str}[/dim]")

        if interrupted_runs:
            summary_parts.append(f"     [bold yellow]⏸️  Interrupted: {len(interrupted_runs)}[/bold yellow]")
            for result in interrupted_runs:
                duration_str = f"({result['duration']:.1f}s)"
                error_str = f" - {result['error']}" if result.get('error') else ""
                summary_parts.append(f"        • [dim]{result['environment']}[/dim] [yellow]{duration_str}[/yellow][dim]{error_str}[/dim]")

        if skipped_runs:
            summary_parts.append(f"     [bold yellow]⏭️  Skipped: {len(skipped_runs)}[/bold yellow]")
            for result in skipped_runs:
                error_str = f" - {result['error']}" if result.get('error') else ""
                summary_parts.append(f"        • [dim]{result['environment']}[/dim][dim]{error_str}[/dim]")

        summary_parts.extend(["", separator])
        complete_message = "\n".join(summary_parts)

        # Store in state
        with self.state._lock:
            self.state.messages.clear()
            self.state.log_multi_experiment_summary(complete_message)


    def log_experiment_summary(self, ulid: str, success: bool, total_actions: int = 0, successful_actions: int = 0, failed_actions: int = 0, total_tests: int = 0, successful_tests: int = 0, failed_tests: int = 0, duration: float = None, level: int = 0, was_interrupted: bool = False):

        # Formatting Logic locally
        def get_status_header(success, interrupted):
            if success: return "[bold green]EXPERIMENT COMPLETED SUCCESSFULLY[/bold green] ✅"
            if interrupted: return "[bold yellow]EXPERIMENT INTERRUPTED[/bold yellow] ⚡"
            return "[bold red]EXPERIMENT FAILED[/bold red] ❌"

        def format_action_summary(successful, total, failed):
            summary = f"Actions: [bold cyan]{successful}[/bold cyan]/[dim]{total}[/dim] passed"
            if failed > 0: summary += f", [bold red]{failed}[/bold red] failed"
            return summary

        def format_test_summary(successful, total, failed):
            if total == 0: return ""
            summary = f"Tests: [bold cyan]{successful}[/bold cyan]/[dim]{total}[/dim] passed"
            if failed > 0: summary += f", [bold red]{failed}[/bold red] failed"
            return summary

        def format_dur(d):
            if not d: return ""
            if d >= 60: return f"[bold cyan]{int(d//60)}m {d%60:.1f}s[/bold cyan]"
            return f"[bold cyan]{d:.1f}s[/bold cyan]"

        summary_parts = []
        indent = "  "
        line_width = self.console.size.width
        separator = "[dim]" + "─" * line_width + "[/dim]"

        summary_parts.extend(["", separator, get_status_header(success, was_interrupted)])

        duration_text = format_dur(duration)
        if duration_text:
            summary_parts.append(f"{indent}⏱️  Duration: {duration_text}")

        # Actions
        action_summary_txt = format_action_summary(successful_actions, total_actions, failed_actions)
        if total_actions > 0:
            summary_parts.append(f"{indent}📊 {action_summary_txt}")
        elif not success:
            msg = "No actions executed (experiment was interrupted)" if was_interrupted else "No actions executed (experiment failed during setup)"
            summary_parts.append(f"{indent}📊 {msg}")

        # Tests
        test_summary_txt = format_test_summary(successful_tests, total_tests, failed_tests)
        if total_tests > 0:
            summary_parts.append(f"{indent}🧪 {test_summary_txt}")

        summary_parts.extend([f"{indent}🆔 Run ID: [dim]{ulid}[/dim]"])
        summary_parts.extend(["", separator])

        complete_message = "\n".join(summary_parts)

        with self.state._lock:
            if 'EXPERIMENT_TIMER' in self.state.messages:
                del self.state.messages['EXPERIMENT_TIMER']
            # We can use generic log call or direct dict set
            self.state.messages['EXPERIMENT_SUMMARY'] = self.state._get_default_message_structure(
                message=complete_message, level=level, status=StatusEnum.NONE
            )

    def log_warning(self, identifier: str, message: str, level: int = 0, duration: float = None):
        self.state.log_warning(identifier, message, level, duration)

    def log_error(self, identifier: str, message: str, level: int = 0, duration: float = None):
        self.state.log_error(identifier, message, level, duration)

    def log_interrupted(self, identifier: str, message: str, level: int = 0, duration: float = None):
        self.state.log_interrupted(identifier, message, level, duration)

    def log_failed(self, identifier: str, message: str, level: int = 0, duration: float = None):
        self.state.log_failed(identifier, message, level, duration)

    def log_finished(self, identifier: str, message: str, level: int = 0, duration: float = None):
        self.state.log_finished(identifier, message, level, duration)

    def change_log_message(self, identifier: str, message: str):
        self.state.change_log_message(identifier, message)

    def log_spinner(self, identifier: str, message: str, level: int = 0, spinner: str = 'dots', spinner_style: str = 'bold blue', start_time: datetime = None):
        self.state.log_spinner(identifier, message, level, spinner, spinner_style, start_time)

    def log_spinner_done(self, identifier: str, status: int, message: str = None, result_status: int = None, duration: float = None):
        self.state.log_spinner_done(identifier, status, message, result_status, duration)

    def exists(self, identifier: str):
        return self.state.exists(identifier)

    def _format_experiment_timer_duration(self, seconds: float, status: int) -> str:
        # Reusing the state's static-like formatter if we made one, or just re-implement.
        # It's simple enough to re-implement or call state's if we moved it.
        # I did not make it a public static method on state, but an instance method.
        # It is just a formatting helper.
        if status == StatusEnum.SUCCESS: color = "green"
        elif status == StatusEnum.FAILED: color = "red"
        else: color = "cyan"

        if seconds >= 60:
            minutes = int(seconds // 60)
            remaining = seconds % 60
            time_str = f"[{color}]{minutes}[/{color}]m [{color}]{remaining:.2f}[/{color}]s"
        else:
            time_str = f"[{color}]{seconds:.2f}[/{color}]s"
        return f"({time_str})"

    def start_experiment_timer(self, experiment_name: str = None):
        self.state.start_experiment_timer()

    def finish_experiment_timer(self, success: bool = True):
        self.state.finish_experiment_timer(success)

    def log_interactive_pause(self, identifier: str, message: str, level: int = 0) -> str:
        """
        Display an interactive pause message and wait for user input.
        Shows the pause message in flow console only, without disrupting the display.
        Returns the user input.
        """
        import os
        import platform
        import queue
        import threading
        import time

        # Show pause message in flow console
        if platform.system() == 'Windows':
            pause_message = f"{message} - Press 'c' to continue"
        else:
            pause_message = f"{message} - Press 'c' and then Enter to continue"

        # Log as warning to make it stand out in the flow console
        # Use level 2 to match main playbook actions (same as other actions)
        display_level = 2  # Main playbook action level
        self.state.log_interactive_pause(identifier, pause_message, display_level)

        # Use a separate thread for input handling to avoid interfering with Rich Live
        input_queue = queue.Queue()
        input_thread_stop = threading.Event()

        def input_worker():
            """Worker thread to handle input without blocking Rich Live."""
            try:
                if os.name == 'nt':  # Windows
                    import msvcrt
                    while not input_thread_stop.is_set():
                        if msvcrt.kbhit():
                            char = msvcrt.getch().decode('utf-8', errors='ignore').lower()
                            input_queue.put(char)
                            break
                        time.sleep(0.05)  # Faster polling in separate thread
                else:  # Unix/Linux
                    # Use standard input() which is more reliable than select/readline
                    try:
                        # This will block in the separate thread, not affecting Rich Live
                        user_input = input().strip().lower()
                        if user_input:
                            input_queue.put(user_input[0])  # Put first character
                        else:
                            input_queue.put('c')  # Empty input treated as continue
                    except (EOFError, KeyboardInterrupt):
                        input_queue.put('interrupted')
            except Exception as e:
                log.error(f"Input worker thread error: {e}")
                input_queue.put('error')

        # Start input worker thread
        input_thread = threading.Thread(target=input_worker, daemon=True)
        input_thread.start()

        user_input = None
        try:
            # Main thread polls the queue without blocking
            while True:
                try:
                    # Check for input from worker thread (non-blocking)
                    char = input_queue.get(timeout=0.1)

                    if char == 'c':
                        user_input = 'c'
                        break
                    if char in ['interrupted', '\x03', '\x04']:
                        user_input = 'interrupted'
                        break
                    if char == 'error':
                        user_input = 'error'
                        break
                    # Invalid input, continue waiting
                    continue

                except queue.Empty:
                    # No input yet, continue polling
                    # This maintains Rich Live responsiveness
                    continue
                except (EOFError, KeyboardInterrupt):
                    user_input = 'interrupted'
                    break

        finally:
            # Clean up input thread
            input_thread_stop.set()
            # Give thread a moment to finish
            input_thread.join(timeout=0.5)

        # Update the pause message to show completion in flow console
        if user_input == 'c':
            self.state.log_finished(identifier, f"{message} - Continued", display_level)
            return 'c'
        if user_input == 'interrupted':
            self.state.log_interrupted(identifier, f"{message} - Interrupted", display_level)
            return 'interrupted'
        self.state.log_failed(identifier, f"{message} - Invalid input, continuing anyway", display_level)
        return user_input or 'timeout'

    def print_debug_flow_messages(self):
        with self.state._lock:
            from rich import print
            print(self.state.messages)


class FlowConsoleManager:
    """Manager for active ExperimentFlowConsole instances."""
    def __init__(self):
        self.handlers = {}

    def add_handler(self, experiment_run_ulid: str, handler: ExperimentFlowConsole):
        self.handlers[experiment_run_ulid] = handler

    def get_handler(self, experiment_run_ulid: str) -> ExperimentFlowConsole:
        return self.handlers.get(experiment_run_ulid)

    def remove_handler(self, experiment_run_ulid: str):
        if experiment_run_ulid in self.handlers:
            del self.handlers[experiment_run_ulid]


flowconsolemanager = FlowConsoleManager()
