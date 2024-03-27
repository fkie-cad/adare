from watchdog.events import FileSystemEventHandler, FileSystemEvent
from pathlib import Path
import cattrs

from adarelib.types import EventSystemData

import logging
log = logging.getLogger(__name__)


def read_event_file(event_file: Path) -> EventSystemData:
    with open(event_file, 'r') as f:
        data = f.read()
    return cattrs.structure(data, EventSystemData)


class EventHandler(FileSystemEventHandler):
    experimentrun_uuid: str

    def __init__(self, experimentrun_uuid: str):
        self.experimentrun_uuid = experimentrun_uuid


    def on_created(self, event: FileSystemEvent) -> None:
        # check if file is events.yml
        if event.src_path.endswith('events.yml'):
            print('created')
            eventssystemdata = read_event_file(Path(event.src_path))
            # create event system data in database and link to experiment run

    def on_changed(self, event: FileSystemEvent) -> None:
        # check if file is events.yml
        if event.src_path.endswith('events.yml'):
            print('changed')
            eventssystemdata = read_event_file(Path(event.src_path))
            # create event system data in database and link to experiment run
