from collections import defaultdict
from datetime import datetime
from pathlib import Path

from adarevm.config import TIMESTAMP_FORMAT
from adarelib.helperfunctions.yaml import dict_to_yaml


import logging
log = logging.getLogger(__name__)


class EventSystemV1:
    """
    EventSystemV1 class.

    Summary:
        Represents a simple event logging system.

    Explanation:
        This class provides functionality to log events with different levels and write them to a YAML file.

    Attributes:
        levels: A list of available event levels.
        path: The path to the YAML file.
        data: A dictionary containing metadata and logged events.

    Methods:
        __init__: Initializes an EventSystemV1 object.
        log: Logs an event with a specified message and level.
        write: Writes the logged events to a YAML file.

    Args:
        path: The path to the YAML file.

    Returns:
        None
    """

    levels = ['info', 'warning', 'error']
    path: Path
    data: defaultdict

    def __init__(self, path: Path):
        self.path = path
        self.data = defaultdict(list, {
            'name': 'EventSystem',
            'version': '0.0.1',
            'start_time': datetime.now().isoformat(),
            'events': []
        })

    def log(self, message: str, level: str = 'info'):
        if not level:
            level = 'info'
        if level not in self.levels:
            raise ValueError(f'Invalid level: {level}')
        self.data['events'].append({
            'time': datetime.now().strftime(TIMESTAMP_FORMAT),
            'message': message,
            'level': level
        })

    def write(self):
        self.data['end_time'] = datetime.now().strftime(TIMESTAMP_FORMAT)
        dict_to_yaml(self.path, self.data)
