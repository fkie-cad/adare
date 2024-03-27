import time
from pathlib import Path
import json
from watchdog.events import FileSystemEventHandler, FileSystemEvent

import logging
log = logging.getLogger(__name__)


class BreakPoint:
    name: str
    file: Path

    def __init__(self, name: str, json_file: Path = None):

        self.name = name
        self.file = json_file

    def trigger(self):
        continue_value = False
        while not continue_value:
            user_input = input(f'(Breakpoint: {self.name}) Press y to continue: ')
            if user_input == 'y':
                continue_value = True
        if self.file:
            self.file.unlink()

    @classmethod
    def from_json(cls, json_file: Path):
        try:
            with open(json_file, 'r') as f:
                json_data = json.load(f)
        except json.JSONDecodeError:
            log.warning(f'Breakpoint file {json_file} could not be read')
            return None
        name = json_data.get('name', None)
        return None if name is None else cls(name, json_file)

    def to_json(self, json_file: Path):
        data = {
            'name': self.name
        }
        with open(json_file, 'w') as f:
            json.dump(data, f)


class BreakpointReceiveHandler(FileSystemEventHandler):
    breakpoints: list[str]

    def __init__(self, breakpoints: list[str]):
        self.breakpoints = breakpoints

    def on_created(self, event: FileSystemEvent) -> None:
        breakpoint_file = Path(event.src_path)
        bp = BreakPoint.from_json(breakpoint_file)
        if bp:
            if bp.name in self.breakpoints:
                log.info(f'Breakpoint {bp.name} received')
                bp.trigger()
            else:
                breakpoint_file.unlink()


def set_breakpoint(name: str, json_file: Path):
    bp = BreakPoint(name)
    bp.to_json(json_file)
    log.info(f'Breakpoint {name} set')
    while json_file.is_file():
        time.sleep(0.1)
    log.info(f'Breakpoint {name} resolved')
