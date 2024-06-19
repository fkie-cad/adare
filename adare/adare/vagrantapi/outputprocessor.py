# external imports
import re
from abc import ABC, abstractmethod
import datetime

# internal imports
from adarelib.types.stage import Stage
from adare.database.api.stage import StageDbApi
from adare.backend.experiment.threadingevents import experiment_event_manager
from adarelib.config import StatusEnum, TIMESTAMP_FORMAT

# configure logging
import logging
log = logging.getLogger(__name__)


class OutputProcessor(ABC):
    @abstractmethod
    def process(self, line: str):
        pass


class VagrantOutputProcessor(OutputProcessor):
    experiment_run_ulid: str
    machine: str
    provider: str

    # pattern to match the header which contains the machine and provider
    # e.g. Bringing machine 'X' up with 'Y' provider...
    header_pattern = re.compile(r"Bringing machine '(?P<machine>.+)' up with '(?P<provider>.+)' provider\.\.\.")
    vagrant_message_pattern = re.compile(r"==> (?P<machine>.+?): (?P<message>.+)")
    submessage_pattern = re.compile(r" {4}(?P<machine>.+?): (?P<message>.+)")

    stage_message_pattern = re.compile(r"stage (?P<stage>.+): (?P<message>.+) \((?P<timestamp>.+)\) (?P<status>.*)")
    shutdown_message_pattern = re.compile(r"--- SHUTDOWN ---")

    def __init__(self, experiment_run_ulid: str):
        self.experiment_run_ulid = experiment_run_ulid
        self.machine = ''
        self.provider = ''

    def process(self, line: str):
        # debug output but remove the newline character
        log.debug(line[:-1])
        if match := self.header_pattern.match(line):
            self.machine = match.group('machine')
            self.provider = match.group('provider')
        elif match := self.submessage_pattern.match(line):
            if match:
                message = match.group('message')
                if match := self.stage_message_pattern.match(message):
                    log.info(f'stage message detected: {message}')
                    self._parse_stage_message(match)
                elif match := self.shutdown_message_pattern.match(message):
                    log.info('shutdown message detected')
                    experiment_event_manager.get_threading_event(self.experiment_run_ulid, 'shutdown').set()

    def _parse_stage_message(self, match):
        stage_name = match.group('stage')
        message = match.group('message')
        timestamp = match.group('timestamp')
        status = match.group('status')
        if message not in ['start', 'end']:
            log.warning('so far only start and end messages are supported for stages')
        stage_class = Stage.get_subclass(f'box.{stage_name}')
        if stage_class:
            stage = stage_class()

            if message == 'start':
                stage.start_time = datetime.datetime.strptime(timestamp, TIMESTAMP_FORMAT)
            if message == 'end':
                stage.end_time = datetime.datetime.strptime(timestamp, TIMESTAMP_FORMAT)
                stage.status = StatusEnum.FINISHED
            if status != '(...)':
                stage.status = StatusEnum.from_string(status)

            with StageDbApi() as api:
                api.update_stage_in_run(stage, self.experiment_run_ulid)


class VagrantDestroyOutputProcessor(OutputProcessor):
    experiment_run_ulid: str

    def __init__(self, experiment_run_ulid: str):
        self.experiment_run_ulid = experiment_run_ulid

    def process(self, line: str):
        log.info(line[:-1])
