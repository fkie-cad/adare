from watchdog.events import FileSystemEventHandler, FileSystemEvent
from pathlib import Path
import cattrs

from adarelib.types import EventSystemData

import logging
log = logging.getLogger(__name__)


def read_event_file(event_file: Path) -> EventSystemData:
    with open(event_file, 'r') as f:
        data = f.read()
        return EventSystemData.from_dict(data)


class EventHandler(FileSystemEventHandler):
    experimentrun_uuid: str

    def __init__(self, experimentrun_uuid: str):
        self.experimentrun_uuid = experimentrun_uuid

    def on_modified(self, event: FileSystemEvent) -> None:
        eventssystemdata = None
        if event.src_path.endswith('events.yml'):
            try:
                eventssystemdata = read_event_file(Path(event.src_path))
            except cattrs.errors.ClassValidationError as e:
                log.error(f'Error reading event file: {e}')
                log.error(e, exc_info=True)
        print(eventssystemdata)

