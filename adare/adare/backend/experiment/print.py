from rich.console import Console
import threading
import time


class ExperimentFlowConsole:
    console: Console
    ctrlc_event: threading.Event

    def __init__(self, ctrlc_event: threading.Event):
        self.console = Console()
        self.ctrlc_event = ctrlc_event

    def log_success(self, message: str):
        self.console.print(f'[green]:black_small_square:[/green] {message}')

    def log_warning(self, message: str):
        # yellow exclamation mark surrounded by square brackets
        self.console.print(f'[yellow]:black_small_square:[/yellow] {message}')

    def log_error(self, message: str):
        # red cross surrounded by square brackets
        self.console.print(f'[red]:x:[/red] {message}')

    def log_interrupted(self):
        self.console.print(f'[yellow]:black_small_square:[/yellow] vagrant interrupted by user')

    def log_ongoing(self, message: str, event: threading.Event):
        spinner_thread = threading.Thread(target=self.__run_spinner, args=(message, event))
        spinner_thread.start()
        return spinner_thread

    def __run_spinner(self, message: str, event: threading.Event):
        with self.console.status(message, spinner="dots", spinner_style="bold blue") as status:
            while not event.is_set() and not self.ctrlc_event.is_set():
                time.sleep(0.1)
            if self.ctrlc_event.is_set():
                self.log_interrupted()
            status.stop()
