from rich.console import Console
import threading
import time
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

    layout: Text

    def __init__(self, disable: bool = False, external_stop_event: threading.Event = None):
        self.console = Console()
        self.stop_event = threading.Event()
        self.external_stop_event = external_stop_event
        self.messages = {}
        self.thread = None
        self.disable = disable
        self._lock = threading.Lock()

        terminal_size = self.console.size
        # Set the height as terminal height minus 10
        desired_height = terminal_size.height - 10 if terminal_size.height > 10 else 1
        self.console = Console(height=desired_height)

        self.layout = Text('Loading...')

    def _start_live_in_thread(self):
        tick_count = 0
        with Live(self.layout, console=self.console, refresh_per_second=self.ticks_per_second) as live:
            while not self.stop_event.is_set():
                # Check for external interruption (Ctrl-C) - no need to add separate message
                # The interrupted stages will show "(interrupted by user)" inline
                    
                messages_as_str = '\n'.join([self._generate_message(identifier, spinner_position=tick_count) for identifier in self.messages.keys()])
                #log.debug(f"Rich Live rendering (tick {tick_count}, msg count: {len(self.messages)}): {repr(messages_as_str[:100])}")

                live.update(messages_as_str)
                tick_count += 1
                time.sleep(0.1)
        log.debug('rich live thread stopped')

    def start(self):
        if not self.disable:
            self.thread = threading.Thread(target=self._start_live_in_thread)
            self.thread.start()

    def stop(self):
        if not self.disable:
            self.stop_event.set()
            self.thread.join()

    def _generate_message(self, identifier: str, spinner_position: int = 0):
        with self._lock:
            if identifier not in self.messages:
                return ""
            message_object = self.messages[identifier]
            message = message_object['message']
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

            if message_object['result_status']:
                message = f'{message} {StatusEnum.get_icon(message_object["result_status"], color=True)}'

            return message

    def log_breakpoint_done(self, identifier: str, message: str):
        with self._lock:
            self.messages[identifier] = {
                'message': message,
                'spinner': None,
                'spinner_style': None,
                'level': 0,
                'status': StatusEnum.BREAKPOINT_RESOLVED,
                'result_status': None,
            }

    def log_success(self, identifier: str, message: str, level: int = 0):
        with self._lock:
            self.messages[identifier] = {
                'message': message,
                'spinner': None,
                'spinner_style': None,
                'level': level,
                'status': StatusEnum.SUCCESS,
                'result_status': None,
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
            }

    def log_warning(self, identifier: str, message: str, level: int = 0):
        with self._lock:
            self.messages[identifier] = {
                'message': message,
                'spinner': None,
                'spinner_style': None,
                'level': level,
                'status': StatusEnum.WARNING,
                'result_status': None,
            }

    def log_error(self, identifier: str, message: str, level: int = 0):
        with self._lock:
            self.messages[identifier] = {
                'message': message,
                'spinner': None,
                'spinner_style': None,
                'level': level,
                'status': StatusEnum.ERROR,
                'result_status': None,
            }

    def log_interrupted(self, identifier: str, message: str, level: int = 0):
        with self._lock:
            self.messages[identifier] = {
                'message': message,
                'spinner': None,
                'spinner_style': None,
                'level': level,
                'status': StatusEnum.INTERRUPTED,
                'result_status': None,
            }

    def log_failed(self, identifier: str, message: str, level: int = 0):
        with self._lock:
            self.messages[identifier] = {
                'message': message,
                'spinner': None,
                'spinner_style': None,
                'level': level,
                'status': StatusEnum.FAILED,
                'result_status': None,
            }

    def log_finished(self, identifier: str, message: str, level: int = 0):
        with self._lock:
            self.messages[identifier] = {
                'message': message,
                'spinner': None,
                'spinner_style': None,
                'level': level,
                'status': StatusEnum.FINISHED,
                'result_status': None,
            }

    def change_log_message(self, identifier: str, message: str):
        with self._lock:
            if identifier in self.messages:
                self.messages[identifier]['message'] = message

    def log_spinner(self, identifier: str, message: str, level: int = 0, spinner: str = 'dots', spinner_style: str = 'bold blue'):
        with self._lock:
            self.messages[identifier] = {
                'message': message,
                'spinner': spinner,
                'spinner_style': spinner_style,
                'level': level,
                'status': StatusEnum.NONE,
                'result_status': None,
            }

    def log_spinner_done(self, identifier: str, status: int, message: str = None, result_status: int = None):
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
            self.messages[identifier] = updated_msg

    def exists(self, identifier: str):
        with self._lock:
            return identifier in self.messages

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