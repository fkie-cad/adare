# external imports
from pathlib import Path

# logging configuration
import logging
log = logging.getLogger(__name__)


class InputParser:
    input = None
    parsed_input = None

    def __init__(self, input):
        if Path(input).is_file():
            self.input = input
        else:
            raise FileNotFoundError

    def parse(self):
        pass