from rich.console import Console
import threading
import time
from rich.live import Live
from rich.text import Text
from rich.spinner import SPINNERS

from adarelib.config import StatusEnum

# configure logging
import logging
log = logging.getLogger(__name__)


class ExperimentFlowConsole:
    console: Console
    stop_event: threading.Event
    thread: threading.Thread or None
    disable: bool

    messages: dict
    ticks_per_second: int = 12

    def __init__(self, disable: bool = False):
        self.console = Console()
        self.stop_event = threading.Event()
        self.messages = {}
        self.thread = None
        self.disable = disable

    def _start_live_in_thread(self):
        text = Text('Loading...')
        tick_count = 0
        with Live(text, console=self.console, refresh_per_second=self.ticks_per_second) as live:
            while not self.stop_event.is_set():
                messages_as_str = '\n'.join([self._generate_message(identifier, spinner_position=tick_count) for identifier in self.messages.keys()])
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
        message_object = self.messages[identifier]
        message = message_object['message']
        if message_object['status'] == StatusEnum.SUCCESS:
            message = f'[green]:heavy_check_mark:[/green] {message}'
        elif message_object['status'] == StatusEnum.WARNING:
            message = f'[yellow]![/yellow] {message}'
        elif message_object['status'] == StatusEnum.ERROR:
            message = f'[red]:heavy_multiplication_x:[/red] {message}'
        elif message_object['status'] == StatusEnum.INTERRUPTED:
            message = f'[yellow]:high_voltage:[/yellow] {message}'

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

        return message

    def log_success(self, identifier: str, message: str, level: int = 0):
        self.messages[identifier] = {
            'message': message,
            'spinner': None,
            'spinner_style': None,
            'level': level,
            'status': StatusEnum.SUCCESS
        }

    def log_warning(self, identifier: str, message: str, level: int = 0):
        self.messages[identifier] = {
            'message': message,
            'spinner': None,
            'spinner_style': None,
            'level': level,
            'status': StatusEnum.WARNING
        }

    def log_error(self, identifier: str, message: str, level: int = 0):
        self.messages[identifier] = {
            'message': message,
            'spinner': None,
            'spinner_style': None,
            'level': level,
            'status': StatusEnum.ERROR
        }

    def log_interrupted(self, identifier: str, message: str, level: int = 0):
        self.messages[identifier] = {
            'message': message,
            'spinner': None,
            'spinner_style': None,
            'level': level,
            'status': StatusEnum.INTERRUPTED
        }

    def change_log_message(self, identifier: str, message: str):
        self.messages[identifier]['message'] = message

    def log_spinner(self, identifier: str, message: str, level: int = 0, spinner: str = 'dots', spinner_style: str = 'bold blue'):
        self.messages[identifier] = {
            'message': message,
            'spinner': spinner,
            'spinner_style': spinner_style,
            'level': level,
            'status': StatusEnum.NONE
        }

    def log_spinner_done(self, identifier: str, status: int, message: str = None):
        updated_msg = self.messages[identifier]
        updated_msg['spinner'] = None
        updated_msg['spinner_style'] = None
        updated_msg['status'] = status
        if message:
            updated_msg['message'] = message
        self.messages[identifier] = updated_msg

    def exists(self, identifier: str):
        return identifier in self.messages.keys()


class FlowConsoleManager:
    def __init__(self):
        self.handlers = {}  # Dictionary to store experiment_id to handler mappings

    def add_handler(self, experimentrun_uuid: str, handler: ExperimentFlowConsole):
        self.handlers[experimentrun_uuid] = handler

    def get_handler(self, experimentrun_uuid: str) -> ExperimentFlowConsole:
        return self.handlers[experimentrun_uuid]


flowconsolemanager = FlowConsoleManager()
