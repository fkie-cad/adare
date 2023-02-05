# internal imports
from adare.inputparser.InputParser import InputParser
from adare.customyaml.customloader import create_yaml_loader_dumper_inputfiles
from adare.helperFunctions.yaml import yaml_to_dict

# logging configuration
import logging
log = logging.getLogger(__name__)


class YAMLInputParser(InputParser):
    def __init__(self, input):
        super().__init__(input)

    def parse(self):
        log.debug(f'start to read input yaml file ({self.input})')
        loader, dumper = create_yaml_loader_dumper_inputfiles()
        self.parsed_input = yaml_to_dict(self.input, loader=loader)
        log.debug(f'read input yaml file ({self.input}) was successful')
        return self.parsed_input
