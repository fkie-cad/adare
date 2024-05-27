import contextlib
import time
from pathlib import Path
import json
import re
from watchdog.events import FileSystemEventHandler, FileSystemEvent
import attrs
from typing import Optional

from adarelib.config import BREAKPOINT_LIMIT_SECONDS

import logging
log = logging.getLogger(__name__)


@attrs.define
class BreakPoint:
    name: str
    description: str
    usage: list[str]
    file: Optional[Path] = None

    def trigger(self):
        continue_value = False
        while not continue_value:
            user_input = input(f'(Breakpoint: {self.name}) Press y to continue: ')
            if user_input == 'y':
                continue_value = True
        if self.file:
            self.file.unlink()

    def trigger_if_in_breakpoints(self, breakpoints: list['BreakPoint']):
        if self.name in [bp.name for bp in breakpoints]:
            self.trigger()

    @classmethod
    def from_json(cls, json_file: Path):
        try:
            with open(json_file, 'r') as f:
                json_data = json.load(f)
        except json.JSONDecodeError:
            log.warning(f'Breakpoint file {json_file} could not be read')
            return None
        name = json_data.get('name', None)
        description = json_data.get('description', '')
        usage = json_data.get('usage', [])
        return None if name is None else cls(name, description, usage, json_file)

    def __to_json(self, json_file: Path):
        data = {
            'name': self.name
        }
        with open(json_file, 'w') as f:
            json.dump(data, f)

    def trigger_on_guest(self, breakpoint_directory: Path):
        file = breakpoint_directory / f'{self.name}.json'
        self.__to_json(file)
        log.info(f'Breakpoint {self.name} set')
        start_time = time.time()
        while file.is_file():
            time.sleep(0.1)
            if time.time() - start_time > BREAKPOINT_LIMIT_SECONDS:
                log.warning(f'Breakpoint {self.name} not resolved after {BREAKPOINT_LIMIT_SECONDS} seconds')
                break
        log.info(f'Breakpoint {self.name} resolved')

    def trigger_on_guest_if_in_breakpoints(self, breakpoints: list['BreakPoint'], json_file: Path):
        if self.name in [bp.name for bp in breakpoints]:
            self.trigger_on_guest(json_file)


class BreakpointReceiveHandler(FileSystemEventHandler):

    def on_created(self, event: FileSystemEvent) -> None:
        breakpoint_file = Path(event.src_path)
        if bp := BreakPoint.from_json(breakpoint_file):
            log.info(f'Breakpoint {bp.name} received')
            bp.trigger()


def resolve_breakpoints(breakpoints_identifier: list[str]) -> list[BreakPoint]:
    if not breakpoints_identifier:
        return []
    breakpoints = []
    for bp_identifier in breakpoints_identifier:
        # check if identifier is a breakpoint name
        if bp := next((bp for bp in BREAKPOINTS if bp.name == bp_identifier), None):
            breakpoints.append(bp)
            continue
        # check if identifier is the index of a breakpoint
        with contextlib.suppress(ValueError):
            index = int(bp_identifier) - 1
            if 0 <= index < len(BREAKPOINTS):
                breakpoints.append(BREAKPOINTS[index])
                continue
        # check if identifier is of format bp1
        with contextlib.suppress(ValueError):
            index = int(bp_identifier[2:3]) - 1
            if 0 <= index < len(BREAKPOINTS):
                breakpoints.append(BREAKPOINTS[index])
                continue
        # apply str as regex to names and descriptions
        try:
            compiled_regex = re.compile(bp_identifier)
        except re.error:
            log.warning(f'Breakpoint {bp_identifier} not found')
            continue
        breakpoints.extend(bp for bp in BREAKPOINTS if compiled_regex.search(bp.name))
    # remove duplicates
    return breakpoints


### define break point names
BP_HOST_AFTER_VAGRANTFILE_CREATION = BreakPoint(
    name='after_vagrantfile_creation',
    description='This breakpoint is triggered directly after the Vagrantfile has been created.',
    usage=[
        'can be used to view if the Vagrantfile has been created correctly',
        'can be used to experimentally modify the Vagrantfile before the box is started',
    ],
)

BP_HOST_BEFORE_BOX_START = BreakPoint(
    name='before_box_start',
    description='This breakpoint is triggered right before the box is started.',
    usage=[
        'can be used to check if setup for the box is correct (e.g. files for provisioning exist, ...)',
    ]
)

BP_BOX_BEFORE_ACTION = BreakPoint(
    name='before_action',
    description='This breakpoint is triggered before the experiment action is run.',
    usage=[
        'can be used to check if installations of software have been successful',
    ],
)

BP_BOX_BEFORE_BOX_STOP = BreakPoint(
    name='before_box_stop',
    description='This breakpoint is triggered right before the box is stopped and after the experiment action and further scripts has run.',
    usage=[
        'can be used to check the state of the box',
    ]
)

BP_HOST_BEFORE_CLEANUP = BreakPoint(
    name='before_cleanup',
    description='This breakpoint is triggered right before the cleanup is executed.',
    usage=[
        'can be used to check if the created files within the experiment are correct',
    ]
)

# define lookup table for break points
BREAKPOINTS = [
    BP_HOST_AFTER_VAGRANTFILE_CREATION,
    BP_HOST_BEFORE_BOX_START,
    BP_BOX_BEFORE_ACTION,
    BP_BOX_BEFORE_BOX_STOP,
    BP_HOST_BEFORE_CLEANUP
]
