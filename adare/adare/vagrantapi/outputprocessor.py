# external imports
import re
from abc import ABC, abstractmethod

# internal imports
from adarelib.types.experiment import Stage
from adare.database.api.stage import StageDbApi

# configure logging
import logging
log = logging.getLogger(__name__)


class OutputProcessor(ABC):
    @abstractmethod
    def process(self, line: str):
        pass


class VagrantOutputProcessor(OutputProcessor):
    experiment_run_uuid: str
    machine: str
    provider: str

    # pattern to match the header which contains the machine and provider
    # e.g. Bringing machine 'X' up with 'Y' provider...
    header_pattern = re.compile(r"Bringing machine '(?P<machine>.+)' up with '(?P<provider>.+)' provider\.\.\.")
    vagrant_message_pattern = re.compile(r"==> (?P<machine>.+): (?P<message>.+)")
    submessage_pattern = re.compile(r" {4}(?P<machine>.+): (?P<message>.+)")

    stage_message_pattern = re.compile(r"stage (?P<stage>.+): (?P<message>.+) \((?P<timestamp>.+)\)")

    def __init__(self, experiment_run_uuid: str):
        self.experiment_run_uuid = experiment_run_uuid
        self.machine = ''
        self.provider = ''

    def process(self, line: str):
        if match := self.header_pattern.match(line):
            self.machine = match.group('machine')
            self.provider = match.group('provider')
        elif match := self.vagrant_message_pattern.match(line):
            # these are vagrant log messages sent by vagrant
            if match:
                message = match.group('message')
                log.debug(message)
        elif match := self.submessage_pattern.match(line):
            # these are messages within a provisioner, ...
            if match:
                message = match.group('message')
                if match := self.stage_message_pattern.match(message):
                    self._parse_stage_message(match)
                else:
                    log.debug(message)

    def _parse_stage_message(self, match):
        stage = match.group('stage')
        message = match.group('message')
        timestamp = match.group('timestamp')
        if message not in ['start', 'end']:
            log.warning('so far only start and end messages are supported for stages')
        stage_data = {
            'name': stage,
        }
        if message == 'start':
            stage_data['start_time'] = timestamp
        if message == 'end':
            stage_data['end_time'] = timestamp
        stage = Stage.from_data(stage_data)
        with StageDbApi() as api:
            api.update_stage_in_run(stage, self.experiment_run_uuid)