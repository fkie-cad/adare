from rich.console import Console
import threading
import time
from rich.live import Live
from rich.progress import Progress, TextColumn, BarColumn, SpinnerColumn


class ExperimentFlowConsole:
    console: Console
    ctrlc_event: threading.Event
    spinners: dict

    def __init__(self, ctrlc_event: threading.Event):
        self.console = Console()
        self.ctrlc_event = ctrlc_event
        self.spinners = {}

    def log_success(self, message: str, level: int = 0):
        print_line = '\t'*level + f'[green]:black_small_square:[/green] {message}'
        self.console.print(print_line)

    def log_warning(self, message: str, level: int = 0):
        print_line = '\t'*level + f'[yellow]:black_small_square:[/yellow] {message}'
        self.console.print(print_line)

    def log_error(self, message: str, level: int = 0):
        print_line = '\t'*level + f'[red]:black_small_square:[/red] {message}'
        self.console.print(print_line)

    def log_interrupted(self, level: int = 0):
        print_line = '\t'*level + f'[yellow]:black_small_square:[/yellow] interrupted by user'
        self.console.print(print_line)

    def log_ongoing(self, spinner: str,message: str, event: threading.Event, level: int = 0):
        self.spinners[spinner] = {
            'thread': None,
            'stop': event,
            'message': message,
        }
        spinner_thread = threading.Thread(target=self.__run_spinner, args=(spinner, level,))
        spinner_thread.start()
        self.spinners[spinner]['thread'] = spinner_thread

    def change_spinner_text(self, spinner: str, new_text: str):
        self.spinners[spinner]['message'] = new_text

    def __run_spinner(self, spinner: str, level: int = 0):
        columns = [
            SpinnerColumn(spinner_name="dots", style="bold blue"),
            TextColumn(self.spinners[spinner]["message"]),
        ]
        if level > 0:
            columns = [TextColumn("\t"*level)] + columns

        progress = Progress(
            *columns
        )

        # Start a live display with the spinner
        with Live(progress, console=self.console, auto_refresh=True) as live:
            task = progress.add_task("", total=1)
            while not self.spinners[spinner]['stop'].is_set() and not self.ctrlc_event.is_set():
                progress.update(task, advance=0)
                time.sleep(0.1)
            if self.ctrlc_event.is_set():
                self.log_interrupted()
            # After task is done, update the live display to show a checkmark
            live.update('\t'*level + f'[green]:black_small_square:[/green] {self.spinners[spinner]["message"]}')
