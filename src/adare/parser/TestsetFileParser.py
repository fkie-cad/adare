# external imports
from pathlib import Path

# internal imports
from adare.customyaml.customloader import create_yaml_loader_dumper_inputfiles
from adare.helperFunctions.yaml import yaml_to_dict

# logging configuration
import logging
log = logging.getLogger(__name__)


class TestsetFileParser:
    file: Path

    def __init__(self, testset_file: Path):
        self.file = testset_file

    def parse(self):
        log.debug(f'start to read input yaml file ({self.file})')
        loader, dumper = create_yaml_loader_dumper_inputfiles()
        parsed_input = yaml_to_dict(self.file, loader=loader)
        log.debug(f'read input yaml file ({self.file}) was successful')
        return parsed_input
