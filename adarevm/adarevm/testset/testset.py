from pathlib import Path
import shutil

from adarelib.parsers import parse_testsetfile
from adarelib.types.testset import TestsetFile
from adarelib.testfunction import import_basictest_subclasses, get_missing_testfunctions, structure_tests
from adarelib.event import EventSystem
from adarelib.types.event import TestEvent, CommandEvent
from adarevm.shell import execute_on_shell
from adarelib.exceptions import LoggedErrorException

import logging
log = logging.getLogger(__name__)


class TestsetExecutionError(LoggedErrorException):
    pass


class Testset:
    supported_tests: dict
    testsetfile: TestsetFile
    tests: dict

    event_system: EventSystem

    def __init__(self, testfunctions_directory: Path, testsetfile: Path, event_system: EventSystem):
        self.supported_tests = import_basictest_subclasses(testfunctions_directory)
        self.testsetfile: TestsetFile = parse_testsetfile(testsetfile)

        if unsupported_testfunctions := get_missing_testfunctions(
                self.testsetfile, self.supported_tests
        ):
            raise TestsetExecutionError(log, 'testset contains tests that are not supported by the testfunction collection')

        self.tests, self.structure_error_dict = structure_tests(self.testsetfile, self.supported_tests)
        if self.structure_error_dict:
            raise TestsetExecutionError(log, 'testset contains tests that are not supported by the testfunction collection')

        self.event_system = event_system

    def execute_command(self, command_name: str):
        available_commands = [com.name for com in self.testsetfile.commands]
        if command_name not in available_commands:
            raise TestsetExecutionError(log, f'command {command_name} is not available')
        # retrieve the command from the testsetfile
        command = next(com for com in self.testsetfile.commands if com.name == command_name)
        self.event_system.log(
            CommandEvent(
                name=command_name, command=command.command, status='running',
            )
        )

        toolpath = command.command.split(' ')[0]
        if shutil.which(toolpath):
            return

        log.error(f'tool with path {toolpath} does NOT exist')
        toolpath = f'./{toolpath}'
        command_path = f'./{command.command}'
        if not shutil.which(toolpath):
            log.error(f'tool with path {toolpath} does NOT exist')
            self.event_system.log(
                CommandEvent(
                    name=command_name, command=command.command, status='failed', error=f'tool with path {toolpath} does NOT exist'
                )
            )
            raise TestsetExecutionError(log, f'tool with path {toolpath} does NOT exist')
        execute_on_shell(command_path.split(" "), event_system=self.event_system)

    def __check_if_command_already_executed(self, command_name: str) -> bool:
        command_events = [event for event in self.event_system.data.events if isinstance(event, CommandEvent)]
        return any(event.name == command_name for event in command_events)

    def test(self, name: str, variables: dict):
        if name not in self.tests:
            log.error(f'test with name {name} does NOT exist')
            raise TestsetExecutionError(log, f'test with name {name} does NOT exist')
        test = self.tests[name]

        test_in_testsetfile = next(t for t in self.testsetfile.tests if t.name == name)
        if test_in_testsetfile.depends_on:
            for dependency in test_in_testsetfile.depends_on:
                if not self.__check_if_command_already_executed(dependency):
                    self.execute_command(dependency)
        test.variables = variables
        self.event_system.log(
            TestEvent(
                test_name=name, status='running'
            )
        )
        test_result = test.test()
        self.event_system.log(
            TestEvent(
                test_name=name, status='done', result=test_result
            )
        )
        self.event_system.save()

    def testall(self, variables: dict):
        for test in self.tests:
            self.test(test, variables)
