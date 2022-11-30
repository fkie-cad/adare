# internal imports
from parseandtest.inputparser.InputParser import InputParser
import parseandtest.yamlfeatures as yml

# logging configuration
import logging
log = logging.getLogger(__name__)


class YAMLInputParser(InputParser):
    def __init__(self, input):
        super().__init__(input)

    def parse(self):
        log.debug(f'start to read input yaml file ({self.input})')
        loader, dumper = yml.create_yaml_loader_dumper_inputfiles()
        self.parsed_input = yml.yaml_to_dict(self.input, loader=loader)
        log.debug(f'read input yaml file ({self.input}) was successful')
