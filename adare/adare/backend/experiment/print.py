from rich.console import Console
import threading
import time
from datetime import datetime, timezone
from rich.live import Live
from rich.text import Text
from rich.layout import Layout
from rich.spinner import SPINNERS

from adarelib.constants import StatusEnum

# configure logging
import logging
log = logging.getLogger(__name__)


class ExperimentFlowConsole:
    console: Console
    stop_event: threading.Event
    thread: threading.Thread | None
    disable: bool
    external_stop_event: threading.Event | None

    messages: dict
    ticks_per_second: int = 12
    _lock: threading.Lock
    _original_log_level: int | None  # Store original console log level
    
    # Live duration tracking
    experiment_start_time: datetime | None
    show_live_duration: bool

    layout: Text

    def __init__(self, disable: bool = False, external_stop_event: threading.Event = None):
        self.console = Console()
        self.stop_event = threading.Event()
        self.external_stop_event = external_stop_event
        self.messages = {}
        self.thread = None
        self.disable = disable
        self._lock = threading.Lock()
        self._original_log_level = None
        
        # Initialize live duration tracking
        self.experiment_start_time = None
        self.show_live_duration = False

        terminal_size = self.console.size
        desired_height = terminal_size.height - 2 if terminal_size.height > 2 else 1
        self.console = Console(height=desired_height) 

        self.layout = Text('Loading...')

    def _start_live_in_thread(self):
        tick_count = 0
        with Live(self.layout, console=self.console, refresh_per_second=self.ticks_per_second,
                  auto_refresh=False, transient=False) as live:
            while not self.stop_event.is_set():
                try:
                    with self._lock:
                        message_identifiers = list(self.messages.keys())
                        # Ensure experiment timer appears first if it exists
                        if 'EXPERIMENT_TIMER' in message_identifiers:
                            message_identifiers.remove('EXPERIMENT_TIMER')
                            message_identifiers.insert(0, 'EXPERIMENT_TIMER')

                    # Generate messages and filter out empty ones to avoid blank lines
                    generated_messages = [self._generate_message(identifier, spinner_position=tick_count) for identifier in message_identifiers]
                    non_empty_messages = [msg for msg in generated_messages if msg.strip()]
                    messages_as_str = '\n'.join(non_empty_messages)
                    live.update(messages_as_str)
                    live.refresh()  # Force manual refresh since auto_refresh=False
                    tick_count += 1

                except Exception as e:
                    # Don't let message generation errors break the refresh cycle
                    log.error(f"Error in flow console refresh cycle: {e}")
                    # Continue with a fallback display
                    try:
                        live.update("Flow console error - please check logs")
                        live.refresh()
                    except:
                        pass  # If even this fails, just continue the loop

                time.sleep(0.1)
        log.debug('rich live thread stopped')

    def start(self):
        if not self.disable:
            # Suppress console logging to avoid interference with rich display
            self._suppress_console_logging()
            self.thread = threading.Thread(target=self._start_live_in_thread)
            self.thread.start()

    def stop(self):
        if not self.disable:
            self.stop_event.set()
            self.thread.join()
            # Restore original console logging level
            self._restore_console_logging()

    def _suppress_console_logging(self):
        """Suppress console logging when flow console is active.
        
        ISSUE CONTEXT: When the experiment flow console (Rich live display) is active,
        regular Python logging messages (INFO, WARNING, ERROR) would interfere with
        the clean Rich console output, creating a messy mixed display of:
        - Rich-formatted experiment progress with spinners and status icons
        - Interleaved plain text log messages from various components
        
        SOLUTION: Temporarily raise console logging level to CRITICAL to suppress
        most log messages while preserving:
        - File logging (unaffected, continues normally)
        - Critical error messages (still shown if needed)
        - Clean Rich console display without interference
        
        This ensures users see a clean experiment progress display instead of
        mixed logging output that was difficult to read and follow.
        """
        from adare.setup_logging import set_console_log_level
        
        # Store current log level of console handlers
        root_logger = logging.getLogger()
        for handler in root_logger.handlers:
            if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
                self._original_log_level = handler.level
                break
        
        # Set console logging to CRITICAL to suppress most messages
        set_console_log_level(logging.CRITICAL)

    def _restore_console_logging(self):
        """Restore original console logging level."""
        if self._original_log_level is not None:
            from adare.setup_logging import set_console_log_level
            set_console_log_level(self._original_log_level)

    def _generate_message(self, identifier: str, spinner_position: int = 0):
        with self._lock:
            if identifier not in self.messages:
                return ""
            message_object = self.messages[identifier]
            message = message_object['message']

            # Special handling for experiment timer
            if message_object.get('is_experiment_timer'):
                # For experiment timer, only show duration if available
                # If message is empty and no duration to show yet, return empty string to hide this line
                if not message and not message_object.get('duration') and not message_object.get('start_time'):
                    return ""
                # Skip icon addition for experiment timer - duration will be the only content
                pass
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
                message = ' ' * 2 * message_object['level'] + message

            # Add result_status right after message text (before duration)
            if message_object['result_status']:
                message = f'{message} {StatusEnum.get_icon(message_object["result_status"], color=True)}'

            # Add duration display aligned to the right if available
            duration_text = None
            
            if message_object.get('duration'):
                # Final duration (when completed)
                if message_object.get('is_experiment_timer'):
                    duration_text = self._format_experiment_timer_duration(
                        message_object['duration'], message_object['status']
                    )
                else:
                    duration_text = f"({message_object['duration']:.2f}s)"
            elif message_object.get('start_time'):
                # Live duration
                elapsed_seconds = (datetime.now(timezone.utc) - message_object['start_time']).total_seconds()
                if message_object.get('is_experiment_timer'):
                    duration_text = self._format_experiment_timer_duration(
                        elapsed_seconds, message_object['status']
                    )
                else:
                    duration_text = f"({elapsed_seconds:.2f}s)"
            
            if duration_text:
                terminal_width = self.console.size.width
                # Calculate the total line length to prevent wrapping
                from rich.text import Text

                # Build the complete line first
                complete_line = f"{message} {duration_text}"
                complete_obj = Text.from_markup(complete_line)
                complete_width = self.console.measure(complete_obj).maximum

                if complete_width > terminal_width:
                    # Line is too long, need to truncate the message part
                    duration_obj = Text.from_markup(duration_text)
                    duration_width = self.console.measure(duration_obj).maximum

                    # Calculate how much space we have for the message
                    available_for_message = terminal_width - duration_width - 4  # -4 for " " + "..."

                    if available_for_message > 10:  # Ensure we have reasonable space
                        # Handle multiline messages (like heredoc commands) specially
                        message_obj = Text.from_markup(message)
                        if len(message_obj) > available_for_message:
                            # Check if the ORIGINAL message (not Rich object) is multiline
                            is_multiline = '\n' in message

                            if is_multiline:
                                # For truly multiline content, show only the first line
                                first_line = message.split('\n')[0].strip()
                                # Remove any Rich markup from first line for safer truncation
                                import re
                                # Strip Rich markup like [bold], [/bold], etc.
                                clean_first_line = re.sub(r'\[/?[^\]]*\]', '', first_line)

                                # If first line is still too long, truncate it
                                if len(clean_first_line) > available_for_message:
                                    clean_first_line = clean_first_line[:available_for_message-3].strip()

                                message = f"{clean_first_line}..."
                            else:
                                # Single line that's just too long - truncate safely
                                # Strip Rich markup for safer truncation
                                import re
                                clean_message = re.sub(r'\[/?[^\]]*\]', '', message)
                                if len(clean_message) > available_for_message:
                                    clean_message = clean_message[:available_for_message-3].strip()
                                message = f"{clean_message}..."

                        # Right-align the duration
                        current_width = self.console.measure(Text.from_markup(message)).maximum
                        padding = terminal_width - current_width - duration_width
                        if padding > 1:
                            message = f"{message}{' ' * (padding - 1)} {duration_text}"
                        else:
                            message = f"{message} {duration_text}"
                    else:
                        # Very narrow terminal, just truncate severely
                        message = f"{message[:terminal_width-10]}... {duration_text}"
                else:
                    # Line fits properly, add right-aligned duration with padding
                    duration_obj = Text.from_markup(duration_text)
                    duration_width = self.console.measure(duration_obj).maximum

                    message_obj = Text.from_markup(message)
                    message_width = self.console.measure(message_obj).maximum

                    # Calculate padding to right-align duration
                    padding = terminal_width - message_width - duration_width
                    if padding > 1:
                        message = f"{message}{' ' * (padding - 1)} {duration_text}"
                    else:
                        message = f"{message} {duration_text}"

            return message


    def log_success(self, identifier: str, message: str, level: int = 0, duration: float = None):
        with self._lock:
            self.messages[identifier] = {
                'message': message,
                'spinner': None,
                'spinner_style': None,
                'level': level,
                'status': StatusEnum.SUCCESS,
                'result_status': None,
                'duration': duration,
            }

    def log_ulid(self, ulid: str, level: int = 0):
        with self._lock:
            self.messages['ULID'] = {
                'message': f'ULID: {ulid}',
                'spinner': None,
                'spinner_style': None,
                'level': level,
                'status': StatusEnum.NONE,
                'result_status': None,
                'duration': None,
            }

    def log_experiment_summary(self, ulid: str, success: bool, total_actions: int = 0, successful_actions: int = 0, failed_actions: int = 0, total_tests: int = 0, successful_tests: int = 0, failed_tests: int = 0, duration: float = None, level: int = 0, was_interrupted: bool = False):
        """Log a comprehensive, visually appealing experiment summary."""
        with self._lock:
            overall_status = self._determine_overall_status(success, was_interrupted)
            action_summary = self._format_action_summary(successful_actions, total_actions, failed_actions)
            test_summary = self._format_test_summary(successful_tests, total_tests, failed_tests)
            duration_text = self._format_duration(duration)
            
            summary_parts = self._build_summary_parts(
                success, was_interrupted, duration_text, action_summary, 
                test_summary, total_actions, total_tests, ulid
            )
            
            complete_message = "\n".join(summary_parts)
            
            # Replace the experiment timer with the summary for final display
            if 'EXPERIMENT_TIMER' in self.messages:
                del self.messages['EXPERIMENT_TIMER']
            
            self.messages['EXPERIMENT_SUMMARY'] = {
                'message': complete_message,
                'spinner': None,
                'spinner_style': None,
                'level': level,
                'status': None,
                'result_status': None,
                'duration': None,
            }

    def _determine_overall_status(self, success: bool, was_interrupted: bool) -> int:
        """Determine the overall experiment status."""
        if success:
            return StatusEnum.SUCCESS
        elif was_interrupted:
            return StatusEnum.INTERRUPTED
        else:
            return StatusEnum.FAILED

    def _format_action_summary(self, successful: int, total: int, failed: int) -> str:
        """Format the action summary statistics."""
        summary = f"Actions: [bold cyan]{successful}[/bold cyan]/[dim]{total}[/dim] passed"
        if failed > 0:
            summary += f", [bold red]{failed}[/bold red] failed"
        return summary

    def _format_test_summary(self, successful: int, total: int, failed: int) -> str:
        """Format the test summary statistics."""
        if total == 0:
            return ""
        
        summary = f"Tests: [bold cyan]{successful}[/bold cyan]/[dim]{total}[/dim] passed"
        if failed > 0:
            summary += f", [bold red]{failed}[/bold red] failed"
        return summary

    def _format_duration(self, duration: float) -> str:
        """Format experiment duration."""
        if not duration:
            return ""
        
        if duration >= 60:
            minutes = int(duration // 60)
            remaining_seconds = duration % 60
            return f"[bold cyan]{minutes}m {remaining_seconds:.1f}s[/bold cyan]"
        else:
            return f"[bold cyan]{duration:.1f}s[/bold cyan]"

    def _get_status_header(self, success: bool, was_interrupted: bool) -> str:
        """Get the appropriate status header with icon."""
        if success:
            return f"[bold green]EXPERIMENT COMPLETED SUCCESSFULLY[/bold green] ✅"
        elif was_interrupted:
            return f"[bold yellow]EXPERIMENT INTERRUPTED[/bold yellow] ⚡"
        else:
            return f"[bold red]EXPERIMENT FAILED[/bold red] ❌"

    def _build_summary_parts(self, success: bool, was_interrupted: bool, duration_text: str, 
                           action_summary: str, test_summary: str, total_actions: int, 
                           total_tests: int, ulid: str) -> list[str]:
        """Build the complete summary message parts."""
        summary_parts = []
        indent = "  "  # 2 spaces for inner message indentation
        
        line_width = self.console.size.width
        separator = "[dim]" + "─" * line_width + "[/dim]"
        
        # Header section
        summary_parts.extend(["", separator, self._get_status_header(success, was_interrupted)])
        
        # Duration line
        if duration_text:
            summary_parts.append(f"{indent}⏱️  Duration: {duration_text}")
        
        # Results section
        self._add_results_section(summary_parts, indent, total_actions, action_summary, 
                                success, was_interrupted, total_tests, test_summary)
        
        # ULID section
        summary_parts.extend([f"{indent}🆔 Run ID: [dim]{ulid}[/dim]"])
        
        # Footer
        summary_parts.extend(["", separator])
        
        return summary_parts

    def _add_results_section(self, summary_parts: list[str], indent: str, total_actions: int, 
                           action_summary: str, success: bool, was_interrupted: bool, 
                           total_tests: int, test_summary: str):
        """Add the results section to summary parts."""
        if total_actions > 0:
            summary_parts.append(f"{indent}📊 {action_summary}")
        elif not success:
            message = "No actions executed (experiment was interrupted)" if was_interrupted else "No actions executed (experiment failed during setup)"
            summary_parts.append(f"{indent}📊 {message}")
        
        if total_tests > 0:
            summary_parts.append(f"{indent}🧪 {test_summary}")

    def log_warning(self, identifier: str, message: str, level: int = 0, duration: float = None):
        with self._lock:
            self.messages[identifier] = {
                'message': message,
                'spinner': None,
                'spinner_style': None,
                'level': level,
                'status': StatusEnum.WARNING,
                'result_status': None,
                'duration': duration,
            }

    def log_error(self, identifier: str, message: str, level: int = 0, duration: float = None):
        with self._lock:
            self.messages[identifier] = {
                'message': message,
                'spinner': None,
                'spinner_style': None,
                'level': level,
                'status': StatusEnum.ERROR,
                'result_status': None,
                'duration': duration,
            }

    def log_interrupted(self, identifier: str, message: str, level: int = 0, duration: float = None):
        with self._lock:
            self.messages[identifier] = {
                'message': message,
                'spinner': None,
                'spinner_style': None,
                'level': level,
                'status': StatusEnum.INTERRUPTED,
                'result_status': None,
                'duration': duration,
            }

    def log_failed(self, identifier: str, message: str, level: int = 0, duration: float = None):
        with self._lock:
            self.messages[identifier] = {
                'message': message,
                'spinner': None,
                'spinner_style': None,
                'level': level,
                'status': StatusEnum.FAILED,
                'result_status': None,
                'duration': duration,
            }

    def log_finished(self, identifier: str, message: str, level: int = 0, duration: float = None):
        with self._lock:
            self.messages[identifier] = {
                'message': message,
                'spinner': None,
                'spinner_style': None,
                'level': level,
                'status': StatusEnum.FINISHED,
                'result_status': None,
                'duration': duration,
            }
        

    def change_log_message(self, identifier: str, message: str):
        with self._lock:
            if identifier in self.messages:
                self.messages[identifier]['message'] = message

    def log_spinner(self, identifier: str, message: str, level: int = 0, spinner: str = 'dots', spinner_style: str = 'bold blue', start_time: datetime = None):
        with self._lock:
            self.messages[identifier] = {
                'message': message,
                'spinner': spinner,
                'spinner_style': spinner_style,
                'level': level,
                'status': StatusEnum.NONE,
                'result_status': None,
                'duration': None,
                'start_time': start_time,  # Track when this stage started
            }

    def log_spinner_done(self, identifier: str, status: int, message: str = None, result_status: int = None, duration: float = None):
        with self._lock:
            if identifier not in self.messages:
                log.warning(f"Attempted to update non-existent spinner message: {identifier}")
                return
            updated_msg = self.messages[identifier]
            updated_msg['spinner'] = None
            updated_msg['spinner_style'] = None
            updated_msg['status'] = status
            updated_msg['result_status'] = result_status
            if message:
                updated_msg['message'] = message
            if duration is not None:
                updated_msg['duration'] = duration
            self.messages[identifier] = updated_msg

    def exists(self, identifier: str):
        with self._lock:
            return identifier in self.messages

    def _format_experiment_timer_duration(self, seconds: float, status: int) -> str:
        """Format experiment timer duration with appropriate color and time units."""
        # Choose color based on status
        if status == StatusEnum.SUCCESS:
            color = "green"
        elif status == StatusEnum.FAILED:
            color = "red"
        else:
            color = "cyan"
        
        # Format time with colored numbers, grey units
        if seconds >= 60:
            minutes = int(seconds // 60)
            remaining_seconds = seconds % 60
            time_str = f"[{color}]{minutes}[/{color}]m [{color}]{remaining_seconds:.2f}[/{color}]s"
        else:
            time_str = f"[{color}]{seconds:.2f}[/{color}]s"
        
        return f"({time_str})"

    def start_experiment_timer(self, experiment_name: str = None):
        """Start the experiment timer header row that shows live total time."""
        with self._lock:
            self.experiment_start_time = datetime.now(timezone.utc)
            self.messages['EXPERIMENT_TIMER'] = {
                'message': "",  # Empty message - duration will be shown via start_time
                'spinner': None,
                'spinner_style': None,
                'level': 0,
                'status': StatusEnum.NONE,
                'result_status': None,
                'duration': None,
                'start_time': self.experiment_start_time,
                'is_experiment_timer': True,  # Flag for special handling
            }

    def finish_experiment_timer(self, success: bool = True):
        """Finalize the experiment timer with completion status."""
        with self._lock:
            if 'EXPERIMENT_TIMER' in self.messages:
                timer_msg = self.messages['EXPERIMENT_TIMER']
                if timer_msg.get('start_time'):
                    # Calculate final duration
                    end_time = datetime.now(timezone.utc)
                    timer_msg['duration'] = (end_time - timer_msg['start_time']).total_seconds()
                timer_msg['status'] = StatusEnum.SUCCESS if success else StatusEnum.FAILED
                timer_msg['start_time'] = None  # Stop live updates

    def log_interactive_pause(self, identifier: str, message: str, level: int = 0) -> str:
        """
        Display an interactive pause message and wait for user input.
        Shows the pause message in flow console only, without disrupting the display.
        Returns the user input.
        """
        import platform
        import threading
        import queue
        import sys
        import os
        import time

        # Show pause message in flow console
        if platform.system() == 'Windows':
            pause_message = f"{message} - Press 'c' to continue"
        else:
            pause_message = f"{message} - Press 'c' and then Enter to continue"


        # Log as warning to make it stand out in the flow console
        # Use level 2 to match main playbook actions (same as other actions)
        display_level = 2  # Main playbook action level
        with self._lock:
            self.messages[identifier] = {
                'message': pause_message,
                'spinner': None,
                'spinner_style': None,
                'level': display_level,
                'status': StatusEnum.PAUSE,  # Use pause status to show pause icon
                'result_status': None,
                'duration': None,
            }

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
                    elif char in ['interrupted', '\x03', '\x04']:
                        user_input = 'interrupted'
                        break
                    elif char == 'error':
                        user_input = 'error'
                        break
                    else:
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
            self.log_finished(identifier, f"{message} - Continued", display_level)
            return 'c'
        elif user_input == 'interrupted':
            with self._lock:
                self.messages[identifier] = {
                    'message': f"{message} - Interrupted",
                    'spinner': None,
                    'spinner_style': None,
                    'level': display_level,
                    'status': StatusEnum.INTERRUPTED,
                    'result_status': None,
                    'duration': None,
                }
            return 'interrupted'
        else:
            with self._lock:
                self.messages[identifier] = {
                    'message': f"{message} - Invalid input, continuing anyway",
                    'spinner': None,
                    'spinner_style': None,
                    'level': display_level,
                    'status': StatusEnum.FAILED,
                    'result_status': None,
                    'duration': None,
                }
            return user_input or 'timeout'

    def print_debug_flow_messages(self):
        """Print all flow messages for debugging purposes."""
        with self._lock:
            if not self.messages:
                print("\n=== EXPERIMENT FLOW DEBUG: No messages to display ===")
                return

            print("\n" + "="*60)
            print("EXPERIMENT FLOW DEBUG MESSAGES")
            print("="*60)

            for identifier, message_object in self.messages.items():
                status_icon = StatusEnum.get_icon(message_object['status'], color=False)
                print(f"[{identifier}] {status_icon} {message_object['message']}")

                if message_object['result_status']:
                    result_icon = StatusEnum.get_icon(message_object['result_status'], color=False)
                    print(f"    └─ Result: {result_icon}")

            print("="*60)
            print(f"Total messages: {len(self.messages)}")
            print("="*60 + "\n")


class FlowConsoleManager:
    def __init__(self):
        self._handlers = {}
        self._lock = threading.Lock()

    def add_handler(self, experimentrun_ulid: str, handler: ExperimentFlowConsole):
        with self._lock:
            self._handlers[experimentrun_ulid] = handler

    def get_handler(self, experimentrun_ulid: str) -> ExperimentFlowConsole | None:
        with self._lock:
            return self._handlers.get(experimentrun_ulid)

    def remove_handler(self, experimentrun_ulid: str):
        with self._lock:
            self._handlers.pop(experimentrun_ulid, None)



flowconsolemanager = FlowConsoleManager()